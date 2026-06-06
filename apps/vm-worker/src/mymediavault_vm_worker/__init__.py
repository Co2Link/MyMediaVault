from __future__ import annotations

import argparse
import asyncio
import re
import sys
import tempfile
import time
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
from mymediavault_vm_worker.preview import (
    GeneratedFrame,
    GeneratedSheet,
    PreviewEngine,
    PreviewEngineConfig,
    PreviewRequest,
    PreviewResult,
    configure_default_logging,
)
from mymediavault_vm_worker.preview.core.models import (
    DEFAULT_ANCHOR_RETRY_RANGE_MB,
    DEFAULT_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS,
    DEFAULT_EXTRACT_FRAMES_PER_ANCHOR,
    DEFAULT_MAX_SELECTOR_CANDIDATES_PER_ANCHOR,
    DEFAULT_MIN_SELECTOR_CANDIDATES_PER_ANCHOR,
    DEFAULT_TORRENT_CACHE_MAX_MB,
)

from .actor_analysis import DEFAULT_MODELS_DIR, FaceModels, YuNetSFaceAnalyzer
from .actor_worker import (
    DEFAULT_ACTOR_ANALYSIS_LEASE_SECONDS,
    DEFAULT_ACTOR_ANALYSIS_MAX_ATTEMPTS,
    DEFAULT_ACTOR_ANALYSIS_POLL_INTERVAL_SECONDS,
    ActorAnalysisWorker,
)

DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_MAX_CONCURRENCY = 20
DEFAULT_STALE_PROCESSING_MINUTES = 120
DEFAULT_PREVIEW_SESSION_FAIRNESS_SECONDS = 2 * 60 * 60
DEFAULT_PREVIEW_FAILURE_LIMIT = 3
DEFAULT_EXTERNAL_FAILURE_COOLDOWN_SECONDS = 300
DEFAULT_PREVIEW_CACHE_DIR = Path("/var/cache/mymediavault/vm-worker")
DEFAULT_DEBUG_LOG_PATH = Path(".local/logs/vm-worker-debug.log")
DEFAULT_DEBUG_LOG_ROTATION = "100 MB"
DEFAULT_DEBUG_LOG_RETENTION = "7 days"
DEFAULT_METADATA_DHT_TIMEOUT_SECONDS = 600
SPARSE_CONTINUATION_LOG_INTERVAL_SECONDS = 10 * 60
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
MONGODB_CREDENTIAL_PATTERN = re.compile(r"(mongodb(?:\+srv)?://[^:/@\s]+:)([^@\s]+)(@)")


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
    preview_worker_enabled: bool = Field(
        default=True, alias="MMV_PREVIEW_WORKER_ENABLED"
    )
    actor_analysis_worker_enabled: bool = Field(
        default=True, alias="MMV_ACTOR_ANALYSIS_WORKER_ENABLED"
    )
    actor_analysis_models_dir: Path = Field(
        default=DEFAULT_MODELS_DIR, alias="MMV_ACTOR_ANALYSIS_MODELS_DIR"
    )
    actor_analysis_poll_interval_seconds: float = Field(
        default=DEFAULT_ACTOR_ANALYSIS_POLL_INTERVAL_SECONDS,
        alias="MMV_ACTOR_ANALYSIS_POLL_INTERVAL_SECONDS",
    )
    actor_analysis_lease_seconds: int = Field(
        default=DEFAULT_ACTOR_ANALYSIS_LEASE_SECONDS,
        alias="MMV_ACTOR_ANALYSIS_LEASE_SECONDS",
    )
    actor_analysis_max_attempts: int = Field(
        default=DEFAULT_ACTOR_ANALYSIS_MAX_ATTEMPTS,
        alias="MMV_ACTOR_ANALYSIS_MAX_ATTEMPTS",
    )
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
    preview_extract_frames_per_anchor: int = Field(
        default=DEFAULT_EXTRACT_FRAMES_PER_ANCHOR,
        alias="MMV_PREVIEW_EXTRACT_FRAMES_PER_ANCHOR",
    )
    preview_min_selector_candidates_per_anchor: int = Field(
        default=DEFAULT_MIN_SELECTOR_CANDIDATES_PER_ANCHOR,
        alias="MMV_PREVIEW_MIN_SELECTOR_CANDIDATES_PER_ANCHOR",
    )
    preview_max_selector_candidates_per_anchor: int = Field(
        default=DEFAULT_MAX_SELECTOR_CANDIDATES_PER_ANCHOR,
        alias="MMV_PREVIEW_MAX_SELECTOR_CANDIDATES_PER_ANCHOR",
    )
    preview_anchor_retry_range_mb: tuple[float, ...] = Field(
        default=DEFAULT_ANCHOR_RETRY_RANGE_MB,
        alias="MMV_PREVIEW_ANCHOR_RETRY_RANGE_MB",
    )
    preview_download_progress_timeout_seconds: float = Field(
        default=DEFAULT_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS,
        alias="MMV_PREVIEW_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS",
    )
    preview_session_fairness_seconds: float = Field(
        default=DEFAULT_PREVIEW_SESSION_FAIRNESS_SECONDS,
        alias="MMV_PREVIEW_SESSION_FAIRNESS_SECONDS",
    )
    preview_failure_limit: int = Field(
        default=DEFAULT_PREVIEW_FAILURE_LIMIT,
        alias="MMV_PREVIEW_FAILURE_LIMIT",
    )
    preview_external_failure_cooldown_seconds: int = Field(
        default=DEFAULT_EXTERNAL_FAILURE_COOLDOWN_SECONDS,
        alias="MMV_PREVIEW_EXTERNAL_FAILURE_COOLDOWN_SECONDS",
    )
    preview_cache_dir: Path = Field(
        default=DEFAULT_PREVIEW_CACHE_DIR,
        alias="MMV_PREVIEW_CACHE_DIR",
    )
    preview_cache_max_mb: float = Field(
        default=DEFAULT_TORRENT_CACHE_MAX_MB,
        alias="MMV_PREVIEW_CACHE_MAX_MB",
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
    metadata_fetch_timeout_seconds: int = Field(
        default=20, alias="MMV_TORRENT_FETCH_TIMEOUT_SECONDS"
    )
    metadata_resolver_urls: list[str] = Field(
        default_factory=lambda: ["https://itorrents.org/torrent/{info_hash}.torrent"],
        alias="MMV_TORRENT_RESOLVER_URLS",
    )
    metadata_dht_fallback_enabled: bool = Field(
        default=True, alias="MMV_TORRENT_DHT_FALLBACK_ENABLED"
    )
    metadata_dht_timeout_seconds: int = Field(
        default=DEFAULT_METADATA_DHT_TIMEOUT_SECONDS,
        alias="MMV_TORRENT_DHT_TIMEOUT_SECONDS",
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
        if (
            not self.preview_worker_enabled
            and not self.actor_analysis_worker_enabled
        ):
            msg = "At least one VM-worker pipeline must be enabled"
            raise ValueError(msg)
        if self.preview_worker_enabled and not (self.openai_api_key or "").strip():
            msg = "OPENAI_API_KEY must be set for torrent-preview Pydantic AI frame selection"
            raise ValueError(msg)
        if self.preview_extract_frames_per_anchor < 1:
            msg = "MMV_PREVIEW_EXTRACT_FRAMES_PER_ANCHOR must be at least 1"
            raise ValueError(msg)
        if self.preview_min_selector_candidates_per_anchor < 1:
            msg = "MMV_PREVIEW_MIN_SELECTOR_CANDIDATES_PER_ANCHOR must be at least 1"
            raise ValueError(msg)
        if (
            self.preview_min_selector_candidates_per_anchor
            > self.preview_max_selector_candidates_per_anchor
        ):
            msg = (
                "MMV_PREVIEW_MIN_SELECTOR_CANDIDATES_PER_ANCHOR must be less than "
                "or equal to MMV_PREVIEW_MAX_SELECTOR_CANDIDATES_PER_ANCHOR"
            )
            raise ValueError(msg)
        if (
            self.preview_max_selector_candidates_per_anchor
            > self.preview_extract_frames_per_anchor
        ):
            msg = (
                "MMV_PREVIEW_MAX_SELECTOR_CANDIDATES_PER_ANCHOR must be less than "
                "or equal to MMV_PREVIEW_EXTRACT_FRAMES_PER_ANCHOR"
            )
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
        if self.preview_session_fairness_seconds <= 0:
            msg = "MMV_PREVIEW_SESSION_FAIRNESS_SECONDS must be greater than 0"
            raise ValueError(msg)
        if self.preview_failure_limit <= 0:
            msg = "MMV_PREVIEW_FAILURE_LIMIT must be greater than 0"
            raise ValueError(msg)
        if self.preview_external_failure_cooldown_seconds <= 0:
            msg = "MMV_PREVIEW_EXTERNAL_FAILURE_COOLDOWN_SECONDS must be greater than 0"
            raise ValueError(msg)
        if self.preview_cache_max_mb <= 0:
            msg = "MMV_PREVIEW_CACHE_MAX_MB must be greater than 0"
            raise ValueError(msg)
        if not self.metadata_resolver_urls:
            msg = "MMV_TORRENT_RESOLVER_URLS must include at least one resolver URL"
            raise ValueError(msg)
        if self.torrent_provider not in {"fake", "http"}:
            msg = "MMV_TORRENT_PROVIDER must be fake or http"
            raise ValueError(msg)
        if self.actor_analysis_poll_interval_seconds <= 0:
            msg = "MMV_ACTOR_ANALYSIS_POLL_INTERVAL_SECONDS must be greater than 0"
            raise ValueError(msg)
        if self.actor_analysis_lease_seconds <= 0:
            msg = "MMV_ACTOR_ANALYSIS_LEASE_SECONDS must be greater than 0"
            raise ValueError(msg)
        if self.actor_analysis_max_attempts <= 0:
            msg = "MMV_ACTOR_ANALYSIS_MAX_ATTEMPTS must be greater than 0"
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
    processingState: str = "queued"
    processingPhase: str | None = None
    processingQueuedAt: datetime | None = None
    processingAvailableAt: datetime | None = None
    processingLeaseUntil: datetime | None = None
    processingFailureCount: int = 0
    processingLastOutcome: str | None = None
    processingLastError: str | None = None
    processingUpdatedAt: datetime | None = None
    processingDiagnostics: dict[str, Any] = Field(default_factory=dict)
    files: list[dict[str, Any]] = Field(default_factory=list)
    previewFrames: list[TorrentPreviewFrame] = Field(default_factory=list)
    previewSheet: TorrentPreviewSheet | None = None
    previewDiagnostics: TorrentPreviewDiagnostics = Field(
        default_factory=TorrentPreviewDiagnostics
    )
    systemActorIds: list[str] = Field(default_factory=list)
    userActorIds: list[str] = Field(default_factory=list)
    actorAnalysisStatus: str = "pending"
    actorAnalysisAttempts: int = 0
    actorAnalysisLastAttemptAt: datetime | None = None
    actorAnalysisUpdatedAt: datetime | None = None
    actorAnalysisLeaseUntil: datetime | None = None
    actorAnalysisFingerprint: str | None = None
    actorAnalysisError: str | None = None
    actorAnalysisDiagnostics: dict[str, Any] = Field(default_factory=dict)

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
            failure_kind = (
                "transient" if error.code in TRANSIENT_HTTP_STATUSES else "permanent"
            )
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
        if len(normalized) != 40 or any(
            char not in "0123456789abcdef" for char in normalized
        ):
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
                for alert in session.pop_alerts():
                    if "metadata" in str(alert).lower():
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


class MongoPreviewJobLease:
    def __init__(
        self,
        *,
        torrent: Torrent,
        blob_store: BlobStore,
        artifact_version: str,
        artifact_fingerprint: str,
    ) -> None:
        self._torrent = torrent
        self._blob_store = blob_store
        self._artifact_version = artifact_version
        self._artifact_fingerprint = artifact_fingerprint
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
        should_replace_artifacts = (
            _should_replace_preview_artifacts(self._torrent, result)
            or result.status == "failed"
        )
        stored_frames = (
            await self._store_frames(result.info_hash, result.artifact.frames)
            if should_replace_artifacts
            else []
        )
        stored_sheet = (
            await self._store_sheet(result.info_hash, result.artifact.sheet)
            if should_replace_artifacts
            else None
        )
        update_result = await Torrent.get_pymongo_collection().update_one(
            {"_id": self._torrent.id, "processingState": "running"},
            _success_update(
                result,
                stored_frames=stored_frames,
                stored_sheet=stored_sheet,
                artifact_version=self._artifact_version,
                artifact_fingerprint=self._artifact_fingerprint,
                replace_artifacts=should_replace_artifacts,
            ),
        )
        if should_replace_artifacts and update_result.matched_count:
            await self._delete_old_keys(
                _preview_keys_from_stored(stored_frames, stored_sheet)
            )

    async def fail(self, error: Exception) -> None:
        message = str(error) or error.__class__.__name__
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
                    "processingState": "running",
                    "processingUpdatedAt": datetime.now(UTC),
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


class TorrentProcessingScheduler:
    """Run FIFO torrent preview sessions with explicit slot ownership."""

    def __init__(
        self,
        *,
        settings: PreviewWorkerSettings,
        blob_store: BlobStore,
        engine: PreviewEngine,
    ) -> None:
        self._blob_store = blob_store
        self._engine = engine
        self._poll_interval_seconds = max(
            0.5, settings.preview_worker_poll_interval_seconds
        )
        self._max_concurrency = max(1, settings.preview_worker_max_concurrency)
        self._lease_seconds = max(
            60,
            settings.preview_repair_stale_processing_minutes * 60,
            round(settings.preview_session_fairness_seconds * 2),
        )
        self._fairness_seconds = settings.preview_session_fairness_seconds
        self._failure_limit = settings.preview_failure_limit
        self._external_failure_cooldown_seconds = (
            settings.preview_external_failure_cooldown_seconds
        )
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
            if settings.metadata_dht_fallback_enabled
            and settings.torrent_provider == "http"
            else None
        )
        self._stopping = False
        self._last_sparse_continuation_log_at: dict[str, float] = {}

    def stop(self) -> None:
        self._stopping = True

    async def run(self) -> None:
        logger.info(
            "Torrent processing scheduler started with max_concurrency={} fairness_seconds={}",
            self._max_concurrency,
            self._fairness_seconds,
        )
        await self._engine.start()
        tasks: set[asyncio.Task[None]] = set()
        try:
            while tasks or not self._stopping:
                await self._repair_stale_running()
                await self._queue_stale_artifacts()
                while not self._stopping and len(tasks) < self._max_concurrency:
                    torrent = await self._claim_one()
                    if torrent is None:
                        break
                    tasks.add(
                        asyncio.create_task(
                            self._run_session(torrent),
                            name=f"torrent-processing:{torrent.id}",
                        )
                    )
                if not tasks:
                    await asyncio.sleep(self._poll_interval_seconds)
                    continue
                done, tasks = await asyncio.wait(
                    tasks,
                    timeout=self._poll_interval_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self._engine.close()

    async def _claim_one(self) -> Torrent | None:
        now = datetime.now(UTC)
        document = await Torrent.get_pymongo_collection().find_one_and_update(
            {
                "processingState": {"$in": ["queued", "partial"]},
                "$or": [
                    {"processingAvailableAt": None},
                    {"processingAvailableAt": {"$lte": now}},
                    {"processingAvailableAt": {"$exists": False}},
                ],
            },
            {
                "$set": {
                    "processingState": "running",
                    "processingPhase": "resolving_metadata",
                    "processingLeaseUntil": now + timedelta(seconds=self._lease_seconds),
                    "processingLastOutcome": "running",
                    "processingLastError": None,
                    "processingUpdatedAt": now,
                    "processingAvailableAt": None,
                }
            },
            sort=[("processingQueuedAt", 1), ("_id", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            return None
        torrent = Torrent.model_validate(document)
        logger.bind(
            job_id=torrent.id,
            info_hash=torrent.infoHash,
            queued_at=torrent.processingQueuedAt,
        ).debug("Claimed FIFO torrent processing session")
        return torrent

    async def _repair_stale_running(self) -> None:
        now = datetime.now(UTC)
        result = await Torrent.get_pymongo_collection().update_many(
            {
                "processingState": "running",
                "$or": [
                    {"processingLeaseUntil": None},
                    {"processingLeaseUntil": {"$lt": now}},
                    {"processingLeaseUntil": {"$exists": False}},
                ],
            },
            {
                "$set": {
                    "processingState": "queued",
                    "processingPhase": None,
                    "processingQueuedAt": now,
                    "processingAvailableAt": None,
                    "processingLeaseUntil": None,
                    "processingLastOutcome": "lease_expired",
                    "processingUpdatedAt": now,
                }
            },
        )
        if result.modified_count:
            logger.info("Requeued {} stale torrent processing sessions", result.modified_count)

    async def _queue_stale_artifacts(self) -> None:
        now = datetime.now(UTC)
        result = await Torrent.get_pymongo_collection().update_many(
            {
                "processingState": "complete",
                "$or": [
                    {"previewDiagnostics.artifactVersion": {"$ne": self._engine.artifact_version}},
                    {
                        "previewDiagnostics.artifactFingerprint": {
                            "$ne": self._engine.artifact_fingerprint
                        }
                    },
                ],
            },
            {
                "$set": {
                    "processingState": "queued",
                    "processingPhase": None,
                    "processingQueuedAt": now,
                    "processingAvailableAt": None,
                    "processingLeaseUntil": None,
                    "processingLastOutcome": "artifact_stale",
                    "processingUpdatedAt": now,
                }
            },
        )
        if result.modified_count:
            logger.info("Queued {} torrents with stale preview artifacts", result.modified_count)

    async def _run_session(self, torrent: Torrent) -> None:
        started_at = time.monotonic()
        last_downloaded_bytes = 0
        last_complete_piece_count = 0
        last_decode_complete_piece_count: int | None = None
        lease = MongoPreviewJobLease(
            torrent=torrent,
            blob_store=self._blob_store,
            artifact_version=self._engine.artifact_version,
            artifact_fingerprint=self._engine.artifact_fingerprint,
        )
        try:
            torrent = await self._ensure_metadata(torrent)
            lease = MongoPreviewJobLease(
                torrent=torrent,
                blob_store=self._blob_store,
                artifact_version=self._engine.artifact_version,
                artifact_fingerprint=self._engine.artifact_fingerprint,
            )
            while not self._stopping:
                await self._set_phase(torrent.id, "generating_preview")
                torrent_bytes = await lease.load_torrent_bytes()
                async with self._engine.preview_artifact(
                    PreviewRequest(
                        torrent_bytes=torrent_bytes,
                        min_complete_piece_count=last_decode_complete_piece_count,
                    )
                ) as result:
                    await lease.complete(result)
                made_useful_progress = _made_useful_progress(
                    result,
                    last_downloaded_bytes=last_downloaded_bytes,
                    last_complete_piece_count=last_complete_piece_count,
                )
                last_downloaded_bytes = max(
                    last_downloaded_bytes,
                    result.diagnostics.downloaded_bytes,
                )
                last_complete_piece_count = max(
                    last_complete_piece_count,
                    result.diagnostics.last_complete_piece_count or 0,
                )
                if result.artifact.frames or result.status == "failed":
                    last_decode_complete_piece_count = (
                        result.diagnostics.last_complete_piece_count
                    )
                if result.status == "succeeded":
                    await self._finish(torrent, "complete", "completed")
                    return
                if _is_permanent_preview_failure(result):
                    await self._finish(
                        torrent,
                        "exhausted",
                        "invalid_media",
                        result.status_reason,
                    )
                    return
                if _is_external_preview_failure(result):
                    await self._fail_or_requeue(torrent, result.status_reason)
                    return
                queue_pressure = await self._has_queued_work(exclude_id=torrent.id)
                fairness_elapsed = time.monotonic() - started_at >= self._fairness_seconds
                if queue_pressure and (fairness_elapsed or not made_useful_progress):
                    outcome = (
                        "yielded_fairness" if fairness_elapsed else "yielded_inactive"
                    )
                    await self._yield(torrent, result, outcome)
                    return
                self._log_sparse_continuation(
                    torrent,
                    result,
                    made_useful_progress=made_useful_progress,
                    queue_pressure=queue_pressure,
                )
            await self._requeue(torrent, "worker_stopped")
        except MetadataResolutionError as error:
            if error.failure_kind == "permanent":
                await self._finish(torrent, "exhausted", "invalid_metadata", str(error))
            else:
                await self._fail_or_requeue(torrent, str(error), outcome="metadata_unavailable")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("Unexpected torrent processing failure for {}", torrent.id)
            await self._fail_or_requeue(torrent, str(error) or error.__class__.__name__)
        finally:
            await self._engine.release_session(torrent.infoHash)

    async def _ensure_metadata(self, torrent: Torrent) -> Torrent:
        if torrent.rawBlobKey:
            return torrent
        try:
            metadata = await self._resolver.fetch(torrent.infoHash)
        except MetadataResolutionError as http_error:
            if self._dht_resolver is None:
                raise
            try:
                metadata = await self._dht_resolver.fetch(torrent.infoHash)
                metadata["resolverDiagnostics"] = [
                    *http_error.diagnostics.get("resolvers", []),
                    *metadata["resolverDiagnostics"],
                ]
            except MetadataResolutionError as dht_error:
                raise _combine_metadata_errors(http_error, dht_error) from dht_error
        blob_key = f"torrents/{torrent.infoHash}.torrent"
        await self._blob_store.put_bytes(blob_key, metadata["raw"], "application/x-bittorrent")
        await Torrent.get_pymongo_collection().update_one(
            {"_id": torrent.id, "processingState": "running"},
            {
                "$set": {
                    "name": metadata["name"],
                    "sizeBytes": metadata["sizeBytes"],
                    "rawBlobKey": blob_key,
                    "files": metadata["files"],
                    "processingDiagnostics.metadata": {
                        "resolvers": metadata["resolverDiagnostics"],
                    },
                }
            },
        )
        torrent.rawBlobKey = blob_key
        torrent.name = metadata["name"]
        torrent.sizeBytes = metadata["sizeBytes"]
        torrent.files = metadata["files"]
        return torrent

    async def _set_phase(self, torrent_id: str, phase: str) -> None:
        now = datetime.now(UTC)
        await Torrent.get_pymongo_collection().update_one(
            {"_id": torrent_id, "processingState": "running"},
            {
                "$set": {
                    "processingPhase": phase,
                    "processingLeaseUntil": now + timedelta(seconds=self._lease_seconds),
                    "processingUpdatedAt": now,
                }
            },
        )

    async def _has_queued_work(self, *, exclude_id: str) -> bool:
        now = datetime.now(UTC)
        return (
            await Torrent.get_pymongo_collection().find_one(
                {
                    "_id": {"$ne": exclude_id},
                    "processingState": {"$in": ["queued", "partial"]},
                    "$or": [
                        {"processingAvailableAt": None},
                        {"processingAvailableAt": {"$lte": now}},
                        {"processingAvailableAt": {"$exists": False}},
                    ],
                },
                {"_id": 1},
            )
            is not None
        )

    async def _yield(self, torrent: Torrent, result: PreviewResult, outcome: str) -> None:
        state = "partial" if result.artifact.frames or torrent.previewFrames else "queued"
        await self._requeue(torrent, outcome, state=state)

    async def _fail_or_requeue(
        self,
        torrent: Torrent,
        error: str,
        *,
        outcome: str = "transient_failure",
    ) -> None:
        failure_count = torrent.processingFailureCount + 1
        if failure_count >= self._failure_limit:
            await self._finish(torrent, "exhausted", "failure_limit_reached", error, failure_count)
            return
        torrent.processingFailureCount = failure_count
        await self._requeue(
            torrent,
            outcome,
            error,
            failure_count=failure_count,
            cooldown_seconds=self._external_failure_cooldown_seconds,
        )

    def _log_sparse_continuation(
        self,
        torrent: Torrent,
        result: PreviewResult,
        *,
        made_useful_progress: bool,
        queue_pressure: bool,
    ) -> None:
        now = time.monotonic()
        last_logged_at = self._last_sparse_continuation_log_at.get(torrent.id)
        should_log = (
            made_useful_progress
            or last_logged_at is None
            or now - last_logged_at >= SPARSE_CONTINUATION_LOG_INTERVAL_SECONDS
        )
        if not should_log:
            return
        self._last_sparse_continuation_log_at[torrent.id] = now
        logger.bind(
            job_id=torrent.id,
            info_hash=torrent.infoHash,
            status=result.status,
            downloaded_bytes=result.diagnostics.downloaded_bytes,
            complete_piece_count=result.diagnostics.last_complete_piece_count,
            peer_count=result.diagnostics.last_num_peers,
            seed_count=result.diagnostics.last_num_seeds,
            made_useful_progress=made_useful_progress,
            queue_pressure=queue_pressure,
        ).debug("Continuing torrent session without yielding")

    async def _requeue(
        self,
        torrent: Torrent,
        outcome: str,
        error: str | None = None,
        *,
        state: str = "queued",
        failure_count: int | None = None,
        cooldown_seconds: int | None = None,
    ) -> None:
        now = datetime.now(UTC)
        values: dict[str, Any] = {
            "processingState": state,
            "processingPhase": None,
            "processingQueuedAt": now,
            "processingAvailableAt": (
                now + timedelta(seconds=cooldown_seconds)
                if cooldown_seconds is not None
                else None
            ),
            "processingLeaseUntil": None,
            "processingLastOutcome": outcome,
            "processingLastError": error,
            "processingUpdatedAt": now,
        }
        if failure_count is not None:
            values["processingFailureCount"] = failure_count
        await Torrent.get_pymongo_collection().update_one(
            {"_id": torrent.id, "processingState": "running"},
            {"$set": values},
        )
        logger.bind(job_id=torrent.id, info_hash=torrent.infoHash, outcome=outcome).info(
            "Queued torrent processing session at FIFO tail"
        )

    async def _finish(
        self,
        torrent: Torrent,
        state: str,
        outcome: str,
        error: str | None = None,
        failure_count: int | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "processingState": state,
            "processingPhase": None,
            "processingAvailableAt": None,
            "processingLeaseUntil": None,
            "processingLastOutcome": outcome,
            "processingLastError": error,
            "processingUpdatedAt": datetime.now(UTC),
        }
        if failure_count is not None:
            values["processingFailureCount"] = failure_count
        await Torrent.get_pymongo_collection().update_one(
            {"_id": torrent.id, "processingState": "running"},
            {"$set": values},
        )
        logger.bind(job_id=torrent.id, info_hash=torrent.infoHash, outcome=outcome).info(
            "Finished torrent processing session"
        )


def _is_permanent_preview_failure(result: PreviewResult) -> bool:
    return result.status == "failed" and (
        result.diagnostics.selected_file is None
        or "no downloadable bytes" in result.status_reason.lower()
    )


def _made_useful_progress(
    result: PreviewResult,
    *,
    last_downloaded_bytes: int,
    last_complete_piece_count: int,
) -> bool:
    del last_downloaded_bytes
    return (result.diagnostics.last_complete_piece_count or 0) > last_complete_piece_count


def _is_external_preview_failure(result: PreviewResult) -> bool:
    return result.status == "failed" and any(
        warning.startswith("Preview decode/selection failed:")
        for warning in result.diagnostics.warnings
    )


class PreviewWorker:
    def __init__(
        self,
        *,
        settings: PreviewWorkerSettings,
    ) -> None:
        self._settings = settings
        self._client = AsyncMongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
        )
        self._database = self._client[settings.mongodb_database]
        self._blob_store = BlobStore(settings)
        if settings.actor_analysis_worker_enabled:
            face_models = FaceModels.from_manifest(
                models_dir=settings.actor_analysis_models_dir
            )
            self._actor_analysis_worker = ActorAnalysisWorker(
                database=self._database,
                blob_store=self._blob_store,
                analyzer=YuNetSFaceAnalyzer(models=face_models),
                model_version=face_models.version,
                poll_interval_seconds=settings.actor_analysis_poll_interval_seconds,
                lease_seconds=settings.actor_analysis_lease_seconds,
                max_attempts=settings.actor_analysis_max_attempts,
            )
        else:
            self._actor_analysis_worker = None
        self._config = (
            PreviewEngineConfig(
                extract_frames_per_anchor=settings.preview_extract_frames_per_anchor,
                min_selector_candidates_per_anchor=(
                    settings.preview_min_selector_candidates_per_anchor
                ),
                max_selector_candidates_per_anchor=(
                    settings.preview_max_selector_candidates_per_anchor
                ),
                anchor_retry_range_mb=settings.preview_anchor_retry_range_mb,
                download_progress_timeout_seconds=(
                    settings.preview_download_progress_timeout_seconds
                ),
                torrent_cache_dir=settings.preview_cache_dir,
                torrent_cache_max_mb=settings.preview_cache_max_mb,
            )
            if settings.preview_worker_enabled
            else None
        )
        self._engine = PreviewEngine(config=self._config) if self._config else None
        self._torrent_processing_scheduler = (
            TorrentProcessingScheduler(
                settings=settings,
                blob_store=self._blob_store,
                engine=self._engine,
            )
            if self._engine is not None
            else None
        )

    async def run(self) -> None:
        await init_beanie(database=self._database, document_models=[Torrent])
        logger.info(
            "VM worker started with torrent_processing_enabled={} actor_analysis_enabled={}",
            self._torrent_processing_scheduler is not None,
            self._actor_analysis_worker is not None,
        )
        tasks: list[asyncio.Task[None]] = []
        if self._torrent_processing_scheduler is not None:
            logger.info(
                "Torrent processing worker started with artifact_version={} artifact_fingerprint={}",
                self._engine.artifact_version if self._engine else None,
                self._engine.artifact_fingerprint if self._engine else None,
            )
            tasks.append(asyncio.create_task(self._torrent_processing_scheduler.run()))
        if self._actor_analysis_worker is not None:
            tasks.append(asyncio.create_task(self._actor_analysis_worker.run()))
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
            if self._torrent_processing_scheduler is not None:
                self._torrent_processing_scheduler.stop()
            if self._actor_analysis_worker is not None:
                self._actor_analysis_worker.stop()
            await self._client.close()

    def stop(self) -> None:
        if self._torrent_processing_scheduler is not None:
            self._torrent_processing_scheduler.stop()
        if self._actor_analysis_worker is not None:
            self._actor_analysis_worker.stop()


def _success_update(
    result: PreviewResult,
    *,
    stored_frames: list[dict[str, Any]],
    stored_sheet: dict[str, Any] | None,
    artifact_version: str,
    artifact_fingerprint: str,
    replace_artifacts: bool = True,
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
        "processingState": "running",
        "processingUpdatedAt": now,
        "previewDiagnostics": diagnostics,
    }
    if replace_artifacts:
        values["previewFrames"] = stored_frames
        values["previewSheet"] = stored_sheet
        values["actorAnalysisStatus"] = "pending"
        values["actorAnalysisAttempts"] = 0
        values["actorAnalysisLeaseUntil"] = None
        values["actorAnalysisError"] = None
    return {"$set": values}


def _should_replace_preview_artifacts(torrent: Torrent, result: PreviewResult) -> bool:
    if result.status == "succeeded":
        return True
    if result.status != "partial" or not result.artifact.frames:
        return False
    current_count = len(torrent.previewFrames)
    new_count = len(result.artifact.frames)
    if new_count > current_count:
        return True
    if new_count < current_count:
        return False
    return _selected_anchor_count(result) > _stored_selected_anchor_count(torrent)


def _selected_anchor_count(result: PreviewResult) -> int:
    frame_selection = result.diagnostics.frame_selection
    if frame_selection is None:
        return 0
    return len(set(frame_selection.selected_anchor_indexes))


def _stored_selected_anchor_count(torrent: Torrent) -> int:
    frame_selection = torrent.previewDiagnostics.details.get("frame_selection")
    if not isinstance(frame_selection, dict):
        return 0
    selected = frame_selection.get("selected_anchor_indexes")
    if not isinstance(selected, list):
        return 0
    return len({item for item in selected if isinstance(item, int)})


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
    args = parser.parse_args()
    settings = PreviewWorkerSettings()
    if args.max_concurrency is not None:
        settings.preview_worker_max_concurrency = args.max_concurrency
    if args.poll_interval_seconds is not None:
        settings.preview_worker_poll_interval_seconds = args.poll_interval_seconds
    if args.stale_processing_minutes is not None:
        settings.preview_repair_stale_processing_minutes = args.stale_processing_minutes
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
