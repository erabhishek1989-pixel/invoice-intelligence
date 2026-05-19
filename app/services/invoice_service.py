"""
Synchronous invoice processing — called directly from the upload route.
Ported from the former Azure Function processor.
"""
import json
import logging
import os

from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from flask import current_app

from app import db
from app.models import Document, Invoice, LineItem

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.7


def process_document(doc: Document) -> Invoice:
    """
    Run Document Intelligence on the blob, save results to DB.
    Updates doc.status and returns the saved Invoice.
    Raises on failure (caller should catch and mark doc as failed).
    """
    endpoint = current_app.config["AZURE_DOC_INTELLIGENCE_ENDPOINT"]
    key = current_app.config["AZURE_DOC_INTELLIGENCE_KEY"]

    if not endpoint or not key:
        raise RuntimeError("Document Intelligence not configured — set AZURE_DOC_INTELLIGENCE_ENDPOINT and KEY")

    doc.status = "processing"
    db.session.commit()

    client = DocumentAnalysisClient(endpoint, AzureKeyCredential(key))
    poller = client.begin_analyze_document_from_url("prebuilt-invoice", doc.blob_url)
    result = poller.result()

    extracted = _extract_fields(result)

    invoice = Invoice(
        document_id=doc.id,
        vendor_name=extracted.get("vendor_name"),
        vendor_address=extracted.get("vendor_address"),
        invoice_number=extracted.get("invoice_number"),
        invoice_date=extracted.get("invoice_date"),
        due_date=extracted.get("due_date"),
        subtotal=extracted.get("subtotal"),
        tax_amount=extracted.get("tax_amount"),
        total_amount=extracted.get("total_amount"),
        currency=extracted.get("currency", "INR"),
        payment_status="unpaid",
        raw_json=extracted.get("raw_json"),
    )
    db.session.add(invoice)
    db.session.flush()  # get invoice.id

    for item in extracted.get("line_items", []):
        db.session.add(LineItem(
            invoice_id=invoice.id,
            description=item.get("description"),
            quantity=item.get("quantity"),
            unit_price=item.get("unit_price"),
            line_total=item.get("line_total"),
        ))

    from datetime import datetime
    doc.status = "processed"
    doc.processed_at = datetime.utcnow()
    db.session.commit()

    logger.info("Processed document %d → invoice %d", doc.id, invoice.id)
    return invoice


# ── Field extraction ──────────────────────────────────────────────────────────

def _extract_fields(result) -> dict:
    out = {}
    for doc in result.documents:
        out["vendor_name"]    = _str_field(doc.fields.get("VendorName"))
        out["vendor_address"] = _address_field(doc.fields.get("VendorAddress"))
        out["invoice_number"] = _str_field(doc.fields.get("InvoiceId"))
        out["invoice_date"]   = _date_field(doc.fields.get("InvoiceDate"))
        out["due_date"]       = _date_field(doc.fields.get("DueDate"))

        subtotal,      _        = _currency_field(doc.fields.get("SubTotal"))
        tax_amount,    _        = _currency_field(doc.fields.get("TotalTax"))
        total_amount,  currency = _currency_field(doc.fields.get("InvoiceTotal"))

        out["subtotal"]      = subtotal
        out["tax_amount"]    = tax_amount
        out["total_amount"]  = total_amount
        out["currency"]      = currency or "INR"

        items_field = doc.fields.get("Items")
        if items_field and items_field.confidence >= CONFIDENCE_THRESHOLD:
            out["line_items"] = _extract_line_items(items_field)
        else:
            out["line_items"] = []
        break  # first document only

    out["raw_json"] = json.dumps(result.to_dict(), default=str)
    return out


def _str_field(field):
    if field is None:
        return None
    if field.confidence is not None and field.confidence < CONFIDENCE_THRESHOLD:
        return None
    return str(field.value) if field.value is not None else None


def _address_field(field):
    if field is None:
        return None
    if field.confidence is not None and field.confidence < CONFIDENCE_THRESHOLD:
        return None
    v = field.value
    if v is None:
        return field.content
    parts = [
        getattr(v, "street_address", None),
        getattr(v, "city", None),
        getattr(v, "state", None),
        getattr(v, "postal_code", None),
        getattr(v, "country_region", None),
    ]
    return ", ".join(p for p in parts if p) or field.content


def _date_field(field):
    if field is None:
        return None
    if field.confidence is not None and field.confidence < CONFIDENCE_THRESHOLD:
        return None
    return field.value


def _currency_field(field):
    if field is None:
        return None, None
    if field.confidence is not None and field.confidence < CONFIDENCE_THRESHOLD:
        return None, None
    v = field.value
    if v is None:
        return None, None
    amount = getattr(v, "amount", None)
    symbol = getattr(v, "symbol", None) or getattr(v, "currency_symbol", None)
    return amount, symbol


def _extract_line_items(items_field) -> list:
    items = []
    for item in (items_field.value or []):
        f = item.value or {}
        amount,     _ = _currency_field(f.get("Amount"))
        unit_price, _ = _currency_field(f.get("UnitPrice"))
        qty = f.get("Quantity")
        items.append({
            "description": _str_field(f.get("Description")),
            "quantity":    qty.value if qty else None,
            "unit_price":  unit_price,
            "line_total":  amount,
        })
    return items
