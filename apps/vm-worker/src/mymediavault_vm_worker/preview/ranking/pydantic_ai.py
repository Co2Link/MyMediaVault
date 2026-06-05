"""Pydantic AI-backed frame ranking."""

from __future__ import annotations

import base64
import asyncio
from dataclasses import dataclass, replace
import os
from typing import Protocol, cast

import cv2
import logfire
from mymediavault_vm_worker.preview.logging import bind_log
from pydantic import BaseModel, Field, create_model
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


class FrameRankingOutput(BaseModel):
    """Structured frame chooser output returned by the model."""

    choices: list[str] = Field(
        default_factory=list,
        description=(
            "Selected candidate ids in the same order as the supplied anchor groups."
        ),
    )
    reason: str


@dataclass(frozen=True)
class _RankCandidate:
    frame_id: str
    frame: ExtractedFrame
    image_url: str


@dataclass(frozen=True)
class _RankSelection:
    selected_ids: list[str]
    reason: str


class _AgentResult(Protocol):
    output: FrameRankingOutput


class _RankingAgent(Protocol):
    async def run(
        self, user_prompt: list[UserContent], **kwargs: object
    ) -> _AgentResult: ...


class PydanticAIFrameRanker:
    """Choose timestamp-verified anchor preview candidates with Pydantic AI."""

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
        eligible_anchor_indexes: list[int] | None = None,
    ) -> FrameRankingResult:
        eligible = (
            list(range(target_frames))
            if eligible_anchor_indexes is None
            else list(eligible_anchor_indexes)
        )
        pool = _candidate_pool(
            frames,
            target_frames=target_frames,
            candidates_per_anchor=self._candidates_per_anchor,
            eligible_anchor_indexes=eligible,
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
                    eligible_anchor_indexes=eligible,
                ),
            )

        try:
            agent = self._agent or self._default_agent()
        except LLMConfigurationError:
            raise

        try:
            selection = await self._select_ids_with_timeout_retry(
                agent,
                candidates=candidates,
                target_frames=target_frames,
                eligible_anchor_indexes=eligible,
                context=context,
            )
        except Exception as exc:
            msg = f"Pydantic AI frame ranking failed: {exc}"
            raise RuntimeError(msg) from exc

        selected, repaired = _selected_frames_from_ids(
            selection.selected_ids,
            candidates=candidates,
            eligible_anchor_indexes=eligible,
        )
        selected_anchor_indexes = [
            frame.anchor_index for frame in selected if frame.anchor_index is not None
        ]
        bind_log(
            info_hash=context.info_hash,
            selected_file=context.selected_file.path,
            ranker="pydantic-ai",
            model=self._model,
            candidate_count=len(candidates),
            target_frames=target_frames,
            eligible_anchor_indexes=eligible,
            candidates_per_anchor=self._candidates_per_anchor,
            model_selected_ids=selection.selected_ids,
            selected_frame_count=len(selected),
            repaired_anchor_indexes=repaired,
            reason=selection.reason,
        ).info(
            "Pydantic AI frame chooser selected "
            f"{len(selected)}/{len(eligible)} eligible anchors from {len(candidates)} candidates"
        )
        return FrameRankingResult(
            frames=selected,
            llm=LLMSelectionDiagnostics(
                model=self._model,
                candidate_frame_count=len(candidates),
                selected_frame_count=len(selected),
                target_frame_count=target_frames,
                reason=selection.reason,
                eligible_anchor_indexes=eligible,
                selected_anchor_indexes=selected_anchor_indexes,
                repaired_anchor_indexes=repaired,
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
                    "You choose video preview frames. Candidates have already "
                    "passed local clean-decode and image sanity checks. Choose "
                    "exactly one candidate id from each anchor group; do not reject "
                    "an anchor group. Prefer frames that help downstream actor "
                    "identification: clear, sharp, well-lit human faces first, "
                    "clearly visible people next, and representative frames only "
                    "when no usable person is visible for that anchor."
                ),
            ),
        )

    async def _select_ids_with_timeout_retry(
        self,
        agent: _RankingAgent,
        *,
        candidates: list[_RankCandidate],
        target_frames: int,
        eligible_anchor_indexes: list[int],
        context: PreviewContext,
    ) -> _RankSelection:
        try:
            return await self._select_ids(
                agent,
                candidates=candidates,
                target_frames=target_frames,
                eligible_anchor_indexes=eligible_anchor_indexes,
                context=context,
            )
        except Exception as exc:
            if not _is_timeout_exception(exc):
                raise
            bind_log(
                info_hash=context.info_hash,
                selected_file=context.selected_file.path,
                ranker="pydantic-ai",
                model=self._model,
                candidate_count=len(candidates),
                target_frames=target_frames,
                eligible_anchor_indexes=eligible_anchor_indexes,
                timeout_seconds=self._timeout_seconds,
                error=str(exc),
            ).warning("Pydantic AI frame chooser timed out; retrying once")
            return await self._select_ids(
                agent,
                candidates=candidates,
                target_frames=target_frames,
                eligible_anchor_indexes=eligible_anchor_indexes,
                context=context,
            )

    async def _select_ids(
        self,
        agent: _RankingAgent,
        *,
        candidates: list[_RankCandidate],
        target_frames: int,
        eligible_anchor_indexes: list[int],
        context: PreviewContext,
    ) -> _RankSelection:
        configure_logfire()
        with logfire.span(
            "rank preview frames",
            model=self._model,
            candidate_count=len(candidates),
            target_frames=target_frames,
            eligible_anchor_count=len(eligible_anchor_indexes),
            selected_file=context.selected_file.path,
        ):
            result = await agent.run(
                _input_content(candidates, target_frames, context),
                output_type=_output_model(len(eligible_anchor_indexes)),
                model_settings={"timeout": self._timeout_seconds},
            )
        output = result.output
        return _RankSelection(
            selected_ids=list(output.choices),
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


def _is_timeout_exception(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return True
    message = str(exc).lower()
    return "timed out" in message or "timeout" in message


def _candidate_pool(
    frames: list[ExtractedFrame],
    *,
    target_frames: int,
    candidates_per_anchor: int,
    eligible_anchor_indexes: list[int],
) -> list[ExtractedFrame]:
    required_anchor_indexes = {
        index for index in eligible_anchor_indexes if 0 <= index < target_frames
    }
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
    return sorted(
        pool,
        key=lambda frame: (
            frame.anchor_index if frame.anchor_index is not None else target_frames,
            -frame.score,
            frame.timestamp_seconds,
        ),
    )


def _selected_frames_from_ids(
    selected_ids: list[str],
    *,
    candidates: list[_RankCandidate],
    eligible_anchor_indexes: list[int],
) -> tuple[list[ExtractedFrame], list[int]]:
    by_id = {candidate.frame_id: candidate for candidate in candidates}
    by_anchor: dict[int, list[_RankCandidate]] = {}
    for candidate in candidates:
        anchor_index = candidate.frame.anchor_index
        if anchor_index is None:
            continue
        by_anchor.setdefault(anchor_index, []).append(candidate)
    for anchor_candidates in by_anchor.values():
        anchor_candidates.sort(key=lambda candidate: candidate.frame.score, reverse=True)

    selected: list[ExtractedFrame] = []
    repaired: list[int] = []
    used_ids: set[str] = set()
    for anchor_index, selected_id in zip(
        eligible_anchor_indexes, selected_ids, strict=False
    ):
        candidate = by_id.get(selected_id)
        if (
            candidate is None
            or candidate.frame.anchor_index != anchor_index
            or selected_id in used_ids
        ):
            anchor_candidates = by_anchor.get(anchor_index, [])
            candidate = anchor_candidates[0] if anchor_candidates else None
            repaired.append(anchor_index)
        if candidate is None:
            continue
        used_ids.add(candidate.frame_id)
        selected.append(replace(candidate.frame, accepted_by_llm=True))
    return selected, repaired


def _output_model(choice_count: int) -> type[FrameRankingOutput]:
    return create_model(
        f"FrameRankingOutput{choice_count}",
        __base__=FrameRankingOutput,
        choices=(
            list[str],
            Field(
                min_length=choice_count,
                max_length=choice_count,
                description=(
                    "Selected candidate ids in the same order as the supplied "
                    "anchor groups. Always choose one id per anchor group."
                ),
            ),
        ),
    )


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
            f"Choose preview frames for {context.selected_file.path}. Anchor "
            "groups appear in order below. Return choices in that same order. "
            f"The target preview has {target_frames} anchors, but this request may "
            "include only anchors that currently have enough clean candidates."
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
                    f"{candidate.frame_id}: timestamp={frame.timestamp_seconds:.3f}s, "
                    f"score={frame.score:.4f}, "
                    f"size={frame.width}x{frame.height}, "
                    f"anchor_ratio={frame.anchor_ratio}, "
                    f"decode_method={frame.decode_method}"
                ),
                ImageUrl(url=candidate.image_url),
            ]
        )
    return content
