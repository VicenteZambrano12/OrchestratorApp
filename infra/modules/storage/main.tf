resource "google_storage_bucket" "app_data" {
  project                     = var.project_id
  name                        = var.bucket_name
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels                      = merge(var.common_labels, { component = "storage" })

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_storage_bucket_iam_member" "cloud_run_images" {
  bucket = google_storage_bucket.app_data.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${var.cloud_run_service_account_email}"

  condition {
    title       = "read-exercise-images"
    description = "Read only objects beneath images/; bucket listing and writes are not granted."
    expression  = "resource.name.startsWith('projects/_/buckets/${google_storage_bucket.app_data.name}/objects/images/')"
  }
}
