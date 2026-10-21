# Terraform and Google provider compatibility for the application serving tier.
#
# Declares the provider contract for Cloud Run v2 services and service-level IAM.
# The parent environment supplies Google Cloud credentials, project, and region;
# runtime service-account selection remains a separate module input.

terraform {
  required_version = ">= 1.13.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}
