variable "project_id" {
  type        = string
  description = "The GCP project ID to deploy resources into."
}

variable "region" {
  type        = string
  description = "The GCP region to deploy resources into."
}

variable "bucket_name" {
  type        = string
  description = "The name of the production application bucket."
}

variable "common_labels" {
  type        = map(string)
  description = "Common labels applied to resources that support them."
  default = {
    app        = "orchestratorapp"
    env        = "prod"
    managed-by = "terraform"
    project    = "portfolio"
  }
}

variable "neon_org_id" {
  type        = string
  description = "Neon organization ID, supplied by the NEON_ORG_ID GitHub variable."

  validation {
    condition     = can(regex("^org-[a-z0-9]+(-[a-z0-9]+)*$", var.neon_org_id))
    error_message = "Set NEON_ORG_ID to the organization ID beginning with org- from Neon Organization settings."
  }
}

variable "neon_region_id" {
  type        = string
  description = "Neon region for the production database; Neon does not support Madrid."
  default     = "aws-eu-central-1"
}

variable "cloud_run_service_account_email" {
  type        = string
  description = "Dedicated runtime identity with access to the application secrets and images."
}

variable "artifact_registry_repository_id" {
  type        = string
  description = "Dedicated production Docker repository, matching GCP_AR_REPOSITORY in GitHub."
  default     = "orchestratorapp-repo"
}

variable "app_container_image" {
  type        = string
  description = "Immutable application image selected by the build-and-plan workflow."

  validation {
    condition     = can(regex("^${var.region}-docker\\.pkg\\.dev/${var.project_id}/${var.artifact_registry_repository_id}/orchestratorapp@sha256:[0-9a-f]{64}$", var.app_container_image))
    error_message = "app_container_image must be a sha256 digest in the dedicated production application repository."
  }
}

variable "app_secret_version" {
  type        = string
  description = "Populated orch_app_secret JSON version; update after CLI rotation to deploy a new revision."
  default     = "2"

  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.app_secret_version))
    error_message = "app_secret_version must be a positive numeric Secret Manager version."
  }
}
