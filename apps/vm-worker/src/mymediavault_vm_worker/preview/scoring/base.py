"""Frame scoring interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod

from mymediavault_vm_worker.preview.core.models import ExtractedFrame


class FrameScorer(ABC):
    """Assigns quality scores to extracted candidate frames."""

    @abstractmethod
    def score(self, frames: list[ExtractedFrame]) -> list[ExtractedFrame]:
        """Return frames with updated scores."""
