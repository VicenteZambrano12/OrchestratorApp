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
