terraform {
  required_version = ">= 1.6.0"

  backend "azurerm" {
    container_name = "tfstate"
    key            = "dev.terraform.tfstate"
  }

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
}
