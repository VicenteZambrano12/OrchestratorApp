# Serving endpoint exported to the production environment.
#
# Provides the shared frontend/API origin without exposing runtime settings.
# The parent root forwards it to CI/CD for post-deployment verification.

output "cloud_run_url" {
  description = "Public frontend and same-origin /api base URL forwarded by the production root to CI/CD health and frontend checks."
  value       = google_cloud_run_v2_service.backend.uri
}
