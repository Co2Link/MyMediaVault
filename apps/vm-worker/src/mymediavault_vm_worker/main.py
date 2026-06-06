from __future__ import annotations

import argparse
import asyncio

from beanie import init_beanie
from loguru import logger
from pymongo import AsyncMongoClient

from mymediavault_vm_worker.actor.config import FaceModels
from mymediavault_vm_worker.actor.vision import YuNetSFaceAnalyzer
from mymediavault_vm_worker.actor.worker import ActorAnalysisWorker
from mymediavault_vm_worker.logging import _configure_vm_worker_logging
from mymediavault_vm_worker.models import Torrent
from mymediavault_vm_worker.preview import PreviewEngine, PreviewEngineConfig
from mymediavault_vm_worker.preview_pipeline import TorrentProcessingScheduler
from mymediavault_vm_worker.settings import PreviewWorkerSettings
from mymediavault_vm_worker.storage import BlobStore

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
