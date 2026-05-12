resource "random_password" "administrator_password" {
  length           = 24
  special          = true
  min_lower        = 1
  min_upper        = 1
  min_numeric      = 1
  min_special      = 1
  override_special = "!@#$%&*()-_=+[]{}<>:?"
}

resource "azurerm_mongo_cluster" "this" {
  name                   = var.cluster_name
  resource_group_name    = var.resource_group_name
  location               = var.location
  administrator_username = var.administrator_username
  administrator_password = random_password.administrator_password.result
  shard_count            = 1
  compute_tier           = var.compute_tier
  high_availability_mode = var.high_availability_mode
  storage_size_in_gb     = var.storage_size_in_gb
  version                = var.mongo_version
  public_network_access  = "Enabled"
  tags                   = var.tags
}

resource "azapi_resource" "allow_azure_services_firewall_rule" {
  type      = "Microsoft.DocumentDB/mongoClusters/firewallRules@2025-09-01"
  name      = "allow-azure-services"
  parent_id = azurerm_mongo_cluster.this.id

  body = {
    properties = {
      startIpAddress = "0.0.0.0"
      endIpAddress   = "0.0.0.0"
    }
  }

  schema_validation_enabled = false
}
