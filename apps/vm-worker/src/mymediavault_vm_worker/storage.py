from __future__ import annotations

import asyncio
from pathlib import Path

import boto3
from botocore.client import BaseClient

from mymediavault_vm_worker.settings import PreviewWorkerSettings

class BlobStore:
    def __init__(self, settings: PreviewWorkerSettings) -> None:
        self._settings = settings
        self._bucket_name = settings.r2_bucket_name
        self._root = Path.cwd() / ".local" / "blob-storage"
        self._client = self._build_r2_client()

    def get_bytes(self, key: str) -> bytes:
        if self._client is None:
            return (self._root / key).read_bytes()
        result = self._client.get_object(Bucket=self._bucket_name, Key=key)
        return result["Body"].read()

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        if self._client is None:
            target = self._root / key
            target.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(target.write_bytes, data)
            return key

        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    async def put_file(self, key: str, path: Path, content_type: str) -> str:
        if self._client is None:
            target = self._root / key
            target.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(target.write_bytes, path.read_bytes())
            return key

        await asyncio.to_thread(
            self._client.upload_file,
            str(path),
            self._bucket_name,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        return key

    async def delete_if_exists(self, key: str) -> None:
        if self._client is None:
            await asyncio.to_thread((self._root / key).unlink, missing_ok=True)
            return
        await asyncio.to_thread(
            self._client.delete_object, Bucket=self._bucket_name, Key=key
        )

    def _build_r2_client(self) -> BaseClient | None:
        if not (
            self._settings.r2_endpoint
            and self._settings.r2_access_key_id
            and self._settings.r2_secret_access_key
        ):
            return None
        return boto3.client(
            "s3",
            endpoint_url=self._settings.r2_endpoint,
            aws_access_key_id=self._settings.r2_access_key_id,
            aws_secret_access_key=self._settings.r2_secret_access_key,
            region_name="auto",
        )

