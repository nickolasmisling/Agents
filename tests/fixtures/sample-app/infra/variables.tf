variable "aws_region" {
  description = "AWS region for all batchtrack resources."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment name (dev, qa, prod)."
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "qa", "prod"], var.environment)
    error_message = "environment must be one of dev, qa, prod."
  }
}

variable "name_prefix" {
  description = "Prefix used when naming resources."
  type        = string
  default     = "batchtrack"
}

variable "vpc_id" {
  description = "VPC that hosts the application and database."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block of the VPC."
  type        = string
  default     = "10.40.0.0/16"
}

variable "db_subnet_ids" {
  description = "Subnets for the RDS subnet group (at least two AZs)."
  type        = list(string)
}

variable "db_instance_class" {
  description = "RDS instance class for the records database."
  type        = string
  default     = "db.m6g.large"
}

variable "db_allocated_storage" {
  description = "Initial storage for the records database, in GiB."
  type        = number
  default     = 100
}
