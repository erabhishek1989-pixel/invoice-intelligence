import json
import logging
import os

import azure.functions as func

from db_writer import find_document_id_by_blob_url, save_invoice, set_document_status
from processor import process_invoice_document

logger = logging.getLogger(__name__)

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="health")
def health(req: func.HttpRequest) -> func.HttpResponse:
    """
    Diagnostic endpoint — checks env vars, queue message count, and DB connectivity.
    GET https://func-invoiceai-prod-centralindia-001.azurewebsites.net/api/health
    """
    import traceback
    from azure.storage.queue import QueueServiceClient

    result = {"status": "ok", "env": {}, "queue": {}, "db": {}}

    # 1. Env vars
    required_keys = [
        "AZURE_STORAGE_CONNECTION_STRING",
        "AZURE_DOC_INTELLIGENCE_ENDPOINT",
        "DATABASE_URL",
        "FUNCTIONS_WORKER_RUNTIME",
        "AzureWebJobsFeatureFlags",
        "WEBSITE_RUN_FROM_PACKAGE",
    ]
    result["env"] = {k: ("set" if os.environ.get(k) else "MISSING") for k in required_keys}

    # 2. Queue — peek for messages
    try:
        conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        qsc = QueueServiceClient.from_connection_string(conn_str)
        qc = qsc.get_queue_client("invoice-processing")
        props = qc.get_queue_properties()
        msgs = list(qc.peek_messages(max_messages=5))
        result["queue"] = {
            "approximate_count": props.approximate_message_count,
            "peeked_messages": len(msgs),
            "sample": [m.content[:120] if m.content else "" for m in msgs],
        }
    except Exception as exc:
        result["queue"] = {"error": str(exc), "trace": traceback.format_exc()[-300:]}

    # 3. DB — quick connectivity check
    try:
        from db_writer import _engine
        with _engine().connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        result["db"] = {"connected": True}
    except Exception as exc:
        result["db"] = {"connected": False, "error": str(exc)[-200:]}

    return func.HttpResponse(
        json.dumps(result, indent=2),
        mimetype="application/json",
        status_code=200,
    )


@app.queue_trigger(
    arg_name="msg",
    queue_name="invoice-processing",
    connection="AZURE_STORAGE_CONNECTION_STRING",
)
def process_invoice(msg: func.QueueMessage) -> None:
    """
    Triggered when Event Grid writes a BlobCreated event to the
    'invoice-processing' Storage Queue.

    Full pipeline:
      1. Parse blob URL from queue message
      2. Find the Document record in the database
      3. Mark document as "processing"
      4. Call Document Intelligence to extract invoice fields
      5. Save extracted data to invoices + line_items tables
      6. Mark document as "processed" (or "failed" on error)
    """
    # ── 1. Parse queue message ────────────────────────────────────────────────
    try:
        body = msg.get_body().decode("utf-8")
        event = json.loads(body)
    except Exception as exc:
        logger.error("Cannot parse queue message body: %s", exc)
        return  # un-parseable message — drop it, don't retry

    data = event.get("data", {})
    blob_url = data.get("url", "")

    if not blob_url:
        logger.warning("Queue message has no blob URL — skipping. Raw event: %s", event)
        return

    logger.info("Received blob event for: %s", blob_url)

    # ── 2. Find Document record ───────────────────────────────────────────────
    doc_id = find_document_id_by_blob_url(blob_url)
    if doc_id is None:
        # The Flask app creates the Document row before the blob is uploaded,
        # but in rare cases the DB commit might be slightly delayed.
        logger.error(
            "No Document record found for blob URL: %s — "
            "the message will be retried by the queue runtime.",
            blob_url,
        )
        # Raise so the queue runtime retries (up to maxDequeueCount times).
        raise ValueError(f"Document not found for blob_url: {blob_url}")

    # ── 3. Mark as processing ─────────────────────────────────────────────────
    set_document_status(doc_id, "processing")
    logger.info("Document %d marked as processing", doc_id)

    # ── 4 + 5 + 6. Extract → Save → Mark done ─────────────────────────────────
    try:
        extracted = process_invoice_document(blob_url)
        save_invoice(doc_id, extracted)
        set_document_status(doc_id, "processed")
        logger.info("Document %d processed successfully", doc_id)

    except Exception as exc:
        logger.error("Processing failed for document %d: %s", doc_id, exc, exc_info=True)
        set_document_status(doc_id, "failed", str(exc))
        # Do NOT re-raise — the document is marked failed and retrying
        # Document Intelligence on the same blob won't produce different results.
