"""Frame candidate grouping and deterministic local selection."""

from __future__ import annotations

from dataclasses import dataclass

from mymediavault_vm_worker.preview.core.models import (
    ExtractedFrame,
    FrameSelectionDiagnostics,
    TARGET_FRAMES,
)
from mymediavault_vm_worker.preview.frame_selection.base import FrameSelectionResult


@dataclass(frozen=True)
class FrameCandidate:
    frame_id: str
    frame: ExtractedFrame
    image_url: str


def candidate_pool(
    frames: list[ExtractedFrame],
    *,
    candidates_per_anchor: int,
) -> list[ExtractedFrame]:
    """Return up to the configured top scored candidates for each target anchor."""

    pool: list[ExtractedFrame] = []
    for anchor_index in range(TARGET_FRAMES):
        anchor_frames = sorted(
            (
                frame
                for frame in frames
                if frame.anchor_index == anchor_index and frame.score > 0
            ),
            key=lambda frame: frame.score,
            reverse=True,
        )
        pool.extend(anchor_frames[:candidates_per_anchor])
    return sorted(
        pool,
        key=lambda frame: (
            frame.anchor_index if frame.anchor_index is not None else TARGET_FRAMES,
            -frame.score,
            frame.timestamp_seconds,
        ),
    )


def eligible_anchor_indexes(
    frames: list[ExtractedFrame],
    *,
    min_candidates_per_anchor: int,
) -> list[int]:
    """Return anchors that have enough positive-scored candidates for selection."""

    counts = positive_candidate_counts_by_anchor(frames)
    return [
        anchor_index
        for anchor_index in range(TARGET_FRAMES)
        if counts.get(anchor_index, 0) >= min_candidates_per_anchor
    ]


def local_partial_selection(
    frames: list[ExtractedFrame],
    *,
    min_candidates_per_anchor: int,
) -> FrameSelectionResult:
    """Select one best local candidate for each eligible anchor."""

    eligible = eligible_anchor_indexes(
        frames,
        min_candidates_per_anchor=min_candidates_per_anchor,
    )
    selected: list[ExtractedFrame] = []
    for anchor_index in eligible:
        anchor_frames = sorted(
            (
                frame
                for frame in frames
                if frame.anchor_index == anchor_index and frame.score > 0
            ),
            key=lambda frame: frame.score,
            reverse=True,
        )
        if anchor_frames:
            selected.append(anchor_frames[0])

    method = "local_partial" if selected else "none"
    reason = (
        f"Selected local best frames for {len(selected)} of {TARGET_FRAMES} anchors"
        if selected
        else "No target anchors had enough clean local candidates"
    )
    return FrameSelectionResult(
        frames=selected,
        diagnostics=FrameSelectionDiagnostics(
            selection_method=method,
            model=None,
            candidate_frame_count=len(frames),
            selected_frame_count=len(selected),
            target_frame_count=TARGET_FRAMES,
            reason=reason,
            eligible_anchor_indexes=eligible,
            selected_anchor_indexes=[
                frame.anchor_index
                for frame in selected
                if frame.anchor_index is not None
            ],
        ),
    )


def candidate_counts_by_anchor(frames: list[ExtractedFrame]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for frame in frames:
        anchor_index = frame.anchor_index
        if anchor_index is None or not 0 <= anchor_index < TARGET_FRAMES:
            continue
        counts[anchor_index] = counts.get(anchor_index, 0) + 1
    return counts


def positive_candidate_counts_by_anchor(frames: list[ExtractedFrame]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for frame in frames:
        anchor_index = frame.anchor_index
        if (
            anchor_index is None
            or not 0 <= anchor_index < TARGET_FRAMES
            or frame.score <= 0
        ):
            continue
        counts[anchor_index] = counts.get(anchor_index, 0) + 1
    return counts
