resource "google_secret_manager_secret" "app" {
  project   = var.project_id
  secret_id = var.secret_id
  labels    = merge(var.common_labels, { component = "secrets" })

  replication {
    user_managed {
      replicas {
        location = var.secret_region
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret_version" "initial" {
  secret          = google_secret_manager_secret.app.id
  secret_data     = jsonencode({})
  deletion_policy = "DISABLE"

  lifecycle {
    # A later manually populated version may retire this empty seed.
    ignore_changes = [enabled]
  }
}

resource "google_secret_manager_secret_iam_member" "cloud_run_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.app.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.cloud_run_service_account_email}"
}
