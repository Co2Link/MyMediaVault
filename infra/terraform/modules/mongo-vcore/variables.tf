variable "cluster_name" {
  description = "Name for the MongoDB vCore cluster."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]{3,63}$", var.cluster_name))
    error_message = "cluster_name must be 3-63 characters of lowercase letters, digits, or hyphens."
  }
}

variable "location" {
  description = "Azure region for the MongoDB vCore cluster."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group containing the MongoDB vCore cluster."
  type        = string
}

variable "tags" {
  description = "Common tags applied to the cluster."
  type        = map(string)
  default     = {}
}

variable "administrator_username" {
  description = "Administrator username for the cluster."
  type        = string
  default     = "clusteradmin"
}

variable "compute_tier" {
  description = "Compute tier for the cluster."
  type        = string
  default     = "Free"
}

variable "high_availability_mode" {
  description = "High availability mode for the cluster."
  type        = string
  default     = "Disabled"
}

variable "storage_size_in_gb" {
  description = "Storage size in GB for the cluster."
  type        = number
  default     = 32
}

variable "mongo_version" {
  description = "MongoDB version for the cluster."
  type        = string
  default     = "8.0"
}
