mock_provider "google" {
  override_during = plan
}

variables {
  project_id            = "basicrahgapp"
  region                = "europe-southwest1"
  app_container_image   = "europe-southwest1-docker.pkg.dev/basicrahgapp/orchestratorapp-repo/orchestratorapp@sha256:c1491886fa0077a400166e2eb9ff8e4b7c75906a7eb572521dae4dfe4f5b2438"
  service_account_email = "orchestratorapp-runtime@basicrahgapp.iam.gserviceaccount.com"
  secret_id             = "orch_app_secret"
  secret_version        = "2"
  common_labels         = { app = "orchestratorapp", env = "prod" }
}

run "production_service" {
  command = plan

  assert {
    condition     = google_cloud_run_v2_service.backend.name == "orchestratorapp-prod" && google_cloud_run_v2_service.backend.project == "basicrahgapp" && google_cloud_run_v2_service.backend.location == "europe-southwest1"
    error_message = "Deploy only the dedicated Madrid production service."
  }

  assert {
    condition     = google_cloud_run_v2_service.backend.deletion_protection && google_cloud_run_v2_service.backend.template[0].service_account == var.service_account_email
    error_message = "Protect the service and use the least-privileged runtime identity."
  }

  assert {
    condition     = google_cloud_run_v2_service.backend.scaling[0].max_instance_count == 1 && google_cloud_run_v2_service.backend.template[0].scaling[0].min_instance_count == 0 && google_cloud_run_v2_service.backend.template[0].scaling[0].max_instance_count == 1
    error_message = "The demo must scale to zero and limit service and revision scaling to one instance."
  }

  assert {
    condition     = google_cloud_run_v2_service.backend.template[0].containers[0].resources[0].cpu_idle && google_cloud_run_v2_service.backend.template[0].containers[0].resources[0].limits["cpu"] == "1" && google_cloud_run_v2_service.backend.template[0].containers[0].resources[0].limits["memory"] == "512Mi"
    error_message = "Use request-based CPU allocation with demo-sized resources."
  }

  assert {
    condition     = google_cloud_run_v2_service.backend.template[0].containers[0].image == var.app_container_image && google_cloud_run_v2_service.backend.template[0].containers[0].ports[0].container_port == 8080
    error_message = "Deploy the selected immutable image on the combined server's port."
  }

  assert {
    condition     = google_cloud_run_v2_service.backend.template[0].volumes[0].secret[0].secret == "orch_app_secret" && google_cloud_run_v2_service.backend.template[0].volumes[0].secret[0].items[0].version == "2" && google_cloud_run_v2_service.backend.template[0].volumes[0].secret[0].items[0].mode == 292 && google_cloud_run_v2_service.backend.template[0].volumes[0].secret[0].items[0].path == "orch_app_secret.json"
    error_message = "Mount the pinned populated JSON version read-only, readable by the non-root container."
  }

  assert {
    condition     = one([for env in google_cloud_run_v2_service.backend.template[0].containers[0].env : env.value if env.name == "APP_SECRETS_FILE"]) == "/var/secrets/orch_app_secret.json" && google_cloud_run_v2_service.backend.template[0].containers[0].volume_mounts[0].mount_path == "/var/secrets"
    error_message = "The runtime loader must receive the mounted JSON file, not an unused JSON environment variable."
  }

  assert {
    condition     = google_cloud_run_v2_service.backend.template[0].containers[0].startup_probe[0].http_get[0].path == "/api/health" && google_cloud_run_v2_service.backend.template[0].containers[0].liveness_probe[0].http_get[0].path == "/api/health"
    error_message = "Probe the actual combined backend health endpoint."
  }

  assert {
    condition     = google_cloud_run_v2_service_iam_member.public_access.member == "allUsers" && google_cloud_run_v2_service_iam_member.public_access.role == "roles/run.invoker" && length(google_cloud_run_v2_service.backend.template[0].vpc_access) == 0 && google_cloud_run_v2_service.backend.traffic[0].percent == 100
    error_message = "Expose the app publicly and route to the latest revision without unused VPC infrastructure."
  }
}

run "reject_mutable_image" {
  command = plan
  variables {
    app_container_image = "europe-southwest1-docker.pkg.dev/basicrahgapp/orchestratorapp-repo/orchestratorapp:latest"
  }
  expect_failures = [var.app_container_image]
}

run "reject_unpinned_secret" {
  command = plan
  variables {
    secret_version = "latest"
  }
  expect_failures = [var.secret_version]
}

run "reject_invalid_runtime_identity" {
  command = plan
  variables {
    service_account_email = "user@example.com"
  }
  expect_failures = [var.service_account_email]
}

run "reject_invalid_service_name" {
  command = plan
  variables {
    service_name = "BasicRAG_App"
  }
  expect_failures = [var.service_name]
}
