# Production remote-state configuration for the Google Cloud and Neon stack.
#
# Uses a pre-existing GCS bucket and application-specific prefix so local
# operators and CI/CD share state and GCS-backed locking. The bucket and its IAM
# are bootstrapped outside this stack; the Terraform deployer needs state access,
# while the application runtime does not. State contains generated database
# credentials and secret payloads, so bucket access is a privileged boundary.

terraform {
  backend "gcs" {
    bucket = "terraform_bucket_portfolio"
    prefix = "orchestrator_app"
  }
}
