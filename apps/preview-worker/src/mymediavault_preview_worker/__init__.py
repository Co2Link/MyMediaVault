from __future__ import annotations

import argparse
import asyncio
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
    PreviewContext,
    PreviewEngine,
    PreviewEngineConfig,
    PreviewOutput,
    PreviewOutputHandler,
    PreviewRequest,
    StoredFrame,
    StoredPreview,
    StoredSheet,
)

DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_MAX_CONCURRENCY = 20
DEFAULT_STALE_PROCESSING_MINUTES = 120


class PreviewWorkerSettings(BaseSettings):
    mongodb_uri: str = Field(alias="MONGODB_URI")
    mongodb_database: str = Field(default="mymediavault", alias="MMV_MONGODB_DB_NAME")
    mongodb_server_selection_timeout_ms: int = Field(default=10000, alias="MMV_MONGODB_SERVER_SELECTION_TIMEOUT_MS")
    r2_endpoint: str | None = Field(default=None, alias="R2_ENDPOINT")
    r2_access_key_id: str | None = Field(default=None, alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str | None = Field(default=None, alias="R2_SECRET_ACCESS_KEY")
    r2_bucket_name: str = Field(default="torrent-raw", alias="R2_BUCKET_NAME")
    preview_worker_max_concurrency: int = Field(default=DEFAULT_MAX_CONCURRENCY, alias="MMV_PREVIEW_WORKER_MAX_CONCURRENCY")
    preview_worker_poll_interval_seconds: float = Field(
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        alias="MMV_PREVIEW_WORKER_POLL_INTERVAL_SECONDS",
    )
    preview_repair_stale_processing_minutes: int = Field(
        default=DEFAULT_STALE_PROCESSING_MINUTES,
        alias="MMV_PREVIEW_REPAIR_STALE_PROCESSING_MINUTES",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @model_validator(mode="after")
    def validate_storage_credentials(self) -> PreviewWorkerSettings:
        credentials = [self.r2_endpoint, self.r2_access_key_id, self.r2_secret_access_key]
        if any(credentials) and not all(credentials):
            msg = "R2_ENDPOINT, R2_ACCESS_KEY_ID, and R2_SECRET_ACCESS_KEY must be set together"
            raise ValueError(msg)
        return self

    @property
    def use_r2(self) -> bool:
        return bool(self.r2_endpoint and self.r2_access_key_id and self.r2_secret_access_key)


class TorrentPreviewFrame(BaseModel):
    key: str
    width: int
    height: int
    timestampSeconds: float
    score: float
    metadata: dict[str, str] = Field(default_factory=dict)


class TorrentPreviewSheet(BaseModel):
    key: str
    width: int
    height: int
    mimeType: str
    metadata: dict[str, str] = Field(default_factory=dict)


class TorrentPreviewDiagnostics(BaseModel):
    artifactVersion: str | None = None
    artifactFingerprint: str | None = None
    downloadedBytes: int | None = None
    elapsedSeconds: float | None = None
    attempts: int | None = None
    strategyName: str | None = None
    selectedFilePath: str | None = None
    selectedFileSizeBytes: int | None = None
    failureReason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class Torrent(Document):
    id: str = Field(alias="_id")
    infoHash: str
    rawBlobKey: str | None = None
    metadataStatus: str = "pending"
    previewStatus: str = "pending"
    previewError: str | None = None
    previewAttempts: int = 0
    previewLastAttemptAt: datetime | None = None
    previewUpdatedAt: datetime | None = None
    previewFrames: list[TorrentPreviewFrame] = Field(default_factory=list)
    previewSheet: TorrentPreviewSheet | None = None
    previewDiagnostics: TorrentPreviewDiagnostics = Field(default_factory=TorrentPreviewDiagnostics)

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
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket_name, Key=key)

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


class R2PreviewOutputHandler(PreviewOutputHandler):
    def __init__(self, blob_store: BlobStore) -> None:
        self._blob_store = blob_store

    async def handle(
        self,
        context: PreviewContext,
        output: PreviewOutput,
    ) -> StoredPreview:
        frames: list[StoredFrame] = []
        for index, frame in enumerate(output.frames, start=1):
            suffix = frame.path.suffix or ".jpg"
            key = (
                f"previews/{context.info_hash}/"
                f"frame_{index:03d}_{int(frame.timestamp_seconds * 1000):012d}{suffix}"
            )
            await self._blob_store.put_file(key, frame.path, "image/jpeg")
            frames.append(
                StoredFrame(
                    uri=key,
                    score=frame.score,
                    width=frame.width,
                    height=frame.height,
                    timestamp_seconds=frame.timestamp_seconds,
                    metadata={
                        "selected_file": context.selected_file.path,
                        "timestamp_seconds": f"{frame.timestamp_seconds:.3f}",
                        "width": str(frame.width),
                        "height": str(frame.height),
                        "score": f"{frame.score:.6f}",
                        "anchor_index": ""
                        if frame.anchor_index is None
                        else str(frame.anchor_index),
                        "anchor_ratio": ""
                        if frame.anchor_ratio is None
                        else f"{frame.anchor_ratio:.6f}",
                        "decode_method": frame.decode_method,
                    },
                )
            )

        sheet = None
        if output.sheet is not None:
            key = f"previews/{context.info_hash}/preview_sheet.jpg"
            await self._blob_store.put_file(key, output.sheet.path, output.sheet.mime_type)
            sheet = StoredSheet(
                uri=key,
                width=output.sheet.width,
                height=output.sheet.height,
                mime_type=output.sheet.mime_type,
                metadata=dict(output.sheet.metadata),
            )

        return StoredPreview(frames=frames, sheet=sheet)


class PreviewWorker:
    def __init__(
        self,
        *,
        settings: PreviewWorkerSettings,
    ) -> None:
        self._settings = settings
        self._max_concurrency = max(1, settings.preview_worker_max_concurrency)
        self._poll_interval_seconds = max(0.5, settings.preview_worker_poll_interval_seconds)
        self._stale_processing_minutes = max(1, settings.preview_repair_stale_processing_minutes)
        self._client = AsyncMongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
        )
        self._database = self._client[settings.mongodb_database]
        self._blob_store = BlobStore(settings)
        self._config = PreviewEngineConfig()
        self._artifact_fingerprint = self._config.artifact_fingerprint()
        self._engine = PreviewEngine(
            config=self._config,
            output_handler=R2PreviewOutputHandler(self._blob_store),
        )
        self._stopping = False

    async def run(self) -> None:
        await init_beanie(database=self._database, document_models=[Torrent])
        await self._engine.start()
        logger.info(
            "Preview worker started with max_concurrency={} artifact_fingerprint={}",
            self._max_concurrency,
            self._artifact_fingerprint,
        )
        try:
            while not self._stopping:
                await self._repair_stale_processing()
                torrents = await self._claim_batch()
                if not torrents:
                    await asyncio.sleep(self._poll_interval_seconds)
                    continue
                await asyncio.gather(*(self._process_torrent(torrent) for torrent in torrents))
        finally:
            await self._engine.close()
            await self._client.close()

    def stop(self) -> None:
        self._stopping = True

    async def _claim_batch(self) -> list[Torrent]:
        claimed: list[Torrent] = []
        for query in self._claim_queries():
            while len(claimed) < self._max_concurrency:
                torrent = await self._claim_one(query)
                if torrent is None:
                    break
                claimed.append(torrent)
            if len(claimed) >= self._max_concurrency:
                break
        return claimed

    def _claim_queries(self) -> list[dict[str, Any]]:
        base = {
            "metadataStatus": "succeeded",
            "rawBlobKey": {"$type": "string", "$ne": ""},
        }
        return [
            {
                **base,
                "$or": [
                    {"previewStatus": {"$exists": False}},
                    {"previewStatus": "pending"},
                ],
            },
            {
                **base,
                "previewStatus": "succeeded",
                "previewDiagnostics.artifactFingerprint": {"$ne": self._artifact_fingerprint},
            },
        ]

    async def _claim_one(self, query: dict[str, Any]) -> Torrent | None:
        now = datetime.now(UTC)
        document = await Torrent.get_pymongo_collection().find_one_and_update(
            query,
            {
                "$set": {
                    "previewStatus": "processing",
                    "previewError": None,
                    "previewLastAttemptAt": now,
                },
                "$inc": {"previewAttempts": 1},
            },
            sort=[("updatedAt", 1), ("_id", 1)],
            return_document=ReturnDocument.AFTER,
        )
        return Torrent.model_validate(document) if document else None

    async def _repair_stale_processing(self) -> None:
        stale_before = datetime.now(UTC) - timedelta(minutes=self._stale_processing_minutes)
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
                    "previewError": "Preview processing timed out and was requeued.",
                }
            },
        )
        if result.modified_count:
            logger.info("Requeued {} stale preview jobs", result.modified_count)

    async def _process_torrent(self, torrent: Torrent) -> None:
        torrent_id = torrent.id
        info_hash = torrent.infoHash
        raw_blob_key = torrent.rawBlobKey
        if raw_blob_key is None:
            return
        old_keys = _preview_keys(torrent)
        logger.info("Generating preview for torrent {}", info_hash)

        try:
            raw_torrent = await asyncio.to_thread(self._blob_store.get_bytes, raw_blob_key)
            result = await self._engine.preview(PreviewRequest(torrent_bytes=raw_torrent))
            update = _success_update(result)
            await Torrent.get_pymongo_collection().update_one({"_id": torrent_id}, update)
            await self._delete_old_keys(old_keys, _preview_keys_from_result(result))
            logger.info("Preview finished for torrent {} with status {}", info_hash, result.status)
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            await Torrent.get_pymongo_collection().update_one(
                {"_id": torrent_id},
                {
                    "$set": {
                        "previewStatus": "failed",
                        "previewError": message,
                        "previewUpdatedAt": datetime.now(UTC),
                        "previewDiagnostics.failureReason": message,
                    }
                },
            )
            logger.exception("Preview failed for torrent {}", info_hash)

    async def _delete_old_keys(self, old_keys: set[str], new_keys: set[str]) -> None:
        for key in old_keys - new_keys:
            await self._blob_store.delete_if_exists(key)


