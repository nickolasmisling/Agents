terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
  }

  backend "s3" {
    bucket         = "batchtrack-terraform-state"
    key            = "prod/batchtrack.tfstate"
    region         = "us-east-1"
    dynamodb_table = "batchtrack-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Application = "batchtrack"
      Environment = var.environment
      Owner       = "mes-platform"
    }
  }
}

# --- Batch report exports -------------------------------------------------

resource "aws_s3_bucket" "batch_reports" {
  bucket = "${var.name_prefix}-${var.environment}-batch-reports"
}

resource "aws_s3_bucket_ownership_controls" "batch_reports" {
  bucket = aws_s3_bucket.batch_reports.id

  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_public_access_block" "batch_reports" {
  bucket = aws_s3_bucket.batch_reports.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_acl" "batch_reports" {
  bucket = aws_s3_bucket.batch_reports.id
  acl    = "public-read"

  depends_on = [
    aws_s3_bucket_ownership_controls.batch_reports,
    aws_s3_bucket_public_access_block.batch_reports,
  ]
}

# --- Network --------------------------------------------------------------

resource "aws_security_group" "backend" {
  name        = "${var.name_prefix}-${var.environment}-backend"
  description = "batchtrack app hosts and records database"
  vpc_id      = var.vpc_id

  ingress {
    description = "API from inside the VPC"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  ingress {
    description = "Ops SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "PostgreSQL for app and reporting gateway"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- Records database -----------------------------------------------------

resource "aws_db_subnet_group" "records" {
  name       = "${var.name_prefix}-${var.environment}-records"
  subnet_ids = var.db_subnet_ids
}

resource "aws_db_instance" "records" {
  identifier     = "${var.name_prefix}-${var.environment}-records"
  engine         = "postgres"
  engine_version = "15.6"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 4
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "batchtrack"
  username = "batchtrack_admin"
  password = "Btr4ck-Prod-2024!"

  db_subnet_group_name   = aws_db_subnet_group.records.name
  vpc_security_group_ids = [aws_security_group.backend.id]
  publicly_accessible    = true
  multi_az               = true

  backup_retention_period   = 35
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.name_prefix}-${var.environment}-records-final"
}

output "db_endpoint" {
  value = aws_db_instance.records.address
}

output "reports_bucket" {
  value = aws_s3_bucket.batch_reports.bucket
}
