mock_provider "google" {
  override_during = plan
}

variables {
  project_id    = "basicrahgapp"
  location      = "europe-southwest1"
  repository_id = "orchestratorapp-repo"
  common_labels = { app = "orchestratorapp", env = "prod" }
}

run "dedicated_registry_with_two_version_retention" {
  command = plan

  assert {
    condition     = google_artifact_registry_repository.default.repository_id == "orchestratorapp-repo" && google_artifact_registry_repository.default.location == "europe-southwest1" && google_artifact_registry_repository.default.format == "DOCKER"
    error_message = "Use the dedicated application Docker repository in Madrid."
  }

  assert {
    condition     = !google_artifact_registry_repository.default.cleanup_policy_dry_run && length(google_artifact_registry_repository.default.cleanup_policies) == 2
    error_message = "Both real keep/delete cleanup policies must be enabled."
  }

  assert {
    condition     = one([for policy in google_artifact_registry_repository.default.cleanup_policies : policy if policy.action == "KEEP"]).most_recent_versions[0].keep_count == 2
    error_message = "The native keep policy must retain exactly two versions."
  }

  assert {
    condition     = one([for policy in google_artifact_registry_repository.default.cleanup_policies : policy if policy.action == "KEEP"]).most_recent_versions[0].package_name_prefixes == tolist(["orchestratorapp"])
    error_message = "The keep policy must target this application, not BasicRAGapp."
  }

  assert {
    condition     = one([for policy in google_artifact_registry_repository.default.cleanup_policies : policy if policy.action == "DELETE"]).condition[0].tag_state == "ANY" && one([for policy in google_artifact_registry_repository.default.cleanup_policies : policy if policy.action == "DELETE"]).condition[0].package_name_prefixes == tolist(["orchestratorapp"])
    error_message = "Old tagged and untagged versions must be eligible for deletion only for this app."
  }

  assert {
    condition     = output.repository_url == "europe-southwest1-docker.pkg.dev/basicrahgapp/orchestratorapp-repo"
    error_message = "Expose the Docker repository URL."
  }
}

run "reject_invalid_repository_id" {
  command = plan
  variables {
    repository_id = "Other/Repo"
  }
  expect_failures = [var.repository_id]
}

run "reject_image_with_tag" {
  command = plan
  variables {
    image_name = "orchestratorapp:latest"
  }
  expect_failures = [var.image_name]
}
