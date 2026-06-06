from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from mymediavault_vm_worker.preview import (
    PREVIEW_ARTIFACT_VERSION,
    PreviewEngine,
    PreviewHarnessConfig,
    PreviewJobLease,
    PreviewResult,
    PreviewWorkerHarness,
    TARGET_FRAMES,
)
from mymediavault_vm_worker.preview.harness import cancel_preview_tasks

from .conftest import (
    AcceptAllSelector,
    FakeDecoder,
    FakeTorrentClient,
    torrent_bytes,
)
from .test_engine import _engine_config


@dataclass
class FakeLease:
    job_id: str
    torrent_bytes: bytes
    result: PreviewResult | None = None
    error: Exception | None = None

    async def load_torrent_bytes(self) -> bytes:
        return self.torrent_bytes

    async def complete(self, result: PreviewResult) -> None:
        self.result = result

    async def fail(self, error: Exception) -> None:
        self.error = error


class FakeJobSource:
    def __init__(self, leases: list[FakeLease]) -> None:
        self._leases = leases
        self.claims: list[dict[str, Any]] = []

    async def claim_batch(
        self,
        *,
        limit: int,
        artifact_version: str,
        artifact_fingerprint: str,
    ) -> list[FakeLease]:
        self.claims.append(
            {
                "limit": limit,
                "artifact_version": artifact_version,
                "artifact_fingerprint": artifact_fingerprint,
            }
        )
        claimed = self._leases[:limit]
        self._leases = self._leases[limit:]
        return claimed


def test_harness_runs_claimed_jobs_and_closes_engine(tmp_path) -> None:
    async def run() -> None:
        torrent_client = FakeTorrentClient()
        engine = PreviewEngine(
            config=_engine_config(target_frames=3),
            torrent_client=torrent_client,
            decoder=FakeDecoder(frame_count=TARGET_FRAMES),
            _frame_selector=AcceptAllSelector(),
            workspace_root=tmp_path / "workspace",
        )
        leases = [
            FakeLease("job-1", torrent_bytes([("one.mp4", 10_000)])),
            FakeLease("job-2", torrent_bytes([("two.mp4", 10_000)])),
        ]
        source = FakeJobSource(leases)
        callback_results: list[tuple[str, str]] = []

        async def callback(lease: PreviewJobLease, result: PreviewResult) -> None:
            callback_results.append((lease.job_id, result.status))

        harness = PreviewWorkerHarness(
            engine=engine,
            job_source=source,
            config=PreviewHarnessConfig(max_concurrency=2, run_once=True),
            result_callback=callback,
        )

        await harness.run()

        assert [lease.result.status for lease in leases if lease.result] == [
            "succeeded",
            "succeeded",
        ]
        assert [lease.error for lease in leases] == [None, None]
        assert callback_results == [("job-1", "succeeded"), ("job-2", "succeeded")]
        assert source.claims == [
            {
                "limit": 2,
                "artifact_version": PREVIEW_ARTIFACT_VERSION,
                "artifact_fingerprint": engine.artifact_fingerprint,
            }
        ]
        assert torrent_client.started is True
        assert torrent_client.closed is True

    asyncio.run(run())


def test_harness_reports_unexpected_job_failure(tmp_path) -> None:
    class FailingLease(FakeLease):
        async def load_torrent_bytes(self) -> bytes:
            msg = "blob missing"
            raise RuntimeError(msg)

    async def run() -> None:
        engine = PreviewEngine(
            config=_engine_config(target_frames=3),
            torrent_client=FakeTorrentClient(),
            decoder=FakeDecoder(frame_count=TARGET_FRAMES),
            _frame_selector=AcceptAllSelector(),
            workspace_root=tmp_path / "workspace",
        )
        lease = FailingLease("job-1", b"unused")
        harness = PreviewWorkerHarness(
            engine=engine,
            job_source=FakeJobSource([lease]),
            config=PreviewHarnessConfig(run_once=True),
        )

        await harness.run()

        assert lease.result is None
        assert isinstance(lease.error, RuntimeError)
        assert str(lease.error) == "blob missing"

    asyncio.run(run())


