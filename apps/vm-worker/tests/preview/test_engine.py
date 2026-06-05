from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mymediavault_vm_worker.preview import (
    ExtractedFrame,
    LLMSelectionDiagnostics,
    PREVIEW_ARTIFACT_VERSION,
    PreviewContext,
    PreviewEngine,
    PreviewEngineConfig,
    PreviewRequest,
    SelectedFile,
)
from mymediavault_vm_worker.preview.planning.base import DownloadLayout
from mymediavault_vm_worker.preview.ranking.base import FrameRankingResult
from mymediavault_vm_worker.preview.torrent.client import PreviewRangeDownload
from mymediavault_vm_worker.preview.torrent.metadata import TorrentMetadata

from .conftest import AcceptAllRanker, FakeDecoder, FakeTorrentClient, torrent_bytes


def test_engine_returns_succeeded_result_and_cleans_workspace(tmp_path) -> None:
    async def run() -> None:
        workspace_root = tmp_path / "workspace"
        torrent_client = FakeTorrentClient()
        engine = PreviewEngine(
            config=_engine_config(target_frames=3),
            torrent_client=torrent_client,
            decoder=FakeDecoder(frame_count=3),
            _frame_ranker=AcceptAllRanker(),
            workspace_root=workspace_root,
        )

        async with engine.preview_artifact(
            PreviewRequest(torrent_bytes=torrent_bytes([("movie.mkv", 10_000)]))
        ) as result:
            assert result.status == "succeeded"
            assert engine.artifact_version == PREVIEW_ARTIFACT_VERSION
            assert engine.artifact_fingerprint == engine.config.artifact_fingerprint(
                sheet_recipe=engine._sheet_renderer.artifact_recipe()
            )
            assert result.info_hash
            assert result.diagnostics.selected_file is not None
            assert result.diagnostics.selected_file.path == "movie.mkv"
            assert result.diagnostics.llm is not None
            assert result.diagnostics.llm.candidate_frame_count == 3
            assert result.diagnostics.llm.selected_frame_count == 3
            assert result.diagnostics.llm.target_frame_count == 3
            assert len(result.artifact.frames) == 3
            assert result.artifact.sheet is not None
            assert result.status_reason is None
            sheet_path = result.artifact.sheet.path
            assert sheet_path.exists()

        await engine.close()

        assert not (workspace_root / result.info_hash).exists()
        assert not sheet_path.exists()
        assert torrent_client.started is True
        assert torrent_client.closed is True

    asyncio.run(run())


def test_engine_returns_partial_when_some_anchors_are_accepted(tmp_path) -> None:
    async def run() -> None:
        engine = PreviewEngine(
            config=_engine_config(target_frames=3, anchor_retry_range_mb=()),
            torrent_client=FakeTorrentClient(),
            decoder=FakeDecoder(frame_count=1),
            _frame_ranker=AcceptAllRanker(),
            workspace_root=tmp_path / "workspace",
        )

        async with engine.preview_artifact(
            PreviewRequest(torrent_bytes=torrent_bytes([("movie.mp4", 10_000)]))
        ) as result:
            assert result.status == "partial"
            assert len(result.artifact.frames) == 1
            assert result.artifact.sheet is not None
            assert result.status_reason == (
                "Only 1 of 3 target anchors produced selected frames"
            )

    asyncio.run(run())


def test_engine_retries_missing_llm_visible_anchors_before_ranking(tmp_path) -> None:
    async def run() -> None:
        torrent_client = FakeTorrentClient()
        decoder = FakeDecoder(frame_count=1)
        engine = PreviewEngine(
            config=_engine_config(target_frames=3),
            torrent_client=torrent_client,
            decoder=decoder,
            _frame_ranker=AcceptAllRanker(),
            workspace_root=tmp_path / "workspace",
        )

        async with engine.preview_artifact(
            PreviewRequest(torrent_bytes=torrent_bytes([("movie.mp4", 100_000_000)]))
        ) as result:
            assert result.status == "succeeded"
            assert result.status_reason is None
            assert [frame.timestamp_seconds for frame in result.artifact.frames] == [
                25.0,
                50.0,
                75.0,
            ]
            assert torrent_client.download_calls == 3
            assert decoder.anchors == [
                (0.25, 0.5, 0.75),
                (0.5, 0.75),
                (0.75,),
            ]
            retry = result.diagnostics.anchor_retry
            assert retry is not None
            assert retry.initial_missing_anchor_indexes == [1, 2]
            assert retry.final_missing_anchor_indexes == []
            assert retry.attempt_count == 2
            assert retry.attempts[0].target_anchor_indexes == [1, 2]
            assert retry.attempts[0].remaining_missing_anchor_indexes == [2]
            assert retry.attempts[1].target_anchor_indexes == [2]
            assert retry.attempts[1].remaining_missing_anchor_indexes == []

    asyncio.run(run())


