import json
import logging
import azure.functions as func
from processor import process_invoice_document

logger = logging.getLogger(__name__)

app = func.FunctionApp()


@app.queue_trigger(
    arg_name="msg",
    queue_name="invoice-processing",
    connection="AZURE_STORAGE_CONNECTION_STRING",
)
def process_invoice(msg: func.QueueMessage) -> None:
    """
    Triggered when Event Grid writes a BlobCreated event to the
    'invoice-processing' Storage Queue.

    Event Grid delivers the event as a JSON object in the queue message body:
    {
      "id": "...",
      "eventType": "Microsoft.Storage.BlobCreated",
      "subject": "/blobServices/default/containers/invoices/blobs/file.pdf",
      "data": {
        "url": "https://<account>.blob.core.windows.net/invoices/file.pdf",
        ...
      }
    }
    """
    try:
        body = msg.get_body().decode("utf-8")
        event = json.loads(body)
    except Exception as exc:
        logger.error("Failed to parse queue message: %s", exc)
        return

    data = event.get("data", {})
    blob_url = data.get("url", "")
    document_id = event.get("id")

    if not blob_url:
        logger.warning("Queue message has no blob URL — skipping. Event: %s", event)
        return

    logger.info("Processing blob: %s (event id: %s)", blob_url, document_id)
    process_invoice_document(blob_url, document_id)
