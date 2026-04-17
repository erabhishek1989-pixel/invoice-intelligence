import uuid
from flask import current_app
from azure.storage.blob import BlobServiceClient


def upload_to_blob(file_storage) -> str:
    connection_string = current_app.config["AZURE_STORAGE_CONNECTION_STRING"]
    container = current_app.config["AZURE_STORAGE_CONTAINER"]

    blob_name = f"{uuid.uuid4()}-{file_storage.filename}"

    client = BlobServiceClient.from_connection_string(connection_string)
    blob_client = client.get_blob_client(container=container, blob=blob_name)
    blob_client.upload_blob(file_storage.stream, overwrite=True)

    return blob_client.url
