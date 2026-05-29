from __future__ import annotations

import argparse
import asyncio
import random
import re
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import boto3
from beanie import Document, init_beanie
from botocore.client import BaseClient
from loguru import logger
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pymongo import AsyncMongoClient, ReturnDocument
from torrent_preview import (
    GeneratedFrame,
    GeneratedSheet,
    PreviewHarnessConfig,
    PreviewEngine,
    PreviewEngineConfig,
    PreviewJobLease,
    PreviewJobSource,
    PreviewResult,
    PreviewWorkerHarness,
    configure_default_logging,
)

DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_MAX_CONCURRENCY = 20
DEFAULT_STALE_PROCESSING_MINUTES = 120
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_TARGET_FRAMES = 9
DEFAULT_ANCHOR_RETRY_RANGE_MB = (64.0, 128.0, 256.0, 384.0, 512.0, 768.0)
DEFAULT_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS = 300.0
DEFAULT_PREVIEW_RETRY_DELAYS_SECONDS = (900, 3600, 14400)
DEFAULT_DEBUG_LOG_PATH = Path(".local/logs/vm-worker-debug.log")
DEFAULT_DEBUG_LOG_ROTATION = "100 MB"
DEFAULT_DEBUG_LOG_RETENTION = "7 days"
DEFAULT_METADATA_RETRY_DELAYS_SECONDS = (60, 120, 240, 480, 960, 1920)
DEFAULT_METADATA_LEASE_SECONDS = 1800
REDACTED_LOG_VALUE = "[redacted]"
SENSITIVE_LOG_KEYS = {
    "authorization",
    "aws_access_key_id",
    "aws_secret_access_key",
    "cookie",
    "mongodb_uri",
    "openai_api_key",
    "r2_access_key_id",
    "r2_secret_access_key",
    "set_cookie",
}
OPENAI_KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
MONGODB_CREDENTIAL_PATTERN = re.compile(
    r"(mongodb(?:\+srv)?://[^:/@\s]+:)([^@\s]+)(@)"
)


