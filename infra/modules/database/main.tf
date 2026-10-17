resource "neon_project" "default" {
  name                     = "${var.app_name}-${var.environment}"
  org_id                   = var.neon_org_id
  region_id                = var.neon_region_id
  pg_version               = var.pg_version
  autoscaling_limit_min_cu = 0.25
  autoscaling_limit_max_cu = 0.25
  suspend_timeout_seconds  = 300

  branch {
    name = var.environment
  }

  # Project defaults do not configure the initial compute.
  primary_compute {
    autoscaling_limit_min_cu = 0.25
    autoscaling_limit_max_cu = 0.25
    suspend_timeout_seconds  = 300
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "neon_role" "app" {
  project_id = neon_project.default.id
  branch_id  = neon_project.default.default_branch_id
  name       = var.db_user
}

resource "neon_database" "app" {
  project_id = neon_project.default.id
  branch_id  = neon_project.default.default_branch_id
  name       = var.db_name
  owner_name = neon_role.app.name

  lifecycle {
    prevent_destroy = true
  }
}

locals {
  database_uri = format(
    "postgresql://%s:%s@%s/%s?sslmode=require",
    urlencode(neon_role.app.name),
    replace(urlencode(neon_role.app.password), "+", "%20"),
    neon_project.default.database_host_pooler,
    urlencode(neon_database.app.name),
  )
}

resource "google_secret_manager_secret" "database_url" {
  project   = var.project_id
  secret_id = "${var.app_name}-${var.environment}-database-url"
  labels    = merge(var.common_labels, { component = "database" })

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

resource "google_secret_manager_secret_version" "database_url" {
  secret          = google_secret_manager_secret.database_url.id
  secret_data     = local.database_uri
  deletion_policy = "DISABLE"
}

resource "google_secret_manager_secret_iam_member" "cloud_run_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.cloud_run_service_account_email}"
}
