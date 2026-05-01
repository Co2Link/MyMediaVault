variable "prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "static_web_app_location" {
  type    = string
  default = null
}

variable "resource_group_name" {
  type = string
}

variable "backend_image" {
  type = string
}

variable "backend_commit_sha" {
  type    = string
  default = "local"
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

variable "entra_tenant_id" {
  type = string
}

variable "backend_entra_client_id" {
  type = string
}

variable "entra_openapi_client_id" {
  type = string
}

variable "entra_api_scope" {
  type = string
}

variable "admin_object_ids" {
  type    = list(string)
  default = []
}

variable "admin_role_names" {
  type    = list(string)
  default = ["Admin", "MyMediaVault.Admin"]
}

resource "azurerm_container_app_environment" "main" {
  name                = "${var.prefix}-apps"
  location            = var.location
  resource_group_name = var.resource_group_name
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
    min_replicas               = 0
    cooldown_period_in_seconds = 600

    container {
      name   = "backend"
      image  = var.backend_image
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "MMV_ENVIRONMENT"
        value = "production"
      }

      env {
        name  = "MMV_COMMIT_SHA"
        value = var.backend_commit_sha
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
        name  = "MMV_ENTRA_TENANT_ID"
        value = var.entra_tenant_id
      }

      env {
        name  = "MMV_ENTRA_CLIENT_ID"
        value = var.backend_entra_client_id
      }

      env {
        name  = "MMV_ENTRA_OPENAPI_CLIENT_ID"
        value = var.entra_openapi_client_id
      }

      env {
        name  = "MMV_ENTRA_API_SCOPE"
        value = var.entra_api_scope
      }

      env {
        name  = "MMV_ADMIN_OBJECT_IDS"
        value = jsonencode(var.admin_object_ids)
      }

      env {
        name  = "MMV_ADMIN_ROLE_NAMES"
        value = jsonencode(var.admin_role_names)
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
  location            = coalesce(var.static_web_app_location, var.location)
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
