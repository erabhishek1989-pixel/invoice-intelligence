import json
import re
from flask import current_app
from openai import AzureOpenAI

_SYSTEM_PROMPT = """You are a financial assistant for a small business.
You have access to an invoice database with these tables:

TABLE invoices:
  id, vendor_name, invoice_number, invoice_date, due_date,
  subtotal, tax_amount, total_amount, currency, payment_status,
  doc_type (purchase = I paid them, sale = they paid me)

TABLE line_items:
  id, invoice_id, description, quantity, unit_price, line_total

Rules:
1. Return ONLY a raw SQL SELECT query — no markdown, no backticks, no explanation.
2. For "last month": WHERE invoice_date >= DATEADD(month,-1,GETDATE())
3. For "this month": WHERE MONTH(invoice_date) = MONTH(GETDATE())
4. For vendor search: WHERE vendor_name LIKE '%search_term%'
5. Always use SUM() for totals, COUNT() for counts.
6. Always include currency in SELECT when showing amounts.
7. SELECT only — never DELETE, UPDATE, INSERT, DROP.
8. If the question cannot be answered from this data: return exactly CANNOT_ANSWER"""


def _get_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=current_app.config["AZURE_OPENAI_ENDPOINT"],
        api_key=current_app.config["AZURE_OPENAI_API_KEY"],
        api_version="2024-02-01",
    )


def _clean_sql(raw: str) -> str:
    """Strip markdown code fences GPT-4o sometimes adds despite instructions."""
    raw = raw.strip()
    # Remove ```sql ... ``` or ``` ... ```
    raw = re.sub(r"^```(?:sql)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def generate_sql(question: str) -> str:
    client = _get_client()
    deployment = current_app.config["AZURE_OPENAI_DEPLOYMENT"]

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": question},
        ],
        temperature=0,
        max_tokens=400,
    )
    raw = response.choices[0].message.content.strip()
    return _clean_sql(raw)


def generate_answer(question: str, results: list[dict]) -> str:
    client = _get_client()
    deployment = current_app.config["AZURE_OPENAI_DEPLOYMENT"]

    prompt = (
        f"Data: {json.dumps(results, default=str)}\n"
        f"Answer this in one clear sentence: {question}\n"
        "Format amounts with currency symbol. Be concise. No markdown."
    )

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": "You are a concise financial assistant."},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.3,
        max_tokens=150,
    )
    return response.choices[0].message.content.strip()
