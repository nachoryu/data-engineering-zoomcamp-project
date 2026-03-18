terraform {
  required_version = ">= 1.3"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project     = var.project_id
  region      = var.region
  credentials = file(var.credentials_file)
}

locals {
  bucket_name = var.bucket_name != "" ? var.bucket_name : "${var.project_id}-github-analytics"
}

# GCS Data Lake Bucket
resource "google_storage_bucket" "data_lake" {
  name          = local.bucket_name
  location      = var.location
  force_destroy = false

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }

  uniform_bucket_level_access = true
}

# BigQuery Dataset
resource "google_bigquery_dataset" "github_analytics" {
  dataset_id  = "github_analytics"
  location    = var.location
  description = "GitHub Archive event data for analytics"

  labels = {
    env = "production"
  }
}

# BigQuery raw events table (partitioned + clustered)
resource "google_bigquery_table" "raw_github_events" {
  dataset_id          = google_bigquery_dataset.github_analytics.dataset_id
  table_id            = "raw_github_events"
  deletion_protection = false

  description = "Raw GitHub Archive events loaded from GCS. Partitioned by event date, clustered by event type for query efficiency."

  time_partitioning {
    type  = "DAY"
    field = "created_at"
  }

  clustering = ["type"]

  schema = jsonencode([
    { name = "id", type = "STRING", mode = "NULLABLE" },
    { name = "type", type = "STRING", mode = "NULLABLE" },
    {
      name = "actor"
      type = "RECORD"
      mode = "NULLABLE"
      fields = [
        { name = "id", type = "INTEGER", mode = "NULLABLE" },
        { name = "login", type = "STRING", mode = "NULLABLE" },
        { name = "display_login", type = "STRING", mode = "NULLABLE" },
        { name = "gravatar_id", type = "STRING", mode = "NULLABLE" },
        { name = "url", type = "STRING", mode = "NULLABLE" },
        { name = "avatar_url", type = "STRING", mode = "NULLABLE" }
      ]
    },
    {
      name = "repo"
      type = "RECORD"
      mode = "NULLABLE"
      fields = [
        { name = "id", type = "INTEGER", mode = "NULLABLE" },
        { name = "name", type = "STRING", mode = "NULLABLE" },
        { name = "url", type = "STRING", mode = "NULLABLE" }
      ]
    },
    {
      name = "org"
      type = "RECORD"
      mode = "NULLABLE"
      fields = [
        { name = "id", type = "INTEGER", mode = "NULLABLE" },
        { name = "login", type = "STRING", mode = "NULLABLE" },
        { name = "gravatar_id", type = "STRING", mode = "NULLABLE" },
        { name = "url", type = "STRING", mode = "NULLABLE" },
        { name = "avatar_url", type = "STRING", mode = "NULLABLE" }
      ]
    },
    { name = "payload", type = "JSON", mode = "NULLABLE" },
    { name = "public", type = "BOOLEAN", mode = "NULLABLE" },
    { name = "created_at", type = "TIMESTAMP", mode = "NULLABLE" }
  ])
}
