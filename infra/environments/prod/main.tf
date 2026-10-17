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

provider "neon" {}

provider "google" {
  project = var.project_id
  region  = var.region
}

module "artifact_registry" {
  source        = "../../modules/artifact_registry"
  project_id    = var.project_id
  location      = var.region
  repository_id = var.artifact_registry_repository_id
  image_name    = "orchestratorapp"
  common_labels = var.common_labels
}

import {
  id = "projects/${var.project_id}/locations/${var.region}/repositories/${var.artifact_registry_repository_id}"
  to = module.artifact_registry.google_artifact_registry_repository.default
}

module "storage" {
  source                          = "../../modules/storage"
  project_id                      = var.project_id
  region                          = var.region
  bucket_name                     = var.bucket_name
  common_labels                   = var.common_labels
  cloud_run_service_account_email = var.cloud_run_service_account_email
}

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

module "secrets" {
  source                          = "../../modules/secrets"
  project_id                      = var.project_id
  secret_id                       = "orch_app_secret"
  secret_region                   = var.region
  cloud_run_service_account_email = var.cloud_run_service_account_email
  common_labels                   = var.common_labels
}
