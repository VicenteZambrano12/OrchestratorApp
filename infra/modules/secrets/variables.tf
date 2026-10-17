variable "project_id" {
  type        = string
  description = "GCP project in which to create the application JSON secret."
}

variable "secret_id" {
  type        = string
  description = "Name of the application JSON secret."

  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]{1,255}$", var.secret_id))
    error_message = "secret_id must contain 1-255 letters, numbers, underscores, or hyphens."
  }
}

variable "secret_region" {
  type        = string
  description = "GCP region for the Secret Manager replica."
  default     = "europe-southwest1"

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]+$", var.secret_region))
    error_message = "secret_region must be a GCP region ID, such as europe-southwest1."
  }
}

variable "cloud_run_service_account_email" {
  type        = string
  description = "Dedicated runtime identity allowed to read this secret."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*@[a-z][a-z0-9-]+\\.iam\\.gserviceaccount\\.com$", var.cloud_run_service_account_email))
    error_message = "cloud_run_service_account_email must be a GCP service account email."
  }
}

variable "common_labels" {
  type        = map(string)
  description = "Common labels applied to the application secret."
  default     = {}
}
