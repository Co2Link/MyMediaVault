"""Timeline anchor helpers for preview frame extraction."""

from __future__ import annotations


def timeline_anchors(target_frames: int) -> tuple[float, ...]:
    """Return evenly spaced timeline anchors away from video edges."""

    if target_frames < 1:
        return ()
    return tuple(
        round((index + 1) / (target_frames + 1), 6) for index in range(target_frames)
    )
