terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  use_oidc = true
  features {
    key_vault {
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = true
    }
  }
}

# ─── Data sources ────────────────────────────────────────────────────────────

data "azurerm_client_config" "current" {}

# ─── Resource Group ──────────────────────────────────────────────────────────

resource "azurerm_resource_group" "main" {
  name     = "rg-${var.project}-${local.suffix}-001"
  location = var.location
  tags     = local.common_tags
}

# ─── Log Analytics Workspace (required by App Insights) ──────────────────────

resource "azurerm_log_analytics_workspace" "main" {
  name                = "law-${var.project}-${local.suffix}-001"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.common_tags
}

# ─── Application Insights ────────────────────────────────────────────────────

resource "azurerm_application_insights" "main" {
  name                = "ai-${var.project}-${local.suffix}-001"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = local.common_tags
}

# ─── Storage Account ─────────────────────────────────────────────────────────

resource "azurerm_storage_account" "main" {
  # max 24 chars, no hyphens
  name                     = "st${var.project}${var.environment}001"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
  tags                     = local.common_tags
}

resource "azurerm_storage_container" "invoices" {
  name                  = "invoices"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

# ─── Azure SQL ───────────────────────────────────────────────────────────────

resource "azurerm_mssql_server" "main" {
  name                         = "sql-${var.project}-${local.suffix}-001"
  resource_group_name          = azurerm_resource_group.main.name
  location                     = azurerm_resource_group.main.location
  version                      = "12.0"
  administrator_login          = var.sql_admin_login
  administrator_login_password = var.sql_admin_password
  minimum_tls_version          = "1.2"

  azuread_administrator {
    login_username = "AzureAD Admin"
    object_id      = data.azurerm_client_config.current.object_id
  }

  tags = local.common_tags
}

resource "azurerm_mssql_database" "main" {
  name      = "sqldb-${var.project}-${var.environment}-001"
  server_id = azurerm_mssql_server.main.id
  sku_name  = "Basic"
  tags      = local.common_tags
}

resource "azurerm_mssql_firewall_rule" "azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# ─── Key Vault ───────────────────────────────────────────────────────────────

resource "azurerm_key_vault" "main" {
  name                       = "kv-${var.project}-${var.environment}-001"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false

  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id

    secret_permissions = [
      "Get", "List", "Set", "Delete", "Purge", "Recover"
    ]
  }

  tags = local.common_tags
}

resource "azurerm_key_vault_secret" "doc_intelligence_key" {
  name         = "doc-intelligence-key"
  value        = var.doc_intelligence_key
  key_vault_id = azurerm_key_vault.main.id
}

resource "azurerm_key_vault_secret" "openai_api_key" {
  name         = "openai-api-key"
  value        = var.openai_api_key
  key_vault_id = azurerm_key_vault.main.id
}

resource "azurerm_key_vault_secret" "secret_key" {
  name         = "flask-secret-key"
  value        = var.secret_key
  key_vault_id = azurerm_key_vault.main.id
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  value        = var.database_url
  key_vault_id = azurerm_key_vault.main.id
}

resource "azurerm_key_vault_secret" "sql_admin_password" {
  name         = "sql-admin-password"
  value        = var.sql_admin_password
  key_vault_id = azurerm_key_vault.main.id
}

# ─── Document Intelligence ───────────────────────────────────────────────────

resource "azurerm_cognitive_account" "doc_intelligence" {
  name                = "docintel-${var.project}-${var.environment}-001"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  kind                = "FormRecognizer"
  sku_name            = "F0"
  tags                = local.common_tags
}

# ─── Azure OpenAI ────────────────────────────────────────────────────────────

resource "azurerm_cognitive_account" "openai" {
  name                = "oai-${var.project}-${local.suffix}-001"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  kind                = "OpenAI"
  sku_name            = "S0"
  tags                = local.common_tags
}

resource "azurerm_cognitive_deployment" "gpt4o" {
  name                 = var.openai_deployment_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = "gpt-4o"
    version = "2024-11-20"
  }

  scale {
    type     = "Standard"
    capacity = 10
  }
}

# ─── App Service Plan ────────────────────────────────────────────────────────

resource "azurerm_service_plan" "main" {
  name                = "asp-${var.project}-${local.suffix}-001"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  os_type             = "Linux"
  sku_name            = "F1"
  tags                = local.common_tags
}

# ─── App Service ─────────────────────────────────────────────────────────────

