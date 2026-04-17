# Invoice Intelligence
## Claude Code Project Instructions

---

## What This Project Is
A web application where a small team (2-5 users) uploads invoices, receipts,
and bills (PDF, JPG, PNG, mix of English and Hindi). Azure Document Intelligence
extracts structured data from every document. Users then query their financial
data by typing or speaking — "how much did I spend with Sharma Traders last
month", "what is total sales this week", "which invoices are unpaid" — and
get an instant spoken and text response powered by GPT-4o.

Volume: 100-1000 documents/month
Languages: English and Hindi mixed
Formats: PDF scans, digital PDFs, phone photos (JPG/PNG)
Users: 2-5 people, simple username/password login

---

## Architecture — Read This First

### The core flow has two separate pipelines:

UPLOAD PIPELINE (async — happens in background):
User uploads file
  → Flask saves to Azure Blob Storage
  → Event Grid fires on blob creation
  → Azure Function picks it up
  → Calls Document Intelligence API
  → Extracts: vendor, amount, date, line items, currency, doc type
  → Saves structured rows to Azure SQL
  → Updates document status to "processed"

QUERY PIPELINE (real-time — happens when user asks a question):
User speaks or types a question
  → Browser Speech API converts voice to text (free, no Azure cost)
  → Flask sends text to GPT-4o with the database schema as context
  → GPT-4o returns a SQL query
  → Flask runs the SQL against Azure SQL
  → Flask sends results back to GPT-4o for a natural language answer
  → Response spoken back via browser SpeechSynthesis API

### Why Text-to-SQL not RAG:
Invoice data is structured (vendor, amount, date, line items).
SQL gives exact numeric answers — "£12,450 total sales last month".
RAG is for unstructured document content — not needed here.
GPT-4o is excellent at generating SQL from natural language.

---

## Tech Stack — Do Not Change These Choices

### Backend
- Python 3.11
- Flask (web framework)
- SQLAlchemy + Flask-Migrate (ORM and migrations)
- Flask-Login (session management, simple username/password)
- Gunicorn (production WSGI server)
- azure-functions (processing pipeline only)

### Frontend
- Bootstrap 5 (CSS framework)
- Vanilla JavaScript (no frameworks)
- Jinja2 (templating)
- Browser Web Speech API — SpeechRecognition (voice input, free)
- Browser SpeechSynthesis API (voice output, free)
- No React, no Vue, no Node

### Azure Services
- Azure App Service (Linux, Python 3.11) — Flask web app
- Azure Blob Storage — raw invoice file storage
- Azure Event Grid — triggers function on blob upload
- Azure Functions (Python) — document processing orchestrator
- Azure Document Intelligence (FormRecognizer) — extract invoice fields
- Azure OpenAI (GPT-4o) — natural language to SQL + answer formatting
- Azure SQL Database (Basic tier) — structured invoice data
- Azure Key Vault — all secrets and API keys
- Azure Application Insights — monitoring and logging
- Managed Identity — no passwords between Azure services

### Infrastructure as Code
- Terraform only — never ARM templates, never Azure Portal
- Provider: azurerm ~> 3.110
- Backend: Azure Blob Storage
- Always use_oidc = true in provider
- All resources tagged: environment, project, owner, managed-by

### CI/CD
- GitHub Actions only
- Two workflows:
  1. terraform-deploy.yml — infra (validate → plan → apply with approval gate)
  2. app-deploy.yml — Flask app (test → deploy to App Service)
- OIDC auth to Azure — never client secrets in pipelines
- Manual approval gate via GitHub Environment "production"
- Runs on ubuntu-latest

---

## Project Structure
```
invoice-intelligence/
├── .github/
│   └── workflows/
│       ├── terraform-deploy.yml
│       └── app-deploy.yml
├── app/
│   ├── __init__.py             # Flask app factory
│   ├── config.py               # Config from env vars only
│   ├── models.py               # SQLAlchemy models
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py             # Login/logout (username+password)
│   │   ├── dashboard.py        # Document list, upload, status
│   │   └── chat.py             # Query endpoint (text + voice)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── blob_service.py     # Upload to Azure Blob Storage
│   │   ├── sql_service.py      # Query execution
│   │   └── gpt_service.py      # GPT-4o text-to-SQL + answer
│   ├── templates/
│   │   ├── base.html           # Master layout
│   │   ├── login.html          # Login page
│   │   ├── dashboard.html      # Document list + upload
│   │   └── chat.html           # Chat + voice interface
│   └── static/
│       ├── css/
│       │   └── style.css
│       └── js/
│           └── voice.js        # Browser Speech API logic
├── function_app/
│   ├── __init__.py             # Azure Function entry point
│   ├── processor.py            # Document Intelligence caller
│   └── requirements.txt        # Function dependencies only
├── terraform/
│   ├── main.tf                 # All Azure resources
│   ├── variables.tf
│   ├── outputs.tf
│   └── backend.tf
├── app.py                      # Flask entry point
├── requirements.txt            # App dependencies
├── .env                        # Local dev — never commit
├── .gitignore
└── CLAUDE.md                   # This file
```

