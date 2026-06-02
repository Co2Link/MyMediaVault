"""Pydantic AI-backed frame ranking."""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace
import os
from typing import Protocol, cast

import cv2
import logfire
from mymediavault_vm_worker.preview.logging import bind_log
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.messages import ImageUrl, UserContent

from mymediavault_vm_worker.preview.llm.providers import (
    LLMConfigurationError,
    configure_llm_observability,
    openai_responses_model,
)
from mymediavault_vm_worker.preview.core.models import (
    ExtractedFrame,
    LLMSelectionDiagnostics,
    PreviewContext,
)
from mymediavault_vm_worker.preview.llm.observability import configure_logfire
from mymediavault_vm_worker.preview.ranking.base import FrameRankingResult

_THUMBNAIL_MAX_WIDTH = 320
_JPEG_QUALITY = 78


class FrameRankingAnchorChoice(BaseModel):
    """A single per-anchor frame acceptance decision."""

    anchor_index: int
    accepted_id: str | None = Field(
        default=None,
        description="Accepted candidate id for this anchor, or null when unusable.",
    )


class FrameRankingOutput(BaseModel):
    """Structured frame ranking output returned by the model."""

    anchor_choices: list[FrameRankingAnchorChoice] = Field(
        default_factory=list,
        description=(
            "One decision per requested anchor. Include accepted_id only when a "
            "candidate for that anchor is technically usable."
        ),
    )
    accepted_ids: list[str] = Field(
        default_factory=list,
        description="Deprecated fallback frame ids accepted for display.",
    )
    reason: str


@dataclass(frozen=True)
class _RankCandidate:
    frame_id: str
    frame: ExtractedFrame
    image_url: str


@dataclass(frozen=True)
class _RankSelection:
    accepted_ids: list[str]
    reason: str


class _AgentResult(Protocol):
    output: FrameRankingOutput


class _RankingAgent(Protocol):
    async def run(
        self, user_prompt: list[UserContent], **kwargs: object
    ) -> _AgentResult: ...


