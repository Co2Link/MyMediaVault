"""Structured output models for frame selection."""

from __future__ import annotations

from pydantic import BaseModel, Field

from mymediavault_vm_worker.preview.core.models import TARGET_FRAMES


class AnchorChoice(BaseModel):
    """One selected candidate for one timeline anchor."""

    anchor_index: int
    candidate_id: str


class FrameSelectionOutput(BaseModel):
    """Structured frame-selection output returned by the model."""

    choices: list[AnchorChoice] = Field(
        min_length=TARGET_FRAMES,
        max_length=TARGET_FRAMES,
        description="Exactly one selected candidate for every target anchor.",
    )
    reason: str
