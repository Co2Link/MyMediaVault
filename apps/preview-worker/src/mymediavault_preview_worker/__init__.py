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
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
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
        if not self.openai_api_key.strip():
            msg = "OPENAI_API_KEY must be set for torrent-preview Pydantic AI ranking"
            raise ValueError(msg)
        if self.preview_target_frames not in {3, 9, 16}:
            msg = "MMV_PREVIEW_TARGET_FRAMES must be one of 3, 9, or 16"
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
    rawBlobKey: str | None = None
    metadataStatus: str = "pending"
    previewStatus: str = "pending"
    previewAttempts: int = 0
    previewLastAttemptAt: datetime | None = None
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


class MongoPreviewJobLease(PreviewJobLease):
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
        return await asyncio.to_thread(self._blob_store.get_bytes, raw_blob_key)

    async def complete(self, result: PreviewResult) -> None:
        stored_frames = await self._store_frames(result.info_hash, result.artifact.frames)
        stored_sheet = await self._store_sheet(result.info_hash, result.artifact.sheet)
        has_replacement_artifacts = bool(stored_frames or stored_sheet)
        await Torrent.get_pymongo_collection().update_one(
            {"_id": self._torrent.id},
            _success_update(
                result,
                stored_frames=stored_frames,
                stored_sheet=stored_sheet,
                artifact_version=self._artifact_version,
                artifact_fingerprint=self._artifact_fingerprint,
                replace_artifacts=has_replacement_artifacts,
            ),
        )
        if has_replacement_artifacts:
            await self._delete_old_keys(
                _preview_keys_from_stored(stored_frames, stored_sheet)
            )

    async def fail(self, error: Exception) -> None:
        message = str(error) or error.__class__.__name__
        await Torrent.get_pymongo_collection().update_one(
            {"_id": self._torrent.id},
            {
                "$set": {
                    "previewStatus": "failed",
                    "previewUpdatedAt": datetime.now(UTC),
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
    ) -> None:
        self._blob_store = blob_store
        self._stale_processing_minutes = max(1, stale_processing_minutes)
        self._max_attempts = max(1, max_attempts)

    async def claim_batch(
        self,
        *,
        limit: int,
        artifact_version: str,
        artifact_fingerprint: str,
    ) -> list[MongoPreviewJobLease]:
        await self._repair_stale_processing()
        claimed: list[MongoPreviewJobLease] = []
        for query, reset_attempts in self._claim_plans(
            artifact_version=artifact_version,
            artifact_fingerprint=artifact_fingerprint,
        ):
            while len(claimed) < limit:
                torrent = await self._claim_one(query, reset_attempts=reset_attempts)
                if torrent is None:
                    break
                claimed.append(
                    MongoPreviewJobLease(
                        torrent=torrent,
                        blob_store=self._blob_store,
                        artifact_version=artifact_version,
                        artifact_fingerprint=artifact_fingerprint,
                    )
                )
            if len(claimed) >= limit:
                break
        return claimed

    def _claim_plans(
        self,
        *,
        artifact_version: str,
        artifact_fingerprint: str,
    ) -> list[tuple[dict[str, Any], bool]]:
        pending_query, retry_query = self._claim_queries(
            artifact_version=artifact_version,
            artifact_fingerprint=artifact_fingerprint,
        )
        return [
            (pending_query, False),
            (
                self._artifact_stale_query(
                    artifact_version=artifact_version,
                    artifact_fingerprint=artifact_fingerprint,
                ),
                True,
            ),
            (retry_query, False),
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
                    "previewAttempts": 1,
                },
            }
            if reset_attempts
            else {
                "$set": {
                    "previewStatus": "processing",
                    "previewLastAttemptAt": now,
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
        self._config = PreviewEngineConfig(
            target_frames=settings.preview_target_frames,
        )
        self._engine = PreviewEngine(config=self._config)
        self._harness: PreviewWorkerHarness | None = None

    async def run(self) -> None:
        await init_beanie(database=self._database, document_models=[Torrent])
        job_source = MongoPreviewJobSource(
            blob_store=self._blob_store,
            stale_processing_minutes=self._stale_processing_minutes,
            max_attempts=self._max_attempts,
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
            "Preview worker started with max_concurrency={} artifact_version={} artifact_fingerprint={}",
            self._max_concurrency,
            self._engine.artifact_version,
            self._engine.artifact_fingerprint,
        )
        try:
            await self._harness.run()
        finally:
            await self._client.close()
            self._harness = None

    def stop(self) -> None:
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
            "previewDiagnostics": diagnostics,
    }
    if replace_artifacts:
        values["previewFrames"] = stored_frames
        values["previewSheet"] = stored_sheet
    return {"$set": values}


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


def main() -> None:
    configure_default_logging(debug=False)
    parser = argparse.ArgumentParser(
        description="Run the MyMediaVault torrent preview worker."
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

    worker = PreviewWorker(
        settings=settings,
    )
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        worker.stop()
