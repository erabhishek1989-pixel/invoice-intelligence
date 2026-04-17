import os
import json
import logging
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential

logger = logging.getLogger(__name__)

FIELD_MAPPING = {
    "VendorName":    "vendor_name",
    "VendorAddress": "vendor_address",
    "InvoiceId":     "invoice_number",
    "InvoiceDate":   "invoice_date",
    "DueDate":       "due_date",
    "SubTotal":      "subtotal",
    "TotalTax":      "tax_amount",
    "InvoiceTotal":  "total_amount",
    "Items":         "line_items",
}

CONFIDENCE_THRESHOLD = 0.7


def process_invoice_document(blob_url: str, document_id: str | None) -> dict:
    endpoint = os.environ["AZURE_DOC_INTELLIGENCE_ENDPOINT"]
    key = os.environ["AZURE_DOC_INTELLIGENCE_KEY"]

    try:
        client = DocumentAnalysisClient(endpoint, AzureKeyCredential(key))
        poller = client.begin_analyze_document_from_url("prebuilt-invoice", blob_url)
        result = poller.result()
    except Exception as exc:
        logger.error("Document Intelligence failed for %s: %s", blob_url, exc)
        raise

    extracted = {}
    for doc in result.documents:
        for api_field, db_field in FIELD_MAPPING.items():
            field = doc.fields.get(api_field)
            if field is None:
                continue
            if field.confidence is not None and field.confidence < CONFIDENCE_THRESHOLD:
                logger.warning("Low confidence (%.2f) for field %s", field.confidence, api_field)
                extracted[db_field] = None
                continue

            if api_field == "Items":
                extracted[db_field] = _extract_line_items(field)
            else:
                extracted[db_field] = field.value

    extracted["raw_json"] = json.dumps(result.to_dict(), default=str)
    logger.info("Extracted fields for document %s: %s", document_id, list(extracted.keys()))
    return extracted


def _extract_line_items(items_field) -> list[dict]:
    items = []
    for item in (items_field.value or []):
        f = item.value or {}
        items.append({
            "description": _val(f.get("Description")),
            "quantity":    _val(f.get("Quantity")),
            "unit_price":  _val(f.get("UnitPrice")),
            "line_total":  _val(f.get("Amount")),
        })
    return items


def _val(field):
    return field.value if field else None
