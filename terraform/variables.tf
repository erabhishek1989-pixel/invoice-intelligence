variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "eastus"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "prod"
}

variable "project" {
  description = "Project identifier used in resource names"
  type        = string
  default     = "invoiceai"
}

variable "owner" {
  description = "Owner tag value for all resources"
  type        = string
  default     = "er.abhishek1989@gmail.com"
}

variable "doc_intelligence_key" {
  description = "Azure Document Intelligence API key"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "Azure OpenAI API key"
  type        = string
  sensitive   = true
}

variable "secret_key" {
  description = "Flask application secret key"
  type        = string
  sensitive   = true
}

variable "database_url" {
  description = "SQLAlchemy database connection string"
  type        = string
  sensitive   = true
}

variable "sql_admin_login" {
  description = "Azure SQL administrator login username"
  type        = string
  default     = "sqladmin"
}

variable "sql_admin_password" {
  description = "Azure SQL administrator password"
  type        = string
  sensitive   = true
}

variable "openai_deployment_name" {
  description = "Azure OpenAI deployment name for GPT-4o"
  type        = string
  default     = "gpt-4o"
}

locals {
  suffix = "${var.environment}-${var.location}"

  common_tags = {
    environment = var.environment
    project     = var.project
    owner       = var.owner
    managed-by  = "terraform"
  }
}
