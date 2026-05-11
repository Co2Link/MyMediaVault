resource "random_password" "administrator_password" {
  length  = 24
  special = false
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
