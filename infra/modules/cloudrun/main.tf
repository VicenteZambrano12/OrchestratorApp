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
    service_account                  = var.service_account_email
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    max_instance_request_concurrency = 8
    timeout                          = "300s"

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

resource "google_cloud_run_v2_service_iam_member" "public_access" {
  location = google_cloud_run_v2_service.backend.location
  project  = var.project_id
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
