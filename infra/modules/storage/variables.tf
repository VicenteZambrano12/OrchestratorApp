variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "bucket_name" {
  type = string
}

variable "common_labels" {
  type = map(string)
}

variable "cloud_run_service_account_email" {
  description = "Runtime identity allowed to read exercise images, without bucket listing or writes."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*@[a-z][a-z0-9-]+\\.iam\\.gserviceaccount\\.com$", var.cloud_run_service_account_email))
    error_message = "cloud_run_service_account_email must be a GCP service account email."
  }
}
