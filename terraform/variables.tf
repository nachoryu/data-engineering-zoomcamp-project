variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "location" {
  description = "GCP resource location (for BigQuery dataset)"
  type        = string
  default     = "US"
}

variable "bucket_name" {
  description = "GCS bucket name for data lake"
  type        = string
  default     = ""
}

variable "credentials_file" {
  description = "Path to GCP service account JSON key file"
  type        = string
  default     = "../airflow/keys/service_account.json"
}