def test_harness_replenishes_available_capacity_while_jobs_are_running(
    tmp_path,
) -> None:
    @dataclass
    class BlockingLease(FakeLease):
        started: asyncio.Event | None = None
        release: asyncio.Event | None = None

        async def load_torrent_bytes(self) -> bytes:
            assert self.started is not None
            assert self.release is not None
            self.started.set()
            await self.release.wait()
            return self.torrent_bytes

    async def run() -> None:
        engine = PreviewEngine(
            config=_engine_config(target_frames=3),
            torrent_client=FakeTorrentClient(),
            decoder=FakeDecoder(frame_count=TARGET_FRAMES),
            _frame_selector=AcceptAllSelector(),
            workspace_root=tmp_path / "workspace",
        )
        first_started = asyncio.Event()
        second_started = asyncio.Event()
        release = asyncio.Event()
        first = BlockingLease(
            "job-1",
            torrent_bytes([("one.mp4", 10_000)]),
            started=first_started,
            release=release,
        )
        second = BlockingLease(
            "job-2",
            torrent_bytes([("two.mp4", 10_000)]),
            started=second_started,
            release=release,
        )
        source = FakeJobSource([first])
        harness = PreviewWorkerHarness(
            engine=engine,
            job_source=source,
            config=PreviewHarnessConfig(
                max_concurrency=2,
                poll_interval_seconds=0.01,
                stop_when_empty=True,
            ),
        )

        task = asyncio.create_task(harness.run())
        await asyncio.wait_for(first_started.wait(), timeout=1)
        source._leases.append(second)
        await asyncio.wait_for(second_started.wait(), timeout=1)

        assert first.result is None
        assert second.result is None
        assert [claim["limit"] for claim in source.claims[:2]] == [2, 1]

        release.set()
        await asyncio.wait_for(task, timeout=1)

        assert first.result is not None
        assert second.result is not None

    asyncio.run(run())


def test_harness_config_validates_values() -> None:
    with pytest.raises(ValueError, match="max_concurrency"):
        PreviewHarnessConfig(max_concurrency=0)
    with pytest.raises(ValueError, match="poll_interval_seconds"):
        PreviewHarnessConfig(poll_interval_seconds=-1)


def test_harness_can_clear_configured_torrent_cache(tmp_path) -> None:
    async def run() -> None:
        cache_dir = tmp_path / "cache"
        cache_entry = cache_dir / "entry"
        cache_entry.mkdir(parents=True)
        (cache_entry / "piece").write_bytes(b"data")
        engine = PreviewEngine(
            config=_engine_config(target_frames=3, torrent_cache_dir=cache_dir),
            torrent_client=FakeTorrentClient(),
            decoder=FakeDecoder(frame_count=TARGET_FRAMES),
            _frame_selector=AcceptAllSelector(),
            workspace_root=tmp_path / "workspace",
        )
        lease = FakeLease("job-1", torrent_bytes([("one.mp4", 10_000)]))
        harness = PreviewWorkerHarness(
            engine=engine,
            job_source=FakeJobSource([lease]),
            config=PreviewHarnessConfig(run_once=True, clear_cache=True),
        )

        await harness.run()

        assert lease.result is not None
        assert not cache_entry.exists()

    asyncio.run(run())


def test_harness_rejects_file_cache_path_when_clearing(tmp_path) -> None:
    async def run() -> None:
        cache_path = tmp_path / "cache-file"
        cache_path.write_text("not a directory", encoding="utf-8")
        engine = PreviewEngine(
            config=_engine_config(target_frames=3, torrent_cache_dir=cache_path),
            torrent_client=FakeTorrentClient(),
            decoder=FakeDecoder(frame_count=TARGET_FRAMES),
            _frame_selector=AcceptAllSelector(),
            workspace_root=tmp_path / "workspace",
        )
        harness = PreviewWorkerHarness(
            engine=engine,
            job_source=FakeJobSource([]),
            config=PreviewHarnessConfig(run_once=True, clear_cache=True),
        )

        with pytest.raises(ValueError, match="not a directory"):
            await harness.run()

    asyncio.run(run())


def test_cancel_preview_tasks_cancels_pending_tasks() -> None:
    async def run() -> None:
        started = asyncio.Event()

        async def wait_forever() -> object:
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(wait_forever())
        await started.wait()

        await cancel_preview_tasks([task])

        assert task.cancelled()

    asyncio.run(run())
