from __future__ import annotations

import asyncio
from pathlib import Path

import cv2
import numpy as np
import pytest

from mymediavault_vm_worker.preview.decoding.base import FrameDecoder
from mymediavault_vm_worker.preview.core.exceptions import FrameDecodeError
from mymediavault_vm_worker.preview.core.models import (
    ExtractedFrame,
    LLMSelectionDiagnostics,
    PreviewContext,
    PreviewDiagnostics,
    PreviewEngineConfig,
)
from mymediavault_vm_worker.preview.ranking.base import FrameRankingResult
from mymediavault_vm_worker.preview.planning.base import TimelineAnchor
from mymediavault_vm_worker.preview.torrent.client import (
    PreviewRangeDownload,
    TorrentClient,
)
from mymediavault_vm_worker.preview.torrent.metadata import TorrentMetadata


@pytest.fixture(autouse=True)
def _disable_external_services(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("TORRENT_PREVIEW_DISABLE_LOGFIRE", "1")


def bencode(value: object) -> bytes:
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, str):
        return bencode(value.encode())
    if isinstance(value, list):
        return b"l" + b"".join(bencode(item) for item in value) + b"e"
    if isinstance(value, dict):
        items = sorted(
            value.items(),
            key=lambda item: (
                item[0] if isinstance(item[0], bytes) else str(item[0]).encode()
            ),
        )
        payload = b"".join(bencode(key) + bencode(item) for key, item in items)
        return b"d" + payload + b"e"
    raise TypeError(type(value).__name__)


def torrent_bytes(files: list[tuple[str, int]], *, piece_length: int = 16_384) -> bytes:
    if len(files) == 1:
        path, length = files[0]
        info = {
            b"name": path.encode(),
            b"length": length,
            b"piece length": piece_length,
            b"pieces": b"0" * 20,
        }
    else:
        info = {
            b"name": b"sample",
            b"files": [
                {
                    b"length": length,
                    b"path": [part.encode() for part in path.split("/")],
                }
                for path, length in files
            ],
            b"piece length": piece_length,
            b"pieces": b"0" * 20,
        }
    return bencode({b"announce": b"https://tracker.invalid/announce", b"info": info})


class FakeTorrentClient(TorrentClient):
    def __init__(self, *, delay: float = 0.0) -> None:
        self.delay = delay
        self.started = False
        self.closed = False
        self.active_downloads = 0
        self.max_active_downloads = 0
        self.download_calls = 0
        self.timeout_seconds: list[float] = []

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    async def download(
        self,
        torrent_bytes: bytes,
        metadata: TorrentMetadata,
        selected_file,
        layout,
        output_dir: Path,
        config: PreviewEngineConfig,
        timeout_seconds: float,
    ) -> PreviewRangeDownload:
        _ = torrent_bytes, metadata, config
        self.timeout_seconds.append(timeout_seconds)
        self.download_calls += 1
        self.active_downloads += 1
        self.max_active_downloads = max(
            self.max_active_downloads, self.active_downloads
        )
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            media_path = output_dir / selected_file.path
            media_path.parent.mkdir(parents=True, exist_ok=True)
            media_path.write_bytes(b"media")
            return PreviewRangeDownload(
                media_path=media_path,
                downloaded_bytes=layout.total_bytes,
                selected_file_complete=False,
                planned_pieces_complete=True,
                diagnostics=PreviewDiagnostics(
                    torrent_cache_dir=str(config.torrent_cache_dir),
                    torrent_cache_max_mb=config.torrent_cache_max_mb,
                    torrent_cache_entry_exists_before=False,
                    resume_data_exists_before=False,
                ),
            )
        finally:
            self.active_downloads -= 1


