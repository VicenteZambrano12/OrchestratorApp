output "app_bucket_name" {
  value = module.storage.bucket_name
}

output "app_bucket_url" {
  value = module.storage.bucket_url
}

output "database_secret_id" {
  value = module.database.secret_id
}

output "database_secret_version" {
  value = module.database.secret_version
}

output "neon_project_id" {
  value = module.database.neon_project_id
}

output "database_host" {
  value = module.database.database_host
}

output "app_secret_id" {
  value = module.secrets.secret_id
}

output "app_secret_initial_version" {
  value = module.secrets.initial_version
}

output "artifact_registry_repository_url" {
  value = module.artifact_registry.repository_url
}

output "app_container_image" {
  value = var.app_container_image
}

output "cloud_run_url" {
  description = "Public production frontend and same-origin /api endpoint."
  value       = module.cloudrun.cloud_run_url
}