---

## Database Schema

### documents table — one row per uploaded file
```sql
id              INT PRIMARY KEY AUTOINCREMENT
filename        VARCHAR(255)    -- original filename
blob_url        VARCHAR(500)    -- Azure Blob Storage URL
status          VARCHAR(20)     -- pending, processing, processed, failed
doc_type        VARCHAR(50)     -- invoice, receipt, bill
uploaded_by     INT FK users.id
uploaded_at     DATETIME
processed_at    DATETIME NULL
error_message   TEXT NULL
```

### invoices table — extracted structured data
```sql
id              INT PRIMARY KEY AUTOINCREMENT
document_id     INT FK documents.id
vendor_name     VARCHAR(200)    -- extracted vendor/supplier name
vendor_address  TEXT NULL
invoice_number  VARCHAR(100)    -- invoice/receipt reference number
invoice_date    DATE            -- date on the document
due_date        DATE NULL       -- payment due date if present
subtotal        DECIMAL(12,2)   -- amount before tax
tax_amount      DECIMAL(12,2)   -- GST/VAT amount
total_amount    DECIMAL(12,2)   -- total amount
currency        VARCHAR(10)     -- INR, GBP, USD etc
payment_status  VARCHAR(20)     -- paid, unpaid, partial
doc_type        VARCHAR(20)     -- purchase (I paid), sale (I received payment)
notes           TEXT NULL       -- any extra info extracted
raw_json        TEXT            -- full Document Intelligence response JSON
created_at      DATETIME
```

### line_items table — individual line items per invoice
```sql
id              INT PRIMARY KEY AUTOINCREMENT
invoice_id      INT FK invoices.id
description     VARCHAR(500)
quantity        DECIMAL(10,2) NULL
unit_price      DECIMAL(12,2) NULL
line_total      DECIMAL(12,2)
```

### users table — simple auth, no Entra ID
```sql
id              INT PRIMARY KEY AUTOINCREMENT
username        VARCHAR(50) UNIQUE
password_hash   VARCHAR(200)    -- werkzeug generate_password_hash
email           VARCHAR(120)    -- optional
role            VARCHAR(20)     -- admin, user
created_at      DATETIME
```

### query_log table — every question asked
```sql
id              INT PRIMARY KEY AUTOINCREMENT
user_id         INT FK users.id
question        TEXT            -- original natural language question
sql_generated   TEXT            -- SQL generated by GPT-4o
answer          TEXT            -- GPT-4o natural language answer
was_voice       BOOLEAN         -- was this a voice query
created_at      DATETIME
```

---

## Environment Variables
All config from environment variables. Never hardcode.

```
# Azure
AZURE_STORAGE_CONNECTION_STRING  = storage account connection string
AZURE_STORAGE_CONTAINER          = invoices
AZURE_DOC_INTELLIGENCE_ENDPOINT  = https://xxx.cognitiveservices.azure.com/
AZURE_DOC_INTELLIGENCE_KEY       = key (use Key Vault in prod)
AZURE_OPENAI_ENDPOINT            = https://xxx.openai.azure.com/
AZURE_OPENAI_API_KEY             = key (use Key Vault in prod)
AZURE_OPENAI_DEPLOYMENT          = gpt-4o

# Database
DATABASE_URL                     = mssql+pyodbc://...  (Azure SQL)
                                   sqlite:///invoice.db (local dev)

# App
SECRET_KEY                       = random string
FLASK_ENV                        = development / production
```

---

## GitHub Secrets Required
```
AZURE_CLIENT_ID
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
AZURE_DOC_INTELLIGENCE_KEY
AZURE_OPENAI_API_KEY
SECRET_KEY
DATABASE_URL
```

---

## Azure Resources — Naming Convention
```
rg-invoiceai-prod-westus-001        resource group
app-invoiceai-prod-westus-001       app service
asp-invoiceai-prod-westus-001       app service plan
stinvoiceaiprod001                   storage account (no hyphens, max 24 chars)
func-invoiceai-prod-westus-001      azure function
docintel-invoiceai-prod-001          document intelligence
oai-invoiceai-prod-westus-001       azure openai
sql-invoiceai-prod-westus-001       sql server
sqldb-invoiceai-prod-001             sql database
kv-invoiceai-prod-westus-001        key vault
ai-invoiceai-prod-westus-001        application insights
```

---

## Terraform Backend
Create this ONCE manually before first pipeline run:
```bash
az group create --name rg-terraform-state-invoiceai --location westus
az storage account create --name stinvoiceaitfstate --resource-group rg-terraform-state-invoiceai --sku Standard_LRS --location westus
az storage container create --name tfstate --account-name stinvoiceaitfstate
```

