import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone

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

    # 3. DB — quick connectivity check (5 s timeout so health responds fast)
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool
        url = os.environ["DATABASE_URL"]
        eng = create_engine(url, poolclass=NullPool, connect_args={"timeout": 30})
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        result["db"] = {"connected": True}
    except Exception as exc:
        result["db"] = {"connected": False, "error": str(exc)[-200:]}

    # 4. DNS + TCP diagnostics
    try:
        import socket
        import subprocess
        from sqlalchemy.engine import make_url as _make_url
        db_url = os.environ.get("DATABASE_URL", "")
        parsed = _make_url(db_url)
        host = parsed.host or "unknown"
        result["sql_host"] = host  # show the actual hostname being used

        # DNS via Python socket
        try:
            resolved = socket.getaddrinfo(host, 1433, proto=socket.IPPROTO_TCP)
            ips = list({r[4][0] for r in resolved})
            result["dns"] = {"host": host, "resolved_ips": ips}
        except Exception as dns_exc:
            result["dns"] = {"host": host, "error": str(dns_exc)}

        # DNS via nslookup (uses system resolver, different from Python)
        try:
            out = subprocess.check_output(["nslookup", host], timeout=5, stderr=subprocess.STDOUT).decode()
            result["nslookup"] = out[-300:]
        except Exception as ns_exc:
            result["nslookup"] = str(ns_exc)[-200:]

        # TCP port 1433 (use IP if we have one, else hostname)
        connect_target = ips[0] if "ips" in dir() and ips else host
        try:
            sock = socket.create_connection((connect_target, 1433), timeout=10)
            sock.close()
            result["tcp_1433"] = f"reachable ({connect_target})"
        except Exception as tcp_exc:
            result["tcp_1433"] = f"blocked ({connect_target}): {tcp_exc}"

    except Exception as exc:
        result["dns"] = {"error": str(exc)[-300:]}

    return func.HttpResponse(
        json.dumps(result, indent=2),
        mimetype="application/json",
        status_code=200,
    )


@app.route(route="inject")
def inject(req: func.HttpRequest) -> func.HttpResponse:
    """
    DIAGNOSTIC: Manually push a BlobCreated event to the invoice-processing queue.
    Bypasses Event Grid so you can test the queue trigger + processing pipeline directly.

    Usage: GET /api/inject?blob_url=https://stinvoiceaiprod001.blob.core.windows.net/invoices/xxx.pdf
    """
    from azure.storage.queue import QueueServiceClient

    blob_url = req.params.get("blob_url", "").strip()
    if not blob_url:
        return func.HttpResponse(
            json.dumps({"error": "blob_url query parameter is required"}),
            mimetype="application/json",
            status_code=400,
        )

    # Construct an Event Grid BlobCreated event — same schema that process_invoice expects
    event = {
        "id": str(uuid.uuid4()),
        "eventType": "Microsoft.Storage.BlobCreated",
        "subject": "/blobServices/default/containers/invoices/blobs/injected",
        "eventTime": datetime.now(timezone.utc).isoformat(),
        "data": {
            "api": "PutBlob",
            "url": blob_url,
            "blobType": "BlockBlob",
            "contentType": "application/octet-stream",
        },
        "dataVersion": "",
        "metadataVersion": "1",
    }

    try:
        conn_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
        qsc = QueueServiceClient.from_connection_string(conn_str)
        qc = qsc.get_queue_client("invoice-processing")
        # Send as plain JSON — the queue trigger reads msg.get_body() directly
        qc.send_message(json.dumps(event))

        return func.HttpResponse(
            json.dumps(
                {
                    "status": "queued",
                    "blob_url": blob_url,
                    "message": "Event pushed to invoice-processing queue. Queue trigger fires within ~10 s.",
                    "event_id": event["id"],
                },
                indent=2,
            ),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as exc:
        return func.HttpResponse(
            json.dumps({"error": str(exc)}),
            mimetype="application/json",
            status_code=500,
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
    # Event Grid may base64-encode messages to Storage Queue (older behavior).
    # The inject endpoint sends plain JSON.  Handle both formats gracefully.
    try:
        raw = msg.get_body().decode("utf-8")
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            event = json.loads(base64.b64decode(raw).decode("utf-8"))
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
