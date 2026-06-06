"""PreviewEngine orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
import os
import sys
import time
from pathlib import Path
from typing import Any, cast

import logfire
from loguru import logger
from mymediavault_vm_worker.preview.logging import BoundLogger, bind_log

from mymediavault_vm_worker.preview.decoding.base import FrameDecoder
from mymediavault_vm_worker.preview.decoding.ffmpeg import FFmpegFrameDecoder
from mymediavault_vm_worker.preview.core.exceptions import (
    NoVideoFileError,
    PreviewError,
)
from mymediavault_vm_worker.preview.core.models import (
    AnchorRetryAttemptDiagnostics,
    AnchorRetryDiagnostics,
    BYTES_PER_MB,
    ExtractedFrame,
    FrameSelectionDiagnostics,
    GeneratedFrame,
    GeneratedSheet,
    PREVIEW_ARTIFACT_VERSION,
    PreviewArtifact,
    PreviewContext,
    PreviewDiagnostics,
    PreviewEngineConfig,
    PreviewRequest,
    PreviewResult,
    PreviewStatus,
    SelectedFile,
    TARGET_FRAMES,
)
from mymediavault_vm_worker.preview.llm.observability import configure_logfire
from mymediavault_vm_worker.preview.llm.providers import OPENAI_API_KEY_ENV
from mymediavault_vm_worker.preview.planning.base import DownloadLayout, TimelineAnchor
from mymediavault_vm_worker.preview.planning.layout import PreviewLayoutBuilder
from mymediavault_vm_worker.preview.frame_selection.base import (
    FrameSelectionResult,
    FrameSelector,
)
from mymediavault_vm_worker.preview.frame_selection.pydantic_ai import (
    PydanticAIFrameSelector,
)
from mymediavault_vm_worker.preview.scoring.base import FrameScorer
from mymediavault_vm_worker.preview.scoring.quality import QualityFrameScorer
from mymediavault_vm_worker.preview.selection.media import select_largest_video_file
from mymediavault_vm_worker.preview.output.sheet import ThumbnailSheetRenderer
from mymediavault_vm_worker.preview.torrent.client import (
    PreviewRangeDownload,
    TorrentClient,
)
from mymediavault_vm_worker.preview.torrent.metadata import (
    TorrentMetadata,
    parse_torrent_metadata,
)
from mymediavault_vm_worker.preview.torrent.session import TorrentSession
from mymediavault_vm_worker.preview.core.workspace import PreviewWorkspace


@dataclass(frozen=True)
class _DecodePassResult:
    frames: list[ExtractedFrame]
    elapsed_seconds: float


@dataclass(frozen=True)
class _AnchorRetryResult:
    frames: list[ExtractedFrame]
    diagnostics: PreviewDiagnostics
    downloaded_bytes: int
    anchor_retry: AnchorRetryDiagnostics | None


class PreviewEngine:
    """Long-lived concurrent-safe entry point for preview generation."""

    def __init__(
        self,
        config: PreviewEngineConfig | None = None,
        *,
        torrent_client: TorrentClient | None = None,
        decoder: FrameDecoder | None = None,
        scorer: FrameScorer | None = None,
        _frame_selector: FrameSelector | None = None,
        workspace_root: Path | None = None,
        sheet_renderer: ThumbnailSheetRenderer | None = None,
    ) -> None:
        self.config = config or PreviewEngineConfig()
        self._torrent_session = TorrentSession(torrent_client)
        self._decoder = decoder or FFmpegFrameDecoder()
        self._scorer = scorer or QualityFrameScorer()
        self._frame_selector = _frame_selector or self._build_frame_selector()
        self._layout_builder = PreviewLayoutBuilder()
        self._sheet_renderer = sheet_renderer or ThumbnailSheetRenderer()
        self._workspace_root = workspace_root
        self._download_limiter = asyncio.Semaphore(self.config.max_concurrent_downloads)
        self._decode_limiter = asyncio.Semaphore(self.config.max_concurrent_decodes)
        self._lifecycle_lock = asyncio.Lock()
        self._started = False

    async def __aenter__(self) -> PreviewEngine:
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.close()

    @property
    def artifact_version(self) -> str:
        """Human-managed compatibility label for generated preview artifacts."""

        return PREVIEW_ARTIFACT_VERSION

    @property
    def artifact_fingerprint(self) -> str:
        """Stable short hash for the current preview artifact recipe."""

        return self.config.artifact_fingerprint(
            sheet_recipe=self._sheet_renderer.artifact_recipe()
        )

    async def start(self) -> None:
        """Start the shared torrent runtime."""

        async with self._lifecycle_lock:
            if self._started:
                return
            await self._torrent_session.start()
            self._started = True

    async def close(self) -> None:
        """Close the shared torrent runtime."""

        async with self._lifecycle_lock:
            if not self._started:
                return
            await self._torrent_session.close()
            self._started = False

    async def release_session(self, info_hash: str) -> None:
        """Save resume data and release a torrent session after yielding its slot."""

        await self._torrent_session.release(info_hash, self.config)

    @asynccontextmanager
    async def preview_artifact(
        self, request: PreviewRequest
    ) -> AsyncIterator[PreviewResult]:
        """Generate a preview whose temporary files live for the context body."""

        await self.start()
        metadata = parse_torrent_metadata(request.torrent_bytes)
        with PreviewWorkspace(
            metadata.info_hash,
            root=self._workspace_root,
        ) as workspace:
            yield await self._preview_artifact(request, metadata, workspace)

    async def _preview_artifact(
        self,
        request: PreviewRequest,
        metadata: TorrentMetadata,
        workspace: PreviewWorkspace,
    ) -> PreviewResult:
        started_at = time.monotonic()
        warnings: list[str] = []
        downloaded_bytes = 0
        diagnostics = self._torrent_session.client.diagnostics(metadata, self.config)
        try:
            selected_file = select_largest_video_file(
                metadata.files, torrent_name=metadata.name
            )
        except NoVideoFileError as exc:
            return PreviewResult(
                info_hash=metadata.info_hash,
                status="failed",
                status_reason=str(exc),
                artifact=PreviewArtifact(frames=[], sheet=None),
                diagnostics=_result_diagnostics(
                    diagnostics,
                    warnings=warnings,
                    selected_file=None,
                    downloaded_bytes=downloaded_bytes,
                    elapsed_seconds=time.monotonic() - started_at,
                ),
            )
        configure_logfire()
        span_context = cast(
            "Any",
            logfire.span(
                "preview torrent",
                info_hash=metadata.info_hash,
                selected_file=selected_file.path,
                selected_file_size=selected_file.length,
                torrent_file_count=len(metadata.files),
                torrent_total_size=metadata.total_size,
                target_frames=TARGET_FRAMES,
                max_time_seconds=self.config.max_time_seconds,
                max_download_time_seconds=self.config.max_download_time_seconds,
                max_decode_time_seconds=self.config.max_decode_time_seconds,
                anchor_range_mb=self.config.anchor_range_mb,
                edge_range_mb=self.config.edge_range_mb,
            ),
        )
        span = span_context.__enter__()
        preview_logger = bind_log(
            info_hash=metadata.info_hash,
            torrent_title=metadata.name,
            selected_file=selected_file.path,
        )
        try:
            with logger.contextualize(
                info_hash=metadata.info_hash,
                torrent_title=metadata.name,
                selected_file=selected_file.path,
            ):
                preview_logger.bind(
                    selected_file_size=selected_file.length,
                    torrent_file_count=len(metadata.files),
                    torrent_total_size=metadata.total_size,
                    target_frames=TARGET_FRAMES,
                    anchor_range_mb=self.config.anchor_range_mb,
                    edge_range_mb=self.config.edge_range_mb,
                    max_time_seconds=self.config.max_time_seconds,
                    max_download_time_seconds=self.config.max_download_time_seconds,
                    max_decode_time_seconds=self.config.max_decode_time_seconds,
                    anchor_window_seconds=self.config.anchor_window_seconds,
                    torrent_cache_dir=str(self.config.torrent_cache_dir),
                    torrent_cache_max_mb=self.config.torrent_cache_max_mb,
                ).info("Starting preview")
                context = PreviewContext(
                    info_hash=metadata.info_hash, selected_file=selected_file
                )
                layout = self._layout_builder.build_layout(
                    selected_file.length,
                    self.config.anchor_range_bytes,
                    self.config.edge_range_bytes,
                    TARGET_FRAMES,
                )
                if layout is None:
                    return _finish_preview_span(
                        self._failed_result(
                            info_hash=metadata.info_hash,
                            diagnostics=diagnostics,
                            warnings=warnings,
                            selected_file=selected_file,
                            downloaded_bytes=downloaded_bytes,
                            elapsed=time.monotonic() - started_at,
                            reason=(
                                f"Selected file has no downloadable bytes: "
                                f"{selected_file.path}"
                            ),
                        ),
                        span,
                        span_context,
                    )
                preview_logger.bind(
                    ranges=[(item.start, item.end) for item in layout.ranges],
                    anchors=layout.anchors,
                    planned_bytes=layout.total_bytes,
                ).debug("Starting planned preview range download")
                try:
                    download_started_at = time.monotonic()
                    partial = await self._download(
                        request=request,
                        metadata=metadata,
                        selected_file=selected_file,
                        layout=layout,
                        output_dir=workspace.media_dir,
                        timeout_seconds=self._download_timeout(
                            self._remaining_seconds(started_at)
                        ),
                        min_complete_piece_count=request.min_complete_piece_count,
                    )
                    initial_download_elapsed = time.monotonic() - download_started_at
                except Exception as exc:
                    error_diagnostics = getattr(exc, "diagnostics", None)
                    if isinstance(error_diagnostics, PreviewDiagnostics):
                        diagnostics = error_diagnostics
                    warnings.append(f"Preview download failed: {exc}")
                    return _finish_preview_span(
                        self._failed_result(
                            info_hash=metadata.info_hash,
                            diagnostics=diagnostics,
                            warnings=warnings,
                            selected_file=selected_file,
                            downloaded_bytes=downloaded_bytes,
                            elapsed=time.monotonic() - started_at,
                            reason=str(exc),
                        ),
                        span,
                        span_context,
                    )
                downloaded_bytes = partial.downloaded_bytes
                diagnostics = partial.diagnostics
                if not partial.decode_ready:
                    warnings.append("Preview download is waiting for new completed pieces")
                    diagnostics = _result_diagnostics(
                        diagnostics,
                        warnings=warnings,
                        selected_file=selected_file,
                        downloaded_bytes=downloaded_bytes,
                        elapsed_seconds=time.monotonic() - started_at,
                    )
                    return _finish_preview_span(
                        PreviewResult(
                            info_hash=metadata.info_hash,
                            status="partial",
                            status_reason="Waiting for new completed pieces before decoding",
                            artifact=PreviewArtifact(frames=[], sheet=None),
                            diagnostics=diagnostics,
                        ),
                        span,
                        span_context,
                    )
                anchors = _indexed_anchors(layout.anchors)
                decode_budget_remaining = self.config.max_decode_time_seconds
                download_budget_remaining = max(
                    0.0,
                    self.config.max_download_time_seconds - initial_download_elapsed,
                )
                remaining = self._remaining_seconds(started_at)
                if remaining <= 0 or decode_budget_remaining <= 0:
                    warnings.append("Preview timed out before decoding could run")
                    return _finish_preview_span(
                        self._failed_result(
                            info_hash=metadata.info_hash,
                            diagnostics=diagnostics,
                            warnings=warnings,
                            selected_file=selected_file,
                            downloaded_bytes=downloaded_bytes,
                            elapsed=time.monotonic() - started_at,
                            reason="Preview timed out before decoding could run",
                        ),
                        span,
                        span_context,
                    )
                try:
                    decode_pass = await self._decode(
                        partial,
                        workspace.frames_dir / "initial",
                        min(remaining, decode_budget_remaining),
                        anchors,
                        len(layout.anchors),
                    )
                    scored_frames = decode_pass.frames
                    decode_budget_remaining -= decode_pass.elapsed_seconds
                    retry_diagnostics = await self._retry_missing_anchors(
                        request=request,
                        metadata=metadata,
                        selected_file=selected_file,
                        partial=partial,
                        scored_frames=scored_frames,
                        all_anchors=anchors,
                        workspace=workspace,
                        started_at=started_at,
                        diagnostics=diagnostics,
                        downloaded_bytes=downloaded_bytes,
                        warnings=warnings,
                        decode_budget_remaining=max(0.0, decode_budget_remaining),
                        download_budget_remaining=download_budget_remaining,
                    )
                    scored_frames = retry_diagnostics.frames
                    diagnostics = retry_diagnostics.diagnostics
                    downloaded_bytes = retry_diagnostics.downloaded_bytes
                    diagnostics = _with_candidate_diagnostics(
                        diagnostics,
                        retry_diagnostics.frames,
                        target_frames=len(layout.anchors),
                        min_candidates_per_anchor=self.config.min_selector_candidates_per_anchor,
                    )
                    selection = await self._select_frames(
                        scored_frames,
                        context=context,
                    )
                except Exception as exc:
                    warnings.append(f"Preview decode/selection failed: {exc}")
                    return _finish_preview_span(
                        self._failed_result(
                            info_hash=metadata.info_hash,
                            diagnostics=diagnostics,
                            warnings=warnings,
                            selected_file=selected_file,
                            downloaded_bytes=downloaded_bytes,
                            elapsed=time.monotonic() - started_at,
                            reason=str(exc),
                        ),
                        span,
                        span_context,
                    )
                result = await self._result(
                    context=context,
                    source_frames=selection.frames,
                    info_hash=metadata.info_hash,
                    downloaded_bytes=downloaded_bytes,
                    elapsed=time.monotonic() - started_at,
                    warnings=warnings,
                    diagnostics=diagnostics,
                    frame_selection=selection.diagnostics,
                    anchor_retry=retry_diagnostics.anchor_retry,
                    target_frames=len(layout.anchors),
                )
                return _finish_preview_span(result, span, span_context)
        except Exception:
            span_context.__exit__(*sys.exc_info())
            raise

    async def _download(
        self,
        *,
        request: PreviewRequest,
        metadata: TorrentMetadata,
        selected_file: SelectedFile,
        layout: DownloadLayout,
        output_dir: Path,
        timeout_seconds: float,
        min_complete_piece_count: int | None = None,
    ) -> PreviewRangeDownload:
        async with self._download_limiter:
            return await self._torrent_session.client.download(
                request.torrent_bytes,
                metadata,
                selected_file,
                layout,
                output_dir,
                self.config,
                timeout_seconds,
                min_complete_piece_count,
            )

    async def _decode(
        self,
        partial: PreviewRangeDownload,
        frames_dir: Path,
        timeout_seconds: float,
        anchors: tuple[TimelineAnchor, ...],
        target_frames: int,
    ) -> _DecodePassResult:
        started_at = time.monotonic()
        async with self._decode_limiter:
            candidates = await self._decoder.extract_frames(
                partial.media_path,
                frames_dir,
                target_frames,
                timeout_seconds,
                anchors,
                self.config.anchor_window_seconds,
                self.config.extract_frames_per_anchor,
            )
        scored = self._scorer.score(candidates)
        elapsed_seconds = time.monotonic() - started_at
        bind_log(
            media_path=str(partial.media_path),
            candidate_frame_count=len(candidates),
            scored_frame_count=len(scored),
        ).debug("Decoded and scored frames")
        return _DecodePassResult(frames=scored, elapsed_seconds=elapsed_seconds)

    async def _select_frames(
        self,
        frames: list[ExtractedFrame],
        *,
        context: PreviewContext,
    ) -> FrameSelectionResult:
        selection = await self._frame_selector.select(
            frames,
            context=context,
        )
        selected = selection.frames
        bind_log(
            candidate_frame_count=len(frames),
            selected_frame_count=len(selected),
            frame_selector=selection.diagnostics.selection_method,
        ).debug("Selected frames")
        return selection

    async def _retry_missing_anchors(
        self,
        *,
        request: PreviewRequest,
        metadata: TorrentMetadata,
        selected_file: SelectedFile,
        partial: PreviewRangeDownload,
        scored_frames: list[ExtractedFrame],
        all_anchors: tuple[TimelineAnchor, ...],
        workspace: PreviewWorkspace,
        started_at: float,
        diagnostics: PreviewDiagnostics,
        downloaded_bytes: int,
        warnings: list[str],
        decode_budget_remaining: float,
        download_budget_remaining: float,
    ) -> "_AnchorRetryResult":
        target_frames = len(all_anchors)
        missing = _missing_selector_visible_anchor_indexes(
            scored_frames,
            target_frames=target_frames,
            candidates_per_anchor=self.config.max_selector_candidates_per_anchor,
            min_candidates_per_anchor=self.config.min_selector_candidates_per_anchor,
        )
        if not missing or not self.config.anchor_retry_range_mb:
            return _AnchorRetryResult(
                frames=scored_frames,
                diagnostics=diagnostics,
                downloaded_bytes=downloaded_bytes,
                anchor_retry=None,
            )

        initial_missing = list(missing)
        attempts: list[AnchorRetryAttemptDiagnostics] = []
        current_frames = list(scored_frames)
        current_diagnostics = diagnostics
        current_downloaded_bytes = downloaded_bytes
        planned_complete = diagnostics.planned_pieces_complete
        anchors_by_index = {anchor.index: anchor for anchor in all_anchors}
        previous_retry_anchor_indexes: tuple[int, ...] | None = None

        for attempt_index, range_mb in enumerate(
            self.config.anchor_retry_range_mb, start=1
        ):
            if not missing:
                break
            remaining = self._remaining_seconds(started_at)
            if (
                remaining <= 0
                or decode_budget_remaining <= 0
                or download_budget_remaining <= 0
            ):
                warnings.append(
                    "Anchor retry stopped because preview time budget expired"
                )
                break
            retry_anchors = tuple(anchors_by_index[index] for index in missing)
            retry_anchor_indexes = tuple(anchor.index for anchor in retry_anchors)
            retry_layout = self._layout_builder.build_anchor_layout(
                selected_file.length,
                max(1, int(range_mb * BYTES_PER_MB)),
                retry_anchors,
            )
            if retry_layout is None:
                break
            download_timeout = min(remaining, download_budget_remaining)
            download_started_at = time.monotonic()
            try:
                partial = await self._download(
                    request=request,
                    metadata=metadata,
                    selected_file=selected_file,
                    layout=retry_layout,
                    output_dir=workspace.media_dir,
                    timeout_seconds=download_timeout,
                )
            except Exception as exc:
                warnings.append(f"Anchor retry download failed: {exc}")
                break
            download_budget_remaining -= time.monotonic() - download_started_at
            previous_downloaded_bytes = current_downloaded_bytes
            previous_complete_piece_count = (
                current_diagnostics.last_complete_piece_count or 0
            )
            current_downloaded_bytes = partial.downloaded_bytes
            planned_complete = _combined_planned_pieces_complete(
                planned_complete,
                partial.diagnostics.planned_pieces_complete,
            )
            current_diagnostics = replace(
                partial.diagnostics,
                planned_pieces_complete=planned_complete,
            )
            retry_made_progress = (
                current_downloaded_bytes > previous_downloaded_bytes
                or (partial.diagnostics.last_complete_piece_count or 0)
                > previous_complete_piece_count
            )
            if (
                not retry_made_progress
                and retry_anchor_indexes == previous_retry_anchor_indexes
            ):
                clean_counts = _clean_candidate_counts_by_anchor(
                    current_frames,
                    target_frames=target_frames,
                    candidates_per_anchor=self.config.max_selector_candidates_per_anchor,
                )
                attempts.append(
                    AnchorRetryAttemptDiagnostics(
                        range_mb=range_mb,
                        target_anchor_indexes=[
                            anchor.index for anchor in retry_anchors
                        ],
                        decoded_candidate_counts_by_anchor={},
                        clean_candidate_counts_by_anchor={
                            index: clean_counts.get(index, 0)
                            for index in [anchor.index for anchor in retry_anchors]
                        },
                        remaining_missing_anchor_indexes=list(missing),
                        downloaded_bytes=current_downloaded_bytes,
                        planned_pieces_complete=(
                            partial.diagnostics.planned_pieces_complete
                        ),
                    )
                )
                previous_retry_anchor_indexes = retry_anchor_indexes
                continue

            remaining = self._remaining_seconds(started_at)
            if remaining <= 0 or decode_budget_remaining <= 0:
                warnings.append("Anchor retry stopped before retry decoding could run")
                break
            retry_decode = await self._decode(
                partial,
                workspace.frames_dir / f"retry_{attempt_index:03d}",
                min(remaining, decode_budget_remaining),
                retry_anchors,
                target_frames,
            )
            decode_budget_remaining -= retry_decode.elapsed_seconds
            current_frames.extend(retry_decode.frames)
            clean_counts = _clean_candidate_counts_by_anchor(
                current_frames,
                target_frames=target_frames,
                candidates_per_anchor=self.config.max_selector_candidates_per_anchor,
            )
            missing = [
                index
                for index in missing
                if clean_counts.get(index, 0)
                < self.config.min_selector_candidates_per_anchor
            ]
            attempts.append(
                AnchorRetryAttemptDiagnostics(
                    range_mb=range_mb,
                    target_anchor_indexes=list(retry_anchor_indexes),
                    decoded_candidate_counts_by_anchor=_candidate_counts_by_anchor(
                        retry_decode.frames,
                        target_frames=target_frames,
                    ),
                    clean_candidate_counts_by_anchor={
                        index: clean_counts.get(index, 0)
                        for index in [anchor.index for anchor in retry_anchors]
                    },
                    remaining_missing_anchor_indexes=list(missing),
                    downloaded_bytes=current_downloaded_bytes,
                    planned_pieces_complete=partial.diagnostics.planned_pieces_complete,
                )
            )
            previous_retry_anchor_indexes = retry_anchor_indexes

        return _AnchorRetryResult(
            frames=current_frames,
            diagnostics=current_diagnostics,
            downloaded_bytes=current_downloaded_bytes,
            anchor_retry=AnchorRetryDiagnostics(
                range_mb_ladder=self.config.anchor_retry_range_mb,
                initial_missing_anchor_indexes=initial_missing,
                final_missing_anchor_indexes=list(missing),
                attempts=attempts,
            ),
        )

    def _build_frame_selector(self) -> FrameSelector:
        if not os.getenv(OPENAI_API_KEY_ENV):
            msg = f"{OPENAI_API_KEY_ENV} must be set for preview generation"
            raise ValueError(msg)
        return PydanticAIFrameSelector(
            model=self.config.llm_model,
            timeout_seconds=self.config.llm_timeout_seconds,
            candidates_per_anchor=self.config.max_selector_candidates_per_anchor,
            min_candidates_per_anchor=self.config.min_selector_candidates_per_anchor,
        )

    async def _render_sheet(
        self,
        frames: list[ExtractedFrame],
        *,
        target_frames: int,
        preview_logger: BoundLogger,
    ) -> GeneratedSheet:
        try:
            preview_logger.bind(
                frame_count=len(frames),
            ).debug("Rendering preview sheet")
            return self._sheet_renderer.render(
                frames=frames,
                target_frames=target_frames,
                output_dir=frames[0].path.parent,
            )
        except Exception as exc:
            msg = f"Preview sheet rendering failed: {exc}"
            raise PreviewError(msg) from exc

    async def _result(
        self,
        *,
        context: PreviewContext,
        source_frames: list[ExtractedFrame],
        info_hash: str,
        downloaded_bytes: int,
        elapsed: float,
        warnings: list[str],
        diagnostics: PreviewDiagnostics,
        frame_selection: FrameSelectionDiagnostics,
        anchor_retry: AnchorRetryDiagnostics | None,
        target_frames: int,
    ) -> PreviewResult:
        status, status_reason = _preview_status(source_frames, target_frames)
        diagnostics = _result_diagnostics(
            diagnostics,
            warnings=warnings,
            selected_file=context.selected_file,
            downloaded_bytes=downloaded_bytes,
            elapsed_seconds=elapsed,
            frame_selection=frame_selection,
            anchor_retry=anchor_retry,
        )
        if status == "failed":
            result = PreviewResult(
                info_hash=info_hash,
                status=status,
                status_reason=status_reason,
                artifact=PreviewArtifact(frames=[], sheet=None),
                diagnostics=diagnostics,
            )
            bind_log(
                info_hash=info_hash,
                selected_file=context.selected_file.path,
                status=result.status,
                frame_count=0,
                downloaded_bytes=downloaded_bytes,
                elapsed_seconds=round(elapsed, 2),
                status_reason=status_reason,
            ).info("Preview finished")
            return result

        preview_logger = bind_log(
            info_hash=info_hash,
            selected_file=context.selected_file.path,
        )
        sheet = await self._render_sheet(
            source_frames,
            target_frames=target_frames,
            preview_logger=preview_logger,
        )
        result = PreviewResult(
            info_hash=info_hash,
            status=status,
            status_reason=status_reason,
            artifact=PreviewArtifact(
                frames=[_generated_frame(frame) for frame in source_frames],
                sheet=sheet,
            ),
            diagnostics=diagnostics,
        )
        bind_log(
            info_hash=info_hash,
            selected_file=context.selected_file.path,
            status=result.status,
            frame_count=len(result.artifact.frames),
            downloaded_bytes=downloaded_bytes,
            elapsed_seconds=round(elapsed, 2),
            status_reason=status_reason,
        ).info("Preview finished")
        return result

    def _failed_result(
        self,
        *,
        info_hash: str,
        diagnostics: PreviewDiagnostics,
        warnings: list[str],
        selected_file: SelectedFile | None,
        downloaded_bytes: int,
        elapsed: float,
        reason: str,
    ) -> PreviewResult:
        diagnostics = _result_diagnostics(
            diagnostics,
            warnings=warnings,
            selected_file=selected_file,
            downloaded_bytes=downloaded_bytes,
            elapsed_seconds=elapsed,
        )
        return PreviewResult(
            info_hash=info_hash,
            status="failed",
            status_reason=reason or "Preview generation failed",
            artifact=PreviewArtifact(frames=[], sheet=None),
            diagnostics=diagnostics,
        )

    def _remaining_seconds(self, started_at: float) -> float:
        return self.config.max_time_seconds - (time.monotonic() - started_at)

    def _download_timeout(self, remaining_seconds: float) -> float:
        if remaining_seconds > self.config.max_decode_time_seconds:
            remaining_seconds -= self.config.max_decode_time_seconds
        return min(remaining_seconds, self.config.max_download_time_seconds)


def _finish_preview_span(
    result: PreviewResult,
    span: Any | None,
    span_context: Any,
) -> PreviewResult:
    if span is not None:
        span.set_attributes(
            {
                "status": result.status,
                "downloaded_bytes": result.diagnostics.downloaded_bytes,
                "frame_count": len(result.artifact.frames),
                "sheet_created": result.artifact.sheet is not None,
                "elapsed_seconds": round(result.diagnostics.elapsed_seconds, 2),
                "status_reason": result.status_reason,
            }
        )
    span_context.__exit__(None, None, None)
    return result


def _preview_status(
    frames: list[ExtractedFrame],
    target_frames: int,
) -> tuple[PreviewStatus, str | None]:
    required_anchor_indexes = set(range(target_frames))
    selected_anchor_indexes = {
        frame.anchor_index
        for frame in frames
        if (
            frame.anchor_index is not None
            and 0 <= frame.anchor_index < target_frames
        )
    }
    if selected_anchor_indexes >= required_anchor_indexes:
        return "succeeded", None
    if selected_anchor_indexes:
        return (
            "partial",
            (
                f"Only {len(selected_anchor_indexes)} of {target_frames} "
                "target anchors produced selected frames"
            ),
        )
    return "failed", "No target anchors produced selected frames"


def _indexed_anchors(anchors: tuple[float, ...]) -> tuple[TimelineAnchor, ...]:
    return tuple(
        TimelineAnchor(index=index, ratio=ratio) for index, ratio in enumerate(anchors)
    )


def _missing_selector_visible_anchor_indexes(
    frames: list[ExtractedFrame],
    *,
    target_frames: int,
    candidates_per_anchor: int,
    min_candidates_per_anchor: int,
) -> list[int]:
    counts = _clean_candidate_counts_by_anchor(
        frames,
        target_frames=target_frames,
        candidates_per_anchor=candidates_per_anchor,
    )
    return [
        index
        for index in range(target_frames)
        if counts.get(index, 0) < min_candidates_per_anchor
    ]


def _clean_candidate_counts_by_anchor(
    frames: list[ExtractedFrame],
    *,
    target_frames: int,
    candidates_per_anchor: int,
) -> dict[int, int]:
    counts: dict[int, int] = {}
    for anchor_index in range(target_frames):
        anchor_frames = sorted(
            (
                frame
                for frame in frames
                if frame.anchor_index == anchor_index and frame.score > 0
            ),
            key=lambda frame: frame.score,
            reverse=True,
        )
        counts[anchor_index] = len(anchor_frames[:candidates_per_anchor])
    return counts


def _with_candidate_diagnostics(
    diagnostics: PreviewDiagnostics,
    frames: list[ExtractedFrame],
    *,
    target_frames: int,
    min_candidates_per_anchor: int,
) -> PreviewDiagnostics:
    decoded_counts = _candidate_counts_by_anchor(frames, target_frames=target_frames)
    clean_counts = _positive_candidate_counts_by_anchor(
        frames, target_frames=target_frames
    )
    eligible = [
        index
        for index in range(target_frames)
        if clean_counts.get(index, 0) >= min_candidates_per_anchor
    ]
    missing = [index for index in range(target_frames) if index not in eligible]
    return replace(
        diagnostics,
        decoded_candidate_counts_by_anchor=decoded_counts,
        clean_candidate_counts_by_anchor=clean_counts,
        eligible_anchor_indexes=eligible,
        missing_anchor_indexes=missing,
    )


def _candidate_counts_by_anchor(
    frames: list[ExtractedFrame],
    *,
    target_frames: int,
) -> dict[int, int]:
    counts: dict[int, int] = {}
    for frame in frames:
        anchor_index = frame.anchor_index
        if anchor_index is None or not 0 <= anchor_index < target_frames:
            continue
        counts[anchor_index] = counts.get(anchor_index, 0) + 1
    return counts


def _positive_candidate_counts_by_anchor(
    frames: list[ExtractedFrame],
    *,
    target_frames: int,
) -> dict[int, int]:
    counts: dict[int, int] = {}
    for frame in frames:
        anchor_index = frame.anchor_index
        if (
            anchor_index is None
            or not 0 <= anchor_index < target_frames
            or frame.score <= 0
        ):
            continue
        counts[anchor_index] = counts.get(anchor_index, 0) + 1
    return counts


def _combined_planned_pieces_complete(
    previous: bool | None, current: bool | None
) -> bool | None:
    if previous is False or current is False:
        return False
    if previous is None:
        return current
    if current is None:
        return previous
    return previous and current


def _generated_frame(frame: ExtractedFrame) -> GeneratedFrame:
    return GeneratedFrame(
        path=frame.path,
        width=frame.width,
        height=frame.height,
        timestamp_seconds=frame.timestamp_seconds,
    )


def _result_diagnostics(
    diagnostics: PreviewDiagnostics,
    *,
    warnings: list[str],
    selected_file: SelectedFile | None,
    downloaded_bytes: int,
    elapsed_seconds: float,
    frame_selection: FrameSelectionDiagnostics | None = None,
    anchor_retry: AnchorRetryDiagnostics | None = None,
) -> PreviewDiagnostics:
    return PreviewDiagnostics(
        warnings=list(warnings),
        selected_file=selected_file,
        downloaded_bytes=downloaded_bytes,
        elapsed_seconds=elapsed_seconds,
        torrent_cache_dir=diagnostics.torrent_cache_dir,
        torrent_cache_max_mb=diagnostics.torrent_cache_max_mb,
        torrent_cache_entry_exists_before=diagnostics.torrent_cache_entry_exists_before,
        resume_data_exists_before=diagnostics.resume_data_exists_before,
        resume_data_saved=diagnostics.resume_data_saved,
        last_download_rate=diagnostics.last_download_rate,
        last_num_peers=diagnostics.last_num_peers,
        last_num_seeds=diagnostics.last_num_seeds,
        last_torrent_state=diagnostics.last_torrent_state,
        last_complete_piece_count=diagnostics.last_complete_piece_count,
        last_requested_piece_count=diagnostics.last_requested_piece_count,
        planned_pieces_complete=diagnostics.planned_pieces_complete,
        tracker_count=diagnostics.tracker_count,
        tracker_alerts=list(diagnostics.tracker_alerts),
        dht_alerts=list(diagnostics.dht_alerts),
        frame_selection=(
            frame_selection
            if frame_selection is not None
            else diagnostics.frame_selection
        ),
        anchor_retry=anchor_retry
        if anchor_retry is not None
        else diagnostics.anchor_retry,
        decoded_candidate_counts_by_anchor=dict(
            diagnostics.decoded_candidate_counts_by_anchor
        ),
        clean_candidate_counts_by_anchor=dict(
            diagnostics.clean_candidate_counts_by_anchor
        ),
        eligible_anchor_indexes=list(diagnostics.eligible_anchor_indexes),
        missing_anchor_indexes=list(diagnostics.missing_anchor_indexes),
    )
