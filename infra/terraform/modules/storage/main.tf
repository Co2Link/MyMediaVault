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

output "connection_string" {
  value     = azurerm_storage_account.media.primary_connection_string
  sensitive = true
}

output "torrent_container_name" {
  value = azurerm_storage_container.torrents.name
}
