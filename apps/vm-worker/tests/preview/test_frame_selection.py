from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from pydantic import ValidationError
from pydantic_ai import AgentRunResult
from pydantic_ai.messages import ImageUrl

from mymediavault_vm_worker.preview.core.models import (
    ExtractedFrame,
    PreviewContext,
    SelectedFile,
    TARGET_FRAMES,
)
from mymediavault_vm_worker.preview.frame_selection.base import (
    FrameSelectionError,
    FrameSelectionValidationError,
)
from mymediavault_vm_worker.preview.frame_selection.models import (
    AnchorChoice,
    FrameSelectionOutput,
)
from mymediavault_vm_worker.preview.frame_selection.pydantic_ai import (
    PydanticAIFrameSelector,
)


class _FakeAgent:
    def __init__(self, choices: list[AnchorChoice] | None = None) -> None:
        self.choices = _default_choices() if choices is None else choices
        self.calls: list[dict[str, Any]] = []

    async def run(
        self, user_prompt: Any, **kwargs: Any
    ) -> AgentRunResult[FrameSelectionOutput]:
        self.calls.append({"user_prompt": user_prompt, **kwargs})
        return AgentRunResult(
            FrameSelectionOutput(choices=self.choices, reason="fake selection")
        )


class _FailingAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run(
        self, user_prompt: Any, **kwargs: Any
    ) -> AgentRunResult[FrameSelectionOutput]:
        self.calls.append({"user_prompt": user_prompt, **kwargs})
        msg = "api unavailable"
        raise RuntimeError(msg)


def test_frame_selection_output_requires_target_frame_count() -> None:
    with pytest.raises(ValidationError):
        FrameSelectionOutput(
            choices=[AnchorChoice(anchor_index=0, candidate_id="frame_001")],
            reason="too short",
        )


def test_pydantic_ai_selector_uses_vision_request(tmp_path) -> None:
    async def run() -> None:
        agent = _FakeAgent()
        selector = PydanticAIFrameSelector(agent=agent, candidates_per_anchor=2)

        result = await selector.select(_frames(tmp_path), context=_context())

        selected = result.frames
        assert len(selected) == TARGET_FRAMES
        assert [frame.anchor_index for frame in selected] == list(range(TARGET_FRAMES))
        assert result.diagnostics.selection_method == "openai"
        assert result.diagnostics.candidate_frame_count == TARGET_FRAMES * 2
        assert result.diagnostics.selected_frame_count == TARGET_FRAMES
        assert result.diagnostics.target_frame_count == TARGET_FRAMES
        assert result.diagnostics.reason == "fake selection"
        assert result.diagnostics.eligible_anchor_indexes == list(range(TARGET_FRAMES))
        assert result.diagnostics.selected_anchor_indexes == list(range(TARGET_FRAMES))
        assert len(agent.calls) == 1
        call = agent.calls[0]
        assert call["model_settings"] == {"timeout": 30.0}
        content = call["user_prompt"]
        assert any(isinstance(item, ImageUrl) for item in content)
        prompt_text = "\n".join(item for item in content if isinstance(item, str))
        assert "one candidate group per target anchor" in prompt_text
        assert "may include only anchors" not in prompt_text

    asyncio.run(run())


def test_pydantic_ai_selector_returns_local_partial_without_all_anchors(
    tmp_path,
) -> None:
    async def run() -> None:
        agent = _FakeAgent()
        selector = PydanticAIFrameSelector(agent=agent, candidates_per_anchor=2)

        result = await selector.select(_frames(tmp_path, anchor_count=2), context=_context())

        assert agent.calls == []
        assert result.diagnostics.selection_method == "local_partial"
        assert [frame.anchor_index for frame in result.frames] == [0, 1]
        assert result.diagnostics.selected_frame_count == 2
        assert result.diagnostics.target_frame_count == TARGET_FRAMES

    asyncio.run(run())


def test_pydantic_ai_selector_raises_on_wrong_anchor_choice(tmp_path) -> None:
    async def run() -> None:
        choices = _default_choices()
        choices[0] = AnchorChoice(anchor_index=0, candidate_id="frame_003")
        selector = PydanticAIFrameSelector(
            agent=_FakeAgent(choices=choices),
            candidates_per_anchor=2,
        )

        with pytest.raises(FrameSelectionValidationError):
            await selector.select(_frames(tmp_path), context=_context())

    asyncio.run(run())


def test_pydantic_ai_selector_raises_when_api_fails(tmp_path) -> None:
    async def run() -> None:
        agent = _FailingAgent()
        selector = PydanticAIFrameSelector(agent=agent)

        with pytest.raises(FrameSelectionError, match="Pydantic AI frame selection failed"):
            await selector.select(_frames(tmp_path), context=_context())
        assert len(agent.calls) == 1

    asyncio.run(run())


def _default_choices() -> list[AnchorChoice]:
    return [
        AnchorChoice(anchor_index=anchor_index, candidate_id=f"frame_{anchor_index * 2 + 1:03d}")
        for anchor_index in range(TARGET_FRAMES)
    ]


def _context() -> PreviewContext:
    return PreviewContext(
        info_hash="abc123",
        selected_file=SelectedFile(index=0, path="movie.mp4", length=100_000),
    )


def _frames(
    tmp_path: Path,
    *,
    anchor_count: int = TARGET_FRAMES,
    candidates_per_anchor: int = 2,
) -> list[ExtractedFrame]:
    frames: list[ExtractedFrame] = []
    for anchor_index in range(anchor_count):
        for candidate_index in range(candidates_per_anchor):
            index = len(frames)
            path = tmp_path / f"frame-{index}.jpg"
            image = np.full((360, 640, 3), 40 + (index * 5), dtype=np.uint8)
            image[:, candidate_index * 160 : (candidate_index * 160) + 180] = (
                180,
                40 + index * 3,
                90,
            )
            cv2.putText(
                image,
                f"{anchor_index}:{candidate_index}",
                (50, 190),
                cv2.FONT_HERSHEY_SIMPLEX,
                2.0,
                (240, 240, 240),
                6,
            )
            assert cv2.imwrite(str(path), image)
            frames.append(
                ExtractedFrame(
                    path=path,
                    score=1.0 - (candidate_index * 0.1),
                    width=640,
                    height=360,
                    timestamp_seconds=float((anchor_index + 1) * 10 + candidate_index),
                    anchor_index=anchor_index,
                    anchor_ratio=(anchor_index + 1) / (TARGET_FRAMES + 1),
                    decode_method="anchor-window",
                )
            )
    return frames
