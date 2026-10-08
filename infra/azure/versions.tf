terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # No remote state on purpose: the deploy identity is a Contributor on the resource group only, so it
  # cannot register Microsoft.Storage for a state account. The infra workflow imports the three live
  # resources into a fresh local state on every run and plans against that, which is the drift check
  # this file exists for (see .github/workflows/infra.yml).
}

provider "azurerm" {
  features {}
  # Registering resource providers needs subscription scope; the deploy identity only has the resource group.
  resource_provider_registrations = "none"
}
