output "bucket_name" {
  description = "GCS data lake bucket name"
  value       = google_storage_bucket.data_lake.name
}

output "bigquery_dataset" {
  description = "BigQuery dataset ID"
  value       = google_bigquery_dataset.github_analytics.dataset_id
}

output "bigquery_table" {
  description = "BigQuery raw events table ID"
  value       = google_bigquery_table.raw_github_events.table_id
}
