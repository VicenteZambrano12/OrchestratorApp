# Inputs for the private application asset bucket and its runtime read boundary.
#
# The parent environment supplies storage placement, a globally unique bucket
# name, and shared labels. The external Cloud Run identity receives only
# images/-scoped object reads; uploader and deployer identities are not defined.

variable "project_id" {
  type        = string
  description = "Google Cloud project owning the private application asset bucket."
}

variable "region" {
  type        = string
  description = "Google Cloud bucket location selected by the calling environment for application asset storage."
}

variable "bucket_name" {
  type        = string
  description = "Globally unique application bucket name; the backend GCS_IMAGES_BUCKET setting must select this bucket."
}

variable "common_labels" {
  type        = map(string)
  description = "Shared ownership and environment labels merged with the storage component label."
}

variable "cloud_run_service_account_email" {
  description = "Runtime identity allowed to read exercise images, without bucket listing or writes."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*@[a-z][a-z0-9-]+\\.iam\\.gserviceaccount\\.com$", var.cloud_run_service_account_email))
    error_message = "cloud_run_service_account_email must be a GCP service account email."
  }
}
