output "secret_id" {
  description = "Secret ID for Cloud Run value_source.secret_key_ref.secret."
  value       = google_secret_manager_secret.database_url.secret_id
}

output "secret_version" {
  description = "Pinned secret version for Cloud Run value_source.secret_key_ref.version."
  value       = google_secret_manager_secret_version.database_url.version
}

output "neon_project_id" {
  description = "Neon project ID."
  value       = neon_project.default.id
}

output "database_host" {
  description = "Pooled database hostname, without credentials."
  value       = neon_project.default.database_host_pooler
}

output "database_uri" {
  description = "Pooled TLS connection URI. Contains credentials and is stored in Terraform state."
  value       = local.database_uri
  sensitive   = true
}
