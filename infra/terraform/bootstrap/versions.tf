terraform {
  required_version = ">= 1.6.0"

  backend "s3" {
    bucket                      = "mymediavault-tfstate"
    key                         = "bootstrap/terraform.tfstate"
    region                      = "auto"
    endpoint                    = "https://REPLACE_ME"
    access_key                  = "REPLACE_ME"
    secret_key                  = "REPLACE_ME"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    force_path_style            = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