class MetadataResolutionError(Exception):
    def __init__(
        self,
        message: str,
        *,
        failure_kind: str,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_kind = failure_kind
        self.diagnostics = diagnostics or {}


class PreviewWorkerSettings(BaseSettings):
    mongodb_uri: str = Field(alias="MONGODB_URI")
    mongodb_database: str = Field(default="mymediavault", alias="MMV_MONGODB_DB_NAME")
    mongodb_server_selection_timeout_ms: int = Field(
        default=10000, alias="MMV_MONGODB_SERVER_SELECTION_TIMEOUT_MS"
    )
    r2_endpoint: str | None = Field(default=None, alias="R2_ENDPOINT")
    r2_access_key_id: str | None = Field(default=None, alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str | None = Field(default=None, alias="R2_SECRET_ACCESS_KEY")
    r2_bucket_name: str = Field(default="torrent-raw", alias="R2_BUCKET_NAME")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    metadata_worker_enabled: bool = Field(default=True, alias="MMV_METADATA_WORKER_ENABLED")
    preview_worker_enabled: bool = Field(default=True, alias="MMV_PREVIEW_WORKER_ENABLED")
    preview_worker_max_concurrency: int = Field(
        default=DEFAULT_MAX_CONCURRENCY, alias="MMV_PREVIEW_WORKER_MAX_CONCURRENCY"
    )
    preview_worker_poll_interval_seconds: float = Field(
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        alias="MMV_PREVIEW_WORKER_POLL_INTERVAL_SECONDS",
    )
    preview_repair_stale_processing_minutes: int = Field(
        default=DEFAULT_STALE_PROCESSING_MINUTES,
        alias="MMV_PREVIEW_REPAIR_STALE_PROCESSING_MINUTES",
    )
    preview_max_attempts: int = Field(
        default=DEFAULT_MAX_ATTEMPTS, alias="MMV_PREVIEW_MAX_ATTEMPTS"
    )
    preview_target_frames: int = Field(
        default=DEFAULT_TARGET_FRAMES, alias="MMV_PREVIEW_TARGET_FRAMES"
    )
    preview_anchor_retry_range_mb: tuple[float, ...] = Field(
        default=DEFAULT_ANCHOR_RETRY_RANGE_MB,
        alias="MMV_PREVIEW_ANCHOR_RETRY_RANGE_MB",
    )
    preview_download_progress_timeout_seconds: float = Field(
        default=DEFAULT_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS,
        alias="MMV_PREVIEW_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS",
    )
    preview_retry_delays_seconds: list[int] = Field(
        default_factory=lambda: list(DEFAULT_PREVIEW_RETRY_DELAYS_SECONDS),
        alias="MMV_PREVIEW_RETRY_DELAYS_SECONDS",
    )
    vm_worker_debug_log_path: Path = Field(
        default=DEFAULT_DEBUG_LOG_PATH, alias="MMV_VM_WORKER_DEBUG_LOG_PATH"
    )
    vm_worker_debug_log_rotation: str = Field(
        default=DEFAULT_DEBUG_LOG_ROTATION,
        alias="MMV_VM_WORKER_DEBUG_LOG_ROTATION",
    )
    vm_worker_debug_log_retention: str = Field(
        default=DEFAULT_DEBUG_LOG_RETENTION,
        alias="MMV_VM_WORKER_DEBUG_LOG_RETENTION",
    )
    metadata_worker_poll_interval_seconds: float = Field(
        default=5.0, alias="MMV_METADATA_WORKER_POLL_INTERVAL_SECONDS"
    )
    metadata_fetch_timeout_seconds: int = Field(
        default=20, alias="MMV_TORRENT_FETCH_TIMEOUT_SECONDS"
    )
    metadata_resolver_urls: list[str] = Field(
        default_factory=lambda: ["https://itorrents.org/torrent/{info_hash}.torrent"],
        alias="MMV_TORRENT_RESOLVER_URLS",
    )
    metadata_retry_delays_seconds: list[int] = Field(
        default_factory=lambda: list(DEFAULT_METADATA_RETRY_DELAYS_SECONDS),
        alias="MMV_TORRENT_METADATA_RETRY_DELAYS_SECONDS",
    )
    metadata_lease_seconds: int = Field(
        default=DEFAULT_METADATA_LEASE_SECONDS,
        alias="MMV_TORRENT_METADATA_LEASE_SECONDS",
    )
    metadata_dht_fallback_enabled: bool = Field(
        default=True, alias="MMV_TORRENT_DHT_FALLBACK_ENABLED"
    )
    metadata_dht_timeout_seconds: int = Field(
        default=180, alias="MMV_TORRENT_DHT_TIMEOUT_SECONDS"
    )
    torrent_provider: str = Field(default="http", alias="MMV_TORRENT_PROVIDER")

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", populate_by_name=True
    )

    @model_validator(mode="after")
    def validate_storage_credentials(self) -> PreviewWorkerSettings:
        credentials = [
            self.r2_endpoint,
            self.r2_access_key_id,
            self.r2_secret_access_key,
        ]
        if any(credentials) and not all(credentials):
            msg = "R2_ENDPOINT, R2_ACCESS_KEY_ID, and R2_SECRET_ACCESS_KEY must be set together"
            raise ValueError(msg)
        if not self.metadata_worker_enabled and not self.preview_worker_enabled:
            msg = "At least one of MMV_METADATA_WORKER_ENABLED or MMV_PREVIEW_WORKER_ENABLED must be true"
            raise ValueError(msg)
        if self.preview_worker_enabled and not (self.openai_api_key or "").strip():
            msg = "OPENAI_API_KEY must be set for torrent-preview Pydantic AI ranking"
            raise ValueError(msg)
        if self.preview_target_frames not in {3, 9, 16}:
            msg = "MMV_PREVIEW_TARGET_FRAMES must be one of 3, 9, or 16"
            raise ValueError(msg)
        previous_retry_range = 32.0
        for value in self.preview_anchor_retry_range_mb:
            if value <= previous_retry_range:
                msg = (
                    "MMV_PREVIEW_ANCHOR_RETRY_RANGE_MB values must be greater "
                    "than 32 and strictly increasing"
                )
                raise ValueError(msg)
            previous_retry_range = value
        if self.preview_download_progress_timeout_seconds <= 0:
            msg = "MMV_PREVIEW_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS must be greater than 0"
            raise ValueError(msg)
        if any(delay <= 0 for delay in self.preview_retry_delays_seconds):
            msg = "MMV_PREVIEW_RETRY_DELAYS_SECONDS values must be positive"
            raise ValueError(msg)
        if not self.metadata_resolver_urls:
            msg = "MMV_TORRENT_RESOLVER_URLS must include at least one resolver URL"
            raise ValueError(msg)
        if self.torrent_provider not in {"fake", "http"}:
            msg = "MMV_TORRENT_PROVIDER must be fake or http"
            raise ValueError(msg)
        if any(delay <= 0 for delay in self.metadata_retry_delays_seconds):
            msg = "MMV_TORRENT_METADATA_RETRY_DELAYS_SECONDS values must be positive"
            raise ValueError(msg)
        return self

    @property
    def use_r2(self) -> bool:
        return bool(
            self.r2_endpoint and self.r2_access_key_id and self.r2_secret_access_key
        )


class TorrentPreviewFrame(BaseModel):
    key: str
    width: int
    height: int
    timestampSeconds: float


class TorrentPreviewSheet(BaseModel):
    key: str
    width: int
    height: int
    mimeType: str


class TorrentPreviewDiagnostics(BaseModel):
    artifactVersion: str | None = None
    artifactFingerprint: str | None = None
    statusReason: str | None = None
    downloadedBytes: int | None = None
    elapsedSeconds: float | None = None
    selectedFilePath: str | None = None
    selectedFileSizeBytes: int | None = None
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class Torrent(Document):
    id: str = Field(alias="_id")
    infoHash: str
    name: str | None = None
    sizeBytes: int | None = None
    rawBlobKey: str | None = None
    metadataStatus: str = "pending"
    metadataError: str | None = None
    metadataFailureKind: str | None = None
    metadataAttempts: int = 0
    metadataNextAttemptAt: datetime | None = None
    metadataLastAttemptAt: datetime | None = None
    metadataStartedAt: datetime | None = None
    metadataFinishedAt: datetime | None = None
    metadataLeaseUntil: datetime | None = None
    metadataDiagnostics: dict[str, Any] = Field(default_factory=dict)
    files: list[dict[str, Any]] = Field(default_factory=list)
    previewStatus: str = "pending"
    previewAttempts: int = 0
    previewLastAttemptAt: datetime | None = None
    previewNextAttemptAt: datetime | None = None
    previewUpdatedAt: datetime | None = None
    previewFrames: list[TorrentPreviewFrame] = Field(default_factory=list)
    previewSheet: TorrentPreviewSheet | None = None
    previewDiagnostics: TorrentPreviewDiagnostics = Field(
        default_factory=TorrentPreviewDiagnostics
    )

    class Settings:
        name = "torrents"


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
        if not self._settings.use_r2:
            return None
        return boto3.client(
            "s3",
            endpoint_url=self._settings.r2_endpoint,
            aws_access_key_id=self._settings.r2_access_key_id,
            aws_secret_access_key=self._settings.r2_secret_access_key,
            region_name="auto",
        )


class FakeTorrentMetadataResolver:
    async def fetch(self, info_hash: str) -> dict[str, Any]:
        name = f"Fake Torrent {info_hash[:8]}"
        raw = _fake_torrent_payload(name)
        metadata = parse_torrent(raw)
        metadata["resolverDiagnostics"] = [{"url": "fake", "kind": "success"}]
        return metadata


class HttpTorrentMetadataResolver:
    def __init__(self, *, resolver_urls: list[str], timeout_seconds: int) -> None:
        self._resolver_urls = resolver_urls
        self._timeout_seconds = max(1, timeout_seconds)

    async def fetch(self, info_hash: str) -> dict[str, Any]:
        resolver_results: list[dict[str, Any]] = []
        for resolver_url in self._resolver_urls:
            url = self._resolve_url(resolver_url, info_hash)
            try:
                raw = await asyncio.to_thread(self._fetch_url, url)
                metadata = parse_torrent(raw)
                metadata["resolverDiagnostics"] = resolver_results + [
                    {"url": url, "kind": "success"}
                ]
                return metadata
            except MetadataResolutionError as error:
                resolver_results.append(
                    {
                        "url": url,
                        "kind": error.failure_kind,
                        "error": str(error),
                        **error.diagnostics,
                    }
                )

        failure_kind = (
            "transient"
            if any(result["kind"] == "transient" for result in resolver_results)
            else "permanent"
        )
        raise MetadataResolutionError(
            "Unable to fetch a valid .torrent payload from configured resolvers.",
            failure_kind=failure_kind,
            diagnostics={"resolvers": resolver_results},
        )

    def _fetch_url(self, url: str) -> bytes:
        request = urllib.request.Request(
            url, headers={"User-Agent": "MyMediaVault/0.1"}
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout_seconds
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            failure_kind = "transient" if error.code in TRANSIENT_HTTP_STATUSES else "permanent"
            raise MetadataResolutionError(
                f"Resolver returned {error.code}",
                failure_kind=failure_kind,
                diagnostics={"status": error.code},
            ) from error
        except TimeoutError as error:
            raise MetadataResolutionError(
                "Resolver request timed out.",
                failure_kind="transient",
            ) from error
        except OSError as error:
            raise MetadataResolutionError(
                str(error) or "Resolver request failed.",
                failure_kind="transient",
            ) from error

        if not raw:
            raise MetadataResolutionError(
                "Resolver returned an empty response.",
                failure_kind="transient",
            )
        return raw

    @staticmethod
    def _resolve_url(resolver_url: str, info_hash: str) -> str:
        return (
            resolver_url.replace("{info_hash}", info_hash)
            if "{info_hash}" in resolver_url
            else f"{resolver_url.rstrip('/')}/{info_hash}"
        )


class DhtTorrentMetadataResolver:
    def __init__(self, *, timeout_seconds: int) -> None:
        self._timeout_seconds = max(10, timeout_seconds)

    async def fetch(self, info_hash: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._fetch_sync, info_hash)

    def _fetch_sync(self, info_hash: str) -> dict[str, Any]:
        normalized = info_hash.strip().lower()
        if len(normalized) != 40 or any(char not in "0123456789abcdef" for char in normalized):
            raise MetadataResolutionError(
                "Info hash must be 40 hexadecimal characters for DHT fallback.",
                failure_kind="permanent",
            )

        try:
            import libtorrent as lt
        except ImportError as error:
            raise MetadataResolutionError(
                "libtorrent is not available for DHT fallback.",
                failure_kind="transient",
            ) from error

        with tempfile.TemporaryDirectory(prefix="mmv-metadata-") as temp_dir:
            session = lt.session(
                {
                    "enable_dht": True,
                    "enable_lsd": False,
                    "enable_upnp": False,
                    "enable_natpmp": False,
                    "listen_interfaces": "0.0.0.0:6881",
                    "user_agent": "MyMediaVault/0.1",
                }
            )
            handle = session.add_torrent(
                {
                    "url": f"magnet:?xt=urn:btih:{normalized}",
                    "save_path": temp_dir,
                    "upload_mode": True,
                    "paused": False,
                }
            )
            deadline = datetime.now(UTC) + timedelta(seconds=self._timeout_seconds)
            while datetime.now(UTC) < deadline:
                if handle.has_metadata():
                    torrent_info = handle.torrent_file()
                    generated = lt.create_torrent(torrent_info).generate()
                    raw = bytes(lt.bencode(generated))
                    metadata = parse_torrent(raw)
                    metadata["resolverDiagnostics"] = [
                        {"url": f"dht:{normalized}", "kind": "success"}
                    ]
                    session.remove_torrent(handle)
                    return metadata
                alert = session.pop_alert()
                if alert is not None and "metadata" in str(alert).lower():
                    logger.debug("DHT metadata alert: {}", alert)
                import time

                time.sleep(1)
            session.remove_torrent(handle)
        raise MetadataResolutionError(
            "DHT metadata fetch timed out.",
            failure_kind="transient",
            diagnostics={"dht": {"timeoutSeconds": self._timeout_seconds}},
        )


TRANSIENT_HTTP_STATUSES = {408, 409, 425, 429, *range(500, 600)}


class MetadataWorker:
    def __init__(
        self,
        *,
        settings: PreviewWorkerSettings,
        blob_store: BlobStore,
    ) -> None:
        self._blob_store = blob_store
        self._poll_interval_seconds = max(
            0.5, settings.metadata_worker_poll_interval_seconds
        )
        self._retry_delays_seconds = settings.metadata_retry_delays_seconds
        self._lease_seconds = max(60, settings.metadata_lease_seconds)
        self._resolver = (
            FakeTorrentMetadataResolver()
            if settings.torrent_provider == "fake"
            else HttpTorrentMetadataResolver(
                resolver_urls=settings.metadata_resolver_urls,
                timeout_seconds=settings.metadata_fetch_timeout_seconds,
            )
        )
        self._dht_resolver = (
            DhtTorrentMetadataResolver(
                timeout_seconds=settings.metadata_dht_timeout_seconds
            )
            if settings.metadata_dht_fallback_enabled and settings.torrent_provider == "http"
            else None
        )
        self._stopping = False

    async def run(self) -> None:
        logger.info(
            "Metadata worker started with retry_delays_seconds={}",
            self._retry_delays_seconds,
        )
        while not self._stopping:
            claimed = await self._claim_one()
            if claimed is None:
                await asyncio.sleep(self._poll_interval_seconds)
                continue
            await self._process(claimed)

    def stop(self) -> None:
        self._stopping = True

    async def _claim_one(self) -> Torrent | None:
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=self._lease_seconds)
        document = await Torrent.get_pymongo_collection().find_one_and_update(
            {
                "metadataStatus": {"$in": ["pending", "failed"]},
                "$and": [
                    {
                        "$or": [
                            {"metadataNextAttemptAt": None},
                            {"metadataNextAttemptAt": {"$lte": now}},
                            {"metadataNextAttemptAt": {"$exists": False}},
                        ]
                    },
                    {
                        "$or": [
                            {"metadataLeaseUntil": None},
                            {"metadataLeaseUntil": {"$lt": now}},
                            {"metadataLeaseUntil": {"$exists": False}},
                        ]
                    },
                ],
            },
            {
                "$set": {
                    "metadataStatus": "processing",
                    "metadataError": None,
                    "metadataStartedAt": now,
                    "metadataLastAttemptAt": now,
                    "metadataLeaseUntil": lease_until,
                },
                "$inc": {"metadataAttempts": 1},
            },
            sort=[("metadataNextAttemptAt", 1), ("updatedAt", 1), ("_id", 1)],
            return_document=ReturnDocument.AFTER,
        )
        return Torrent.model_validate(document) if document else None

    async def _process(self, torrent: Torrent) -> None:
        try:
            metadata = await self._resolver.fetch(torrent.infoHash)
        except MetadataResolutionError as http_error:
            if self._dht_resolver is None:
                await self._fail(torrent, http_error)
                return
            try:
                metadata = await self._dht_resolver.fetch(torrent.infoHash)
                metadata["resolverDiagnostics"] = [
                    *http_error.diagnostics.get("resolvers", []),
                    *metadata["resolverDiagnostics"],
                ]
            except MetadataResolutionError as dht_error:
                await self._fail(torrent, _combine_metadata_errors(http_error, dht_error))
                return

        blob_key = f"torrents/{torrent.infoHash}.torrent"
        await self._blob_store.put_bytes(
            blob_key, metadata["raw"], "application/x-bittorrent"
        )
        now = datetime.now(UTC)
        await Torrent.get_pymongo_collection().update_one(
            {"_id": torrent.id},
            {
                "$set": {
                    "name": metadata["name"],
                    "sizeBytes": metadata["sizeBytes"],
                    "rawBlobKey": blob_key,
                    "metadataStatus": "succeeded",
                    "metadataError": None,
                    "metadataFailureKind": None,
                    "metadataNextAttemptAt": None,
                    "metadataLeaseUntil": None,
                    "metadataFinishedAt": now,
                    "metadataDiagnostics": {
                        "resolvers": metadata["resolverDiagnostics"],
                    },
                    "files": metadata["files"],
                }
            },
        )
        logger.info("Metadata succeeded for torrent {}", torrent.id)

    async def _fail(self, torrent: Torrent, error: MetadataResolutionError) -> None:
        now = datetime.now(UTC)
        exhausted = torrent.metadataAttempts >= self.max_attempts
        permanent = error.failure_kind == "permanent"
        status = "failed" if permanent or exhausted else "pending"
        next_attempt_at = (
            None if status == "failed" else now + timedelta(seconds=self._next_delay(torrent.metadataAttempts))
        )
        message = str(error)
        if exhausted and not permanent:
            message = f"{message} Metadata retry attempts exhausted."
        await Torrent.get_pymongo_collection().update_one(
            {"_id": torrent.id},
            {
                "$set": {
                    "metadataStatus": status,
                    "metadataError": message,
                    "metadataFailureKind": error.failure_kind,
                    "metadataNextAttemptAt": next_attempt_at,
                    "metadataLeaseUntil": None,
                    "metadataFinishedAt": now if status == "failed" else None,
                    "metadataDiagnostics": error.diagnostics,
                }
            },
        )
        logger.warning(
            "Metadata {} for torrent {}: {}",
            status,
            torrent.id,
            message,
        )

    @property
    def max_attempts(self) -> int:
        return len(self._retry_delays_seconds) + 1

    def _next_delay(self, current_attempt: int) -> int:
        index = max(0, current_attempt - 1)
        if index >= len(self._retry_delays_seconds):
            return self._retry_delays_seconds[-1]
        jitter = random.uniform(0.8, 1.2)
        return max(1, round(self._retry_delays_seconds[index] * jitter))


def parse_torrent(raw: bytes) -> dict[str, Any]:
    decoded, offset = _bdecode(raw, 0)
    if offset != len(raw) or not isinstance(decoded, dict):
        raise MetadataResolutionError(
            "Torrent payload is not a valid bencoded dictionary.",
            failure_kind="transient",
        )
    info = decoded.get(b"info")
    if not isinstance(info, dict):
        raise MetadataResolutionError(
            "Torrent payload is missing an info dictionary.",
            failure_kind="permanent",
        )

    name = _decode_text(info.get(b"name") or info.get(b"name.utf-8") or b"unknown")
    files_value = info.get(b"files")
    files: list[dict[str, Any]]
    if isinstance(files_value, list):
        files = []
        for index, file_record in enumerate(files_value):
            if not isinstance(file_record, dict):
                continue
            path_value = file_record.get(b"path.utf-8") or file_record.get(b"path")
            path = (
                "/".join(_decode_text(segment) for segment in path_value)
                if isinstance(path_value, list)
                else f"{name}/{index}"
            )
            files.append(
                {
                    "path": path,
                    "sizeBytes": _to_int(file_record.get(b"length")),
                    "position": len(files),
                }
            )
    else:
        files = [
            {
                "path": name,
                "sizeBytes": _to_int(info.get(b"length")),
                "position": 0,
            }
        ]

    total_size = sum(file["sizeBytes"] for file in files)
    if not files or total_size <= 0:
        raise MetadataResolutionError(
            "Torrent payload has no usable files.",
            failure_kind="permanent",
        )
    return {
        "name": name,
        "sizeBytes": total_size,
        "files": files,
        "raw": raw,
    }


def _fake_torrent_payload(name: str) -> bytes:
    encoded_name = name.encode()
    return (
        b"d4:infod"
        b"6:lengthi1048576e"
        b"4:name"
        + str(len(encoded_name)).encode()
        + b":"
        + encoded_name
        + b"6:pieces0:"
        b"ee"
    )


def _combine_metadata_errors(
    http_error: MetadataResolutionError,
    dht_error: MetadataResolutionError,
) -> MetadataResolutionError:
    failure_kind = (
        "transient"
        if "transient" in {http_error.failure_kind, dht_error.failure_kind}
        else "permanent"
    )
    return MetadataResolutionError(
        f"{http_error} DHT fallback failed: {dht_error}",
        failure_kind=failure_kind,
        diagnostics={
            "http": http_error.diagnostics,
            "dht": {
                "kind": dht_error.failure_kind,
                "error": str(dht_error),
                **dht_error.diagnostics,
            },
        },
    )


def _bdecode(data: bytes, offset: int) -> tuple[Any, int]:
    if offset >= len(data):
        raise MetadataResolutionError(
            "Unexpected end of bencoded payload.",
            failure_kind="transient",
        )
    token = data[offset : offset + 1]
    if token == b"i":
        end = data.index(b"e", offset)
        return int(data[offset + 1 : end]), end + 1
    if token == b"l":
        values = []
        offset += 1
        while data[offset : offset + 1] != b"e":
            value, offset = _bdecode(data, offset)
            values.append(value)
        return values, offset + 1
    if token == b"d":
        values: dict[bytes, Any] = {}
        offset += 1
        while data[offset : offset + 1] != b"e":
            key, offset = _bdecode(data, offset)
            value, offset = _bdecode(data, offset)
            if isinstance(key, bytes):
                values[key] = value
        return values, offset + 1
    if token.isdigit():
        colon = data.index(b":", offset)
        length = int(data[offset:colon])
        start = colon + 1
        end = start + length
        return data[start:end], end
    raise MetadataResolutionError(
        "Unsupported bencode token.",
        failure_kind="transient",
    )


def _decode_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return "unknown"


def _to_int(value: Any) -> int:
    return value if isinstance(value, int) else 0


class MongoPreviewJobLease(PreviewJobLease):
    def __init__(
        self,
        *,
        torrent: Torrent,
        blob_store: BlobStore,
        artifact_version: str,
        artifact_fingerprint: str,
        max_attempts: int,
        retry_delays_seconds: list[int],
    ) -> None:
        self._torrent = torrent
        self._blob_store = blob_store
        self._artifact_version = artifact_version
        self._artifact_fingerprint = artifact_fingerprint
        self._max_attempts = max_attempts
        self._retry_delays_seconds = retry_delays_seconds
        self._old_keys = _preview_keys(torrent)

    @property
    def job_id(self) -> str:
        return self._torrent.id

    async def load_torrent_bytes(self) -> bytes:
        raw_blob_key = self._torrent.rawBlobKey
        if raw_blob_key is None:
            msg = f"Torrent {self._torrent.id} does not have a raw blob key"
            raise ValueError(msg)
        torrent_bytes = await asyncio.to_thread(
            self._blob_store.get_bytes, raw_blob_key
        )
        logger.bind(
            job_id=self._torrent.id,
            info_hash=self._torrent.infoHash,
            raw_blob_key=raw_blob_key,
            torrent_blob_bytes=len(torrent_bytes),
        ).debug("Loaded preview torrent bytes")
        return torrent_bytes

    async def complete(self, result: PreviewResult) -> None:
        logger.bind(
            job_id=self._torrent.id,
            expected_info_hash=self._torrent.infoHash,
            result_info_hash=result.info_hash,
            status=result.status,
            status_reason=result.status_reason,
            downloaded_bytes=result.diagnostics.downloaded_bytes,
            elapsed_seconds=round(result.diagnostics.elapsed_seconds, 2),
        ).debug("Completing preview job")
        stored_frames = await self._store_frames(result.info_hash, result.artifact.frames)
        stored_sheet = await self._store_sheet(result.info_hash, result.artifact.sheet)
        has_replacement_artifacts = bool(stored_frames or stored_sheet)
        next_attempt_at = _preview_next_attempt_at(
            status=result.status,
            attempts=self._torrent.previewAttempts,
            max_attempts=self._max_attempts,
            retry_delays_seconds=self._retry_delays_seconds,
        )
        await Torrent.get_pymongo_collection().update_one(
            {"_id": self._torrent.id},
            _success_update(
                result,
                stored_frames=stored_frames,
                stored_sheet=stored_sheet,
                artifact_version=self._artifact_version,
                artifact_fingerprint=self._artifact_fingerprint,
                replace_artifacts=has_replacement_artifacts,
                next_attempt_at=next_attempt_at,
            ),
        )
        if has_replacement_artifacts:
            await self._delete_old_keys(
                _preview_keys_from_stored(stored_frames, stored_sheet)
            )

    async def fail(self, error: Exception) -> None:
        message = str(error) or error.__class__.__name__
        next_attempt_at = _preview_next_attempt_at(
            status="failed",
            attempts=self._torrent.previewAttempts,
            max_attempts=self._max_attempts,
            retry_delays_seconds=self._retry_delays_seconds,
        )
        logger.bind(
            job_id=self._torrent.id,
            info_hash=self._torrent.infoHash,
            error_type=error.__class__.__name__,
            status_reason=message,
        ).debug("Failing preview job")
        await Torrent.get_pymongo_collection().update_one(
            {"_id": self._torrent.id},
            {
                "$set": {
                    "previewStatus": "failed",
                    "previewUpdatedAt": datetime.now(UTC),
                    "previewNextAttemptAt": next_attempt_at,
                    "previewDiagnostics.statusReason": message,
                    "previewDiagnostics.artifactVersion": self._artifact_version,
                    "previewDiagnostics.artifactFingerprint": self._artifact_fingerprint,
                }
            },
        )

    async def _delete_old_keys(self, new_keys: set[str]) -> None:
        for key in self._old_keys - new_keys:
            await self._blob_store.delete_if_exists(key)

    async def _store_frames(
        self, info_hash: str, frames: list[GeneratedFrame]
    ) -> list[dict[str, Any]]:
        stored = []
        for index, frame in enumerate(frames, start=1):
            key = f"previews/{info_hash}/frame_{index:03d}.jpg"
            await self._blob_store.put_file(key, frame.path, "image/jpeg")
            stored.append(
                {
                    "key": key,
                    "width": frame.width,
                    "height": frame.height,
                    "timestampSeconds": frame.timestamp_seconds,
                }
            )
        return stored

    async def _store_sheet(
        self, info_hash: str, sheet: GeneratedSheet | None
    ) -> dict[str, Any] | None:
        if sheet is None:
            return None
        key = f"previews/{info_hash}/preview_sheet.jpg"
        await self._blob_store.put_file(key, sheet.path, sheet.mime_type)
        return {
            "key": key,
            "width": sheet.width,
            "height": sheet.height,
            "mimeType": sheet.mime_type,
        }


class MongoPreviewJobSource(PreviewJobSource):
    def __init__(
        self,
        *,
        blob_store: BlobStore,
        stale_processing_minutes: int,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_delays_seconds: list[int] | None = None,
    ) -> None:
        self._blob_store = blob_store
        self._stale_processing_minutes = max(1, stale_processing_minutes)
        self._max_attempts = max(1, max_attempts)
        self._retry_delays_seconds = list(
            retry_delays_seconds or DEFAULT_PREVIEW_RETRY_DELAYS_SECONDS
        )

    async def claim_batch(
        self,
        *,
        limit: int,
        artifact_version: str,
        artifact_fingerprint: str,
    ) -> list[MongoPreviewJobLease]:
        await self._repair_stale_processing()
        claimed: list[MongoPreviewJobLease] = []
        for query, reset_attempts, claim_reason in self._claim_plans(
            artifact_version=artifact_version,
            artifact_fingerprint=artifact_fingerprint,
        ):
            while len(claimed) < limit:
                torrent = await self._claim_one(query, reset_attempts=reset_attempts)
                if torrent is None:
                    break
                logger.bind(
                    job_id=torrent.id,
                    info_hash=torrent.infoHash,
                    claim_reason=claim_reason,
                    preview_attempts=torrent.previewAttempts,
                    preview_status=torrent.previewStatus,
                    reset_attempts=reset_attempts,
                    artifact_version=artifact_version,
                    artifact_fingerprint=artifact_fingerprint,
                ).debug("Claimed preview job")
                claimed.append(
                    MongoPreviewJobLease(
                        torrent=torrent,
                        blob_store=self._blob_store,
                        artifact_version=artifact_version,
                        artifact_fingerprint=artifact_fingerprint,
                        max_attempts=self._max_attempts,
                        retry_delays_seconds=self._retry_delays_seconds,
                    )
                )
            if len(claimed) >= limit:
                break
        if claimed:
            logger.bind(
                claimed_count=len(claimed),
                limit=limit,
            ).debug("Preview job claim scan finished")
        else:
            logger.bind(
                limit=limit,
                max_attempts=self._max_attempts,
                claim_reasons=["pending", "artifact_stale", "retry"],
                artifact_version=artifact_version,
                artifact_fingerprint=artifact_fingerprint,
            ).debug("No preview jobs claimed")
        return claimed

    def _claim_plans(
        self,
        *,
        artifact_version: str,
        artifact_fingerprint: str,
    ) -> list[tuple[dict[str, Any], bool, str]]:
        pending_query, retry_query = self._claim_queries(
            artifact_version=artifact_version,
            artifact_fingerprint=artifact_fingerprint,
        )
        return [
            (pending_query, False, "pending"),
            (
                self._artifact_stale_query(
                    artifact_version=artifact_version,
                    artifact_fingerprint=artifact_fingerprint,
                ),
                True,
                "artifact_stale",
            ),
            (retry_query, False, "retry"),
        ]

    def _claim_queries(
        self,
        *,
        artifact_version: str,
        artifact_fingerprint: str,
    ) -> list[dict[str, Any]]:
        base = {
            "metadataStatus": "succeeded",
            "rawBlobKey": {"$type": "string", "$ne": ""},
        }
        now = datetime.now(UTC)
        retry_schedule = {
            "$or": [
                {"previewNextAttemptAt": None},
                {"previewNextAttemptAt": {"$lte": now}},
                {"previewNextAttemptAt": {"$exists": False}},
            ]
        }
        retryable = {**base, "previewAttempts": {"$lt": self._max_attempts}}
        return [
            {
                **retryable,
                "$or": [
                    {"previewStatus": {"$exists": False}},
                    {"previewStatus": "pending"},
                ],
            },
            {
                **retryable,
                "previewStatus": {"$in": ["failed", "partial"]},
                **retry_schedule,
            },
        ]

    def _artifact_stale_query(
        self,
        *,
        artifact_version: str,
        artifact_fingerprint: str,
    ) -> dict[str, Any]:
        base = {
            "metadataStatus": "succeeded",
            "rawBlobKey": {"$type": "string", "$ne": ""},
        }
        return {
            **base,
            "previewStatus": {"$in": ["succeeded", "failed", "partial"]},
            "$or": [
                {"previewDiagnostics.artifactVersion": {"$exists": False}},
                {"previewDiagnostics.artifactVersion": {"$ne": artifact_version}},
                {"previewDiagnostics.artifactFingerprint": {"$exists": False}},
                {
                    "previewDiagnostics.artifactFingerprint": {
                        "$ne": artifact_fingerprint
                    }
                },
            ],
        }

    async def _claim_one(
        self, query: dict[str, Any], *, reset_attempts: bool = False
    ) -> Torrent | None:
        now = datetime.now(UTC)
        attempt_update = (
            {
                "$set": {
                    "previewStatus": "processing",
                    "previewLastAttemptAt": now,
                    "previewNextAttemptAt": None,
                    "previewAttempts": 1,
                },
            }
            if reset_attempts
            else {
                "$set": {
                    "previewStatus": "processing",
                    "previewLastAttemptAt": now,
                    "previewNextAttemptAt": None,
                },
                "$inc": {"previewAttempts": 1},
            }
        )
        document = await Torrent.get_pymongo_collection().find_one_and_update(
            query,
            attempt_update,
            sort=[("updatedAt", 1), ("_id", 1)],
            return_document=ReturnDocument.AFTER,
        )
        return Torrent.model_validate(document) if document else None

    async def _repair_stale_processing(self) -> None:
        stale_before = datetime.now(UTC) - timedelta(
            minutes=self._stale_processing_minutes
        )
        result = await Torrent.get_pymongo_collection().update_many(
            {
                "previewStatus": "processing",
                "$or": [
                    {"previewLastAttemptAt": None},
                    {"previewLastAttemptAt": {"$lt": stale_before}},
                ],
            },
            {
                "$set": {
                    "previewStatus": "pending",
                    "previewDiagnostics.statusReason": "Preview processing timed out and was requeued.",
                }
            },
        )
        if result.modified_count:
            logger.info("Requeued {} stale preview jobs", result.modified_count)


class PreviewWorker:
    def __init__(
        self,
        *,
        settings: PreviewWorkerSettings,
    ) -> None:
        self._settings = settings
        self._max_concurrency = max(1, settings.preview_worker_max_concurrency)
        self._poll_interval_seconds = max(
            0.5, settings.preview_worker_poll_interval_seconds
        )
        self._stale_processing_minutes = max(
            1, settings.preview_repair_stale_processing_minutes
        )
        self._max_attempts = max(1, settings.preview_max_attempts)
        self._client = AsyncMongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
        )
        self._database = self._client[settings.mongodb_database]
        self._blob_store = BlobStore(settings)
        self._metadata_worker = (
            MetadataWorker(
                settings=settings,
                blob_store=self._blob_store,
            )
            if settings.metadata_worker_enabled
            else None
        )
        self._config = (
            PreviewEngineConfig(
                target_frames=settings.preview_target_frames,
                anchor_retry_range_mb=settings.preview_anchor_retry_range_mb,
                download_progress_timeout_seconds=(
                    settings.preview_download_progress_timeout_seconds
                ),
            )
            if settings.preview_worker_enabled
            else None
        )
        self._engine = PreviewEngine(config=self._config) if self._config else None
        self._harness: PreviewWorkerHarness | None = None

    async def run(self) -> None:
        await init_beanie(database=self._database, document_models=[Torrent])
        logger.info(
            "VM worker started with metadata_enabled={} preview_enabled={}",
            self._metadata_worker is not None,
            self._engine is not None,
        )
        tasks: list[asyncio.Task[None]] = []
        if self._metadata_worker is not None:
            tasks.append(asyncio.create_task(self._metadata_worker.run()))
        if self._engine is not None:
            job_source = MongoPreviewJobSource(
                blob_store=self._blob_store,
                stale_processing_minutes=self._stale_processing_minutes,
                max_attempts=self._max_attempts,
                retry_delays_seconds=self._settings.preview_retry_delays_seconds,
            )
            self._harness = PreviewWorkerHarness(
                engine=self._engine,
                job_source=job_source,
                config=PreviewHarnessConfig(
                    max_concurrency=self._max_concurrency,
                    poll_interval_seconds=self._poll_interval_seconds,
                ),
            )
            logger.info(
                "Preview worker started with preview_max_concurrency={} artifact_version={} artifact_fingerprint={}",
                self._max_concurrency,
                self._engine.artifact_version,
                self._engine.artifact_fingerprint,
            )
            tasks.append(asyncio.create_task(self._harness.run()))
        try:
            done, pending = await asyncio.wait(
                set(tasks),
                return_when=asyncio.FIRST_EXCEPTION,
            )
            for task in done:
                task.result()
            for task in pending:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        finally:
            if self._metadata_worker is not None:
                self._metadata_worker.stop()
            await self._client.close()
            self._harness = None

    def stop(self) -> None:
        if self._metadata_worker is not None:
            self._metadata_worker.stop()
        if self._harness is not None:
            self._harness.stop()


