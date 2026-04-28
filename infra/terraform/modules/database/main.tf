variable "prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

resource "azurerm_mssql_server" "main" {
  name                         = "${var.prefix}-sql"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  version                      = "12.0"
  administrator_login          = "mmvadmin"
  administrator_login_password = "ChangeMe12345!"
}

resource "azurerm_mssql_database" "main" {
  name        = "mymediavault"
  server_id   = azurerm_mssql_server.main.id
  sku_name    = "GP_S_Gen5_1"
  max_size_gb = 32
}
