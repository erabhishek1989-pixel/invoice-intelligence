import json
import logging
import os

from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.7


def process_invoice_document(blob_url: str) -> dict:
    """
    Call Azure Document Intelligence on the blob and return a dict ready
    to be written directly to the invoices + line_items tables.

    Returned keys match the DB column names:
      vendor_name, vendor_address, invoice_number, invoice_date, due_date,
      subtotal, tax_amount, total_amount, currency,
      line_items (list of dicts), raw_json (str)
    """
    endpoint = os.environ["AZURE_DOC_INTELLIGENCE_ENDPOINT"]
    key = os.environ["AZURE_DOC_INTELLIGENCE_KEY"]

    client = DocumentAnalysisClient(endpoint, AzureKeyCredential(key))
    poller = client.begin_analyze_document_from_url("prebuilt-invoice", blob_url)
    result = poller.result()

    extracted = {}

    for doc in result.documents:
        # ── Vendor ──────────────────────────────────────────────────────────
        extracted["vendor_name"] = _str_field(doc.fields.get("VendorName"))
        extracted["vendor_address"] = _address_field(doc.fields.get("VendorAddress"))

        # ── Reference numbers & dates ────────────────────────────────────────
        extracted["invoice_number"] = _str_field(doc.fields.get("InvoiceId"))
        extracted["invoice_date"] = _date_field(doc.fields.get("InvoiceDate"))
        extracted["due_date"] = _date_field(doc.fields.get("DueDate"))

        # ── Amounts — Document Intelligence returns CurrencyValue objects ────
        subtotal, _ = _currency_field(doc.fields.get("SubTotal"))
        tax_amount, _ = _currency_field(doc.fields.get("TotalTax"))
        total_amount, currency = _currency_field(doc.fields.get("InvoiceTotal"))

        extracted["subtotal"] = subtotal
        extracted["tax_amount"] = tax_amount
        extracted["total_amount"] = total_amount
        extracted["currency"] = currency or "INR"

        # ── Line items ───────────────────────────────────────────────────────
        items_field = doc.fields.get("Items")
        if items_field and items_field.confidence >= CONFIDENCE_THRESHOLD:
            extracted["line_items"] = _extract_line_items(items_field)
        else:
            extracted["line_items"] = []

        # Only process the first document in the result
        break

    extracted["raw_json"] = json.dumps(result.to_dict(), default=str)
    logger.info("Extracted fields: %s", [k for k, v in extracted.items() if v is not None])
    return extracted


# ── Field helpers ─────────────────────────────────────────────────────────────

def _str_field(field) -> str | None:
    if field is None:
        return None
    if field.confidence is not None and field.confidence < CONFIDENCE_THRESHOLD:
        logger.warning("Low confidence (%.2f) for string field — returning None", field.confidence)
        return None
    return str(field.value) if field.value is not None else None


def _address_field(field) -> str | None:
    """AddressValue → single string. Falls back to content string if needed."""
    if field is None:
        return None
    if field.confidence is not None and field.confidence < CONFIDENCE_THRESHOLD:
        return None
    v = field.value
    if v is None:
        return field.content  # raw OCR text
    # AddressValue has street_address, city, state, postal_code, country_region
    parts = [
        getattr(v, "street_address", None),
        getattr(v, "city", None),
        getattr(v, "state", None),
        getattr(v, "postal_code", None),
        getattr(v, "country_region", None),
    ]
    return ", ".join(p for p in parts if p) or field.content


def _date_field(field) -> object | None:
    """Returns a datetime.date or None."""
    if field is None:
        return None
    if field.confidence is not None and field.confidence < CONFIDENCE_THRESHOLD:
        return None
    return field.value  # already a datetime.date from the SDK


def _currency_field(field) -> tuple:
    """
    Returns (amount: float | None, symbol: str | None).
    Document Intelligence returns CurrencyValue(amount, symbol).
    """
    if field is None:
        return None, None
    if field.confidence is not None and field.confidence < CONFIDENCE_THRESHOLD:
        logger.warning("Low confidence (%.2f) for currency field — returning None", field.confidence)
        return None, None
    v = field.value
    if v is None:
        return None, None
    amount = getattr(v, "amount", None)
    symbol = getattr(v, "symbol", None) or getattr(v, "currency_symbol", None)
    return amount, symbol


def _extract_line_items(items_field) -> list[dict]:
    items = []
    for item in (items_field.value or []):
        f = item.value or {}
        amount, _ = _currency_field(f.get("Amount"))
        unit_price, _ = _currency_field(f.get("UnitPrice"))
        qty = f.get("Quantity")
        items.append({
            "description": _str_field(f.get("Description")),
            "quantity":    qty.value if qty else None,
            "unit_price":  unit_price,
            "line_total":  amount,
        })
    return items
