variable "prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "backend_image" {
  type = string
}

variable "database_url" {
  type      = string
  sensitive = true
}

variable "azure_storage_connection_string" {
  type      = string
  sensitive = true
}

variable "azure_blob_container" {
  type = string
}

variable "test_mode_enabled" {
  type    = bool
  default = false
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.prefix}-logs"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_container_app_environment" "main" {
  name                       = "${var.prefix}-apps"
  location                   = var.location
  resource_group_name        = var.resource_group_name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
}

resource "azurerm_container_app" "backend" {
  name                         = "${var.prefix}-backend"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  secret {
    name  = "database-url"
    value = var.database_url
  }

  secret {
    name  = "azure-storage-connection-string"
    value = var.azure_storage_connection_string
  }

  ingress {
    external_enabled = true
    target_port      = 8000

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    container {
      name   = "backend"
      image  = var.backend_image
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "MMV_ENVIRONMENT"
        value = var.test_mode_enabled ? "test" : "production"
      }

      env {
        name  = "MMV_TEST_MODE"
        value = tostring(var.test_mode_enabled)
      }

      env {
        name        = "MMV_DATABASE_URL"
        secret_name = "database-url"
      }

      env {
        name        = "MMV_AZURE_STORAGE_CONNECTION_STRING"
        secret_name = "azure-storage-connection-string"
      }

      env {
        name  = "MMV_AZURE_BLOB_CONTAINER"
        value = var.azure_blob_container
      }

      env {
        name  = "MMV_CORS_ORIGINS"
        value = jsonencode(["https://${azurerm_static_web_app.frontend.default_host_name}"])
      }
    }
  }
}

resource "azurerm_static_web_app" "frontend" {
  name                = "${var.prefix}-frontend"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku_tier            = "Free"
  sku_size            = "Free"
}

output "backend_fqdn" {
  value = azurerm_container_app.backend.ingress[0].fqdn
}

output "frontend_default_host_name" {
  value = azurerm_static_web_app.frontend.default_host_name
}

output "frontend_api_key" {
  value     = azurerm_static_web_app.frontend.api_key
  sensitive = true
}
