# GitHub Activity Analytics Dashboard

> **Data Engineering Zoomcamp 2026 — Final Project**

An end-to-end batch data pipeline that ingests [GitHub Archive](https://www.gharchive.org/) event data daily, transforms it in BigQuery, and visualises open-source development trends on a Looker Studio dashboard.

---

## Problem Statement

Every day, millions of events occur on GitHub — pushes, pull requests, issues, forks, and more. This project answers two key questions:

1. **Which event types dominate GitHub activity?** (categorical distribution)
2. **How does GitHub activity change over time?** (temporal trend)

By building an automated pipeline, the dashboard always reflects the latest data without manual intervention.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        GH Archive                               │
│          https://data.gharchive.org/YYYY-MM-DD-H.json.gz        │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP download (24 files/day)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Apache Airflow (Docker)                       │
│   DAG: github_archive_pipeline  │  schedule: daily @ 06:00 UTC  │
│                                                                 │
│   Task 1: download_and_upload_to_gcs                            │
│   Task 2: load_gcs_to_bigquery                                  │
│   Task 3: run_dbt_transformations                               │
└────────┬───────────────────────┬────────────────────────────────┘
         │                       │
         ▼                       ▼
┌────────────────┐    ┌─────────────────────────────────────────┐
│  GCS (Data     │    │          BigQuery (Data Warehouse)      │
│  Lake)         │    │                                         │
│                │───▶│  raw_github_events                      │
│  raw/YYYY/     │    │  ├── Partition: DATE(created_at)        │
│  MM/DD/        │    │  └── Cluster: type                      │
│  *.json.gz     │    │                                         │
└────────────────┘    │  [dbt transforms]                       │
                      │  staging.stg_github_events (VIEW)       │
                      │  marts.fct_events_daily (TABLE)         │
                      │  marts.fct_event_type_summary (TABLE)   │
                      │  marts.fct_hourly_activity (TABLE)      │
                      └────────────────┬────────────────────────┘
                                       │
                                       ▼
                      ┌────────────────────────────────────────┐
                      │        Looker Studio Dashboard         │
                      │                                        │
                      │  Tile 1: Event type distribution       │
                      │          (Pie chart)                   │
                      │  Tile 2: Daily activity trend          │
                      │          (Time series line chart)      │
                      └────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Tool |
|---|---|
| Cloud | Google Cloud Platform (GCP) |
| Infrastructure as Code | Terraform |
| Data Lake | Google Cloud Storage (GCS) |
| Workflow Orchestration | Apache Airflow 2.9 (Docker Compose) |
| Data Warehouse | BigQuery |
| Transformation | dbt (BigQuery adapter) |
| Dashboard | Looker Studio |

---

## Data Pipeline Details

### Ingestion (Batch)
- **Source**: [gharchive.org](https://www.gharchive.org/) — JSON.gz files, one per hour
- **Frequency**: Daily (`@daily`), processes the previous day's 24 files
- **Idempotency**: Re-runs are safe — existing GCS files are skipped, and BigQuery partitions are replaced before reload

### Data Warehouse Optimisation
The `raw_github_events` table is:
- **Partitioned** by `DATE(created_at)` — queries that filter by date only scan relevant partitions, drastically reducing bytes processed
- **Clustered** by `type` — queries that filter or group by event type benefit from cluster pruning within each partition

### dbt Transformations
| Model | Type | Description |
|---|---|---|
| `stg_github_events` | View | Cleans and flattens raw JSON, extracts time dimensions |
| `fct_events_daily` | Table | Daily aggregated metrics + 7-day rolling average |
| `fct_event_type_summary` | Table | Event type distribution with percentage |
| `fct_hourly_activity` | Table | Hourly × day-of-week heatmap data |

---

## Prerequisites

- GCP account (Free Tier is sufficient for testing)
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.3
- [Docker](https://docs.docker.com/get-docker/) + Docker Compose
- [dbt CLI](https://docs.getdbt.com/docs/core/installation) with BigQuery adapter: `pip install dbt-bigquery`

---

## Setup Guide

### 1. GCP Project & Service Account

```bash
# Set your project
export GCP_PROJECT_ID=your-project-id
gcloud config set project $GCP_PROJECT_ID

# Create a service account
gcloud iam service-accounts create github-analytics-sa \
  --display-name="GitHub Analytics Service Account"

# Grant required roles
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:github-analytics-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:github-analytics-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.admin"

# Download the key
mkdir -p airflow/keys
gcloud iam service-accounts keys create airflow/keys/service_account.json \
  --iam-account="github-analytics-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
```

### 2. Provision Infrastructure with Terraform

```bash
cd terraform

terraform init

terraform plan -var="project_id=$GCP_PROJECT_ID"

terraform apply -var="project_id=$GCP_PROJECT_ID"
```

This creates:
- GCS bucket: `$GCP_PROJECT_ID-github-analytics`
- BigQuery dataset: `github_analytics`
- BigQuery table: `raw_github_events` (partitioned + clustered)

### 3. Start Airflow

```bash
cd airflow

# Configure environment
cp .env.example .env
# Edit .env and set GCP_PROJECT_ID and GCS_BUCKET

# Start services
docker compose up -d

# Wait ~30 seconds, then open http://localhost:8080
# Login: admin / admin
```

### 4. Run the Pipeline

**Option A — Airflow UI**
1. Open [http://localhost:8080](http://localhost:8080)
2. Enable the `github_archive_pipeline` DAG
3. Trigger a manual run (or wait for the next scheduled run)

**Option B — Backfill the last 7 days**
```bash
docker compose exec airflow-scheduler \
  airflow dags backfill github_archive_pipeline \
  --start-date 2026-03-08 \
  --end-date 2026-03-14
```

### 5. Run dbt Transformations

```bash
cd dbt

# Set environment variables
export GCP_PROJECT_ID=your-project-id
export BQ_DATASET=github_analytics
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service_account.json

# Install dbt packages
dbt deps

# Run all models
dbt run --profiles-dir .

# Run tests
dbt test --profiles-dir .
```

### 6. Connect Looker Studio Dashboard

1. Go to [Looker Studio](https://lookerstudio.google.com/)
2. Create a new report → Add data → BigQuery
3. Select project `$GCP_PROJECT_ID` → dataset `github_analytics_marts`
4. Add two tiles:
   - **Tile 1**: Pie chart using `fct_event_type_summary` — Dimension: `event_type`, Metric: `event_count`
   - **Tile 2**: Time series using `fct_events_daily` — X: `event_date`, Y: `total_events`

---

## Project Structure

```
.
├── terraform/
│   ├── main.tf               # GCS bucket + BigQuery dataset + table
│   ├── variables.tf
│   └── outputs.tf
├── airflow/
│   ├── docker-compose.yaml
│   ├── .env.example
│   ├── requirements.txt
│   └── dags/
│       └── github_archive_pipeline.py
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── packages.yml
│   └── models/
│       ├── staging/
│       │   ├── sources.yml
│       │   ├── schema.yml
│       │   └── stg_github_events.sql
│       └── marts/
│           ├── schema.yml
│           ├── fct_events_daily.sql
│           ├── fct_event_type_summary.sql
│           └── fct_hourly_activity.sql
└── README.md
```

---

## Dashboard

> **[Link to the dashboard](https://lookerstudio.google.com/reporting/fcff3712-d2fd-4d39-8549-501462ccf1ee)**

| Tile | Chart Type | Data Source | Description |
|---|---|---|---|
| Event Type Distribution | Pie chart | `fct_event_type_summary` | Shows the share of each GitHub event type |
| Daily Activity Trend | Time series | `fct_events_daily` | Total events over time |
