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
    cognitive_account {
      purge_soft_delete_on_destroy = true
    }
  }
}

# ─── Data sources ────────────────────────────────────────────────────────────

data "azurerm_client_config" "current" {}

# ─── Random secrets (generated once, stored in Terraform state) ──────────────

resource "random_password" "secret_key" {
  length  = 64
  special = false
}

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

# Allow Azure datacenter IPs to reach SQL (covers App Service + Function App outbound IPs)
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
  value        = azurerm_cognitive_account.doc_intelligence.primary_access_key
  key_vault_id = azurerm_key_vault.main.id
}

resource "azurerm_key_vault_secret" "openai_api_key" {
  name         = "openai-api-key"
  value        = azurerm_cognitive_account.openai.primary_access_key
  key_vault_id = azurerm_key_vault.main.id
}

resource "azurerm_key_vault_secret" "secret_key" {
  name         = "flask-secret-key"
  value        = random_password.secret_key.result
  key_vault_id = azurerm_key_vault.main.id
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  value        = "mssql+pyodbc://${var.sql_admin_login}:${var.sql_admin_password}@${azurerm_mssql_server.main.fully_qualified_domain_name}/${azurerm_mssql_database.main.name}?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"
  key_vault_id = azurerm_key_vault.main.id
}

resource "azurerm_key_vault_secret" "sql_admin_password" {
  name         = "sql-admin-password"
  value        = var.sql_admin_password
  key_vault_id = azurerm_key_vault.main.id
}

# ─── Document Intelligence ───────────────────────────────────────────────────

resource "azurerm_cognitive_account" "doc_intelligence" {
  name                  = "docintel-${var.project}-${var.environment}-001"
  location              = azurerm_resource_group.main.location
  resource_group_name   = azurerm_resource_group.main.name
  kind                  = "FormRecognizer"
  sku_name              = "F0"
  custom_subdomain_name = "docintel-${var.project}-${var.environment}-001"
  tags                  = local.common_tags
}

# ─── Azure OpenAI ────────────────────────────────────────────────────────────

resource "azurerm_cognitive_account" "openai" {
  name                  = "oai-${var.project}-${local.suffix}-001"
  location              = "eastus"
  resource_group_name   = azurerm_resource_group.main.name
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = "oai-${var.project}-${local.suffix}-001"
  tags                  = local.common_tags
}

# NOTE: azurerm_cognitive_deployment removed — free subscriptions have 0 GPT-4o quota.
# Create the gpt-4o deployment manually in Azure Portal once quota is approved:
# Azure OpenAI Studio → Deployments → Deploy model → gpt-4o

# ─── Virtual Network ─────────────────────────────────────────────────────────
# Kept to avoid deletion-ordering issues (subnet has an App Service association
# link that Azure removes asynchronously after VNet integration is detached).
# The apps no longer use VNet integration — these resources are idle and harmless.

resource "azurerm_virtual_network" "main" {
  name                = "vnet-${var.project}-${local.suffix}-001"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = ["10.0.0.0/16"]
  tags                = local.common_tags
}

resource "azurerm_subnet" "app_service" {
  name                 = "snet-app-${local.suffix}"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.2.0/24"]

  delegation {
    name = "app-service"
    service_delegation {
      name    = "Microsoft.Web/serverFarms"
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
    }
  }
}

# ─── App Service Plan ────────────────────────────────────────────────────────

