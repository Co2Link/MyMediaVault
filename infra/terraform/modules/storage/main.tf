variable "prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

resource "azurerm_storage_account" "media" {
  name                     = replace("${var.prefix}media", "-", "")
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "torrents" {
  name                  = "torrent-raw"
  storage_account_id    = azurerm_storage_account.media.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "function_packages" {
  name                  = "function-packages"
  storage_account_id    = azurerm_storage_account.media.id
  container_access_type = "private"
}

resource "azurerm_storage_queue" "torrent_metadata_jobs" {
  name                 = "torrent-metadata-jobs"
  storage_account_name = azurerm_storage_account.media.name
}

output "connection_string" {
  value     = azurerm_storage_account.media.primary_connection_string
  sensitive = true
}

output "primary_access_key" {
  value     = azurerm_storage_account.media.primary_access_key
  sensitive = true
}

output "torrent_container_name" {
  value = azurerm_storage_container.torrents.name
}

output "function_packages_container_name" {
  value = azurerm_storage_container.function_packages.name
}

output "function_packages_container_endpoint" {
  value = "${azurerm_storage_account.media.primary_blob_endpoint}${azurerm_storage_container.function_packages.name}"
}

output "torrent_metadata_queue_name" {
  value = azurerm_storage_queue.torrent_metadata_jobs.name
}

output "storage_account_name" {
  value = azurerm_storage_account.media.name
}

output "storage_account_id" {
  value = azurerm_storage_account.media.id
}
