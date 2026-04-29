terraform {
  required_providers {
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.0"
    }
  }
}

variable "prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "administrator_login" {
  type    = string
  default = "mmvadmin"
}

variable "administrator_login_password" {
  type      = string
  sensitive = true
}

variable "database_name" {
  type    = string
  default = "mymediavault"
}

variable "server_name" {
  type    = string
  default = null
}

resource "azurerm_mssql_server" "main" {
  name                         = coalesce(var.server_name, "${var.prefix}-sql")
  resource_group_name          = var.resource_group_name
  location                     = var.location
  version                      = "12.0"
  administrator_login          = var.administrator_login
  administrator_login_password = var.administrator_login_password
}

resource "azapi_resource" "main" {
  type                      = "Microsoft.Sql/servers/databases@2025-02-01-preview"
  schema_validation_enabled = false
  name                      = var.database_name
  parent_id                 = azurerm_mssql_server.main.id
  location                  = var.location

  body = {
    properties = {
      createMode                       = "Default"
      useFreeLimit                     = true
      freeLimitExhaustionBehavior      = "AutoPause"
      maxSizeBytes                     = 34359738368
      autoPauseDelay                   = 60
      minCapacity                      = 0.5
      requestedBackupStorageRedundancy = "Local"
      licenseType                      = "LicenseIncluded"
    }
    sku = {
      name     = "GP_S_Gen5_2"
      tier     = "GeneralPurpose"
      family   = "Gen5"
      capacity = 2
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "azurerm_mssql_firewall_rule" "allow_azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

output "administrator_login" {
  value = var.administrator_login
}

output "database_name" {
  value = azapi_resource.main.name
}

output "server_fqdn" {
  value = azurerm_mssql_server.main.fully_qualified_domain_name
}
