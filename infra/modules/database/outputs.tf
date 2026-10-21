# Database integration metadata for the parent environment and operators.
#
# Secret references support migration setup and explicit runtime configuration;
# they do not automatically wire DATABASE_URL into the serving module. The
# credential-bearing URI remains sensitive and is not re-exported by production,
# but is still present in Terraform state.

output "secret_id" {
  description = "Database connection secret ID forwarded by the production root for operators retrieving migration credentials or configuring runtime DATABASE_URL."
  value       = google_secret_manager_secret.database_url.secret_id
}

output "secret_version" {
  description = "Provisioned connection secret version forwarded by the production root for operators selecting credentials during migration or runtime configuration."
  value       = google_secret_manager_secret_version.database_url.version
}

output "neon_project_id" {
  description = "Neon project ID forwarded by the production root for database operators using the Neon console or API."
  value       = neon_project.default.id
}

output "database_host" {
  description = "Credential-free pooled database hostname forwarded by the production root for operator connectivity checks."
  value       = neon_project.default.database_host_pooler
}

output "database_uri" {
  description = "Credential-bearing pooled TLS connection URI available to authorized parent-module consumers; not re-exported by production. Sensitive in CLI output but stored in state."
  value       = local.database_uri
  sensitive   = true
}
