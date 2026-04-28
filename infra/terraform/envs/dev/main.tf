variable "location" {
  type    = string
  default = "eastus"
}

variable "prefix" {
  type    = string
  default = "mmv-dev"
}

module "storage" {
  source              = "../../modules/storage"
  prefix              = var.prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
}

module "database" {
  source              = "../../modules/database"
  prefix              = var.prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
}

module "app" {
  source              = "../../modules/app"
  prefix              = var.prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${var.prefix}"
  location = var.location
}
