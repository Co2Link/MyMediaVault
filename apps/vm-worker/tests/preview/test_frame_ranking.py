from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from pydantic_ai.messages import ImageUrl

from mymediavault_vm_worker.preview.core.models import (
    ExtractedFrame,
    PreviewContext,
    SelectedFile,
)
from mymediavault_vm_worker.preview.ranking import PydanticAIFrameRanker
from mymediavault_vm_worker.preview.ranking.pydantic_ai import FrameRankingOutput


@dataclass
class _FakeAgentResult:
    output: FrameRankingOutput


class _FakeAgent:
    def __init__(self, choices: list[str] | None = None) -> None:
        self.choices = ["frame_001", "frame_002"] if choices is None else choices
        self.calls: list[dict[str, Any]] = []

    async def run(self, user_prompt: Any, **kwargs: Any) -> _FakeAgentResult:
        self.calls.append({"user_prompt": user_prompt, **kwargs})
        return _FakeAgentResult(
            FrameRankingOutput(choices=self.choices, reason="fake selection")
        )


class _FailingAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run(self, user_prompt: Any, **kwargs: Any) -> _FakeAgentResult:
        self.calls.append({"user_prompt": user_prompt, **kwargs})
        msg = "api unavailable"
        raise RuntimeError(msg)


class _TimeoutThenSuccessAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run(self, user_prompt: Any, **kwargs: Any) -> _FakeAgentResult:
        self.calls.append({"user_prompt": user_prompt, **kwargs})
        if len(self.calls) == 1:
            raise TimeoutError("request timed out")
        return _FakeAgentResult(
            FrameRankingOutput(
                choices=["frame_001", "frame_002"],
                reason="retry selection",
            )
        )


def test_pydantic_ai_ranker_uses_vision_request(tmp_path) -> None:
    async def run() -> None:
        agent = _FakeAgent()
        ranker = PydanticAIFrameRanker(agent=agent, candidates_per_anchor=3)

        result = await ranker.rank(
            _frames(tmp_path, 2),
            target_frames=2,
            context=_context(),
        )

        selected = result.frames
        assert len(selected) == 2
        assert [round(frame.timestamp_seconds) for frame in selected] == [10, 20]
        assert [frame.accepted_by_llm for frame in selected] == [True, True]
        assert result.llm.candidate_frame_count == 2
        assert result.llm.selected_frame_count == 2
        assert result.llm.target_frame_count == 2
        assert result.llm.reason == "fake selection"
        assert result.llm.eligible_anchor_indexes == [0, 1]
        assert result.llm.selected_anchor_indexes == [0, 1]
        assert len(agent.calls) == 1
        call = agent.calls[0]
        assert call["model_settings"] == {"timeout": 8.0}
        assert "output_type" in call
        content = call["user_prompt"]
        assert any(isinstance(item, ImageUrl) for item in content)
        prompt_text = "\n".join(item for item in content if isinstance(item, str))
        assert "Choose preview frames" in prompt_text
        assert "Return choices in that same order" in prompt_text

    asyncio.run(run())


def test_pydantic_ai_ranker_keeps_top_candidates_per_anchor(tmp_path) -> None:
    async def run() -> None:
        agent = _FakeAgent(choices=["frame_002", "frame_004", "frame_006"])
        ranker = PydanticAIFrameRanker(agent=agent, candidates_per_anchor=2)
        frames = _frames(tmp_path, 6, paired_anchors=True)

        result = await ranker.rank(
            frames,
            target_frames=3,
            context=_context(),
        )

        selected = result.frames
        assert len(selected) == 3
        assert {frame.anchor_index for frame in selected} == {0, 1, 2}
        assert (
            len(
                [
                    item
                    for item in agent.calls[0]["user_prompt"]
                    if isinstance(item, ImageUrl)
                ]
            )
            == 6
        )

    asyncio.run(run())


def test_pydantic_ai_ranker_repairs_wrong_anchor_choices(tmp_path) -> None:
    async def run() -> None:
        agent = _FakeAgent(choices=["frame_003", "frame_003"])
        ranker = PydanticAIFrameRanker(agent=agent, candidates_per_anchor=2)
        frames = _frames(tmp_path, 4, paired_anchors=True)

        result = await ranker.rank(
            frames,
            target_frames=2,
            context=_context(),
        )

        selected = result.frames
        assert len(selected) == 2
        assert [frame.anchor_index for frame in selected] == [0, 1]
        assert [frame.timestamp_seconds for frame in selected] == [10.0, 30.0]
        assert result.llm.repaired_anchor_indexes == [0]

    asyncio.run(run())


