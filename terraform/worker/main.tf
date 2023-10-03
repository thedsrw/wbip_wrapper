terraform {
  backend "s3" {
    bucket = "terraform-state-dsrw-prod"
    key    = "wbip_wrapper"
    region = "us-east-2"
  }
  required_providers {
    aws = {
      version = "5.19.0"
      source  = "hashicorp/aws"
    }
  }
}

provider "aws" {
  region = "us-east-2"
}