def _success_update(
    result: PreviewResult,
    *,
    stored_frames: list[dict[str, Any]],
    stored_sheet: dict[str, Any] | None,
    artifact_version: str,
    artifact_fingerprint: str,
    replace_artifacts: bool = True,
    next_attempt_at: datetime | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    selected_file = result.diagnostics.selected_file
    diagnostics = {
        "artifactVersion": artifact_version,
        "artifactFingerprint": artifact_fingerprint,
        "statusReason": result.status_reason,
        "downloadedBytes": result.diagnostics.downloaded_bytes,
        "elapsedSeconds": result.diagnostics.elapsed_seconds,
        "selectedFilePath": selected_file.path if selected_file else None,
        "selectedFileSizeBytes": selected_file.length if selected_file else None,
        "warnings": result.diagnostics.warnings,
        "details": _to_plain_dict(result.diagnostics),
    }
    values: dict[str, Any] = {
        "previewStatus": result.status,
        "previewUpdatedAt": now,
        "previewNextAttemptAt": next_attempt_at,
        "previewDiagnostics": diagnostics,
    }
    if replace_artifacts:
        values["previewFrames"] = stored_frames
        values["previewSheet"] = stored_sheet
    return {"$set": values}


def _preview_next_attempt_at(
    *,
    status: str,
    attempts: int,
    max_attempts: int,
    retry_delays_seconds: list[int],
    now: datetime | None = None,
) -> datetime | None:
    if status not in {"failed", "partial"}:
        return None
    if attempts >= max_attempts:
        return None
    if not retry_delays_seconds:
        return None
    delay_index = min(max(0, attempts - 1), len(retry_delays_seconds) - 1)
    return (now or datetime.now(UTC)) + timedelta(
        seconds=retry_delays_seconds[delay_index]
    )


def _preview_keys(torrent: Torrent) -> set[str]:
    keys = {frame.key for frame in torrent.previewFrames if frame.key}
    sheet = torrent.previewSheet
    if sheet and sheet.key:
        keys.add(sheet.key)
    return keys


def _preview_keys_from_stored(
    frames: list[dict[str, Any]], sheet: dict[str, Any] | None
) -> set[str]:
    keys = {frame["key"] for frame in frames if frame.get("key")}
    if sheet and sheet.get("key"):
        keys.add(sheet["key"])
    return keys


def _to_plain_dict(value: Any) -> dict[str, Any]:
    plain = _to_plain_value(value)
    if isinstance(plain, dict):
        return plain
    return {}


def _to_plain_value(value: Any) -> Any:
    if is_dataclass(value):
        return _to_plain_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _to_plain_value(child) for key, child in value.items()}
    if isinstance(value, list | tuple):
        return [_to_plain_value(child) for child in value]
    return value


