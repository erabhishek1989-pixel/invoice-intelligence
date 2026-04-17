terraform {
  backend "azurerm" {
    resource_group_name  = "rg-terraform-state-invoiceai"
    storage_account_name = "stinvoiceaitfstate"
    container_name       = "tfstate"
    key                  = "invoiceai-prod.tfstate"
  }
}
