from pathlib import Path
from typing import Protocol

from azure.storage.blob import BlobServiceClient

from app.core.config import Settings


class BlobStore(Protocol):
    def put_bytes(self, key: str, data: bytes) -> str: ...

    def get_bytes(self, key: str) -> bytes: ...


class FileSystemBlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put_bytes(self, key: str, data: bytes) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get_bytes(self, key: str) -> bytes:
        return (self.root / key).read_bytes()


class AzureBlobStore:
    def __init__(self, connection_string: str, container: str) -> None:
        self.client = BlobServiceClient.from_connection_string(connection_string)
        self.container = self.client.get_container_client(container)
        self.container.create_container(exist_ok=True)

    def put_bytes(self, key: str, data: bytes) -> str:
        self.container.upload_blob(name=key, data=data, overwrite=True)
        return key

    def get_bytes(self, key: str) -> bytes:
        data = self.container.download_blob(key).readall()
        return data if isinstance(data, bytes) else data.encode()


def build_blob_store(settings: Settings) -> BlobStore:
    if settings.azure_storage_connection_string:
        return AzureBlobStore(settings.azure_storage_connection_string, settings.azure_blob_container)
    return FileSystemBlobStore(settings.blob_storage_root)
