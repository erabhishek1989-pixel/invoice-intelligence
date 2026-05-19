import uuid
from flask import current_app
from azure.storage.blob import BlobServiceClient


def upload_to_blob(file_storage) -> tuple[str, str]:
    """
    Upload a file to Azure Blob Storage.
    Returns (blob_url, blob_name) — blob_name is needed to download later.
    """
    connection_string = current_app.config["AZURE_STORAGE_CONNECTION_STRING"]
    container = current_app.config["AZURE_STORAGE_CONTAINER"]

    blob_name = f"{uuid.uuid4()}-{file_storage.filename}"

    client = BlobServiceClient.from_connection_string(connection_string)
    blob_client = client.get_blob_client(container=container, blob=blob_name)
    blob_client.upload_blob(file_storage.stream, overwrite=True)

    return blob_client.url, blob_name


def download_blob_bytes(blob_name: str) -> bytes:
    """
    Download a blob's raw bytes. Used to stream content to Document Intelligence
    instead of passing a URL (container is private, URL is not publicly accessible).
    """
    connection_string = current_app.config["AZURE_STORAGE_CONNECTION_STRING"]
    container = current_app.config["AZURE_STORAGE_CONTAINER"]

    client = BlobServiceClient.from_connection_string(connection_string)
    blob_client = client.get_blob_client(container=container, blob=blob_name)
    return blob_client.download_blob().readall()
