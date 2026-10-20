# Terraform and provider compatibility for the cross-cloud database tier.
#
# Pins the Neon provider used for project/role/database lifecycle and constrains
# the Google provider used for credential storage and IAM. Provider credentials
# and configuration are inherited from the calling environment, not defined here.

terraform {
  required_version = ">= 1.13.0"

  required_providers {
    neon = {
      source  = "kislerdm/neon"
      version = "= 0.18.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}