def test_pydantic_ai_ranker_uses_eligible_anchor_order_for_partials(tmp_path) -> None:
    async def run() -> None:
        agent = _FakeAgent(choices=["frame_001", "frame_005"])
        ranker = PydanticAIFrameRanker(agent=agent, candidates_per_anchor=2)
        frames = _frames(tmp_path, 6, paired_anchors=True)

        result = await ranker.rank(
            frames,
            target_frames=3,
            eligible_anchor_indexes=[0, 2],
            context=_context(),
        )

        assert [frame.anchor_index for frame in result.frames] == [0, 2]
        assert result.llm.eligible_anchor_indexes == [0, 2]
        assert result.llm.selected_anchor_indexes == [0, 2]

    asyncio.run(run())


def test_pydantic_ai_ranker_groups_prompt_candidates_by_anchor(tmp_path) -> None:
    async def run() -> None:
        agent = _FakeAgent(choices=["frame_001", "frame_003"])
        ranker = PydanticAIFrameRanker(agent=agent, candidates_per_anchor=2)
        frames = _frames(tmp_path, 4, paired_anchors=True)
        interleaved_by_timestamp = [
            replace(frames[0], timestamp_seconds=10.0),
            replace(frames[1], timestamp_seconds=40.0),
            replace(frames[2], timestamp_seconds=20.0),
            replace(frames[3], timestamp_seconds=30.0),
        ]

        await ranker.rank(
            interleaved_by_timestamp,
            target_frames=2,
            context=_context(),
        )

        prompt_text = [
            item for item in agent.calls[0]["user_prompt"] if isinstance(item, str)
        ]
        group_lines = [
            item for item in prompt_text if item.startswith("Anchor group:")
        ]
        assert group_lines == [
            "Anchor group: anchor_index=0",
            "Anchor group: anchor_index=1",
        ]

    asyncio.run(run())


def test_pydantic_ai_ranker_raises_when_api_fails(tmp_path) -> None:
    async def run() -> None:
        agent = _FailingAgent()
        ranker = PydanticAIFrameRanker(agent=agent)

        with pytest.raises(RuntimeError, match="Pydantic AI frame ranking failed"):
            await ranker.rank(
                _frames(tmp_path, 2),
                target_frames=2,
                context=_context(),
            )
        assert len(agent.calls) == 1

    asyncio.run(run())


def test_pydantic_ai_ranker_retries_timeout_once(tmp_path) -> None:
    async def run() -> None:
        agent = _TimeoutThenSuccessAgent()
        ranker = PydanticAIFrameRanker(agent=agent)

        result = await ranker.rank(
            _frames(tmp_path, 2),
            target_frames=2,
            context=_context(),
        )

        assert len(agent.calls) == 2
        assert [frame.anchor_index for frame in result.frames] == [0, 1]
        assert result.llm.reason == "retry selection"

    asyncio.run(run())


def _context() -> PreviewContext:
    return PreviewContext(
        info_hash="abc123",
        selected_file=SelectedFile(index=0, path="movie.mp4", length=100_000),
    )


def _frames(
    tmp_path: Path,
    count: int,
    *,
    paired_anchors: bool = False,
) -> list[ExtractedFrame]:
    frames: list[ExtractedFrame] = []
    for index in range(count):
        path = tmp_path / f"frame-{index}.jpg"
        image = np.full((360, 640, 3), 40 + (index * 25), dtype=np.uint8)
        image[:, index * 80 : (index * 80) + 180] = (180, 40 + index * 20, 90)
        cv2.putText(
            image,
            str(index),
            (50 + index * 20, 190),
            cv2.FONT_HERSHEY_SIMPLEX,
            3.0,
            (240, 240, 240),
            8,
        )
        assert cv2.imwrite(str(path), image)
        anchor_index = index // 2 if paired_anchors else index
        frames.append(
            ExtractedFrame(
                path=path,
                score=1.0 - (index * 0.1),
                width=640,
                height=360,
                timestamp_seconds=float((index + 1) * 10),
                anchor_index=anchor_index,
                anchor_ratio=(anchor_index + 1) / 4,
                decode_method="anchor-window",
            )
        )
    return frames
