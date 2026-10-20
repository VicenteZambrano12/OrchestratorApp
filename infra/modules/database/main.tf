# Persistent PostgreSQL tier and credential handoff for the agent application.
#
# Provisions a Neon project, environment branch, and application-owned database,
# then publishes a TLS-required pooled connection URI to Google Secret Manager.
# Neon placement is independent of Google Cloud secret placement. Runtime access
# is secret-scoped; this module does not inject DATABASE_URL into Cloud Run.
# Generated credentials and the URI are stored in state, requiring restricted
# access to the production state backend as well as the secret itself.

# Isolates production database lifecycle and compute from local development,
# with fixed low compute bounds and a six-hour history retention window.
resource "neon_project" "default" {
  name                      = "${var.app_name}-${var.environment}"
  org_id                    = var.neon_org_id
  region_id                 = var.neon_region_id
  pg_version                = var.pg_version
  history_retention_seconds = 21600
  autoscaling_limit_min_cu  = 0.25
  autoscaling_limit_max_cu  = 0.25

  branch {
    name = var.environment
  }

  # The Free plan fixes suspension at 300s. Provider 0.18.0 sends an override
  # even for an omitted timeout inside primary_compute, so that block is left
  # computed. Destruction protection preserves the project's persistent data.
  lifecycle {
    prevent_destroy = true
  }
}

# Gives the application a dedicated database owner with a generated password,
# rather than reusing a default database role; ownership permits schema changes.
resource "neon_role" "app" {
  project_id = neon_project.default.id
  branch_id  = neon_project.default.default_branch_id
  name       = var.db_user
}

# Provides an application-specific schema destination for migration and runtime
# queries while preventing accidental Terraform deletion of persistent data.
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
  # Builds the pooled TLS URI consumed by the connection secret below.
  database_uri = format(
    "postgresql://%s:%s@%s/%s?sslmode=require",
    # 1. Escapes the role name for the URI's user-information component.
    urlencode(neon_role.app.name),
    # 2. Escapes the generated password and converts form-style spaces to %20,
    # since URI user information does not interpret '+' as a space.
    replace(urlencode(neon_role.app.password), "+", "%20"),
    # 3. Uses Neon's pooled endpoint for serverless application connections.
    neon_project.default.database_host_pooler,
    # 4. Escapes the database name for the URI path; sslmode requires TLS.
    urlencode(neon_database.app.name),
  )
}

# Separates database credential distribution from image builds, with an explicit
# replica location and lifecycle protection for the stable secret identifier.
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

# Publishes generated connection credentials for authorized runtime or migration
# consumers; removed versions are disabled rather than immediately destroyed.
resource "google_secret_manager_secret_version" "database_url" {
  secret          = google_secret_manager_secret.database_url.id
  secret_data     = local.database_uri
  deletion_policy = "DISABLE"
}

# Lets the application retrieve only this database connection secret without
# granting project-wide secret access or secret administration privileges.
resource "google_secret_manager_secret_iam_member" "cloud_run_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.cloud_run_service_account_email}"
}
