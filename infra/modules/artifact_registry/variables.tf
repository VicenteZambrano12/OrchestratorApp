# Inputs defining the application container repository and retention scope.
#
# The production root supplies the project, location, and shared labels; package
# selection constrains cleanup to the application's image prefix. These inputs
# configure artifact storage, not CI/CD authentication or repository IAM.

variable "project_id" {
  type        = string
  description = "Google Cloud project owning the application Docker repository."
}

variable "location" {
  type        = string
  description = "Artifact Registry location used by the repository and its Docker registry hostname."
}

variable "repository_id" {
  type        = string
  description = "Dedicated Docker repository ID."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,62}$", var.repository_id))
    error_message = "repository_id must contain lowercase letters, numbers, or hyphens and start with a letter."
  }
}

variable "image_name" {
  type        = string
  description = "Docker image package prefix matched by cleanup policies that retain the two most recent matching package versions."
  default     = "orchestratorapp"

  validation {
    condition     = can(regex("^[a-z0-9]+([._-][a-z0-9]+)*$", var.image_name))
    error_message = "image_name must be a single lowercase Docker image name, without a registry or tag."
  }
}

variable "common_labels" {
  type        = map(string)
  description = "Shared ownership and environment labels merged with the artifact-registry component label."
}