# Public serving tier for the orchestration frontend and same-origin backend.
#
# Runs one combined application container with scale-to-zero and bounded instance
# counts. The supplied service account accesses private images and secrets through
# grants owned by sibling modules. A pinned JSON secret volume supplies runtime
# settings and LLM credentials without embedding them in the container image.
# No VPC connector or private database route is configured here.

# Hosts the frontend and agent API together so browser requests use one origin;
# zero minimum instances limits idle compute cost, not persistence requirements.
resource "google_cloud_run_v2_service" "backend" {
  project             = var.project_id
  name                = var.service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = true

  labels = merge(var.common_labels, { component = "app" })

  scaling {
    max_instance_count = 1
  }

  template {
    # Uses the application identity rather than inheriting deployment privileges.
    service_account                  = var.service_account_email
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    max_instance_request_concurrency = 8
    timeout                          = "300s"

    # Process-local sessions are not shared across instances and can be lost on
    # shutdown or rollout; the instance limit is not a durable session store.
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image = var.app_container_image

      ports {
        container_port = 8080
      }

      env {
        name  = "MODE"
        value = "CLOUD"
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        name  = "APP_SECRETS_FILE"
        value = "/var/secrets/orch_app_secret.json"
      }

      volume_mounts {
        name       = "app-secrets"
        mount_path = "/var/secrets"
      }

      resources {
        cpu_idle          = true
        startup_cpu_boost = false
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      # Allows application initialization before routing traffic; this endpoint
      # does not verify database or LLM availability.
      startup_probe {
        initial_delay_seconds = 0
        timeout_seconds       = 5
        period_seconds        = 10
        failure_threshold     = 24
        http_get {
          path = "/api/health"
          port = 8080
        }
      }

      liveness_probe {
        timeout_seconds   = 5
        period_seconds    = 30
        failure_threshold = 3
        http_get {
          path = "/api/health"
          port = 8080
        }
      }
    }

    volumes {
      name = "app-secrets"
      secret {
        secret = var.secret_id
        items {
          version = var.secret_version
          path    = "orch_app_secret.json"
          # Decimal 292 is 0444: the non-root process can read the root-owned
          # secret file, but cannot write it.
          mode    = 292
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Allows browsers to reach the frontend and API without Google IAM credentials.
# This service-scoped invoker grant does not authorize application operations;
# endpoint authorization must be enforced by the application.
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  location = google_cloud_run_v2_service.backend.location
  project  = var.project_id
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
