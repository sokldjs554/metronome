terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # State lives in a storage account inside the same resource group; the infra workflow creates it
  # and passes the account name with -backend-config (see .github/workflows/infra.yml).
  backend "azurerm" {
    container_name = "tfstate"
    key            = "azure.tfstate"
  }
}

provider "azurerm" {
  features {}
}
