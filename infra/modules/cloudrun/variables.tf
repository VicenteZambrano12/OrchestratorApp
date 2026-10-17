variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "serverless_subnet_id" {
  type = string
}

variable "qdrant_internal_ip" {
  type = string
}

variable "app_container_image" {
  type        = string
  description = "Fully qualified Artifact Registry image URL to deploy."
}

variable "service_account_email" {
  type        = string
  description = "Existing runtime service account for the Cloud Run service."
}

variable "secret_id" {
  type        = string
  description = "Secret Manager secret id holding the app secrets JSON blob."
}

variable "common_labels" {
  type = map(string)
}
