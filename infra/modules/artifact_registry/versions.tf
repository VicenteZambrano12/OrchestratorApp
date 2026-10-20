# Terraform and Google provider compatibility for the artifact storage module.
#
# Declares the provider API contract needed by repository retention policies.
# The calling environment supplies provider configuration and credentials;
# this child module does not establish a separate deployment identity.

terraform {
  required_version = ">= 1.13.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}
