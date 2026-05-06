variable "location" {
  type        = string
  default     = "japaneast"
  description = "Primary region for dev compute resources."
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

variable "prefix" {
  type    = string
  default = "mmv-dev"
}

variable "database_admin_password" {
  type      = string
  sensitive = true
}

variable "auth_secret" {
  type      = string
  sensitive = true
}

variable "app_image" {
  type        = string
  description = "Docker image to deploy to both web and worker container apps."
}

variable "app_commit_sha" {
  type        = string
  default     = "local"
  description = "Source commit deployed by the application containers."
}

variable "entra_tenant_id" {
  type    = string
  default = "2f601908-d99b-48db-af49-314ae7490559"
}

variable "auth_entra_client_id" {
  type    = string
  default = "0efa4e4c-7232-41b0-b8b4-46a45ac3b9ce"
}

variable "auth_entra_client_secret" {
  type      = string
  sensitive = true
}

variable "admin_object_ids" {
  type        = list(string)
  default     = []
  description = "Entra user object IDs that should receive MyMediaVault admin rights."
}

variable "admin_group_object_ids" {
  type        = list(string)
  default     = []
  description = "Entra group object IDs that should receive MyMediaVault admin rights."
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

variable "torrent_worker_poll_interval_seconds" {
  type    = number
  default = 2
}

variable "torrent_job_lease_seconds" {
  type    = number
  default = 30
}

locals {
  database_url = "sqlserver://${module.database.server_fqdn}:1433;database=${module.database.database_name};user=${module.database.administrator_login};password=${var.database_admin_password};encrypt=true;trustServerCertificate=true"
}

module "database" {
  source = "../../modules/database"

  prefix                       = var.prefix
  location                     = var.location
  resource_group_name          = azurerm_resource_group.main.name
  administrator_login_password = var.database_admin_password
}

module "storage" {
  source              = "../../modules/storage"
  prefix              = var.prefix
  location            = var.storage_location
  resource_group_name = azurerm_resource_group.main.name
}

module "app" {
  source                               = "../../modules/app"
  prefix                               = var.prefix
  location                             = var.location
  resource_group_name                  = azurerm_resource_group.main.name
  app_image                            = var.app_image
  app_commit_sha                       = var.app_commit_sha
  database_url                         = local.database_url
  auth_secret                          = var.auth_secret
  auth_entra_client_id                 = var.auth_entra_client_id
  auth_entra_client_secret             = var.auth_entra_client_secret
  entra_tenant_id                      = var.entra_tenant_id
  azure_storage_connection_string      = module.storage.connection_string
  azure_blob_container                 = module.storage.torrent_container_name
  admin_object_ids                     = var.admin_object_ids
  admin_group_object_ids               = var.admin_group_object_ids
  torrent_provider                     = var.torrent_provider
  torrent_resolver_urls                = var.torrent_resolver_urls
  torrent_fetch_timeout_seconds        = var.torrent_fetch_timeout_seconds
  torrent_worker_poll_interval_seconds = var.torrent_worker_poll_interval_seconds
  torrent_job_lease_seconds            = var.torrent_job_lease_seconds
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${var.prefix}"
  location = var.resource_group_location
}

output "web_url" {
  value = "https://${module.app.web_fqdn}"
}

output "worker_name" {
  value = module.app.worker_name
}
