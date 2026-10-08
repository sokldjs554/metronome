# The public server demo on Azure, as code. The same three resources the owner first created with the
# az CLI; `terraform plan` on main must report no changes, which is how the repository proves that this
# file and the live deployment agree.

resource "azurerm_resource_group" "rg" {
  name     = var.resource_group_name
  location = var.location
}

data "azurerm_log_analytics_workspace" "law" {
  count               = var.log_analytics_workspace_name == "" ? 0 : 1
  name                = var.log_analytics_workspace_name
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_container_app_environment" "env" {
  name                       = var.environment_name
  location                   = azurerm_resource_group.rg.location
  resource_group_name        = azurerm_resource_group.rg.name
  logs_destination           = var.log_analytics_workspace_name == "" ? null : "log-analytics"
  log_analytics_workspace_id = var.log_analytics_workspace_name == "" ? null : data.azurerm_log_analytics_workspace.law[0].id

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}

resource "azurerm_container_app" "demo" {
  name                         = var.app_name
  container_app_environment_id = azurerm_container_app_environment.env.id
  resource_group_name          = azurerm_resource_group.rg.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"

  template {
    min_replicas = 0 # scale to zero when idle: the free subscription pays only for requests
    max_replicas = 1

    container {
      name   = var.app_name
      image  = var.image
      cpu    = 1.0
      memory = "2Gi"

      env {
        name  = "PORT"
        value = "8000"
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  lifecycle {
    # The azure workflow rolls new images and revision suffixes on every merge; Terraform owns the
    # shape of the app, not which commit is running.
    ignore_changes = [
      template[0].container[0].image,
      template[0].revision_suffix,
    ]
  }
}
