mock_provider "neon" {
  override_during = plan

  mock_resource "neon_project" {
    defaults = {
      id                   = "demo-project"
      default_branch_id    = "br-demo"
      database_host_pooler = "ep-demo-pooler.eu-central-1.aws.neon.tech"
    }
  }

  mock_resource "neon_role" {
    defaults = {
      password = "test:p@ss/?# +"
    }
  }
}

mock_provider "google" {
  override_during = plan
}

variables {
  project_id                      = "basicrahgapp"
  app_name                        = "orchestratorapp"
  db_name                         = "orchestrator_app"
  db_user                         = "orchestrator_app"
  cloud_run_service_account_email = "orchestratorapp-runtime@basicrahgapp.iam.gserviceaccount.com"
}

run "demo_database_plan" {
  command = plan

  assert {
    condition     = neon_project.default.region_id == "aws-eu-central-1" && neon_project.default.pg_version == 16
    error_message = "The demo must use Frankfurt and PostgreSQL 16 by default."
  }

  assert {
    condition     = neon_project.default.autoscaling_limit_min_cu == 0.25 && neon_project.default.autoscaling_limit_max_cu == 0.25 && neon_project.default.suspend_timeout_seconds == 300
    error_message = "Project defaults must stay at 0.25 CU with five-minute suspension."
  }

  assert {
    condition     = neon_project.default.primary_compute[0].autoscaling_limit_min_cu == 0.25 && neon_project.default.primary_compute[0].autoscaling_limit_max_cu == 0.25 && neon_project.default.primary_compute[0].suspend_timeout_seconds == 300
    error_message = "The initial compute must also stay at 0.25 CU with five-minute suspension."
  }

  assert {
    condition     = neon_project.default.branch[0].name == "prod" && neon_role.app.branch_id == "br-demo" && neon_database.app.branch_id == "br-demo"
    error_message = "The app must reuse the default production branch, not create extra computes."
  }

  assert {
    condition     = neon_database.app.name == "orchestrator_app" && neon_database.app.owner_name == neon_role.app.name
    error_message = "The dedicated database must belong to the dedicated role."
  }

  assert {
    condition     = output.database_uri == "postgresql://orchestrator_app:test%3Ap%40ss%2F%3F%23%20%2B@ep-demo-pooler.eu-central-1.aws.neon.tech/orchestrator_app?sslmode=require"
    error_message = "The URI must use pooling and TLS and correctly escape password punctuation and spaces."
  }

  assert {
    condition     = google_secret_manager_secret_version.database_url.secret_data == output.database_uri && google_secret_manager_secret_version.database_url.deletion_policy == "DISABLE"
    error_message = "The connection URI must be stored in Secret Manager, retaining disabled old versions."
  }

  assert {
    condition     = google_secret_manager_secret.database_url.secret_id == "orchestratorapp-prod-database-url" && google_secret_manager_secret.database_url.replication[0].user_managed[0].replicas[0].location == "europe-southwest1"
    error_message = "The app-specific secret must be replicated in Madrid."
  }

  assert {
    condition     = google_secret_manager_secret_iam_member.cloud_run_access.role == "roles/secretmanager.secretAccessor" && google_secret_manager_secret_iam_member.cloud_run_access.member == "serviceAccount:orchestratorapp-runtime@basicrahgapp.iam.gserviceaccount.com"
    error_message = "Only the supplied runtime account must receive secret accessor access."
  }

  assert {
    condition     = output.database_host == "ep-demo-pooler.eu-central-1.aws.neon.tech" && output.neon_project_id == "demo-project"
    error_message = "Public outputs must expose the pooled hostname and project ID."
  }
}

run "reject_sql_in_database_name" {
  command = plan
  variables {
    db_name = "app;DROP DATABASE postgres"
  }
  expect_failures = [var.db_name]
}

run "reject_default_database" {
  command = plan
  variables {
    db_name = "neondb"
  }
  expect_failures = [var.db_name]
}

run "reject_reserved_role" {
  command = plan
  variables {
    db_user = "pg_admin"
  }
  expect_failures = [var.db_user]
}

run "reject_invalid_service_account" {
  command = plan
  variables {
    cloud_run_service_account_email = "allUsers"
  }
  expect_failures = [var.cloud_run_service_account_email]
}

run "reject_madrid_neon_region" {
  command = plan
  variables {
    neon_region_id = "europe-southwest1"
  }
  expect_failures = [var.neon_region_id]
}

run "reject_unsupported_postgres_version" {
  command = plan
  variables {
    pg_version = 9
  }
  expect_failures = [var.pg_version]
}
