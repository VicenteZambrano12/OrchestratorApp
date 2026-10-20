# Operational interface for the production orchestration stack.
#
# Publishes storage, image, database, and secret identifiers for operators and
# downstream tooling without exposing secret payloads. The deployment workflow
# reads cloud_run_url for post-apply checks; the other values support inspection,
# migration setup, and runtime configuration rather than automatic injection.

output "app_bucket_name" {
  description = "Private application bucket name for operators configuring GCS_IMAGES_BUCKET and exercise-image uploads."
  value       = module.storage.bucket_name
}

output "app_bucket_url" {
  description = "Application bucket gs:// URL for operator-managed image transfers and storage inspection."
  value       = module.storage.bucket_url
}

output "database_secret_id" {
  description = "Database connection secret ID for operators retrieving credentials for migrations or configuring runtime DATABASE_URL; not automatically injected into Cloud Run."
  value       = module.database.secret_id
}

output "database_secret_version" {
  description = "Database connection secret version for operators selecting the provisioned credentials during migration or runtime configuration."
  value       = module.database.secret_version
}

output "neon_project_id" {
  description = "Neon project ID for database operators locating the production project in the Neon console or API."
  value       = module.database.neon_project_id
}

output "database_host" {
  description = "Credential-free pooled PostgreSQL hostname for database operators checking connectivity and connection configuration."
  value       = module.database.database_host
}

output "app_secret_id" {
  description = "Application JSON secret ID for operators publishing runtime settings and LLM API credentials outside Terraform."
  value       = module.secrets.secret_id
}

output "app_secret_initial_version" {
  description = "Empty seed version for bootstrap inspection by operators; deploy a separately populated version through app_secret_version, not this seed."
  value       = module.secrets.initial_version
}

output "artifact_registry_repository_url" {
  description = "Docker repository base URL for operators constructing or checking image references; CI/CD constructs the equivalent path from GitHub variables."
  value       = module.artifact_registry.repository_url
}

output "app_container_image" {
  description = "Deployed immutable image reference for operators correlating the Cloud Run revision with the CI/CD build artifact."
  value       = var.app_container_image
}

output "cloud_run_url" {
  description = "Public frontend and same-origin /api base URL read by the deployment workflow for post-apply health and frontend checks."
  value       = module.cloudrun.cloud_run_url
}
