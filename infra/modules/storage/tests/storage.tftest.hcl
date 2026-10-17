mock_provider "google" {
  override_during = plan
}

variables {
  project_id                      = "basicrahgapp"
  region                          = "europe-southwest1"
  bucket_name                     = "orch_app_bucket"
  common_labels                   = { app = "orchestratorapp", environment = "prod" }
  cloud_run_service_account_email = "orchestratorapp-runtime@basicrahgapp.iam.gserviceaccount.com"
}

run "private_bucket_and_runtime_image_access" {
  command = plan

  assert {
    condition     = google_storage_bucket.app_data.location == "europe-southwest1" && google_storage_bucket.app_data.uniform_bucket_level_access && google_storage_bucket.app_data.public_access_prevention == "enforced" && !google_storage_bucket.app_data.force_destroy
    error_message = "The bucket must remain private, in Madrid, and protected from forced deletion."
  }

  assert {
    condition     = google_storage_bucket_iam_member.cloud_run_images.bucket == "orch_app_bucket" && google_storage_bucket_iam_member.cloud_run_images.member == "serviceAccount:orchestratorapp-runtime@basicrahgapp.iam.gserviceaccount.com" && google_storage_bucket_iam_member.cloud_run_images.role == "roles/storage.objectViewer"
    error_message = "Only the supplied runtime identity must receive object viewer access."
  }

  assert {
    condition     = google_storage_bucket_iam_member.cloud_run_images.condition[0].expression == "resource.name.startsWith('projects/_/buckets/orch_app_bucket/objects/images/')"
    error_message = "Runtime access must be restricted to images/, excluding bucket listing and other objects."
  }
}

run "reject_invalid_runtime_identity" {
  command = plan
  variables {
    cloud_run_service_account_email = "person@example.com"
  }
  expect_failures = [var.cloud_run_service_account_email]
}
