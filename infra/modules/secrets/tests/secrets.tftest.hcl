mock_provider "google" {
  override_during = plan
}

variables {
  project_id                      = "basicrahgapp"
  secret_id                       = "orch_app_secret"
  secret_region                   = "europe-southwest1"
  cloud_run_service_account_email = "orchestratorapp-runtime@basicrahgapp.iam.gserviceaccount.com"
  common_labels                   = { app = "orchestratorapp", env = "prod" }
}

run "empty_json_secret_plan" {
  command = plan

  assert {
    condition     = google_secret_manager_secret.app.secret_id == "orch_app_secret" && google_secret_manager_secret.app.project == "basicrahgapp"
    error_message = "The requested application secret must be created in the production project."
  }

  assert {
    condition     = google_secret_manager_secret.app.replication[0].user_managed[0].replicas[0].location == "europe-southwest1"
    error_message = "The secret must be replicated in Madrid."
  }

  assert {
    condition     = google_secret_manager_secret_version.initial.secret_data == "{}" && google_secret_manager_secret_version.initial.deletion_policy == "DISABLE"
    error_message = "The initial version must contain exactly an empty JSON object, not local credentials."
  }

  assert {
    condition     = google_secret_manager_secret_iam_member.cloud_run_access.secret_id == "orch_app_secret" && google_secret_manager_secret_iam_member.cloud_run_access.role == "roles/secretmanager.secretAccessor" && google_secret_manager_secret_iam_member.cloud_run_access.member == "serviceAccount:orchestratorapp-runtime@basicrahgapp.iam.gserviceaccount.com"
    error_message = "Runtime read access must be scoped to this secret and the dedicated runtime identity."
  }

  assert {
    condition     = output.secret_id == "orch_app_secret" && google_secret_manager_secret.app.labels["component"] == "secrets"
    error_message = "Expose the secret ID and preserve module labels."
  }
}

run "reject_invalid_secret_name" {
  command = plan
  variables {
    secret_id = "invalid/name"
  }
  expect_failures = [var.secret_id]
}

run "reject_invalid_runtime_identity" {
  command = plan
  variables {
    cloud_run_service_account_email = "person@example.com"
  }
  expect_failures = [var.cloud_run_service_account_email]
}

run "reject_invalid_secret_region" {
  command = plan
  variables {
    secret_region = "Madrid"
  }
  expect_failures = [var.secret_region]
}