def test_engine_returns_failed_when_no_anchors_are_accepted(tmp_path) -> None:
    async def run() -> None:
        engine = PreviewEngine(
            config=_engine_config(target_frames=3),
            torrent_client=FakeTorrentClient(),
            decoder=FakeDecoder(frame_count=0),
            _frame_ranker=AcceptAllRanker(),
            workspace_root=tmp_path / "workspace",
        )

        async with engine.preview_artifact(
            PreviewRequest(torrent_bytes=torrent_bytes([("movie.mp4", 10_000)]))
        ) as result:
            assert result.status == "failed"
            assert result.artifact.frames == []
            assert result.artifact.sheet is None
            assert (
                result.status_reason == "No target anchors produced selected frames"
            )

    asyncio.run(run())


def test_engine_limits_concurrent_downloads(tmp_path) -> None:
    async def run() -> None:
        torrent_client = FakeTorrentClient(delay=0.02)
        engine = PreviewEngine(
            config=_engine_config(max_concurrent_downloads=1, target_frames=3),
            torrent_client=torrent_client,
            decoder=FakeDecoder(frame_count=3),
            _frame_ranker=AcceptAllRanker(),
            workspace_root=tmp_path / "workspace",
        )

        async def one(request: PreviewRequest) -> str:
            async with engine.preview_artifact(request) as result:
                return result.status

        requests = [
            PreviewRequest(
                torrent_bytes=torrent_bytes([(f"movie-{index}.mp4", 10_000)])
            )
            for index in range(4)
        ]
        statuses = await asyncio.gather(*(one(request) for request in requests))

        assert statuses == ["succeeded"] * 4
        assert torrent_client.max_active_downloads == 1

    asyncio.run(run())


def test_engine_uses_separate_download_and_decode_timeouts(tmp_path) -> None:
    async def run() -> None:
        torrent_client = FakeTorrentClient()
        decoder = FakeDecoder(frame_count=3)
        engine = PreviewEngine(
            config=_engine_config(
                target_frames=3,
                max_time_seconds=60,
                max_download_time_seconds=12,
                max_decode_time_seconds=7,
            ),
            torrent_client=torrent_client,
            decoder=decoder,
            _frame_ranker=AcceptAllRanker(),
            workspace_root=tmp_path / "workspace",
        )

        async with engine.preview_artifact(
            PreviewRequest(torrent_bytes=torrent_bytes([("movie.mp4", 10_000)]))
        ) as result:
            assert result.status == "succeeded"
            assert torrent_client.timeout_seconds == [12]
            assert decoder.timeout_seconds == [7]

    asyncio.run(run())


def test_engine_decodes_when_requested_pieces_are_incomplete(
    tmp_path,
) -> None:
    class IncompletePieceClient(FakeTorrentClient):
        async def download(
            self,
            torrent_bytes: bytes,
            metadata: TorrentMetadata,
            selected_file: SelectedFile,
            layout: DownloadLayout,
            output_dir: Path,
            config: PreviewEngineConfig,
            timeout_seconds: float,
        ) -> PreviewRangeDownload:
            partial = await super().download(
                torrent_bytes,
                metadata,
                selected_file,
                layout,
                output_dir,
                config,
                timeout_seconds,
            )
            return replace(
                partial,
                diagnostics=replace(
                    partial.diagnostics,
                    last_requested_piece_count=3,
                    last_complete_piece_count=1,
                    planned_pieces_complete=False,
                ),
            )

    async def run() -> None:
        decoder = FakeDecoder(frame_count=3)
        engine = PreviewEngine(
            config=_engine_config(target_frames=3),
            torrent_client=IncompletePieceClient(),
            decoder=decoder,
            _frame_ranker=AcceptAllRanker(),
            workspace_root=tmp_path / "workspace",
        )

        async with engine.preview_artifact(
            PreviewRequest(torrent_bytes=torrent_bytes([("movie.mp4", 10_000)]))
        ) as result:
            assert result.status == "succeeded"
            assert decoder.anchors == [(0.25, 0.5, 0.75)]
            assert result.status_reason is None
            assert result.diagnostics.warnings == []
            assert result.diagnostics.planned_pieces_complete is False

    asyncio.run(run())


