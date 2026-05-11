variable "prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "app_image" {
  type = string
}

variable "app_commit_sha" {
  type    = string
  default = "local"
}

variable "mongodb_uri" {
  type      = string
  sensitive = true
}

variable "mongodb_database" {
  type = string
}

variable "auth_secret" {
  type      = string
  sensitive = true
}

variable "auth_entra_client_id" {
  type = string
}

variable "auth_entra_client_secret" {
  type      = string
  sensitive = true
}

variable "azure_storage_connection_string" {
  type      = string
  sensitive = true
}

variable "azure_storage_access_key" {
  type      = string
  sensitive = true
}

variable "r2_endpoint" {
  type      = string
  sensitive = true
}

variable "r2_access_key_id" {
  type      = string
  sensitive = true
}

variable "r2_secret_access_key" {
  type      = string
  sensitive = true
}

variable "r2_bucket_name" {
  type = string
}

variable "azure_function_package_container_endpoint" {
  type = string
}

variable "entra_tenant_id" {
  type = string
}

variable "admin_object_ids" {
  type    = list(string)
  default = []
}

variable "admin_group_object_ids" {
  type    = list(string)
  default = []
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

resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.prefix}-logs"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_application_insights" "functions" {
  name                = "${var.prefix}-functions-ai"
  location            = var.location
  resource_group_name = var.resource_group_name
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.main.id
}

resource "azurerm_container_app_environment" "main" {
  name                       = "${var.prefix}-apps"
  location                   = var.location
  resource_group_name        = var.resource_group_name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
}

resource "azurerm_container_app" "web" {
  name                         = "${var.prefix}-web"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  secret {
    name  = "mongodb-uri"
    value = var.mongodb_uri
  }

  secret {
    name  = "auth-secret"
    value = var.auth_secret
  }

  secret {
    name  = "entra-client-secret"
    value = var.auth_entra_client_secret
  }

  secret {
    name  = "r2-secret-access-key"
    value = var.r2_secret_access_key
  }

  ingress {
    external_enabled = true
    target_port      = 3000

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas               = 0
    cooldown_period_in_seconds = 300

    container {
      name    = "web"
      image   = var.app_image
      cpu     = 0.25
      memory  = "0.5Gi"
      command = ["npm"]
      args    = ["run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]

      env {
        name  = "NODE_ENV"
        value = "production"
      }

      env {
        name  = "PORT"
        value = "3000"
      }

      env {
        name        = "AUTH_SECRET"
        secret_name = "auth-secret"
      }

      env {
        name  = "AUTH_URL"
        value = "https://${var.prefix}-web.${azurerm_container_app_environment.main.default_domain}"
      }

      env {
        name  = "AUTH_MICROSOFT_ENTRA_ID_ID"
        value = var.auth_entra_client_id
      }

      env {
        name        = "AUTH_MICROSOFT_ENTRA_ID_SECRET"
        secret_name = "entra-client-secret"
      }

      env {
        name  = "AUTH_MICROSOFT_ENTRA_ID_ISSUER"
        value = "https://login.microsoftonline.com/${var.entra_tenant_id}/v2.0"
      }

      env {
        name  = "MMV_COMMIT_SHA"
        value = var.app_commit_sha
      }

      env {
        name        = "MONGODB_URI"
        secret_name = "mongodb-uri"
      }

      env {
        name  = "MMV_MONGODB_DB_NAME"
        value = var.mongodb_database
      }

      env {
        name  = "MMV_ADMIN_OBJECT_IDS"
        value = jsonencode(var.admin_object_ids)
      }

      env {
        name  = "MMV_ADMIN_GROUP_OBJECT_IDS"
        value = jsonencode(var.admin_group_object_ids)
      }

      env {
        name  = "MMV_TORRENT_PROVIDER"
        value = var.torrent_provider
      }

      env {
        name  = "MMV_TORRENT_RESOLVER_URLS"
        value = jsonencode(var.torrent_resolver_urls)
      }

      env {
        name  = "MMV_TORRENT_FETCH_TIMEOUT_SECONDS"
        value = tostring(var.torrent_fetch_timeout_seconds)
      }

      env {
        name  = "R2_ENDPOINT"
        value = var.r2_endpoint
      }

      env {
        name  = "R2_ACCESS_KEY_ID"
        value = var.r2_access_key_id
      }

      env {
        name        = "R2_SECRET_ACCESS_KEY"
        secret_name = "r2-secret-access-key"
      }

      env {
        name  = "R2_BUCKET_NAME"
        value = var.r2_bucket_name
      }
    }
  }
}

resource "azurerm_service_plan" "functions" {
  name                = "${var.prefix}-functions-plan"
  location            = var.location
  resource_group_name = var.resource_group_name
  os_type             = "Linux"
  sku_name            = "FC1"
}

resource "azurerm_function_app_flex_consumption" "torrent_metadata" {
  name                          = "${var.prefix}-functions"
  resource_group_name           = var.resource_group_name
  location                      = var.location
  service_plan_id               = azurerm_service_plan.functions.id
  runtime_name                  = "node"
  runtime_version               = "22"
  storage_container_endpoint    = var.azure_function_package_container_endpoint
  storage_container_type        = "blobContainer"
  storage_authentication_type   = "StorageAccountConnectionString"
  storage_access_key            = var.azure_storage_access_key
  maximum_instance_count        = 1
  instance_memory_in_mb         = 512
  public_network_access_enabled = true

  app_settings = {
    AzureWebJobsStorage                        = var.azure_storage_connection_string
    AUTH_SECRET                                = var.auth_secret
    AUTH_MICROSOFT_ENTRA_ID_ID                 = var.auth_entra_client_id
    AUTH_MICROSOFT_ENTRA_ID_SECRET             = var.auth_entra_client_secret
    AUTH_MICROSOFT_ENTRA_ID_ISSUER             = "https://login.microsoftonline.com/${var.entra_tenant_id}/v2.0"
    MONGODB_URI                                = var.mongodb_uri
    MMV_MONGODB_DB_NAME                        = var.mongodb_database
    MMV_TORRENT_PROVIDER                       = var.torrent_provider
    MMV_TORRENT_RESOLVER_URLS                  = jsonencode(var.torrent_resolver_urls)
    MMV_TORRENT_FETCH_TIMEOUT_SECONDS          = tostring(var.torrent_fetch_timeout_seconds)
    R2_ENDPOINT                                = var.r2_endpoint
    R2_ACCESS_KEY_ID                           = var.r2_access_key_id
    R2_SECRET_ACCESS_KEY                       = var.r2_secret_access_key
    R2_BUCKET_NAME                             = var.r2_bucket_name
    APPLICATIONINSIGHTS_CONNECTION_STRING      = azurerm_application_insights.functions.connection_string
    ApplicationInsightsAgent_EXTENSION_VERSION = "~3"
    FUNCTIONS_EXTENSION_VERSION                = "~4"
  }

  site_config {
    application_insights_connection_string = azurerm_application_insights.functions.connection_string
    minimum_tls_version                    = "1.2"
  }
}

output "web_fqdn" {
  value = azurerm_container_app.web.ingress[0].fqdn
}

output "function_app_name" {
  value = azurerm_function_app_flex_consumption.torrent_metadata.name
}

output "log_analytics_workspace_name" {
  value = azurerm_log_analytics_workspace.main.name
}
