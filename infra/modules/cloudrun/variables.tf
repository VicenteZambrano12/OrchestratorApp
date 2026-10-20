# Inputs for deploying the combined orchestration application to Cloud Run.
#
# The parent environment selects an immutable container and a numeric application
# secret version for reproducible revisions. It also supplies the existing
# runtime identity; this module does not grant that identity data access.

variable "project_id" {
  type        = string
  description = "Google Cloud project hosting the public application service."
}

variable "region" {
  type        = string
  description = "Google Cloud region in which the application service and revisions run."
}

variable "service_name" {
  type        = string
  description = "Dedicated production Cloud Run service name."
  default     = "orchestratorapp-prod"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,47}[a-z0-9]$", var.service_name))
    error_message = "service_name must be 2-49 lowercase letters, digits, or hyphens, starting with a letter and ending with a letter or digit."
  }
}

variable "app_container_image" {
  type        = string
  description = "Immutable Artifact Registry image digest to deploy."

  validation {
    condition     = can(regex("^[a-z0-9-]+-docker\\.pkg\\.dev/[a-z0-9-]+/[a-z0-9-]+/[a-z0-9._-]+@sha256:[0-9a-f]{64}$", var.app_container_image))
    error_message = "app_container_image must be an Artifact Registry image pinned to a sha256 digest."
  }
}

variable "service_account_email" {
  type        = string
  description = "Existing runtime service account for the Cloud Run service."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*@[a-z0-9-]+\\.iam\\.gserviceaccount\\.com$", var.service_account_email))
    error_message = "service_account_email must identify a GCP service account."
  }
}

variable "secret_id" {
  type        = string
  description = "Secret Manager secret id holding the app secrets JSON blob."
}

variable "secret_version" {
  type        = string
  description = "Populated numeric JSON secret version, pinned for reproducible revisions."

  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.secret_version))
    error_message = "secret_version must be a positive numeric version, not latest."
  }
}

variable "common_labels" {
  type        = map(string)
  description = "Shared ownership and environment labels merged with the app component label on the Cloud Run service."
}
