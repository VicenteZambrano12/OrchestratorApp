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
