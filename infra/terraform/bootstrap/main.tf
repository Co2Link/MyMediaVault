variable "r2_endpoint" {
  type        = string
  description = "Cloudflare R2 S3-compatible endpoint."
}

variable "r2_access_key_id" {
  type        = string
  sensitive   = true
  description = "Cloudflare R2 access key ID."
}

variable "r2_secret_access_key" {
  type        = string
  sensitive   = true
  description = "Cloudflare R2 secret access key."
}

variable "state_bucket_name" {
  type        = string
  default     = "mymediavault-tfstate"
  description = "Bucket name for Terraform state."
}

variable "state_key" {
  type        = string
  default     = "bootstrap/terraform.tfstate"
  description = "Object key for bootstrap Terraform state."
}

provider "aws" {
  region                      = "auto"
  access_key                  = var.r2_access_key_id
  secret_key                  = var.r2_secret_access_key
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true

  endpoints {
    s3 = var.r2_endpoint
  }
}

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name
}

resource "aws_s3_bucket" "torrent_raw" {
  bucket = "torrent-raw"
}

output "state_bucket_name" {
  value = aws_s3_bucket.state.bucket
}

output "torrent_raw_bucket_name" {
  value = aws_s3_bucket.torrent_raw.bucket
}
