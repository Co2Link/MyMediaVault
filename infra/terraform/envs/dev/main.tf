variable "location" {
  type    = string
  default = "eastus"
}

variable "prefix" {
  type    = string
  default = "mmv-dev"
}

variable "backend_image" {
  type        = string
  description = "Docker image to deploy to Azure Container Apps."
}

variable "database_admin_login" {
  type    = string
  default = "mmvadmin"
}

variable "database_admin_password" {
  type      = string
  sensitive = true
}

variable "test_mode_enabled" {
  type        = bool
  default     = false
  description = "Enable only for temporary development smoke tests."
}

locals {
  database_url = "mssql+pymssql://${module.database.administrator_login}:${urlencode(var.database_admin_password)}@${module.database.server_fqdn}:1433/${module.database.database_name}?charset=utf8"
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
  administrator_login = var.database_admin_login

  administrator_login_password = var.database_admin_password
}

module "app" {
  source                          = "../../modules/app"
  prefix                          = var.prefix
  location                        = var.location
  resource_group_name             = azurerm_resource_group.main.name
  backend_image                   = var.backend_image
  database_url                    = local.database_url
  azure_storage_connection_string = module.storage.connection_string
  azure_blob_container            = module.storage.torrent_container_name
  test_mode_enabled               = var.test_mode_enabled
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${var.prefix}"
  location = var.location
}

output "backend_url" {
  value = "https://${module.app.backend_fqdn}"
}

output "frontend_url" {
  value = "https://${module.app.frontend_default_host_name}"
}

output "frontend_static_web_app_api_key" {
  value     = module.app.frontend_api_key
  sensitive = true
}
