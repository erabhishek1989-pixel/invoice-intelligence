import azure.functions as func
from function_app.processor import process_invoice_document

app = func.FunctionApp()


@app.event_grid_trigger(arg_name="event")
def process_invoice(event: func.EventGridEvent):
    data = event.get_json()
    blob_url = data.get("url", "")
    document_id = data.get("clientRequestId")
    process_invoice_document(blob_url, document_id)
