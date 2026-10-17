variable "project_id" {
  type = string
}

variable "location" {
  type = string
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
  description = "Application image package governed by the two-version cleanup policies."
  default     = "orchestratorapp"

  validation {
    condition     = can(regex("^[a-z0-9]+([._-][a-z0-9]+)*$", var.image_name))
    error_message = "image_name must be a single lowercase Docker image name, without a registry or tag."
  }
}

variable "common_labels" {
  type = map(string)
}