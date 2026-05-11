output "cluster_id" {
  value       = azurerm_mongo_cluster.this.id
  description = "MongoDB vCore cluster ID."
}

output "cluster_name" {
  value       = azurerm_mongo_cluster.this.name
  description = "MongoDB vCore cluster name."
}

output "administrator_username" {
  value       = azurerm_mongo_cluster.this.administrator_username
  description = "MongoDB vCore administrator username."
}

output "administrator_password" {
  value       = random_password.administrator_password.result
  description = "MongoDB vCore administrator password."
  sensitive   = true
}

output "connection_string" {
  value       = azurerm_mongo_cluster.this.connection_strings[0].value
  description = "MongoDB vCore connection string."
  sensitive   = true
}