def _success_update(result: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    selected_file = result.selected_file
    diagnostics = {
        "artifactVersion": result.artifact_version,
        "artifactFingerprint": result.artifact_fingerprint,
        "downloadedBytes": result.downloaded_bytes,
        "elapsedSeconds": result.elapsed_seconds,
        "attempts": result.attempts,
        "strategyName": result.strategy_name,
        "selectedFilePath": selected_file.path if selected_file else None,
        "selectedFileSizeBytes": selected_file.length if selected_file else None,
        "failureReason": result.failure_reason,
        "warnings": result.warnings,
        "details": _to_plain_dict(result.diagnostics),
    }
    return {
        "$set": {
            "previewStatus": result.status,
            "previewError": result.failure_reason,
            "previewUpdatedAt": now,
            "previewFrames": [
                {
                    "key": frame.uri,
                    "width": frame.width,
                    "height": frame.height,
                    "timestampSeconds": frame.timestamp_seconds,
                    "score": frame.score,
                    "metadata": dict(frame.metadata),
                }
                for frame in result.frames
            ],
            "previewSheet": None
            if result.sheet is None
            else {
                "key": result.sheet.uri,
                "width": result.sheet.width,
                "height": result.sheet.height,
                "mimeType": result.sheet.mime_type,
                "metadata": dict(result.sheet.metadata),
            },
            "previewDiagnostics": diagnostics,
        }
    }


def _preview_keys(torrent: Torrent) -> set[str]:
    keys = {frame.key for frame in torrent.previewFrames if frame.key}
    sheet = torrent.previewSheet
    if sheet and sheet.key:
        keys.add(sheet.key)
    return keys


def _preview_keys_from_result(result: Any) -> set[str]:
    keys = {frame.uri for frame in result.frames}
    if result.sheet is not None:
        keys.add(result.sheet.uri)
    return keys


def _to_plain_dict(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MyMediaVault torrent preview worker.")
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

    worker = PreviewWorker(
        settings=settings,
    )
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        worker.stop()