class FakeDecoder(FrameDecoder):
    def __init__(self, frame_count: int, *, accepted_by_llm: bool = True) -> None:
        self.frame_count = frame_count
        self.accepted_by_llm = accepted_by_llm
        self.timeout_seconds: list[float] = []
        self.anchors: list[tuple[float, ...]] = []

    async def extract_frames(
        self,
        media_path: Path,
        output_dir: Path,
        target_frames: int,
        timeout_seconds: float,
        anchors: tuple[TimelineAnchor | float, ...],
        anchor_window_seconds: float = 30.0,
        extract_frames_per_anchor: int = 1,
    ) -> list[ExtractedFrame]:
        _ = (
            media_path,
            target_frames,
            anchor_window_seconds,
            extract_frames_per_anchor,
        )
        self.timeout_seconds.append(timeout_seconds)
        self.anchors.append(
            tuple(
                anchor.ratio if isinstance(anchor, TimelineAnchor) else anchor
                for anchor in anchors
            )
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        frames: list[ExtractedFrame] = []
        for index in range(self.frame_count):
            frame_path = output_dir / f"frame-{index}.jpg"
            image = np.full((360, 640), 48 + (index * 40), dtype=np.uint8)
            image[:, index * 80 : (index * 80) + 160] = 180
            image[index * 40 : (index * 40) + 120, :] = 24 + (index * 30)
            cv2.putText(
                image,
                str(index),
                (40 + (index * 20), 180),
                cv2.FONT_HERSHEY_SIMPLEX,
                3.0,
                220,
                8,
            )
            assert cv2.imwrite(str(frame_path), image)
            anchor = anchors[index] if index < len(anchors) else None
            anchor_index = (
                anchor.index
                if isinstance(anchor, TimelineAnchor)
                else index
                if anchor is not None
                else None
            )
            anchor_ratio = (
                anchor.ratio
                if isinstance(anchor, TimelineAnchor)
                else anchor
                if anchor is not None
                else None
            )
            frames.append(
                ExtractedFrame(
                    path=frame_path,
                    score=0.0,
                    width=640,
                    height=360,
                    timestamp_seconds=(
                        anchor_ratio * 100 if anchor_ratio is not None else index * 10
                    ),
                    anchor_index=anchor_index,
                    anchor_ratio=anchor_ratio,
                    decode_method="fake-anchor" if anchor_index is not None else "fake",
                    accepted_by_llm=self.accepted_by_llm,
                )
            )
        return frames


class FlakyDecoder(FakeDecoder):
    def __init__(self, frame_count: int) -> None:
        super().__init__(frame_count=frame_count)
        self.calls = 0

    async def extract_frames(
        self,
        media_path: Path,
        output_dir: Path,
        target_frames: int,
        timeout_seconds: float,
        anchors: tuple[TimelineAnchor | float, ...],
        anchor_window_seconds: float = 30.0,
        extract_frames_per_anchor: int = 1,
    ) -> list[ExtractedFrame]:
        self.calls += 1
        if self.calls == 1:
            msg = "probe failed"
            raise FrameDecodeError(msg)
        return await super().extract_frames(
            media_path,
            output_dir,
            target_frames,
            timeout_seconds,
            anchors,
            anchor_window_seconds,
            extract_frames_per_anchor,
        )


class AcceptAllRanker:
    async def rank(
        self,
        frames: list[ExtractedFrame],
        *,
        target_frames: int,
        context: PreviewContext,
        eligible_anchor_indexes: list[int] | None = None,
    ) -> FrameRankingResult:
        del context
        eligible = (
            set(range(target_frames))
            if eligible_anchor_indexes is None
            else set(eligible_anchor_indexes)
        )
        accepted = [
            frame
            for frame in frames
            if frame.anchor_index is not None
            and frame.anchor_index < target_frames
            and frame.anchor_index in eligible
        ]
        selected = [
            frame if frame.accepted_by_llm else _accepted(frame) for frame in accepted
        ]
        return FrameRankingResult(
            frames=selected,
            llm=LLMSelectionDiagnostics(
                model="test-ranker",
                candidate_frame_count=len(frames),
                selected_frame_count=len(selected),
                target_frame_count=target_frames,
                reason="test ranker accepted all anchor frames",
            ),
        )


def _accepted(frame: ExtractedFrame) -> ExtractedFrame:
    from dataclasses import replace

    return replace(frame, accepted_by_llm=True)
