from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger
from pymongo import ReturnDocument

from mymediavault_vm_worker.metadata import (
    DhtTorrentMetadataResolver,
    FakeTorrentMetadataResolver,
    HttpTorrentMetadataResolver,
    MetadataResolutionError,
    _combine_metadata_errors,
)
from mymediavault_vm_worker.models import Torrent
from mymediavault_vm_worker.preview import (
    GeneratedFrame,
    GeneratedSheet,
    PreviewEngine,
    PreviewRequest,
    PreviewResult,
)
from mymediavault_vm_worker.settings import (
    SPARSE_CONTINUATION_LOG_INTERVAL_SECONDS,
    PreviewWorkerSettings,
)
from mymediavault_vm_worker.storage import BlobStore

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
                    last_complete_piece_count=last_complete_piece_count,
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
    last_complete_piece_count: int,
) -> bool:
    return (result.diagnostics.last_complete_piece_count or 0) > last_complete_piece_count


def _is_external_preview_failure(result: PreviewResult) -> bool:
    return result.status == "failed" and any(
        warning.startswith("Preview decode/selection failed:")
        for warning in result.diagnostics.warnings
    )


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

