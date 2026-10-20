# Runtime configuration boundary for the orchestration application.
#
# Owns the Secret Manager container, an empty bootstrap version, and narrowly
# scoped runtime read access. Operators publish populated JSON settings and LLM
# API keys outside Terraform; the parent selects a populated numeric version for
# Cloud Run. Actual application credentials are not supplied to this module.

# Provides a stable regional secret identifier for runtime settings and LLM keys,
# keeping those values separate from the deployable application image.
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

# Seeds the secret for bootstrap only; this empty object is not a usable runtime
# configuration. Populated versions are published outside Terraform.
resource "google_secret_manager_secret_version" "initial" {
  secret          = google_secret_manager_secret.app.id
  secret_data     = jsonencode({})
  deletion_policy = "DISABLE"

  lifecycle {
    # A later manually populated version may retire this empty seed.
    ignore_changes = [enabled]
  }
}

# Permits the runtime identity to read application settings and LLM credentials
# from this secret without granting write access or access to unrelated secrets.
resource "google_secret_manager_secret_iam_member" "cloud_run_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.app.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.cloud_run_service_account_email}"
}
