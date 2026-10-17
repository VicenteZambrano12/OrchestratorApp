output "repository_id" {
  value = google_artifact_registry_repository.default.repository_id
}

output "name" {
  value = google_artifact_registry_repository.default.name
}

output "repository_url" {
  value = "${var.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.default.repository_id}"
}