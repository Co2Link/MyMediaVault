"""Frame selection interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from mymediavault_vm_worker.preview.core.models import (
    ExtractedFrame,
    FrameSelectionDiagnostics,
    PreviewContext,
)


class FrameSelectionError(RuntimeError):
    """Raised when frame selection fails after local candidates are available."""


class FrameSelectionValidationError(FrameSelectionError):
    """Raised when selector output is structurally parsed but semantically invalid."""


@dataclass(frozen=True)
class FrameSelectionResult:
    """Internal frame selection result with public-safe diagnostics."""

    frames: list[ExtractedFrame]
    diagnostics: FrameSelectionDiagnostics


class FrameSelector(Protocol):
    """Select one preview frame per target anchor from scored local candidates."""

    async def select(
        self,
        frames: list[ExtractedFrame],
        *,
        context: PreviewContext,
    ) -> FrameSelectionResult:
        """Return selected preview frames and selection diagnostics."""
