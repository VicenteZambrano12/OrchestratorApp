# Private object-storage tier for application assets and exercise images.
#
# Provides a regionally placed bucket with uniform IAM and enforced prevention
# of public access. The application serves authorized object reads through its
# runtime identity rather than exposing a public bucket. Upload and deployment
# permissions are managed outside this module; data is protected from deletion.

# Retains application assets independently of ephemeral Cloud Run instances;
# bucket-wide IAM avoids per-object ACLs and public-access prevention blocks
# public sharing even if an object ACL or IAM grant is attempted.
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

# Allows the backend to fetch exercise-image objects on behalf of API requests.
# The images/ object condition excludes bucket listing and other prefixes;
# objectViewer grants no writes, keeping runtime access separate from uploads.
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
