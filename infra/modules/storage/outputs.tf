output "bucket_name" {
  value = google_storage_bucket.app_data.name
}

output "bucket_url" {
  value = google_storage_bucket.app_data.url
}