def _configure_vm_worker_logging(settings: PreviewWorkerSettings) -> None:
    configure_default_logging(debug=False, sink=sys.stdout)
    logger.configure(patcher=_redact_log_record)
    settings.vm_worker_debug_log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        settings.vm_worker_debug_log_path,
        level="DEBUG",
        rotation=settings.vm_worker_debug_log_rotation,
        retention=settings.vm_worker_debug_log_retention,
        compression=None,
        serialize=True,
        backtrace=False,
        diagnose=False,
    )


def _redact_log_record(record: dict[str, Any]) -> None:
    record["message"] = _redact_text(str(record["message"]))
    record["extra"] = _redact_log_value(record["extra"], key=None)


def _redact_log_value(value: Any, *, key: str | None) -> Any:
    if key is not None and _is_sensitive_log_key(key):
        return REDACTED_LOG_VALUE
    if isinstance(value, dict):
        return {
            str(child_key): _redact_log_value(child_value, key=str(child_key))
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_log_value(item, key=None) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_log_value(item, key=None) for item in value)
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _is_sensitive_log_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return (
        normalized in SENSITIVE_LOG_KEYS
        or normalized.endswith("_api_key")
        or normalized.endswith("_password")
        or normalized.endswith("_secret")
        or normalized.endswith("_token")
    )


def _redact_text(value: str) -> str:
    redacted = OPENAI_KEY_PATTERN.sub("sk-[redacted]", value)
    return MONGODB_CREDENTIAL_PATTERN.sub(r"\1[redacted]\3", redacted)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the MyMediaVault VM metadata and preview worker."
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
    )
    parser.add_argument(
        "--stale-processing-minutes",
        type=int,
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
    )
    args = parser.parse_args()
    settings = PreviewWorkerSettings()
    if args.max_concurrency is not None:
        settings.preview_worker_max_concurrency = args.max_concurrency
    if args.poll_interval_seconds is not None:
        settings.preview_worker_poll_interval_seconds = args.poll_interval_seconds
    if args.stale_processing_minutes is not None:
        settings.preview_repair_stale_processing_minutes = args.stale_processing_minutes
    if args.max_attempts is not None:
        settings.preview_max_attempts = args.max_attempts
    _configure_vm_worker_logging(settings)
    logger.info(
        "VM worker debug log enabled at {} with rotation={} retention={}",
        settings.vm_worker_debug_log_path,
        settings.vm_worker_debug_log_rotation,
        settings.vm_worker_debug_log_retention,
    )

    worker = PreviewWorker(
        settings=settings,
    )
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        worker.stop()
