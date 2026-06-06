"""Pydantic AI-backed frame selector."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol, cast

import logfire
from loguru import logger
from pydantic_ai import Agent, AgentRunResult
from pydantic_ai.messages import UserContent

from mymediavault_vm_worker.preview.core.models import (
    ExtractedFrame,
    FrameSelectionDiagnostics,
    PreviewContext,
    TARGET_FRAMES,
)
from mymediavault_vm_worker.preview.frame_selection.base import (
    FrameSelectionError,
    FrameSelectionResult,
    FrameSelectionValidationError,
)
from mymediavault_vm_worker.preview.frame_selection.candidates import (
    FrameCandidate,
    candidate_pool,
    eligible_anchor_indexes,
    local_partial_selection,
)
from mymediavault_vm_worker.preview.frame_selection.images import thumbnail_data_url
from mymediavault_vm_worker.preview.frame_selection.models import (
    AnchorChoice,
    FrameSelectionOutput,
)
from mymediavault_vm_worker.preview.frame_selection.prompt import input_content
from mymediavault_vm_worker.preview.llm.observability import configure_logfire
from mymediavault_vm_worker.preview.llm.providers import (
    LLMConfigurationError,
    configure_llm_observability,
    openai_responses_model,
)
from mymediavault_vm_worker.preview.logging import bind_log


class _SelectionAgent(Protocol):
    async def run(
        self, user_prompt: list[UserContent], **kwargs: object
    ) -> AgentRunResult[FrameSelectionOutput]: ...


class PydanticAIFrameSelector:
    """Choose one timestamp-verified preview candidate per target anchor."""

    def __init__(
        self,
        *,
        model: str = "gpt-5.4-mini",
        timeout_seconds: float = 30.0,
        candidates_per_anchor: int = 3,
        min_candidates_per_anchor: int = 2,
        agent: _SelectionAgent | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            msg = "PydanticAIFrameSelector.timeout_seconds must be greater than 0"
            raise ValueError(msg)
        if candidates_per_anchor < 1:
            msg = "PydanticAIFrameSelector.candidates_per_anchor must be at least 1"
            raise ValueError(msg)
        if min_candidates_per_anchor < 1:
            msg = (
                "PydanticAIFrameSelector.min_candidates_per_anchor must be at least 1"
            )
            raise ValueError(msg)
        if min_candidates_per_anchor > candidates_per_anchor:
            msg = (
                "PydanticAIFrameSelector.min_candidates_per_anchor must be less than "
                "or equal to candidates_per_anchor"
            )
            raise ValueError(msg)
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._candidates_per_anchor = candidates_per_anchor
        self._min_candidates_per_anchor = min_candidates_per_anchor
        self._agent = agent

    async def select(
        self,
        frames: list[ExtractedFrame],
        *,
        context: PreviewContext,
    ) -> FrameSelectionResult:
        eligible = eligible_anchor_indexes(
            frames,
            min_candidates_per_anchor=self._min_candidates_per_anchor,
        )
        if eligible != list(range(TARGET_FRAMES)):
            result = local_partial_selection(
                frames,
                min_candidates_per_anchor=self._min_candidates_per_anchor,
            )
            bind_log(
                info_hash=context.info_hash,
                selected_file=context.selected_file.path,
                selector="local-partial",
                candidate_count=len(frames),
                selected_frame_count=len(result.frames),
                eligible_anchor_indexes=eligible,
            ).info(
                "Selected local partial preview frames because not all anchors are eligible"
            )
            return result

        candidates = _candidate_inputs(
            candidate_pool(frames, candidates_per_anchor=self._candidates_per_anchor)
        )
        if not candidates:
            return local_partial_selection(
                frames,
                min_candidates_per_anchor=self._min_candidates_per_anchor,
            )

        try:
            agent = self._agent or self._default_agent()
        except LLMConfigurationError:
            raise

        try:
            output = await self._select(agent, candidates=candidates, context=context)
            selected = _selected_frames_from_output(output, candidates=candidates)
        except FrameSelectionError:
            raise
        except Exception as exc:
            msg = f"Pydantic AI frame selection failed: {exc}"
            raise FrameSelectionError(msg) from exc

        selected_anchor_indexes = [
            frame.anchor_index for frame in selected if frame.anchor_index is not None
        ]
        bind_log(
            info_hash=context.info_hash,
            selected_file=context.selected_file.path,
            selector="pydantic-ai",
            model=self._model,
            candidate_count=len(candidates),
            target_frames=TARGET_FRAMES,
            candidates_per_anchor=self._candidates_per_anchor,
            model_selected_choices=[
                choice.model_dump() for choice in output.choices
            ],
            selected_frame_count=len(selected),
            reason=output.reason,
        ).info(
            "Pydantic AI frame selector selected "
            f"{len(selected)}/{TARGET_FRAMES} target anchors from {len(candidates)} candidates"
        )
        return FrameSelectionResult(
            frames=selected,
            diagnostics=FrameSelectionDiagnostics(
                selection_method="openai",
                model=self._model,
                candidate_frame_count=len(candidates),
                selected_frame_count=len(selected),
                target_frame_count=TARGET_FRAMES,
                reason=output.reason,
                eligible_anchor_indexes=list(range(TARGET_FRAMES)),
                selected_anchor_indexes=selected_anchor_indexes,
            ),
        )

    def _default_agent(self) -> _SelectionAgent:
        configure_llm_observability()
        model = openai_responses_model(self._model)
        return cast(
            "_SelectionAgent",
            Agent(
                model=model,
                output_type=FrameSelectionOutput,
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

    async def _select(
        self,
        agent: _SelectionAgent,
        *,
        candidates: list[FrameCandidate],
        context: PreviewContext,
    ) -> FrameSelectionOutput:
        configure_logfire()
        with logfire.span(
            "select preview frames",
            model=self._model,
            candidate_count=len(candidates),
            target_frames=TARGET_FRAMES,
            selected_file=context.selected_file.path,
        ):
            result = await agent.run(
                input_content(candidates, context),
                model_settings={"timeout": self._timeout_seconds},
            )
        return result.output


def _candidate_inputs(frames: list[ExtractedFrame]) -> list[FrameCandidate]:
    candidates: list[FrameCandidate] = []
    for index, frame in enumerate(frames, start=1):
        image_url = thumbnail_data_url(frame)
        if image_url is None:
            logger.bind(frame_path=str(frame.path)).debug(
                "Skipping frame candidate because thumbnail encoding failed"
            )
            continue
        candidates.append(
            FrameCandidate(
                frame_id=f"frame_{index:03d}",
                frame=frame,
                image_url=image_url,
            )
        )
    return candidates


def _selected_frames_from_output(
    output: FrameSelectionOutput,
    *,
    candidates: list[FrameCandidate],
) -> list[ExtractedFrame]:
    by_id = {candidate.frame_id: candidate for candidate in candidates}
    expected_anchor_indexes = set(range(TARGET_FRAMES))
    seen_anchor_indexes: set[int] = set()
    seen_candidate_ids: set[str] = set()
    selected: list[ExtractedFrame] = []

    for choice in output.choices:
        _validate_choice(
            choice,
            by_id=by_id,
            expected_anchor_indexes=expected_anchor_indexes,
            seen_anchor_indexes=seen_anchor_indexes,
            seen_candidate_ids=seen_candidate_ids,
        )
        candidate = by_id[choice.candidate_id]
        selected.append(replace(candidate.frame))
        seen_anchor_indexes.add(choice.anchor_index)
        seen_candidate_ids.add(choice.candidate_id)

    if seen_anchor_indexes != expected_anchor_indexes:
        missing = sorted(expected_anchor_indexes - seen_anchor_indexes)
        unexpected = sorted(seen_anchor_indexes - expected_anchor_indexes)
        msg = (
            "Frame selection output did not cover the exact target anchors: "
            f"missing={missing}, unexpected={unexpected}"
        )
        raise FrameSelectionValidationError(msg)

    return sorted(
        selected,
        key=lambda frame: (
            frame.anchor_index if frame.anchor_index is not None else TARGET_FRAMES,
            frame.timestamp_seconds,
        ),
    )


def _validate_choice(
    choice: AnchorChoice,
    *,
    by_id: dict[str, FrameCandidate],
    expected_anchor_indexes: set[int],
    seen_anchor_indexes: set[int],
    seen_candidate_ids: set[str],
) -> None:
    if choice.anchor_index not in expected_anchor_indexes:
        msg = f"Unexpected anchor_index in frame selection output: {choice.anchor_index}"
        raise FrameSelectionValidationError(msg)
    if choice.anchor_index in seen_anchor_indexes:
        msg = f"Duplicate anchor_index in frame selection output: {choice.anchor_index}"
        raise FrameSelectionValidationError(msg)
    if choice.candidate_id in seen_candidate_ids:
        msg = f"Duplicate candidate_id in frame selection output: {choice.candidate_id}"
        raise FrameSelectionValidationError(msg)
    candidate = by_id.get(choice.candidate_id)
    if candidate is None:
        msg = f"Unknown candidate_id in frame selection output: {choice.candidate_id}"
        raise FrameSelectionValidationError(msg)
    if candidate.frame.anchor_index != choice.anchor_index:
        msg = (
            "Frame selection output candidate belongs to the wrong anchor: "
            f"candidate_id={choice.candidate_id}, "
            f"choice_anchor={choice.anchor_index}, "
            f"candidate_anchor={candidate.frame.anchor_index}"
        )
        raise FrameSelectionValidationError(msg)