def test_engine_reserves_decode_time_from_overall_timeout(tmp_path) -> None:
    async def run() -> None:
        torrent_client = FakeTorrentClient()
        decoder = FakeDecoder(frame_count=3)
        engine = PreviewEngine(
            config=_engine_config(
                target_frames=3,
                max_time_seconds=20,
                max_download_time_seconds=18,
                max_decode_time_seconds=7,
            ),
            torrent_client=torrent_client,
            decoder=decoder,
            _frame_ranker=AcceptAllRanker(),
            workspace_root=tmp_path / "workspace",
        )

        async with engine.preview_artifact(
            PreviewRequest(torrent_bytes=torrent_bytes([("movie.mp4", 10_000)]))
        ) as result:
            assert result.status == "succeeded"
            assert torrent_client.timeout_seconds[0] == pytest.approx(13, abs=0.2)
            assert decoder.timeout_seconds == [7]

    asyncio.run(run())


def test_engine_uses_injected_frame_ranker(tmp_path) -> None:
    class FirstAnchorRanker:
        def __init__(self) -> None:
            self.contexts: list[PreviewContext] = []

        async def rank(
            self,
            frames: list[ExtractedFrame],
            *,
            target_frames: int,
            context: PreviewContext,
            eligible_anchor_indexes: list[int] | None = None,
        ) -> FrameRankingResult:
            del target_frames, eligible_anchor_indexes
            self.contexts.append(context)
            selected = [replace(frames[0], accepted_by_llm=True)]
            return FrameRankingResult(
                frames=selected,
                llm=LLMSelectionDiagnostics(
                    model="test-ranker",
                    candidate_frame_count=len(frames),
                    selected_frame_count=len(selected),
                    target_frame_count=3,
                    reason="selected first anchor",
                ),
            )

    async def run() -> None:
        ranker = FirstAnchorRanker()
        engine = PreviewEngine(
            config=_engine_config(target_frames=3),
            torrent_client=FakeTorrentClient(),
            decoder=FakeDecoder(frame_count=3),
            _frame_ranker=ranker,
            workspace_root=tmp_path / "workspace",
        )

        async with engine.preview_artifact(
            PreviewRequest(torrent_bytes=torrent_bytes([("movie.mp4", 10_000)]))
        ) as result:
            assert result.status == "partial"
            assert [frame.timestamp_seconds for frame in result.artifact.frames] == [
                25.0
            ]
            assert result.status_reason == (
                "Only 1 of 3 target anchors produced selected frames"
            )
            assert [context.selected_file.path for context in ranker.contexts] == [
                "movie.mp4"
            ]

    asyncio.run(run())


def test_engine_returns_failed_result_for_valid_torrent_without_video(tmp_path) -> None:
    async def run() -> None:
        engine = PreviewEngine(
            config=_engine_config(target_frames=3),
            torrent_client=FakeTorrentClient(),
            decoder=FakeDecoder(frame_count=3),
            _frame_ranker=AcceptAllRanker(),
            workspace_root=tmp_path / "workspace",
        )

        async with engine.preview_artifact(
            PreviewRequest(torrent_bytes=torrent_bytes([("archive.txt", 10_000)]))
        ) as result:
            assert result.status == "failed"
            assert (
                result.status_reason
                == "No supported video file was found in torrent metadata"
            )
            assert result.artifact.frames == []
            assert result.artifact.sheet is None

    asyncio.run(run())


def _engine_config(**kwargs: Any) -> PreviewEngineConfig:
    kwargs.setdefault("min_selector_candidates_per_anchor", 1)
    return PreviewEngineConfig(**kwargs)