resource "azurerm_linux_web_app" "main" {
  name                = "app-${var.project}-${local.suffix}-001"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_stack {
      python_version = "3.11"
    }
  }

  app_settings = {
    "AZURE_STORAGE_CONTAINER"               = azurerm_storage_container.invoices.name
    "AZURE_DOC_INTELLIGENCE_ENDPOINT"       = azurerm_cognitive_account.doc_intelligence.endpoint
    "AZURE_OPENAI_ENDPOINT"                 = azurerm_cognitive_account.openai.endpoint
    "AZURE_OPENAI_DEPLOYMENT"               = var.openai_deployment_name
    "APPINSIGHTS_INSTRUMENTATIONKEY"        = azurerm_application_insights.main.instrumentation_key
    "APPLICATIONINSIGHTS_CONNECTION_STRING" = azurerm_application_insights.main.connection_string

    # Secrets pulled from Key Vault via references
    "AZURE_STORAGE_CONNECTION_STRING" = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=doc-intelligence-key)"
    "AZURE_DOC_INTELLIGENCE_KEY"      = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=doc-intelligence-key)"
    "AZURE_OPENAI_API_KEY"            = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=openai-api-key)"
    "SECRET_KEY"                      = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=flask-secret-key)"
    "DATABASE_URL"                    = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=database-url)"

    "SCM_DO_BUILD_DURING_DEPLOYMENT" = "true"
    "FLASK_ENV"                      = "production"
  }

  logs {
    application_logs {
      file_system_level = "Information"
    }
    http_logs {
      file_system {
        retention_in_days = 7
        retention_in_mb   = 35
      }
    }
  }

  tags = local.common_tags
}

# Grant App Service Managed Identity access to Key Vault
resource "azurerm_key_vault_access_policy" "app_service" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_linux_web_app.main.identity[0].principal_id

  secret_permissions = ["Get", "List"]
}

# Grant App Service Managed Identity access to Storage
resource "azurerm_role_assignment" "app_storage" {
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_linux_web_app.main.identity[0].principal_id
}

# ─── Azure Function (document processing) ────────────────────────────────────

resource "azurerm_storage_account" "function" {
  name                     = "st${var.project}func${var.environment}001"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
  tags                     = local.common_tags
}

resource "azurerm_linux_function_app" "main" {
  name                       = "func-${var.project}-${local.suffix}-001"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  service_plan_id            = azurerm_service_plan.main.id
  storage_account_name       = azurerm_storage_account.function.name
  storage_account_access_key = azurerm_storage_account.function.primary_access_key
  https_only                 = true

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_stack {
      python_version = "3.11"
    }
  }

  app_settings = {
    "AZURE_STORAGE_CONNECTION_STRING" = azurerm_storage_account.main.primary_connection_string
    "AZURE_STORAGE_CONTAINER"         = azurerm_storage_container.invoices.name
    "AZURE_DOC_INTELLIGENCE_ENDPOINT" = azurerm_cognitive_account.doc_intelligence.endpoint
    "AZURE_DOC_INTELLIGENCE_KEY"      = var.doc_intelligence_key
    "DATABASE_URL"                    = var.database_url
    "APPINSIGHTS_INSTRUMENTATIONKEY"  = azurerm_application_insights.main.instrumentation_key
    "FUNCTIONS_WORKER_RUNTIME"        = "python"
    "AzureWebJobsFeatureFlags"        = "EnableWorkerIndexing"
  }

  tags = local.common_tags
}

# ─── Event Grid — trigger Function on blob upload ────────────────────────────

resource "azurerm_eventgrid_system_topic" "storage" {
  name                   = "evgt-${var.project}-storage-${local.suffix}-001"
  location               = azurerm_resource_group.main.location
  resource_group_name    = azurerm_resource_group.main.name
  source_arm_resource_id = azurerm_storage_account.main.id
  topic_type             = "Microsoft.Storage.StorageAccounts"
  tags                   = local.common_tags
}

resource "azurerm_eventgrid_system_topic_event_subscription" "blob_created" {
  name                = "evgs-blob-created-${var.environment}"
  system_topic        = azurerm_eventgrid_system_topic.storage.name
  resource_group_name = azurerm_resource_group.main.name

  included_event_types = ["Microsoft.Storage.BlobCreated"]

  subject_filter {
    subject_begins_with = "/blobServices/default/containers/${azurerm_storage_container.invoices.name}/"
  }

  azure_function_endpoint {
    function_id = "${azurerm_linux_function_app.main.id}/functions/process_invoice"
  }
}
