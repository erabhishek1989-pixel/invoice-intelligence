variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "centralindia"
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
