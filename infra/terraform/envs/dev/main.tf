variable "location" {
  type        = string
  default     = "japaneast"
  description = "Primary region for dev compute and frontend resources."
}

variable "resource_group_location" {
  type        = string
  default     = "eastus"
  description = "Existing resource group metadata location."
}

variable "storage_location" {
  type        = string
  default     = "eastus2"
  description = "Region for the dev storage account."
}

variable "database_location" {
  type        = string
  default     = "westus2"
  description = "Azure SQL free-offer region fixed for this subscription."
}

variable "static_web_app_location" {
  type        = string
  default     = "eastasia"
  description = "Nearest Static Web Apps free-tier region supported by Azure."
}

variable "prefix" {
  type    = string
  default = "mmv-dev"
}

variable "backend_image" {
  type        = string
  description = "Docker image to deploy to Azure Container Apps."
}

variable "backend_commit_sha" {
  type        = string
  default     = "local"
  description = "Source commit deployed by the backend container."
}

variable "database_admin_login" {
  type    = string
  default = "mmvadmin"
}

variable "database_admin_password" {
  type      = string
  sensitive = true
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

variable "torrent_provider" {
  type    = string
  default = "http"
}

variable "torrent_resolver_urls" {
  type    = list(string)
  default = ["https://itorrents.org/torrent/{info_hash}.torrent"]
}

variable "torrent_fetch_timeout_seconds" {
  type    = number
  default = 20
}

variable "torrent_worker_enabled" {
  type    = bool
  default = true
}

variable "torrent_worker_poll_interval_seconds" {
  type    = number
  default = 2
}

variable "torrent_job_lease_seconds" {
  type    = number
  default = 30
}

locals {
  database_url = "mssql+pymssql://${module.database.administrator_login}:${urlencode(var.database_admin_password)}@${module.database.server_fqdn}:1433/${module.database.database_name}?charset=utf8"
}

module "storage" {
  source              = "../../modules/storage"
  prefix              = var.prefix
  location            = var.storage_location
  resource_group_name = azurerm_resource_group.main.name
}

module "database" {
  source              = "../../modules/database"
  prefix              = var.prefix
  location            = var.database_location
  resource_group_name = azurerm_resource_group.main.name
  administrator_login = var.database_admin_login
  database_name       = "mymediavault-free"
  server_name         = "${var.prefix}-sql-wus2"

  administrator_login_password = var.database_admin_password
}

module "app" {
  source                               = "../../modules/app"
  prefix                               = var.prefix
  location                             = var.location
  static_web_app_location              = var.static_web_app_location
  resource_group_name                  = azurerm_resource_group.main.name
  backend_image                        = var.backend_image
  backend_commit_sha                   = var.backend_commit_sha
  database_url                         = local.database_url
  azure_storage_connection_string      = module.storage.connection_string
  azure_blob_container                 = module.storage.torrent_container_name
  entra_tenant_id                      = var.entra_tenant_id
  backend_entra_client_id              = var.backend_entra_client_id
  entra_openapi_client_id              = var.frontend_entra_client_id
  entra_api_scope                      = var.entra_api_scope
  admin_object_ids                     = var.admin_object_ids
  admin_role_names                     = var.admin_role_names
  torrent_provider                     = var.torrent_provider
  torrent_resolver_urls                = var.torrent_resolver_urls
  torrent_fetch_timeout_seconds        = var.torrent_fetch_timeout_seconds
  torrent_worker_enabled               = var.torrent_worker_enabled
  torrent_worker_poll_interval_seconds = var.torrent_worker_poll_interval_seconds
  torrent_job_lease_seconds            = var.torrent_job_lease_seconds
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${var.prefix}"
  location = var.resource_group_location
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
