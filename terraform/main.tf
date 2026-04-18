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
  location            = "eastus"
  resource_group_name = azurerm_resource_group.main.name
  kind                = "OpenAI"
  sku_name            = "S0"
  tags                = local.common_tags
}

# NOTE: azurerm_cognitive_deployment removed — free subscriptions have 0 GPT-4o quota.
# Create the gpt-4o deployment manually in Azure Portal once quota is approved:
# Azure OpenAI Studio → Deployments → Deploy model → gpt-4o

# ─── Virtual Network ─────────────────────────────────────────────────────────

resource "azurerm_virtual_network" "main" {
  name                = "vnet-${var.project}-${local.suffix}-001"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = ["10.0.0.0/16"]
  tags                = local.common_tags
}

# Subnet for private endpoints (SQL, Storage, Key Vault)
resource "azurerm_subnet" "private_endpoints" {
  name                 = "snet-pe-${local.suffix}"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.1.0/24"]

  private_endpoint_network_policies = "Disabled"
}

# Subnet for App Service VNet integration (outbound)
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

# ─── Private DNS Zones ────────────────────────────────────────────────────────

resource "azurerm_private_dns_zone" "sql" {
  name                = "privatelink.database.windows.net"
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone" "blob" {
  name                = "privatelink.blob.core.windows.net"
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone" "keyvault" {
  name                = "privatelink.vaultcore.azure.net"
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "sql" {
  name                  = "pdnslink-sql"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.sql.name
  virtual_network_id    = azurerm_virtual_network.main.id
  registration_enabled  = false
  tags                  = local.common_tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "blob" {
  name                  = "pdnslink-blob"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.blob.name
  virtual_network_id    = azurerm_virtual_network.main.id
  registration_enabled  = false
  tags                  = local.common_tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "keyvault" {
  name                  = "pdnslink-kv"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.keyvault.name
  virtual_network_id    = azurerm_virtual_network.main.id
  registration_enabled  = false
  tags                  = local.common_tags
}

# ─── Private Endpoints ────────────────────────────────────────────────────────

resource "azurerm_private_endpoint" "sql" {
  name                = "pe-sql-${local.suffix}-001"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = local.common_tags

  private_service_connection {
    name                           = "psc-sql"
    private_connection_resource_id = azurerm_mssql_server.main.id
    subresource_names              = ["sqlServer"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "sql-dns-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.sql.id]
  }
}

resource "azurerm_private_endpoint" "blob" {
  name                = "pe-blob-${local.suffix}-001"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = local.common_tags

  private_service_connection {
    name                           = "psc-blob"
    private_connection_resource_id = azurerm_storage_account.main.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "blob-dns-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.blob.id]
  }
}

resource "azurerm_private_endpoint" "keyvault" {
  name                = "pe-kv-${local.suffix}-001"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = local.common_tags

  private_service_connection {
    name                           = "psc-kv"
    private_connection_resource_id = azurerm_key_vault.main.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "kv-dns-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.keyvault.id]
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
  name                      = "app-${var.project}-${local.suffix}-001"
  location                  = azurerm_resource_group.main.location
  resource_group_name       = azurerm_resource_group.main.name
  service_plan_id           = azurerm_service_plan.main.id
  https_only                = true
  virtual_network_subnet_id = azurerm_subnet.app_service.id

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

    # Secrets pulled from Key Vault via references
    "AZURE_STORAGE_CONNECTION_STRING" = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=doc-intelligence-key)"
    "AZURE_DOC_INTELLIGENCE_KEY"      = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=doc-intelligence-key)"
    "AZURE_OPENAI_API_KEY"            = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=openai-api-key)"
    "SECRET_KEY"                      = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=flask-secret-key)"
    "DATABASE_URL"                    = "mssql+pyodbc://${var.sql_admin_login}:${var.sql_admin_password}@${azurerm_mssql_server.main.fully_qualified_domain_name}/${azurerm_mssql_database.main.name}?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"

    "SCM_DO_BUILD_DURING_DEPLOYMENT" = "true"
    "FLASK_ENV"                      = "production"
    "FLASK_APP"                      = "wsgi"
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
  virtual_network_subnet_id  = azurerm_subnet.app_service.id

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

# NOTE: Event Grid subscription removed from Terraform.
# The function endpoint must exist before the subscription can be validated.
# Create it manually after deploying the function code:
# Azure Portal → Event Grid System Topics → evgt-invoiceai-storage-* → Event Subscriptions → Add

# ─── East US VNet for OpenAI Private Endpoint ────────────────────────────────

resource "azurerm_virtual_network" "eastus" {
  name                = "vnet-${var.project}-prod-eastus-001"
  location            = "eastus"
  resource_group_name = azurerm_resource_group.main.name
  address_space       = ["10.1.0.0/16"]
  tags                = local.common_tags
}

resource "azurerm_subnet" "eastus_private_endpoints" {
  name                 = "snet-pe-prod-eastus"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.eastus.name
  address_prefixes     = ["10.1.1.0/24"]

  private_endpoint_network_policies = "Disabled"
}

# ─── VNet Peering: Central India ↔ East US ───────────────────────────────────

resource "azurerm_virtual_network_peering" "centralindia_to_eastus" {
  name                         = "peer-centralindia-to-eastus"
  resource_group_name          = azurerm_resource_group.main.name
  virtual_network_name         = azurerm_virtual_network.main.name
  remote_virtual_network_id    = azurerm_virtual_network.eastus.id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
}

resource "azurerm_virtual_network_peering" "eastus_to_centralindia" {
  name                         = "peer-eastus-to-centralindia"
  resource_group_name          = azurerm_resource_group.main.name
  virtual_network_name         = azurerm_virtual_network.eastus.name
  remote_virtual_network_id    = azurerm_virtual_network.main.id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
}

# ─── Private DNS Zones: OpenAI + Cognitive Services ──────────────────────────

resource "azurerm_private_dns_zone" "openai" {
  name                = "privatelink.openai.azure.com"
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone" "cognitiveservices" {
  name                = "privatelink.cognitiveservices.azure.com"
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

# Link OpenAI DNS zone to both VNets so both regions can resolve it
resource "azurerm_private_dns_zone_virtual_network_link" "openai_centralindia" {
  name                  = "pdnslink-openai-centralindia"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.openai.name
  virtual_network_id    = azurerm_virtual_network.main.id
  registration_enabled  = false
  tags                  = local.common_tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "openai_eastus" {
  name                  = "pdnslink-openai-eastus"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.openai.name
  virtual_network_id    = azurerm_virtual_network.eastus.id
  registration_enabled  = false
  tags                  = local.common_tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "cognitiveservices" {
  name                  = "pdnslink-cognitiveservices"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.cognitiveservices.name
  virtual_network_id    = azurerm_virtual_network.main.id
  registration_enabled  = false
  tags                  = local.common_tags
}

# ─── Private Endpoint: Azure OpenAI (East US) ────────────────────────────────

resource "azurerm_private_endpoint" "openai" {
  name                = "pe-oai-prod-eastus-001"
  location            = "eastus"
  resource_group_name = azurerm_resource_group.main.name
  subnet_id           = azurerm_subnet.eastus_private_endpoints.id
  tags                = local.common_tags

  private_service_connection {
    name                           = "psc-oai"
    private_connection_resource_id = azurerm_cognitive_account.openai.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "oai-dns-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.openai.id]
  }
}

# ─── Private Endpoint: Document Intelligence (Central India) ─────────────────

resource "azurerm_private_endpoint" "doc_intelligence" {
  name                = "pe-docintel-${local.suffix}-001"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = local.common_tags

  private_service_connection {
    name                           = "psc-docintel"
    private_connection_resource_id = azurerm_cognitive_account.doc_intelligence.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "docintel-dns-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.cognitiveservices.id]
  }
}