Backend config in backend.tf:
```hcl
backend "azurerm" {
  resource_group_name  = "rg-terraform-state-invoiceai"
  storage_account_name = "stinvoiceaitfstate"
  container_name       = "tfstate"
  key                  = "invoiceai-prod.tfstate"
}
```

---

## Document Intelligence — Fields to Extract
Use prebuilt-invoice model. Map API response to database:
```python
field_mapping = {
    "VendorName":    "vendor_name",
    "VendorAddress": "vendor_address",
    "InvoiceId":     "invoice_number",
    "InvoiceDate":   "invoice_date",
    "DueDate":       "due_date",
    "SubTotal":      "subtotal",
    "TotalTax":      "tax_amount",
    "InvoiceTotal":  "total_amount",
    "Items":         "line_items"
}
```

Hindi/bilingual handling:
- Document Intelligence handles Hindi OCR automatically
- Store vendor names in Hindi as-is (UTF-8)
- Amounts always extracted as numbers regardless of language
- If confidence < 0.7 flag for manual review, store NULL

---

## GPT-4o Text-to-SQL System Prompt
Send this with every query request:

```
You are a financial assistant for a small business.
You have access to an invoice database.

TABLE invoices:
  id, vendor_name, invoice_number, invoice_date, due_date,
  subtotal, tax_amount, total_amount, currency, payment_status,
  doc_type (purchase=I paid them, sale=they paid me)

TABLE line_items:
  id, invoice_id, description, quantity, unit_price, line_total

Rules:
1. Return ONLY a valid SQL SELECT query. No explanation.
2. For "last month": WHERE invoice_date >= DATEADD(month,-1,GETDATE())
3. For "this month": WHERE MONTH(invoice_date) = MONTH(GETDATE())
4. For vendor search: WHERE vendor_name LIKE '%search_term%'
5. Always use SUM() for totals, COUNT() for counts.
6. Always include currency in SELECT when showing amounts.
7. SELECT only — never DELETE, UPDATE, INSERT, DROP.
8. If the question cannot be answered: return CANNOT_ANSWER

Question: {user_question}
```

After SQL results come back, second GPT-4o call:
```
Data: {sql_results}
Answer this in one clear sentence: {user_question}
Format amounts with currency symbol. Be concise.
```

---

## Voice Interface — Browser APIs (Zero Cost)

Voice INPUT in voice.js:
```javascript
const recognition = new webkitSpeechRecognition();
recognition.lang = 'en-IN';
recognition.continuous = false;
recognition.onresult = (e) => {
    const text = e.results[0][0].transcript;
    sendQuery(text);
};
```

Voice OUTPUT in voice.js:
```javascript
function speak(text) {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-IN';
    utterance.rate = 0.9;
    window.speechSynthesis.speak(utterance);
}
```

Note: Works in Chrome and Edge only. Tell users to use Chrome.

---

## Example Queries to Test
1. "How much total sales last month?"
2. "What is the pending amount from Sharma Traders?"
3. "How many invoices did I receive this week?"
4. "Show me all unpaid invoices over 10000 rupees"
5. "What did I spend on raw materials last quarter?"

All five must work before Phase 6.

---

## Build Order — Follow This Exactly

Phase 1 — Terraform infrastructure
  Create all Azure resources. Verify in portal. Push to trigger CI/CD.

Phase 2 — Database models and migrations
  SQLAlchemy models. Test locally with SQLite.

Phase 3 — Upload and processing pipeline
  Flask upload route → Blob Storage → Event Grid → Function → Doc Intelligence → SQL

Phase 4 — Chat interface
  GPT-4o text-to-SQL. Test all 5 example queries.

Phase 5 — Voice interface
  voice.js. Test in Chrome.

Phase 6 — GitHub Actions CI/CD
  terraform-deploy.yml and app-deploy.yml. Manual approval gate.

---

## Estimated Monthly Azure Cost
```
App Service B1           £12
Azure SQL Basic           £4
Document Intelligence     £0  (free 500 pages/month)
Azure OpenAI GPT-4o      £10  (estimate, depends on usage)
Azure Functions           £0  (consumption, 1M free)
Storage                   £1
Key Vault                 £0
App Insights              £0
─────────────────────────────
Total estimated          ~£27/month
```

---

## Coding Standards
- All errors caught with try/except — never crash on Azure SDK errors
- All routes use @login_required
- Never put Azure SDK calls in routes — always use services layer
- Config always from os.environ — never hardcoded
- All amounts stored as DECIMAL(12,2) — never float
- Validate file extension before upload: pdf, jpg, jpeg, png only
- Max file size: 10MB
- Always validate GPT-4o SQL is SELECT-only before executing

## My Preferences
- Explain what you are doing before writing code
- Tell me if I need to run any manual Azure CLI commands
- Never skip Terraform plan step
- Keep code simple — I am learning while building
- When in doubt, ask me
