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

variable "database_url" {
  type      = string
  sensitive = true
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

variable "azure_blob_container" {
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

variable "torrent_worker_poll_interval_seconds" {
  type    = number
  default = 2
}

variable "torrent_job_lease_seconds" {
  type    = number
  default = 30
}

resource "azurerm_container_app_environment" "main" {
  name                = "${var.prefix}-apps"
  location            = var.location
  resource_group_name = var.resource_group_name
}

resource "azurerm_container_app" "web" {
  name                         = "${var.prefix}-web"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  secret {
    name  = "database-url"
    value = var.database_url
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
    name  = "azure-storage-connection-string"
    value = var.azure_storage_connection_string
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
    cooldown_period_in_seconds = 600

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
        name  = "HOSTNAME"
        value = "0.0.0.0"
      }

      env {
        name        = "AUTH_SECRET"
        secret_name = "auth-secret"
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
        name        = "DATABASE_URL"
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
        name  = "MMV_TORRENT_WORKER_POLL_INTERVAL_SECONDS"
        value = tostring(var.torrent_worker_poll_interval_seconds)
      }

      env {
        name  = "MMV_TORRENT_JOB_LEASE_SECONDS"
        value = tostring(var.torrent_job_lease_seconds)
      }
    }
  }
}

resource "azurerm_container_app" "worker" {
  name                         = "${var.prefix}-worker"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  secret {
    name  = "database-url"
    value = var.database_url
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
    name  = "azure-storage-connection-string"
    value = var.azure_storage_connection_string
  }

  template {
    min_replicas               = 1
    cooldown_period_in_seconds = 600

    container {
      name    = "worker"
      image   = var.app_image
      cpu     = 0.25
      memory  = "0.5Gi"
      command = ["npm"]
      args    = ["run", "worker"]

      env {
        name  = "NODE_ENV"
        value = "production"
      }

      env {
        name        = "AUTH_SECRET"
        secret_name = "auth-secret"
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
        name        = "DATABASE_URL"
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
        name  = "MMV_TORRENT_WORKER_POLL_INTERVAL_SECONDS"
        value = tostring(var.torrent_worker_poll_interval_seconds)
      }

      env {
        name  = "MMV_TORRENT_JOB_LEASE_SECONDS"
        value = tostring(var.torrent_job_lease_seconds)
      }
    }
  }
}

output "web_fqdn" {
  value = azurerm_container_app.web.ingress[0].fqdn
}

output "worker_name" {
  value = azurerm_container_app.worker.name
}
