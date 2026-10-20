# Terraform and Google provider compatibility for runtime configuration storage.
#
# Declares the provider contract for secret replication, version lifecycle, and
# secret-scoped IAM. The calling environment supplies provider configuration and
# deployer credentials; the runtime reader is a separate input identity.

terraform {
  required_version = ">= 1.13.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}
