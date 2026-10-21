# Artifact repository identifiers for the calling environment and image tooling.
#
# Separates API resource identity from the Docker push/pull path. These values
# support parent-module integration and operator inspection; CI/CD in this
# repository constructs its image path from matching GitHub variables.

output "repository_id" {
  description = "Short repository ID available to calling environments or operators selecting the repository in gcloud commands."
  value       = google_artifact_registry_repository.default.repository_id
}

output "name" {
  description = "Fully qualified repository resource name available to parent modules or operators making Artifact Registry API requests."
  value       = google_artifact_registry_repository.default.name
}

output "repository_url" {
  description = "Docker repository base path exported by the production root for operators constructing image push/pull references."
  value       = "${var.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.default.repository_id}"
}