output "resource_group_name" {
  description = "Name of the main resource group"
  value       = azurerm_resource_group.main.name
}

output "app_service_url" {
  description = "Public URL of the Flask web app"
  value       = "https://${azurerm_linux_web_app.main.default_hostname}"
}

output "app_service_name" {
  description = "App Service resource name (used in app-deploy.yml)"
  value       = azurerm_linux_web_app.main.name
}

output "function_app_name" {
  description = "Azure Function App resource name"
  value       = azurerm_linux_function_app.main.name
}

output "storage_account_name" {
  description = "Primary storage account name"
  value       = azurerm_storage_account.main.name
}

output "storage_container_name" {
  description = "Blob container for invoice uploads"
  value       = azurerm_storage_container.invoices.name
}

output "sql_server_fqdn" {
  description = "Fully qualified domain name of the SQL Server"
  value       = azurerm_mssql_server.main.fully_qualified_domain_name
}

output "sql_database_name" {
  description = "SQL Database name"
  value       = azurerm_mssql_database.main.name
}

output "doc_intelligence_endpoint" {
  description = "Document Intelligence endpoint URL"
  value       = azurerm_cognitive_account.doc_intelligence.endpoint
}

output "openai_endpoint" {
  description = "Azure OpenAI endpoint URL"
  value       = azurerm_cognitive_account.openai.endpoint
}

output "key_vault_name" {
  description = "Key Vault name"
  value       = azurerm_key_vault.main.name
}

output "key_vault_uri" {
  description = "Key Vault URI"
  value       = azurerm_key_vault.main.vault_uri
}

output "app_insights_connection_string" {
  description = "Application Insights connection string"
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}

output "app_service_principal_id" {
  description = "Managed Identity principal ID of the App Service"
  value       = azurerm_linux_web_app.main.identity[0].principal_id
}
