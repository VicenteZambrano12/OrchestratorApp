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
