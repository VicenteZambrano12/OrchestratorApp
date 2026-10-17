variable "project_id" {
  type        = string
  description = "The GCP project containing the database connection secret."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid GCP project ID."
  }
}

variable "app_name" {
  type        = string
  description = "Application prefix for the Neon project and GCP secret."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,39}$", var.app_name))
    error_message = "app_name must start with a lowercase letter and contain at most 40 lowercase letters, digits, or hyphens."
  }
}

variable "environment" {
  type        = string
  description = "Environment suffix for the Neon project, branch, and GCP secret."
  default     = "prod"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,19}$", var.environment))
    error_message = "environment must start with a lowercase letter and contain at most 20 lowercase letters, digits, or hyphens."
  }
}

variable "neon_region_id" {
  type        = string
  description = "Neon AWS region; Frankfurt is used for the Madrid-hosted app. Immutable after project creation."
  default     = "aws-eu-central-1"

  validation {
    condition     = can(regex("^aws-[a-z]+(-[a-z]+)+-[0-9]+$", var.neon_region_id))
    error_message = "neon_region_id must be a Neon AWS region ID, such as aws-eu-central-1."
  }
}

variable "pg_version" {
  type        = number
  description = "PostgreSQL major version. Changing it may require database replacement."
  default     = 16

  validation {
    condition     = contains([16, 17], var.pg_version)
    error_message = "pg_version must be 16 or 17."
  }
}

variable "db_name" {
  type        = string
  description = "Name of the dedicated, initially empty application database."

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{0,62}$", var.db_name)) && !contains(["neondb", "postgres", "template0", "template1"], var.db_name)
    error_message = "db_name must be a lowercase SQL identifier of at most 63 characters and not a Neon or PostgreSQL default database name."
  }
}

variable "db_user" {
  type        = string
  description = "Name of the dedicated application database owner, created with a Neon-generated password."

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{0,62}$", var.db_user)) && !startswith(var.db_user, "pg_") && !contains(["neondb_owner", "postgres", "cloud_admin"], var.db_user)
    error_message = "db_user must be a lowercase SQL identifier of at most 63 characters and not a reserved role name or pg_ prefix."
  }
}

variable "cloud_run_service_account_email" {
  type        = string
  description = "Existing dedicated Cloud Run runtime service account; never the Terraform deployer."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*@[a-z][a-z0-9-]+\\.iam\\.gserviceaccount\\.com$", var.cloud_run_service_account_email))
    error_message = "cloud_run_service_account_email must be a GCP service account email."
  }
}

variable "secret_region" {
  type        = string
  description = "GCP region for the Secret Manager replica, independent of the Neon region."
  default     = "europe-southwest1"

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]+$", var.secret_region))
    error_message = "secret_region must be a GCP region ID, such as europe-southwest1."
  }
}

variable "common_labels" {
  type        = map(string)
  description = "Common labels applied to GCP resources."
  default     = {}
}
