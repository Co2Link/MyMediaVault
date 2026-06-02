from __future__ import annotations

import asyncio
from dataclasses import dataclass
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
from mymediavault_vm_worker.preview.ranking.pydantic_ai import (
    FrameRankingAnchorChoice,
    FrameRankingOutput,
)


@dataclass
class _FakeAgentResult:
    output: FrameRankingOutput


class _FakeAgent:
    def __init__(
        self,
        accepted_ids: list[str] | None = None,
        accepted_id_batches: list[list[str]] | None = None,
        output: FrameRankingOutput | None = None,
        output_batches: list[FrameRankingOutput] | None = None,
    ) -> None:
        self.accepted_ids = (
            ["frame_002", "frame_001"] if accepted_ids is None else accepted_ids
        )
        self.accepted_id_batches = list(accepted_id_batches or [])
        self.output = output
        self.output_batches = list(output_batches or [])
        self.calls: list[dict[str, Any]] = []

    async def run(self, user_prompt: Any, **kwargs: Any) -> _FakeAgentResult:
        self.calls.append({"user_prompt": user_prompt, **kwargs})
        if self.output_batches:
            return _FakeAgentResult(self.output_batches.pop(0))
        if self.output is not None:
            return _FakeAgentResult(self.output)
        accepted_ids = (
            self.accepted_id_batches.pop(0)
            if self.accepted_id_batches
            else self.accepted_ids
        )
        return _FakeAgentResult(
            FrameRankingOutput(
                accepted_ids=accepted_ids,
                reason="fake selection",
            )
        )


class _FailingAgent:
    async def run(self, user_prompt: Any, **kwargs: Any) -> _FakeAgentResult:
        del user_prompt, kwargs
        msg = "api unavailable"
        raise RuntimeError(msg)


def test_pydantic_ai_ranker_uses_vision_request(tmp_path) -> None:
    async def run() -> None:
        agent = _FakeAgent()
        ranker = PydanticAIFrameRanker(agent=agent, candidates_per_anchor=3)

        result = await ranker.rank(
            _frames(tmp_path, 3),
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
        assert len(agent.calls) == 1
        call = agent.calls[0]
        assert call["model_settings"] == {"timeout": 8.0}
        content = call["user_prompt"]
        assert any(isinstance(item, ImageUrl) for item in content)
        prompt_text = "\n".join(item for item in content if isinstance(item, str))
        assert "downstream application identify actors" in prompt_text
        assert "clear, sharp, well-lit human faces are best" in prompt_text
        assert "fallback choices only when no usable person is visible" in prompt_text
        assert "Return anchor_choices with exactly one decision" in prompt_text

    asyncio.run(run())


def test_pydantic_ai_ranker_returns_only_model_accepted_frames(tmp_path) -> None:
    async def run() -> None:
        agent = _FakeAgent(accepted_ids=["frame_003"])
        ranker = PydanticAIFrameRanker(agent=agent, candidates_per_anchor=3)

        result = await ranker.rank(
            _frames(tmp_path, 3),
            target_frames=3,
            context=_context(),
        )

        selected = result.frames
        assert len(selected) == 1
        assert [frame.timestamp_seconds for frame in selected] == [30.0]
        assert all(frame.accepted_by_llm for frame in selected)

    asyncio.run(run())


def test_pydantic_ai_ranker_keeps_top_candidates_per_anchor(tmp_path) -> None:
    async def run() -> None:
        agent = _FakeAgent(accepted_ids=["frame_002", "frame_004"])
        ranker = PydanticAIFrameRanker(agent=agent, candidates_per_anchor=2)
        frames = _frames(tmp_path, 6, paired_anchors=True)

        result = await ranker.rank(
            frames,
            target_frames=3,
            context=_context(),
        )

        selected = result.frames
        assert len(selected) == 2
        assert {frame.anchor_index for frame in selected} == {0, 1}
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


def test_pydantic_ai_ranker_deduplicates_accepted_ids_by_anchor(tmp_path) -> None:
    async def run() -> None:
        agent = _FakeAgent(
            accepted_ids=[
                "frame_001",
                "frame_002",
                "frame_003",
                "frame_004",
                "frame_005",
            ]
        )
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
        assert all(frame.accepted_by_llm for frame in selected)

    asyncio.run(run())


def test_pydantic_ai_ranker_uses_single_call_anchor_choices(tmp_path) -> None:
    async def run() -> None:
        agent = _FakeAgent(
            output=FrameRankingOutput(
                anchor_choices=[
                    FrameRankingAnchorChoice(
                        anchor_index=0,
                        accepted_id="frame_001",
                    ),
                    FrameRankingAnchorChoice(
                        anchor_index=1,
                        accepted_id="frame_003",
                    ),
                    FrameRankingAnchorChoice(
                        anchor_index=2,
                        accepted_id="frame_005",
                    ),
                ],
                reason="fake per-anchor selection",
            ),
        )
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
        assert [frame.timestamp_seconds for frame in selected] == [10.0, 30.0, 50.0]
        assert result.llm.reason == "fake per-anchor selection"
        assert len(agent.calls) == 1

    asyncio.run(run())


def test_pydantic_ai_ranker_rejects_mismatched_anchor_choices(tmp_path) -> None:
    async def run() -> None:
        agent = _FakeAgent(
            output=FrameRankingOutput(
                anchor_choices=[
                    FrameRankingAnchorChoice(
                        anchor_index=0,
                        accepted_id="frame_003",
                    ),
                    FrameRankingAnchorChoice(
                        anchor_index=1,
                        accepted_id="frame_003",
                    ),
                ],
                reason="fake validated selection",
            ),
        )
        ranker = PydanticAIFrameRanker(agent=agent, candidates_per_anchor=2)
        frames = _frames(tmp_path, 4, paired_anchors=True)

        result = await ranker.rank(
            frames,
            target_frames=2,
            context=_context(),
        )

        selected = result.frames
        assert len(selected) == 1
        assert selected[0].anchor_index == 1
        assert selected[0].timestamp_seconds == 30.0
        assert len(agent.calls) == 1

    asyncio.run(run())


def test_pydantic_ai_ranker_returns_empty_selection_when_model_accepts_none(
    tmp_path,
) -> None:
    async def run() -> None:
        agent = _FakeAgent(accepted_ids=[])
        ranker = PydanticAIFrameRanker(agent=agent, candidates_per_anchor=3)

        result = await ranker.rank(
            _frames(tmp_path, 3),
            target_frames=3,
            context=_context(),
        )

        assert result.frames == []
        assert result.llm.selected_frame_count == 0

    asyncio.run(run())


def test_pydantic_ai_ranker_raises_when_api_fails(tmp_path) -> None:
    async def run() -> None:
        ranker = PydanticAIFrameRanker(agent=_FailingAgent())

        with pytest.raises(RuntimeError, match="Pydantic AI frame ranking failed"):
            await ranker.rank(
                _frames(tmp_path, 2),
                target_frames=2,
                context=_context(),
            )

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
