# Application secret references for parent-module wiring and operator bootstrap.
#
# Exposes identifiers only, never payloads. The stable secret ID feeds Cloud Run;
# the seed version supports inspection and must not be mistaken for the populated
# numeric version selected separately by the production environment.

output "secret_id" {
  description = "Application JSON secret ID passed by the parent to Cloud Run's secret volume and exported for operators publishing populated versions."
  value       = google_secret_manager_secret.app.secret_id
}

output "initial_version" {
  description = "Empty bootstrap version exported by the parent for operator inspection; after publishing real settings, pin that populated numeric version with app_secret_version."
  value       = google_secret_manager_secret_version.initial.version
}
