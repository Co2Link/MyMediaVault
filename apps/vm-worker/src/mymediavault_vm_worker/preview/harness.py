"""Generic worker harness for adapter-driven preview processing."""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from mymediavault_vm_worker.preview.core.engine import PreviewEngine
from mymediavault_vm_worker.preview.core.models import (
    PreviewRequest,
    PreviewResult,
)
from mymediavault_vm_worker.preview.logging import bind_log


class PreviewJobLease(Protocol):
    """A claimed preview job supplied by an application adapter."""

    @property
    def job_id(self) -> str:
        """Stable application job identifier used for logs and callbacks."""

    async def load_torrent_bytes(self) -> bytes:
        """Load the raw .torrent bytes for this claimed job."""

    async def complete(self, result: PreviewResult) -> None:
        """Persist a successful, partial, or failed preview result."""

    async def fail(self, error: Exception) -> None:
        """Persist an unexpected harness or adapter failure."""


class PreviewJobSource(Protocol):
    """Application-owned source for eligible claimed preview jobs."""

    async def claim_batch(
        self,
        *,
        limit: int,
        artifact_version: str,
        artifact_fingerprint: str,
    ) -> Sequence[PreviewJobLease]:
        """Claim up to ``limit`` jobs that need the current preview artifact."""


@dataclass(frozen=True)
class PreviewHarnessConfig:
    """Settings for the generic preview worker harness."""

    max_concurrency: int = 1
    poll_interval_seconds: float = 5.0
    run_once: bool = False
    stop_when_empty: bool = False
    clear_cache: bool = False

    def __post_init__(self) -> None:
        if self.max_concurrency < 1:
            msg = "PreviewHarnessConfig.max_concurrency must be at least 1"
            raise ValueError(msg)
        if self.poll_interval_seconds < 0:
            msg = "PreviewHarnessConfig.poll_interval_seconds must be non-negative"
            raise ValueError(msg)


class PreviewWorkerHarness:
    """Run preview jobs through one long-lived ``PreviewEngine``."""

    def __init__(
        self,
        *,
        engine: PreviewEngine,
        job_source: PreviewJobSource,
        config: PreviewHarnessConfig | None = None,
        result_callback: Callable[[PreviewJobLease, PreviewResult], Awaitable[None]]
        | None = None,
    ) -> None:
        self._engine = engine
        self._job_source = job_source
        self._config = config or PreviewHarnessConfig()
        self._result_callback = result_callback
        self._stopping = False

    def stop(self) -> None:
        """Ask ``run`` to stop after the current polling or processing cycle."""

        self._stopping = True

    async def run(self) -> None:
        """Run the harness until stopped, or one cycle when ``run_once`` is set."""

        if self._config.clear_cache:
            _clear_engine_cache(self._engine)
        await self._engine.start()
        tasks: set[asyncio.Task[None]] = set()
        claimed_once = False
        try:
            while tasks or not self._stopping:
                if self._stopping:
                    await asyncio.gather(*tasks)
                    return

                available_slots = self._config.max_concurrency - len(tasks)
                if available_slots and not (self._config.run_once and claimed_once):
                    jobs = await self._job_source.claim_batch(
                        limit=available_slots,
                        artifact_version=self._engine.artifact_version,
                        artifact_fingerprint=self._engine.artifact_fingerprint,
                    )
                    if jobs:
                        claimed_once = True
                        tasks.update(self._start_jobs(jobs))
                    elif not tasks and (
                        self._config.run_once or self._config.stop_when_empty
                    ):
                        return

                if not tasks:
                    await asyncio.sleep(self._config.poll_interval_seconds)
                    continue

                done, tasks = await asyncio.wait(
                    tasks,
                    timeout=self._config.poll_interval_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    task.result()
                if self._config.run_once and not tasks:
                    return
        finally:
            await cancel_preview_tasks(tasks)
            await self._engine.close()

    def _start_jobs(self, jobs: Sequence[PreviewJobLease]) -> set[asyncio.Task[None]]:
        return {
            asyncio.create_task(
                self._run_job(job),
                name=f"preview:{job.job_id}",
            )
            for job in jobs
        }

    async def _run_job(self, job: PreviewJobLease) -> None:
        job_logger = bind_log(job_id=job.job_id)
        try:
            job_logger.info("Starting preview job")
            torrent_bytes = await job.load_torrent_bytes()
            async with self._engine.preview_artifact(
                PreviewRequest(torrent_bytes=torrent_bytes)
            ) as result:
                await job.complete(result)
                if self._result_callback is not None:
                    await self._result_callback(job, result)
                job_logger.bind(
                    status=result.status,
                    downloaded_bytes=result.diagnostics.downloaded_bytes,
                    elapsed_seconds=round(result.diagnostics.elapsed_seconds, 2),
                    status_reason=result.status_reason,
                ).info("Preview job finished")
        except Exception as exc:
            await job.fail(exc)
            job_logger.warning("Preview job failed: {}", exc)


async def cancel_preview_tasks(tasks: Iterable[asyncio.Task[Any]]) -> None:
    """Cancel unfinished preview tasks and wait for cancellation cleanup."""

    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def _clear_engine_cache(engine: PreviewEngine) -> None:
    cache_dir = engine.config.torrent_cache_dir
    if not cache_dir.exists():
        return
    if not cache_dir.is_dir():
        msg = f"torrent cache path is not a directory: {cache_dir}"
        raise ValueError(msg)
    shutil.rmtree(cache_dir)
