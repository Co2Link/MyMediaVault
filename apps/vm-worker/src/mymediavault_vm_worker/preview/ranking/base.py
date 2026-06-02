"""Frame ranking interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from mymediavault_vm_worker.preview.core.models import (
    ExtractedFrame,
    LLMSelectionDiagnostics,
    PreviewContext,
)


@dataclass(frozen=True)
class FrameRankingResult:
    """Internal frame ranking result with public-safe diagnostics."""

    frames: list[ExtractedFrame]
    llm: LLMSelectionDiagnostics


class FrameRanker(Protocol):
    """Choose the final preview frames from scored decoder candidates."""

    async def rank(
        self,
        frames: list[ExtractedFrame],
        *,
        target_frames: int,
        context: PreviewContext,
    ) -> FrameRankingResult:
        """Return selected preview frames in display order."""
