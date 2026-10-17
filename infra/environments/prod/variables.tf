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

variable "neon_region_id" {
  type        = string
  description = "Neon region for the production database; Neon does not support Madrid."
  default     = "aws-eu-central-1"
}

variable "cloud_run_service_account_email" {
  type        = string
  description = "Dedicated runtime identity with access to the database connection secret."
}
