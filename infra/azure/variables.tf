variable "location" {
  description = "Azure region (Korea Central keeps the demo close to its audience)."
  type        = string
  default     = "koreacentral"
}

variable "resource_group_name" {
  type    = string
  default = "metronome-rg"
}

variable "environment_name" {
  description = "Container Apps environment that hosts the demo."
  type        = string
  default     = "metronome-env"
}

variable "app_name" {
  type    = string
  default = "metronome-demo"
}

variable "image" {
  description = "Image the app is created with; later deployments change it outside Terraform (see lifecycle)."
  type        = string
  default     = "ghcr.io/sokldjs554/metronome-demo:latest"
}

variable "log_analytics_workspace_name" {
  description = "Workspace the environment sends logs to (az CLI creates one when the environment is created). Empty = none."
  type        = string
  default     = ""
}
