terraform {
  backend "s3" {
    bucket = "terraform-state-dsrw-prod"
    key    = "wbip_wrapper_core_infra"
    region = "us-east-2"
  }
  required_providers {
    aws = {
      version = "4.67.0"
      source  = "hashicorp/aws"
    }
  }
}

provider "aws" {
  region = "us-east-2"
}
