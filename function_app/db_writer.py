"""
Database writer for the Azure Function processor.

Uses SQLAlchemy Core (no Flask, no ORM) so the function stays
independent of the web app. Each public function opens and closes
its own connection — safe for the Azure Functions execution model.
"""
import logging
import os
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)


def _engine():
    """Create a fresh engine. NullPool avoids connection leaks between invocations."""
    url = os.environ["DATABASE_URL"]
    return create_engine(url, poolclass=NullPool)


@contextmanager
def _session():
    engine = _engine()
    conn = engine.connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        engine.dispose()


# ── Public API ────────────────────────────────────────────────────────────────

def find_document_id_by_blob_url(blob_url: str) -> int | None:
    """Return the documents.id for a given blob URL, or None if not found."""
    with _session() as conn:
        row = conn.execute(
            text("SELECT id FROM documents WHERE blob_url = :url"),
            {"url": blob_url},
        ).fetchone()
    return row[0] if row else None


def set_document_status(doc_id: int, status: str, error_message: str = None) -> None:
    """Update document status. For 'processed' also stamps processed_at."""
    with _session() as conn:
        if status == "processed":
            conn.execute(
                text(
                    "UPDATE documents "
                    "SET status = :status, processed_at = :now "
                    "WHERE id = :id"
                ),
                {"status": status, "now": datetime.utcnow(), "id": doc_id},
            )
        elif status == "failed":
            conn.execute(
                text(
                    "UPDATE documents "
                    "SET status = :status, error_message = :err "
                    "WHERE id = :id"
                ),
                {"status": status, "err": (error_message or "")[:500], "id": doc_id},
            )
        else:
            conn.execute(
                text("UPDATE documents SET status = :status WHERE id = :id"),
                {"status": status, "id": doc_id},
            )


def save_invoice(doc_id: int, extracted: dict) -> int:
    """
    Insert one row into invoices and zero-or-more rows into line_items.
    Returns the new invoice id.
    """
    line_items = extracted.get("line_items") or []
    raw_json = extracted.get("raw_json")

    # Normalise date values (Document Intelligence returns datetime.date)
    invoice_date = _as_date(extracted.get("invoice_date"))
    due_date = _as_date(extracted.get("due_date"))

    with _session() as conn:
        # Azure SQL uses OUTPUT INSERTED.id to return the new PK
        row = conn.execute(
            text(
                """
                INSERT INTO invoices (
                    document_id, vendor_name, vendor_address, invoice_number,
                    invoice_date, due_date, subtotal, tax_amount, total_amount,
                    currency, payment_status, doc_type, raw_json, created_at
                )
                OUTPUT INSERTED.id
                VALUES (
                    :document_id, :vendor_name, :vendor_address, :invoice_number,
                    :invoice_date, :due_date, :subtotal, :tax_amount, :total_amount,
                    :currency, :payment_status, :doc_type, :raw_json, :created_at
                )
                """
            ),
            {
                "document_id":    doc_id,
                "vendor_name":    extracted.get("vendor_name"),
                "vendor_address": extracted.get("vendor_address"),
                "invoice_number": extracted.get("invoice_number"),
                "invoice_date":   invoice_date,
                "due_date":       due_date,
                "subtotal":       extracted.get("subtotal"),
                "tax_amount":     extracted.get("tax_amount"),
                "total_amount":   extracted.get("total_amount"),
                "currency":       extracted.get("currency", "INR"),
                "payment_status": "unpaid",
                "doc_type":       None,   # determined manually or by GPT later
                "raw_json":       raw_json,
                "created_at":     datetime.utcnow(),
            },
        ).fetchone()

        invoice_id = row[0]

        for item in line_items:
            conn.execute(
                text(
                    """
                    INSERT INTO line_items
                        (invoice_id, description, quantity, unit_price, line_total)
                    VALUES
                        (:invoice_id, :description, :quantity, :unit_price, :line_total)
                    """
                ),
                {
                    "invoice_id":   invoice_id,
                    "description":  item.get("description"),
                    "quantity":     item.get("quantity"),
                    "unit_price":   item.get("unit_price"),
                    "line_total":   item.get("line_total"),
                },
            )

    logger.info("Saved invoice %d with %d line items for document %d", invoice_id, len(line_items), doc_id)
    return invoice_id


# ── Helpers ───────────────────────────────────────────────────────────────────

def _as_date(value):
    """Accept datetime.date, datetime.datetime, or None."""
    if value is None:
        return None
    if hasattr(value, "date"):
        return value.date()
    return value
