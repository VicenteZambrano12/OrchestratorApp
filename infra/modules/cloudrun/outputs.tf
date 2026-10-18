output "cloud_run_url" {
  description = "Public URL serving the frontend and same-origin /api routes."
  value       = google_cloud_run_v2_service.backend.uri
}
