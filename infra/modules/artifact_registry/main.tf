# Container artifact storage for the orchestration application's delivery path.
#
# Owns the dedicated Docker repository used by CI/CD and Cloud Run image
# references. Package-prefix cleanup retains recent builds while limiting old
# artifacts. Repository bootstrap and push/pull IAM are managed outside this
# module; lifecycle protection guards the repository against Terraform deletion.

# Preserves deployable application images between builds and runtime revisions.
resource "google_artifact_registry_repository" "default" {
  project                = var.project_id
  location               = var.location
  repository_id          = var.repository_id
  format                 = "DOCKER"
  description            = "OrchestratorApp production Docker images managed by Terraform"
  cleanup_policy_dry_run = false
  labels                 = merge(var.common_labels, { component = "artifact-registry" })

  # 1. Protects the two most recent versions of matching application packages;
  # KEEP takes precedence when a version also matches the DELETE policy.
  cleanup_policies {
    id     = "keep-last-2-orchestratorapp"
    action = "KEEP"

    most_recent_versions {
      keep_count            = 2
      package_name_prefixes = [var.image_name]
    }
  }

  # 2. Makes other versions of matching packages eligible for deletion,
  # regardless of tag state; packages outside this prefix are not targeted.
  cleanup_policies {
    id     = "delete-old-orchestratorapp"
    action = "DELETE"

    condition {
      tag_state             = "ANY"
      package_name_prefixes = [var.image_name]
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}