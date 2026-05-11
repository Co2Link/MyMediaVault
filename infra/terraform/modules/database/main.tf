variable "prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "database_name" {
  type    = string
  default = "mymediavault"
}

module "mongo_vcore" {
  source = "../mongo-vcore"

  cluster_name           = "${var.prefix}-mongo"
  location               = var.location
  resource_group_name    = var.resource_group_name
  compute_tier           = "Free"
  high_availability_mode = "Disabled"
  storage_size_in_gb     = 32
  mongo_version          = "8.0"
}

output "database_name" {
  value = var.database_name
}

output "mongodb_uri" {
  value     = module.mongo_vcore.connection_string
  sensitive = true
}

output "mongo_cluster_name" {
  value = module.mongo_vcore.cluster_name
}
