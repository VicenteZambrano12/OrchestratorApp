output "secret_id" {
  description = "Application JSON secret ID."
  value       = google_secret_manager_secret.app.secret_id
}

output "initial_version" {
  description = "Initial empty JSON version. Read latest after adding populated versions."
  value       = google_secret_manager_secret_version.initial.version
}
