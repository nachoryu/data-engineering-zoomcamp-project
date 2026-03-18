"""
GitHub Archive Daily Ingestion Pipeline

Batch pipeline that:
1. Downloads hourly JSON.gz files from gharchive.org for a given day
2. Uploads raw files to GCS (data lake)
3. Loads data from GCS into BigQuery raw_github_events table
4. Triggers dbt transformations
"""

from __future__ import annotations

import os
import logging
import requests
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.utils.dates import days_ago

from google.cloud import storage, bigquery

logger = logging.getLogger(__name__)

# ── Config from environment ──────────────────────────────────────────────────
GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
GCS_BUCKET = os.environ["GCS_BUCKET"]
BQ_DATASET = os.environ.get("BQ_DATASET", "github_analytics")
BQ_TABLE = os.environ.get("BQ_TABLE", "raw_github_events")
GH_ARCHIVE_URL = "https://data.gharchive.org/{date}-{hour}.json.gz"

DEFAULT_ARGS = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


# ── Helper functions ──────────────────────────────────────────────────────────

def _gcs_prefix(date_str: str) -> str:
    """Return GCS prefix for a given date string (YYYY-MM-DD)."""
    year, month, day = date_str.split("-")
    return f"raw/{year}/{month}/{day}"


def download_and_upload_to_gcs(ds: str, **kwargs) -> None:
    """
    Download all 24 hourly GH Archive files for `ds` and upload to GCS.
    ds format: YYYY-MM-DD (Airflow logical date, i.e. yesterday's date)
    """
    storage_client = storage.Client(project=GCP_PROJECT_ID)
    bucket = storage_client.bucket(GCS_BUCKET)
    prefix = _gcs_prefix(ds)

    uploaded = 0
    for hour in range(24):
        url = GH_ARCHIVE_URL.format(date=ds, hour=hour)
        gcs_blob_name = f"{prefix}/{hour:02d}.json.gz"
        blob = bucket.blob(gcs_blob_name)

        # Skip if already uploaded (idempotent)
        if blob.exists():
            logger.info("Already exists, skipping: gs://%s/%s", GCS_BUCKET, gcs_blob_name)
            uploaded += 1
            continue

        logger.info("Downloading %s", url)
        response = requests.get(url, timeout=300, stream=True)
        if response.status_code == 404:
            logger.warning("Not found (404): %s", url)
            continue
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".json.gz", delete=True) as tmp:
            for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
                tmp.write(chunk)
            tmp.flush()
            blob.upload_from_filename(tmp.name, content_type="application/gzip")
            logger.info("Uploaded gs://%s/%s", GCS_BUCKET, gcs_blob_name)
            uploaded += 1

    if uploaded == 0:
        raise ValueError(f"No files uploaded for date {ds}. Check gharchive.org availability.")
    logger.info("Finished uploading %d files for %s", uploaded, ds)


def load_gcs_to_bigquery(ds: str, **kwargs) -> None:
    """
    Load all GCS files for `ds` into BigQuery raw_github_events table.
    Uses WRITE_APPEND so multiple runs are idempotent via date partition pruning.
    """
    bq_client = bigquery.Client(project=GCP_PROJECT_ID)
    prefix = _gcs_prefix(ds)
    gcs_uri = f"gs://{GCS_BUCKET}/{prefix}/*.json.gz"
    table_ref = f"{GCP_PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}"

    # Delete existing partition first to ensure idempotency
    partition_date = ds.replace("-", "")
    partition_table = f"{table_ref}${partition_date}"
    try:
        bq_client.delete_table(partition_table)
        logger.info("Deleted existing partition %s", partition_table)
    except Exception:
        pass  # Partition doesn't exist yet, that's fine

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        autodetect=False,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        ignore_unknown_values=True,
        max_bad_records=100,
        schema=[
            bigquery.SchemaField("id", "STRING"),
            bigquery.SchemaField("type", "STRING"),
            bigquery.SchemaField(
                "actor",
                "RECORD",
                fields=[
                    bigquery.SchemaField("id", "INTEGER"),
                    bigquery.SchemaField("login", "STRING"),
                    bigquery.SchemaField("display_login", "STRING"),
                    bigquery.SchemaField("gravatar_id", "STRING"),
                    bigquery.SchemaField("url", "STRING"),
                    bigquery.SchemaField("avatar_url", "STRING"),
                ],
            ),
            bigquery.SchemaField(
                "repo",
                "RECORD",
                fields=[
                    bigquery.SchemaField("id", "INTEGER"),
                    bigquery.SchemaField("name", "STRING"),
                    bigquery.SchemaField("url", "STRING"),
                ],
            ),
            bigquery.SchemaField(
                "org",
                "RECORD",
                fields=[
                    bigquery.SchemaField("id", "INTEGER"),
                    bigquery.SchemaField("login", "STRING"),
                    bigquery.SchemaField("gravatar_id", "STRING"),
                    bigquery.SchemaField("url", "STRING"),
                    bigquery.SchemaField("avatar_url", "STRING"),
                ],
            ),
            bigquery.SchemaField("payload", "JSON"),
            bigquery.SchemaField("public", "BOOLEAN"),
            bigquery.SchemaField("created_at", "TIMESTAMP"),
        ],
        time_partitioning=bigquery.TimePartitioning(
            field="created_at",
            type_=bigquery.TimePartitioningType.DAY,
        ),
        clustering_fields=["type"],
    )

    load_job = bq_client.load_table_from_uri(gcs_uri, table_ref, job_config=job_config)
    logger.info("BigQuery load job started: %s", load_job.job_id)
    load_job.result()  # Wait for completion
    logger.info(
        "Loaded %d rows into %s for date %s",
        load_job.output_rows,
        table_ref,
        ds,
    )


# ── DAG definition ────────────────────────────────────────────────────────────

with DAG(
    dag_id="github_archive_pipeline",
    description="Daily batch pipeline: GH Archive → GCS → BigQuery → dbt",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2026, 1, 1),
    schedule_interval="0 6 * * *",  # Run at 06:00 UTC daily (processes previous day)
    catchup=False,
    max_active_runs=1,
    tags=["github", "analytics", "batch"],
) as dag:

    # Task 1: Download GH Archive files and upload to GCS
    download_upload = PythonOperator(
        task_id="download_and_upload_to_gcs",
        python_callable=download_and_upload_to_gcs,
        op_kwargs={"ds": "{{ macros.ds_add(ds, -1) }}"},  # Process yesterday's data
    )

    # Task 2: Load from GCS into BigQuery
    load_to_bq = PythonOperator(
        task_id="load_gcs_to_bigquery",
        python_callable=load_gcs_to_bigquery,
        op_kwargs={"ds": "{{ macros.ds_add(ds, -1) }}"},
    )

    # Task 3: Run dbt transformations
    run_dbt = BashOperator(
        task_id="run_dbt_transformations",
        bash_command=(
            "cd /opt/airflow/dbt && "
            "/home/airflow/.local/bin/dbt deps --profiles-dir . && "
            "/home/airflow/.local/bin/dbt run --profiles-dir . --target prod && "
            "/home/airflow/.local/bin/dbt test --profiles-dir . --target prod"
        ),
        env={
            "DBT_TARGET": "prod",
            "GCP_PROJECT_ID": GCP_PROJECT_ID,
            "BQ_DATASET": BQ_DATASET,
        },
        append_env=True,
    )

    download_upload >> load_to_bq >> run_dbt