resource "azurerm_service_plan" "main" {
  name                = "asp-${var.project}-${local.suffix}-001"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  os_type             = "Linux"
  sku_name            = "B1"
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
    app_command_line = "gunicorn --bind=0.0.0.0:8000 --workers=2 --timeout=60 wsgi:app"
  }

  app_settings = {
    "AZURE_STORAGE_CONTAINER"               = azurerm_storage_container.invoices.name
    "AZURE_DOC_INTELLIGENCE_ENDPOINT"       = azurerm_cognitive_account.doc_intelligence.endpoint
    "AZURE_OPENAI_ENDPOINT"                 = azurerm_cognitive_account.openai.endpoint
    "AZURE_OPENAI_DEPLOYMENT"               = var.openai_deployment_name
    "APPINSIGHTS_INSTRUMENTATIONKEY"        = azurerm_application_insights.main.instrumentation_key
    "APPLICATIONINSIGHTS_CONNECTION_STRING" = azurerm_application_insights.main.connection_string

    "AZURE_STORAGE_CONNECTION_STRING" = azurerm_storage_account.main.primary_connection_string
    "AZURE_DOC_INTELLIGENCE_KEY"      = azurerm_cognitive_account.doc_intelligence.primary_access_key
    "AZURE_OPENAI_API_KEY"            = azurerm_cognitive_account.openai.primary_access_key
    "SECRET_KEY"                      = random_password.secret_key.result
    "DATABASE_URL"                    = "mssql+pyodbc://${var.sql_admin_login}:${var.sql_admin_password}@${azurerm_mssql_server.main.fully_qualified_domain_name}/${azurerm_mssql_database.main.name}?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"

    "SCM_DO_BUILD_DURING_DEPLOYMENT" = "true"
    "FLASK_ENV"                      = "production"
    "FLASK_APP"                      = "wsgi"

    # Auto-create admin user on first startup (see app/__init__.py)
    "ADMIN_USERNAME" = var.admin_username
    "ADMIN_PASSWORD" = var.admin_password
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
    "AZURE_DOC_INTELLIGENCE_KEY"      = azurerm_cognitive_account.doc_intelligence.primary_access_key
    "DATABASE_URL"                    = "mssql+pyodbc://${var.sql_admin_login}:${var.sql_admin_password}@${azurerm_mssql_server.main.fully_qualified_domain_name}/${azurerm_mssql_database.main.name}?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"
    "APPINSIGHTS_INSTRUMENTATIONKEY"  = azurerm_application_insights.main.instrumentation_key
    "FUNCTIONS_WORKER_RUNTIME"        = "python"
    "AzureWebJobsFeatureFlags"        = "EnableWorkerIndexing"
    "FUNCTIONS_EXTENSION_VERSION"     = "~4"
    "WEBSITE_RUN_FROM_PACKAGE"        = "0"
  }

  tags = local.common_tags
}

# ─── Event Grid — trigger Function on blob upload (via Storage Queue) ────────
#
# Architecture: Blob upload → Event Grid → Storage Queue → Azure Function
# Using a Queue endpoint avoids the webhook validation handshake entirely.
# Event Grid writes the blob event JSON to the queue; the Function reads it.

resource "azurerm_storage_queue" "invoice_processing" {
  name                 = "invoice-processing"
  storage_account_name = azurerm_storage_account.main.name
}

resource "azurerm_eventgrid_system_topic" "storage" {
  name                   = "evgt-${var.project}-storage-${local.suffix}-001"
  location               = azurerm_resource_group.main.location
  resource_group_name    = azurerm_resource_group.main.name
  source_arm_resource_id = azurerm_storage_account.main.id
  topic_type             = "Microsoft.Storage.StorageAccounts"
  tags                   = local.common_tags
}

resource "azurerm_eventgrid_system_topic_event_subscription" "blob_trigger" {
  name                = "invoice-blob-trigger"
  system_topic        = azurerm_eventgrid_system_topic.storage.name
  resource_group_name = azurerm_resource_group.main.name

  storage_queue_endpoint {
    storage_account_id = azurerm_storage_account.main.id
    queue_name         = azurerm_storage_queue.invoice_processing.name
    # Messages expire after 7 days if not consumed
    queue_message_time_to_live_in_seconds = 604800
  }

  included_event_types = ["Microsoft.Storage.BlobCreated"]

  subject_filter {
    subject_begins_with = "/blobServices/default/containers/invoices/"
  }

  depends_on = [azurerm_storage_queue.invoice_processing]
}