class PydanticAIFrameRanker:
    """Accept timestamp-verified anchor preview candidates with Pydantic AI."""

    def __init__(
        self,
        *,
        model: str = "gpt-5.4-mini",
        timeout_seconds: float = 8.0,
        candidates_per_anchor: int = 3,
        agent: _RankingAgent | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            msg = "PydanticAIFrameRanker.timeout_seconds must be greater than 0"
            raise ValueError(msg)
        if candidates_per_anchor < 1:
            msg = "PydanticAIFrameRanker.candidates_per_anchor must be at least 1"
            raise ValueError(msg)
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._candidates_per_anchor = candidates_per_anchor
        self._agent = agent

    async def rank(
        self,
        frames: list[ExtractedFrame],
        *,
        target_frames: int,
        context: PreviewContext,
    ) -> FrameRankingResult:
        pool = _candidate_pool(
            frames,
            target_frames=target_frames,
            candidates_per_anchor=self._candidates_per_anchor,
        )
        candidates = _rank_candidates(pool)
        if not candidates:
            return FrameRankingResult(
                frames=[],
                llm=LLMSelectionDiagnostics(
                    model=self._model,
                    candidate_frame_count=0,
                    selected_frame_count=0,
                    target_frame_count=target_frames,
                    reason="No candidate frames were available for LLM ranking",
                ),
            )

        try:
            agent = self._agent or self._default_agent()
        except LLMConfigurationError:
            raise

        try:
            selection = await self._select_ids(
                agent,
                candidates=candidates,
                target_frames=target_frames,
                context=context,
            )
        except Exception as exc:
            msg = f"Pydantic AI frame ranking failed: {exc}"
            raise RuntimeError(msg) from exc

        by_id = {candidate.frame_id: candidate.frame for candidate in candidates}
        selected = [
            replace(by_id[frame_id], accepted_by_llm=True)
            for frame_id in selection.accepted_ids
            if frame_id in by_id
        ]
        accepted = _dedupe_accepted_by_anchor(selected, target_frames)
        bind_log(
            info_hash=context.info_hash,
            selected_file=context.selected_file.path,
            ranker="pydantic-ai",
            model=self._model,
            candidate_count=len(candidates),
            target_frames=target_frames,
            candidates_per_anchor=self._candidates_per_anchor,
            model_selected_frame_count=len(selected),
            accepted_ids=selection.accepted_ids,
            selected_frame_count=len(accepted),
            reason=selection.reason,
        ).info(
            "Pydantic AI frame ranking selected "
            f"{len(accepted)}/{target_frames} frames from {len(candidates)} candidates"
        )
        return FrameRankingResult(
            frames=accepted,
            llm=LLMSelectionDiagnostics(
                model=self._model,
                candidate_frame_count=len(candidates),
                selected_frame_count=len(accepted),
                target_frame_count=target_frames,
                reason=selection.reason,
            ),
        )

    def _default_agent(self) -> _RankingAgent:
        configure_llm_observability()
        model = openai_responses_model(self._model)
        return cast(
            "_RankingAgent",
            Agent(
                model=model,
                output_type=FrameRankingOutput,
                instructions=(
                    "You accept video preview frames. Return only frames that are "
                    "visually clear and undamaged. Prefer frames that are most useful "
                    "for downstream actor identification: clear, sharp, well-lit "
                    "human faces first, then clearly visible people, then technically "
                    "usable representative frames only when no usable person is "
                    "visible for that anchor. When candidates have anchor_index "
                    "values, evaluate each required anchor and return at most one "
                    "acceptable frame per anchor. Return fewer only when all "
                    "candidates for an anchor are damaged or unusable."
                ),
            ),
        )

    async def _select_ids(
        self,
        agent: _RankingAgent,
        *,
        candidates: list[_RankCandidate],
        target_frames: int,
        context: PreviewContext,
    ) -> _RankSelection:
        configure_logfire()
        with logfire.span(
            "rank preview frames",
            model=self._model,
            candidate_count=len(candidates),
            target_frames=target_frames,
            selected_file=context.selected_file.path,
        ):
            result = await agent.run(
                _input_content(candidates, target_frames, context),
                model_settings={"timeout": self._timeout_seconds},
            )
        output = result.output
        accepted_ids = _accepted_ids_from_output(output, candidates, target_frames)
        return _RankSelection(
            accepted_ids=accepted_ids,
            reason=output.reason,
        )


def _rank_candidates(frames: list[ExtractedFrame]) -> list[_RankCandidate]:
    candidates: list[_RankCandidate] = []
    for index, frame in enumerate(frames, start=1):
        image_url = _thumbnail_data_url(frame)
        if image_url is None:
            continue
        candidates.append(
            _RankCandidate(
                frame_id=f"frame_{index:03d}",
                frame=frame,
                image_url=image_url,
            )
        )
    return candidates


def llm_visible_candidate_counts_by_anchor(
    frames: list[ExtractedFrame],
    *,
    target_frames: int,
    candidates_per_anchor: int,
) -> dict[int, int]:
    """Return candidate counts that would be visible to the LLM prompt."""

    counts: dict[int, int] = {}
    for candidate in _rank_candidates(
        _candidate_pool(
            frames,
            target_frames=target_frames,
            candidates_per_anchor=candidates_per_anchor,
        )
    ):
        anchor_index = candidate.frame.anchor_index
        if anchor_index is None:
            continue
        counts[anchor_index] = counts.get(anchor_index, 0) + 1
    return counts


def _candidate_pool(
    frames: list[ExtractedFrame],
    *,
    target_frames: int,
    candidates_per_anchor: int,
) -> list[ExtractedFrame]:
    required_anchor_indexes = set(range(target_frames))
    anchored = [
        frame
        for frame in frames
        if frame.anchor_index in required_anchor_indexes and frame.score > 0
    ]
    pool: list[ExtractedFrame] = []
    for anchor_index in sorted(required_anchor_indexes):
        anchor_frames = sorted(
            (frame for frame in anchored if frame.anchor_index == anchor_index),
            key=lambda frame: frame.score,
            reverse=True,
        )
        pool.extend(anchor_frames[:candidates_per_anchor])
    return sorted(pool, key=lambda frame: frame.timestamp_seconds)


def _dedupe_accepted_by_anchor(
    frames: list[ExtractedFrame], target_frames: int
) -> list[ExtractedFrame]:
    by_anchor: dict[int, ExtractedFrame] = {}
    for frame in frames:
        if frame.anchor_index is None or not 0 <= frame.anchor_index < target_frames:
            continue
        current = by_anchor.get(frame.anchor_index)
        if current is None or frame.score > current.score:
            by_anchor[frame.anchor_index] = frame
    return [by_anchor[index] for index in sorted(by_anchor)]


def _accepted_ids_from_output(
    output: FrameRankingOutput,
    candidates: list[_RankCandidate],
    target_frames: int,
) -> list[str]:
    by_id = {candidate.frame_id: candidate for candidate in candidates}
    accepted_ids: list[str] = []
    seen_anchor_indexes: set[int] = set()
    for choice in output.anchor_choices:
        accepted_id = choice.accepted_id
        if accepted_id is None:
            continue
        candidate = by_id.get(accepted_id)
        if candidate is None:
            continue
        anchor_index = candidate.frame.anchor_index
        if (
            anchor_index != choice.anchor_index
            or anchor_index is None
            or not 0 <= anchor_index < target_frames
            or anchor_index in seen_anchor_indexes
        ):
            continue
        seen_anchor_indexes.add(anchor_index)
        accepted_ids.append(accepted_id)

    if accepted_ids:
        return accepted_ids
    return [frame_id for frame_id in output.accepted_ids if isinstance(frame_id, str)]


def _thumbnail_data_url(frame: ExtractedFrame) -> str | None:
    return frame_thumbnail_data_url(frame.path)


def frame_thumbnail_data_url(path: str | os.PathLike[str]) -> str | None:
    """Encode an image path as a small JPEG data URL for vision requests."""

    image = cv2.imread(os.fspath(path), cv2.IMREAD_COLOR)
    if image is None:
        return None
    height, width = image.shape[:2]
    if width > _THUMBNAIL_MAX_WIDTH:
        scale = _THUMBNAIL_MAX_WIDTH / width
        image = cv2.resize(
            image,
            (_THUMBNAIL_MAX_WIDTH, max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    ok, encoded = cv2.imencode(
        ".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY]
    )
    if not ok:
        return None
    payload = base64.b64encode(encoded.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{payload}"


def _input_content(
    candidates: list[_RankCandidate],
    target_frames: int,
    context: PreviewContext,
) -> list[UserContent]:
    content: list[UserContent] = [
        (
            f"Accept preview frames for "
            f"{context.selected_file.path}. Prefer frames that help a downstream "
            "application identify actors: clear, sharp, well-lit human faces are "
            "best; clearly visible people are next best; technically usable "
            "representative frames are fallback choices only when no usable person "
            "is visible for that anchor. Avoid black screens, corruption, partial "
            "macroblock damage, title cards when better content exists, and "
            "unusable decode artifacts. "
            f"The success contract requires one accepted frame for each "
            f"anchor_index from 0 through {target_frames - 1}. Candidates are "
            "grouped by anchor_index. Return anchor_choices with exactly one "
            "decision for every anchor_index. Set accepted_id to the single best "
            "candidate id for that anchor when one is technically usable, or null "
            "only when all candidates for that anchor are unusable."
        )
    ]
    for candidate in candidates:
        frame = candidate.frame
        content.extend(
            [
                (
                    f"{candidate.frame_id}: timestamp={frame.timestamp_seconds:.3f}s, "
                    f"score={frame.score:.4f}, "
                    f"size={frame.width}x{frame.height}, "
                    f"anchor_index={frame.anchor_index}, "
                    f"anchor_ratio={frame.anchor_ratio}, "
                    f"decode_method={frame.decode_method}"
                ),
                ImageUrl(url=candidate.image_url),
            ]
        )
    return content
