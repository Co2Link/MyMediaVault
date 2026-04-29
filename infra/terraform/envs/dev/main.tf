variable "location" {
  type        = string
  default     = "japaneast"
  description = "Primary region for dev compute and frontend resources."
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

variable "entra_tenant_id" {
  type    = string
  default = "2f601908-d99b-48db-af49-314ae7490559"
}

variable "frontend_entra_client_id" {
  type    = string
  default = "60458566-1aed-4e15-934b-47d12c79c95c"
}

variable "backend_entra_client_id" {
  type    = string
  default = "93b539f6-6b22-43ce-a536-033009c9f06d"
}

variable "entra_api_scope" {
  type    = string
  default = "api://93b539f6-6b22-43ce-a536-033009c9f06d/access_as_user"
}

variable "admin_object_ids" {
  type        = list(string)
  default     = []
  description = "Entra user object IDs that should receive MyMediaVault admin rights."
}

variable "admin_role_names" {
  type    = list(string)
  default = ["Admin", "MyMediaVault.Admin"]
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
  database_name       = "mymediavault-free"
  server_name         = "${var.prefix}-sql-jpe"

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
  entra_tenant_id                 = var.entra_tenant_id
  backend_entra_client_id         = var.backend_entra_client_id
  entra_api_scope                 = var.entra_api_scope
  admin_object_ids                = var.admin_object_ids
  admin_role_names                = var.admin_role_names
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

output "frontend_build_variables" {
  value = {
    VITE_ENTRA_TENANT_ID = var.entra_tenant_id
    VITE_ENTRA_CLIENT_ID = var.frontend_entra_client_id
    VITE_API_SCOPE       = var.entra_api_scope
    VITE_API_BASE_URL    = "https://${module.app.backend_fqdn}"
  }
}
