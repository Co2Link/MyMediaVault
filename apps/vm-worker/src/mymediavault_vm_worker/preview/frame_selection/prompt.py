"""Prompt construction for Pydantic AI frame selection."""

from __future__ import annotations

from pydantic_ai.messages import ImageUrl, UserContent

from mymediavault_vm_worker.preview.core.models import PreviewContext, TARGET_FRAMES
from mymediavault_vm_worker.preview.frame_selection.candidates import FrameCandidate


def input_content(
    candidates: list[FrameCandidate],
    context: PreviewContext,
) -> list[UserContent]:
    content: list[UserContent] = [
        (
            f"Choose preview frames for {context.selected_file.path}. You receive "
            f"one candidate group per target anchor. The target preview has "
            f"{TARGET_FRAMES} anchors. Return exactly one choice for every anchor "
            "as {anchor_index, candidate_id}. Do not reject anchors."
        )
    ]
    current_anchor: int | None = None
    for candidate in candidates:
        frame = candidate.frame
        if frame.anchor_index != current_anchor:
            current_anchor = frame.anchor_index
            content.append(f"Anchor group: anchor_index={current_anchor}")
        content.extend(
            [
                (
                    f"Candidate {candidate.frame_id}: "
                    f"anchor_index={frame.anchor_index}, "
                    f"timestamp_seconds={frame.timestamp_seconds:.3f}, "
                    f"local_quality_score={frame.score:.4f}, "
                    f"decode_method={frame.decode_method}"
                ),
                ImageUrl(url=candidate.image_url),
            ]
        )
    return content
