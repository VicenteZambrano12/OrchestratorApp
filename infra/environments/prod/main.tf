# Production composition root for the AI agent orchestration application.
#
# Connects Google Cloud container delivery, scale-to-zero Cloud Run compute,
# private object storage, and Secret Manager with a Neon PostgreSQL deployment.
# Child modules own resource configuration and resource-scoped IAM bindings;
# this file supplies the production identity, locations, and shared labels.
#
# The Cloud Run service account is supplied externally. Modules grant it read
# access to exercise images and application/database secrets, not broad project
# administration. Application secret payloads are populated outside this root;
# Cloud Run mounts the version selected by var.app_secret_version.
#
# Cloud Run accepts public requests through the compute module's invoker binding;
# that binding does not make the storage bucket or secrets publicly accessible.
# Provider constraints are declared here, while remote state is configured
# separately in backend.tf. This root does not provision VPC networking.

terraform {
  required_version = "~> 1.13.0"

  required_providers {
    neon = {
      source  = "kislerdm/neon"
      version = "= 0.18.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}

# Manages the external PostgreSQL service alongside its Google Cloud consumers.
provider "neon" {}

# Keeps Google Cloud resources in the target production project and region.
provider "google" {
  project = var.project_id
  region  = var.region
}

# Retains application container images for the build-and-deploy pipeline, with
# cleanup policies that preserve the two most recent matching image versions.
module "artifact_registry" {
  source        = "../../modules/artifact_registry"
  project_id    = var.project_id
  location      = var.region
  repository_id = var.artifact_registry_repository_id
  image_name    = "orchestratorapp"
  common_labels = var.common_labels
}

# Adopts the existing production image repository into Terraform ownership
# instead of attempting to create a second repository at the same location.
import {
  id = "projects/${var.project_id}/locations/${var.region}/repositories/${var.artifact_registry_repository_id}"
  to = module.artifact_registry.google_artifact_registry_repository.default
}

# Keeps application objects private while allowing the runtime identity to read
# only the images/ prefix; its IAM condition excludes bucket listing and writes.
module "storage" {
  source                          = "../../modules/storage"
  project_id                      = var.project_id
  region                          = var.region
  bucket_name                     = var.bucket_name
  common_labels                   = var.common_labels
  cloud_run_service_account_email = var.cloud_run_service_account_email
}

# Provisions production PostgreSQL and stores its TLS-required pooled connection
# URI in Secret Manager. Grants the runtime identity access to that secret so
# database credentials need not be embedded in the deployed container image.
module "database" {
  source                          = "../../modules/database"
  project_id                      = var.project_id
  app_name                        = "orchestratorapp"
  environment                     = "prod"
  neon_org_id                     = var.neon_org_id
  neon_region_id                  = var.neon_region_id
  db_name                         = "orchestrator_app"
  db_user                         = "orchestrator_app"
  cloud_run_service_account_email = var.cloud_run_service_account_email
  secret_region                   = var.region
  common_labels                   = var.common_labels
}

# Establishes the application secret container and an empty seed version.
# Secret-scoped accessor permission lets the runtime mount populated application
# configuration without granting it permission to administer or update secrets.
module "secrets" {
  source                          = "../../modules/secrets"
  project_id                      = var.project_id
  secret_id                       = "orch_app_secret"
  secret_region                   = var.region
  cloud_run_service_account_email = var.cloud_run_service_account_email
  common_labels                   = var.common_labels
}

# Hosts the scale-to-zero application container under the supplied runtime
# identity, mounting the selected application secret version as a read-only file.
# Public invocation is configured in this module; application authorization
# remains the responsibility of the application rather than Cloud Run IAM.
module "cloudrun" {
  source                = "../../modules/cloudrun"
  project_id            = var.project_id
  region                = var.region
  app_container_image   = var.app_container_image
  service_account_email = var.cloud_run_service_account_email
  secret_id             = module.secrets.secret_id
  secret_version        = var.app_secret_version
  common_labels         = var.common_labels

  # Waits for backing services and their runtime IAM grants, including those
  # not expressed by the application-secret reference, before deploying compute.
  depends_on = [module.secrets, module.storage, module.database]
}
