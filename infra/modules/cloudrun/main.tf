resource "google_cloud_run_v2_service" "backend" {
  name                = "basicragapp-backend"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  labels = merge(var.common_labels, { component = "backend" })

  template {
    service_account = var.service_account_email

    # No Redis is wired up, so session state lives in fakeredis: an in-memory
    # cache local to a single process. Pin to exactly one instance so every
    # request is served by the same process and the cache is actually shared.
    scaling {
      min_instance_count = 1
      max_instance_count = 1
    }

    containers {
      image = var.app_container_image

      env {
        name  = "QDRANT_HOST"
        value = var.qdrant_internal_ip
      }

      env {
        name  = "QDRANT_PORT"
        value = "6333"
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }

      # Single worker so fakeredis's in-memory cache (no real Redis configured) is
      # shared by every request instead of being split across sibling processes.
      env {
        name  = "MAX_WORKERS"
        value = "1"
      }

      env {
        name = "APP_SECRETS_JSON"
        value_source {
          secret_key_ref {
            secret  = var.secret_id
            version = "latest"
          }
        }
      }

      # Default 512Mi was getting OOM-killed by the ML/genai import stack across gunicorn workers.
      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }
    }

    vpc_access {
      network_interfaces {
        subnetwork = var.serverless_subnet_id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }
  }
}

resource "google_cloud_run_service_iam_member" "public_access" {
  location = google_cloud_run_v2_service.backend.location
  project  = var.project_id
  service  = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
