"""Frame decoding interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from mymediavault_vm_worker.preview.core.models import ExtractedFrame
from mymediavault_vm_worker.preview.planning.base import TimelineAnchor


class FrameDecoder(ABC):
    """Extracts candidate frames from a downloaded media file."""

    @abstractmethod
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
        """Extract timestamp-verified anchor candidate frames into output_dir."""
