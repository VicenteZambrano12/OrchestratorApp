# Storage integration references exported to the parent environment.
#
# Supplies the private bucket identity for runtime settings and operator-managed
# asset transfers. The gs:// URL is a storage address, not a public HTTP endpoint;
# consumers still require the appropriate IAM permissions.

output "bucket_name" {
  description = "Private bucket name forwarded by the production root for operators configuring runtime GCS_IMAGES_BUCKET and asset uploads."
  value       = google_storage_bucket.app_data.name
}

output "bucket_url" {
  description = "Bucket gs:// URL forwarded by the production root for operators running storage inspection and asset transfer commands."
  value       = google_storage_bucket.app_data.url
}
