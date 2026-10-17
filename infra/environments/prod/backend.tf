terraform {
  backend "gcs" {
    bucket = "terraform_bucket_portfolio"
    prefix = "orchestrator_app"
  }
}
