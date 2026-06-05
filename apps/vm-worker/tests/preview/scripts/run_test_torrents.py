"""Run real torrent preview integration checks against local .torrent files.

This script is intentionally outside normal pytest collection because it uses
real torrent networking and ffmpeg. Run it manually when the devcontainer has
the runtime dependencies installed.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import ImageUrl, UserContent

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mymediavault_vm_worker.preview import (
    PreviewEngine,
    PreviewEngineConfig,
    PreviewHarnessConfig,
    PreviewResult,
    PreviewWorkerHarness,
    configure_default_logging,
)
from mymediavault_vm_worker.preview.core.models import (
    DEFAULT_ANCHOR_RANGE_MB,
    DEFAULT_ANCHOR_WINDOW_SECONDS,
    DEFAULT_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS,
    DEFAULT_EDGE_RANGE_MB,
    DEFAULT_EXTRACT_FRAMES_PER_ANCHOR,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    DEFAULT_MAX_SELECTOR_CANDIDATES_PER_ANCHOR,
    DEFAULT_MAX_DECODE_TIME_SECONDS,
    DEFAULT_MAX_DOWNLOAD_TIME_SECONDS,
    DEFAULT_MAX_TIME_SECONDS,
    DEFAULT_MIN_SELECTOR_CANDIDATES_PER_ANCHOR,
    DEFAULT_TARGET_FRAMES,
    DEFAULT_TORRENT_CACHE_MAX_MB,
    GeneratedFrame,
    GeneratedSheet,
    PreviewArtifact,
    _default_torrent_cache_dir,
)
from mymediavault_vm_worker.preview.llm.providers import (
    LLMConfigurationError,
    configure_llm_observability,
    openai_responses_model,
)
from mymediavault_vm_worker.preview.ranking import frame_thumbnail_data_url


_MIN_MEAN_LUMA = 24.0
_MIN_LUMA_STDDEV = 8.0
_MAX_DARK_PIXEL_RATIO = 0.90
_MIN_PAIRWISE_MEAN_ABS_DIFF = 15.0
_MAX_PAIRWISE_CORRELATION = 0.80
_TRUTHFUL_PARTIAL_DIR_NAME = "truthful-partial"


class _PreviewFrameJudgement(BaseModel):
    good_preview: bool
    reason: str
    damage_notes: str
    diversity_notes: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run torrent-preview against local test .torrent files."
    )
    parser.add_argument(
        "--torrent-dir",
        type=Path,
        default=Path("tmp/test-torrents"),
        help="Directory containing .torrent files.",
    )
    parser.add_argument(
        "--torrent-glob",
        default="**/*.torrent",
        help="Glob, relative to --torrent-dir, for selecting torrent files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tmp/integration-preview-output"),
        help=(
            "Directory for selected preview frames and summary JSON. Existing "
            "contents are removed before each run."
        ),
    )
    parser.add_argument(
        "--concurrency",
        type=_positive_int,
        default=1,
        help=(
            "Number of torrent previews to run concurrently. The default is 1 "
            "so per-torrent acceptance diagnostics are easy to read."
        ),
    )
    parser.add_argument("--target-frames", type=int, default=DEFAULT_TARGET_FRAMES)
    parser.add_argument(
        "--anchor-range-mb",
        type=float,
        default=DEFAULT_ANCHOR_RANGE_MB,
        help="Preview range size in MiB around each timeline anchor.",
    )
    parser.add_argument(
        "--edge-range-mb",
        type=float,
        default=DEFAULT_EDGE_RANGE_MB,
        help="Preview range size in MiB at the selected file head and tail.",
    )
    parser.add_argument(
        "--max-time-seconds", type=float, default=DEFAULT_MAX_TIME_SECONDS
    )
    parser.add_argument(
        "--max-download-time-seconds",
        type=float,
        default=DEFAULT_MAX_DOWNLOAD_TIME_SECONDS,
    )
    parser.add_argument(
        "--download-progress-timeout-seconds",
        type=float,
        default=DEFAULT_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--max-decode-time-seconds", type=float, default=DEFAULT_MAX_DECODE_TIME_SECONDS
    )
    parser.add_argument(
        "--anchor-window-seconds", type=float, default=DEFAULT_ANCHOR_WINDOW_SECONDS
    )
    parser.add_argument("--llm-model", default=DEFAULT_LLM_MODEL)
    parser.add_argument(
        "--llm-timeout-seconds",
        type=float,
        default=DEFAULT_LLM_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--extract-frames-per-anchor",
        type=int,
        default=DEFAULT_EXTRACT_FRAMES_PER_ANCHOR,
        help="Maximum decoded frame extraction attempts per preview anchor.",
    )
    parser.add_argument(
        "--min-selector-candidates-per-anchor",
        type=int,
        default=DEFAULT_MIN_SELECTOR_CANDIDATES_PER_ANCHOR,
        help="Minimum clean candidates per anchor required before selection.",
    )
    parser.add_argument(
        "--max-selector-candidates-per-anchor",
        type=int,
        default=DEFAULT_MAX_SELECTOR_CANDIDATES_PER_ANCHOR,
        help="Maximum clean candidates per anchor sent to the selector.",
    )
    parser.add_argument("--llm-judge-model", default="gpt-5.4")
    parser.add_argument("--llm-judge-timeout-seconds", type=float, default=12.0)
    parser.add_argument(
        "--allow-truthful-partial",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Allow any torrent to pass with a truthful partial result. By default, "
            "only torrents under the truthful-partial fixture folder are eligible."
        ),
    )
    parser.add_argument(
        "--torrent-cache-dir",
        type=Path,
        default=_default_torrent_cache_dir(),
        help=("Cache directory for torrent preview range downloads."),
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Remove the configured torrent cache directory before running.",
    )
    parser.add_argument(
        "--torrent-cache-max-mb",
        type=float,
        default=DEFAULT_TORRENT_CACHE_MAX_MB,
        help="Maximum disk usage in MB for the torrent cache.",
    )
    parser.add_argument(
        "--tracker",
        action="append",
        default=[],
        help="Additional tracker announce URL. May be passed multiple times.",
    )
    parser.add_argument(
        "--no-default-trackers",
        action="store_true",
        help="Disable fetching the default tracker list.",
    )
    parser.add_argument(
        "--require-success",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exit non-zero unless every torrent succeeds and frame checks pass.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print loguru debug logs with structured context.",
    )
    args = parser.parse_args()
    _clear_output_dir(args.output_dir)

    configure_default_logging(debug=args.debug, sink=sys.stdout)
    try:
        results = asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("Interrupted by user; cancelled in-flight previews.", file=sys.stderr)
        raise SystemExit(130) from None
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results_path = args.output_dir / "results.json"
    results_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"Wrote {results_path}")
    if args.require_success and not _all_results_good(results):
        raise SystemExit(1)


def _clear_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


async def _run(args: argparse.Namespace) -> list[dict[str, Any]]:
    torrent_paths = sorted(args.torrent_dir.glob(args.torrent_glob))
    if not torrent_paths:
        msg = f"No .torrent files found in {args.torrent_dir}"
        raise SystemExit(msg)

    config = PreviewEngineConfig(
        max_concurrent_downloads=args.concurrency,
        max_concurrent_decodes=args.concurrency,
        anchor_range_mb=args.anchor_range_mb,
        edge_range_mb=args.edge_range_mb,
        max_time_seconds=args.max_time_seconds,
        max_download_time_seconds=args.max_download_time_seconds,
        download_progress_timeout_seconds=args.download_progress_timeout_seconds,
        max_decode_time_seconds=args.max_decode_time_seconds,
        target_frames=args.target_frames,
        anchor_window_seconds=args.anchor_window_seconds,
        llm_model=args.llm_model,
        llm_timeout_seconds=args.llm_timeout_seconds,
        extract_frames_per_anchor=args.extract_frames_per_anchor,
        min_selector_candidates_per_anchor=args.min_selector_candidates_per_anchor,
        max_selector_candidates_per_anchor=args.max_selector_candidates_per_anchor,
        torrent_cache_dir=args.torrent_cache_dir,
        torrent_cache_max_mb=args.torrent_cache_max_mb,
        trackers=tuple(args.tracker),
        use_default_trackers=not args.no_default_trackers,
    )
    results: list[dict[str, Any] | None] = [None for _ in torrent_paths]
    job_source = _TorrentFileJobSource(torrent_paths)

    engine = PreviewEngine(config=config)
    harness = PreviewWorkerHarness(
        engine=engine,
        job_source=job_source,
        config=PreviewHarnessConfig(
            max_concurrency=args.concurrency,
            stop_when_empty=True,
            clear_cache=args.clear_cache,
        ),
        result_callback=lambda lease, result: _record_result(
            args,
            results,
            cast("_TorrentFileLease", lease),
            result,
        ),
    )
    await harness.run()
    return [item for item in results if item is not None]


@dataclass(frozen=True)
class _TorrentFileLease:
    index: int
    torrent_path: Path

    @property
    def job_id(self) -> str:
        return self.torrent_path.name

    async def load_torrent_bytes(self) -> bytes:
        return await asyncio.to_thread(self.torrent_path.read_bytes)

    async def complete(self, result: PreviewResult) -> None:
        _ = result

    async def fail(self, error: Exception) -> None:
        raise error


class _TorrentFileJobSource:
    def __init__(self, torrent_paths: list[Path]) -> None:
        self._pending = [
            _TorrentFileLease(index=index, torrent_path=torrent_path)
            for index, torrent_path in enumerate(torrent_paths)
        ]

    async def claim_batch(
        self,
        *,
        limit: int,
        artifact_version: str,
        artifact_fingerprint: str,
    ) -> list[_TorrentFileLease]:
        _ = artifact_version, artifact_fingerprint
        batch = self._pending[:limit]
        self._pending = self._pending[limit:]
        return batch


async def _record_result(
    args: argparse.Namespace,
    results: list[dict[str, Any] | None],
    lease: _TorrentFileLease,
    result: PreviewResult,
) -> None:
    item = await _result_item(args, lease.torrent_path, result)
    results[lease.index] = item
    if args.debug:
        print(
            "RESULT " + json.dumps(item, ensure_ascii=False),
            flush=True,
        )


async def _result_item(
    args: argparse.Namespace,
    torrent_path: Path,
    result: PreviewResult,
) -> dict[str, Any]:
    stored_artifact = _store_result_artifacts(result, args.output_dir)
    data = asdict(result)
    data["artifact"] = asdict(stored_artifact)
    data["torrent"] = torrent_path.name
    data["torrent_path"] = str(torrent_path)
    data["fixture_mode"] = _fixture_mode(torrent_path, args.torrent_dir)
    if result.diagnostics.selected_file is not None:
        data["selected_file"] = asdict(result.diagnostics.selected_file)
    data["frames"] = [asdict(frame) for frame in stored_artifact.frames]
    data["sheet"] = (
        asdict(stored_artifact.sheet) if stored_artifact.sheet is not None else None
    )
    data["downloaded_bytes"] = result.diagnostics.downloaded_bytes
    data["frame_checks"] = [_frame_check(frame) for frame in stored_artifact.frames]
    data["sheet_check"] = _sheet_check(stored_artifact.sheet)
    data["frame_set_check"] = _frame_set_check(stored_artifact.frames)
    data["llm_judge"] = await _llm_judge(args, result, stored_artifact)
    status_check = _status_check(data, args)
    data["accepted_anchor_coverage_check"] = _accepted_anchor_coverage_check(
        data,
        args,
    )
    llm_judge_required = _llm_judge_required(data, status_check)
    data["quality_ok"] = (
        status_check["ok"]
        and data["accepted_anchor_coverage_check"]["ok"]
        and _frame_artifacts_ok(data)
        and _sheet_contract_ok(data)
        and data["frame_set_check"]["ok"]
        and (data["llm_judge"]["ok"] or not llm_judge_required)
    )
    data["llm_judge_required"] = llm_judge_required
    data["acceptance_status_check"] = status_check
    data["elapsed_seconds"] = round(result.diagnostics.elapsed_seconds, 2)
    return _jsonable(data)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        msg = "must be at least 1"
        raise argparse.ArgumentTypeError(msg)
    return parsed


async def _llm_judge(
    args: argparse.Namespace, result: PreviewResult, artifact: PreviewArtifact
) -> dict[str, Any]:
    if not artifact.frames:
        return {
            "enabled": True,
            "ok": False,
            "reason": "no frames to judge",
        }

    configure_llm_observability()
    content = _llm_judge_content(result, artifact, _expected_target_frames(args))
    try:
        model = openai_responses_model(args.llm_judge_model)
        agent = Agent(
            model=model,
            output_type=_PreviewFrameJudgement,
            instructions=(
                "You are judging technical preview-frame quality. Reject visually "
                "damaged decoded frames, black frames, severe corruption, and image "
                "sets that are visually near-identical. Judge only technical preview "
                "quality, not content category, graphicness, nudity, sexual content, "
                "violence, medical-looking content, or whether a scene is tasteful. "
                "Do not reject solely because frames show the same subject, scene "
                "type, activity, body part, explicit content, apparent injury, or "
                "adjacent timestamps when the images are technically clear and "
                "visually different enough to preview the video."
            ),
        )
        response = await agent.run(
            content,
            model_settings={"timeout": args.llm_judge_timeout_seconds},
        )
        judgement = cast("_PreviewFrameJudgement", response.output)
        return {
            "enabled": True,
            "ok": judgement.good_preview,
            "model": args.llm_judge_model,
            "reason": judgement.reason,
            "damage_notes": judgement.damage_notes,
            "diversity_notes": judgement.diversity_notes,
        }
    except LLMConfigurationError as exc:
        return {
            "enabled": True,
            "ok": False,
            "model": args.llm_judge_model,
            "reason": str(exc),
        }
    except Exception as exc:
        return {
            "enabled": True,
            "ok": False,
            "model": args.llm_judge_model,
            "reason": f"LLM judge failed: {exc}",
        }


def _llm_judge_content(
    result: PreviewResult, artifact: PreviewArtifact, target_frames: int
) -> list[UserContent]:
    selected_file = result.diagnostics.selected_file
    content: list[UserContent] = [
        (
            f"Judge this preview result. status={result.status}, "
            f"target_frames={target_frames}, actual_frames={len(artifact.frames)}, "
            f"selected_file={selected_file.path if selected_file else ''}. "
            "A good complete preview has clear, visually undamaged frames with "
            "meaningful visual diversity in composition or timestamp. A partial "
            "result may still be acceptable only when the available frames are "
            "clear and the result truthfully reports partial status. For partial "
            "results, do not reject solely because actual_frames is below "
            "target_frames; judge the visible frames and note incompleteness in "
            "the reason. Do not reject based on content category or the same "
            "person appearing in multiple frames; reject diversity only when "
            "frames are near-duplicate images, not because the subject matter is "
            "explicit, graphic, or uncomfortable."
        )
    ]
    for index, frame in enumerate(artifact.frames, start=1):
        image_url = frame_thumbnail_data_url(frame.path)
        content.append(
            f"frame_{index:03d}: timestamp={frame.timestamp_seconds:.3f}s, "
            f"size={frame.width}x{frame.height}"
        )
        if image_url is not None:
            content.append(ImageUrl(url=image_url))
    return content


def _llm_judge_required(
    data: dict[str, Any],
    status_check: dict[str, Any],
) -> bool:
    if not status_check["ok"]:
        return False
    if status_check["mode"] == "truthful-partial" and _planned_pieces_incomplete(data):
        return False
    return status_check["mode"] in {"strict", "truthful-partial"} and bool(
        data["frames"]
    )


def _status_check(
    data: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    target_frames = _expected_target_frames(args)
    if data["status"] == "succeeded" and len(data["frames"]) == target_frames:
        return {
            "ok": True,
            "mode": "strict",
            "reason": "succeeded with one selected frame for every anchor",
        }
    truthful_partial_allowed = args.allow_truthful_partial or (
        data["fixture_mode"] == "truthful-partial"
    )
    if truthful_partial_allowed and _is_partial_with_frames(data):
        return {
            "ok": True,
            "mode": "truthful-partial",
            "reason": _truthful_partial_reason(data),
        }
    if truthful_partial_allowed and _is_truthful_failed_without_artifact(data):
        return {
            "ok": True,
            "mode": "truthful-failed",
            "reason": "failed result accepted because no displayable artifact was available",
        }
    if _is_partial_with_frames(data):
        return {
            "ok": False,
            "mode": "strict",
            "reason": (
                "truthful partial result is not allowed for this strict-success "
                "torrent fixture"
            ),
        }
    return {
        "ok": False,
        "mode": "strict",
        "reason": (
            f"status={data['status']} frames={len(data['frames'])} "
            f"target_frames={target_frames}"
        ),
    }


def _accepted_anchor_coverage_check(
    data: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    if data["status"] != "succeeded":
        return {
            "ok": True,
            "reason": "accepted anchor coverage is required only for succeeded results",
        }
    target_frames = _expected_target_frames(args)
    ok = len(data["frames"]) == target_frames
    return {
        "ok": ok,
        "expected_frame_count": target_frames,
        "actual_frame_count": len(data["frames"]),
        "reason": (
            "succeeded result has one selected frame per expected anchor"
            if ok
            else "succeeded result has the wrong frame count"
        ),
    }


def _is_partial_with_frames(data: dict[str, Any]) -> bool:
    return data["status"] == "partial" and len(data["frames"]) > 0


def _is_truthful_failed_without_artifact(data: dict[str, Any]) -> bool:
    return (
        data["status"] == "failed"
        and len(data["frames"]) == 0
        and data.get("sheet") is None
    )


def _frame_artifacts_ok(data: dict[str, Any]) -> bool:
    if data["status"] == "failed":
        return len(data["frames"]) == 0
    return len(data["frames"]) > 0 and all(item["ok"] for item in data["frame_checks"])


def _sheet_contract_ok(data: dict[str, Any]) -> bool:
    if data["status"] == "failed":
        return data.get("sheet") is None
    return bool(data.get("sheet")) and data["sheet_check"]["ok"]


def _planned_pieces_incomplete(data: dict[str, Any]) -> bool:
    diagnostics = data.get("diagnostics") or {}
    complete = diagnostics.get("last_complete_piece_count")
    requested = diagnostics.get("last_requested_piece_count")
    return (
        isinstance(complete, int)
        and isinstance(requested, int)
        and requested > complete
    )


def _truthful_partial_reason(data: dict[str, Any]) -> str:
    if _planned_pieces_incomplete(data):
        return "partial result accepted because requested pieces were incomplete"
    return "partial result accepted for truthful-partial fixture"


def _store_result_artifacts(result: PreviewResult, output_dir: Path) -> PreviewArtifact:
    target_dir = output_dir / result.info_hash
    target_dir.mkdir(parents=True, exist_ok=True)
    frames: list[GeneratedFrame] = []
    for index, frame in enumerate(result.artifact.frames, start=1):
        destination = target_dir / f"frame_{index:03d}.jpg"
        shutil.copy2(frame.path, destination)
        frames.append(
            GeneratedFrame(
                path=destination,
                width=frame.width,
                height=frame.height,
                timestamp_seconds=frame.timestamp_seconds,
            )
        )
    sheet = None
    if result.artifact.sheet is not None:
        destination = target_dir / "preview_sheet.jpg"
        shutil.copy2(result.artifact.sheet.path, destination)
        sheet = GeneratedSheet(
            path=destination,
            width=result.artifact.sheet.width,
            height=result.artifact.sheet.height,
            mime_type=result.artifact.sheet.mime_type,
        )
    return PreviewArtifact(frames=frames, sheet=sheet)


def _expected_target_frames(args: argparse.Namespace) -> int:
    return args.target_frames


def _fixture_mode(torrent_path: Path, torrent_dir: Path) -> str:
    try:
        relative_parts = torrent_path.relative_to(torrent_dir).parts
    except ValueError:
        relative_parts = torrent_path.parts
    if _TRUTHFUL_PARTIAL_DIR_NAME in relative_parts[:-1]:
        return "truthful-partial"
    return "strict"


def _frame_check(frame: GeneratedFrame) -> dict[str, Any]:
    path = frame.path
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    jpeg_complete = False
    if exists and size >= 4:
        with path.open("rb") as file:
            head = file.read(2)
            file.seek(-2, 2)
            tail = file.read(2)
        jpeg_complete = head == b"\xff\xd8" and tail == b"\xff\xd9"
    visual = _visual_check(path) if exists and jpeg_complete else _empty_visual_check()
    ok = (
        exists
        and size >= 1024
        and jpeg_complete
        and frame.width >= 64
        and frame.height >= 64
        and frame.timestamp_seconds >= 0
        and visual["visual_ok"]
    )
    return {
        "path": path,
        "exists": exists,
        "size_bytes": size,
        "jpeg_complete": jpeg_complete,
        "width": frame.width,
        "height": frame.height,
        "timestamp_seconds": round(frame.timestamp_seconds, 3),
        **visual,
        "ok": ok,
    }


def _sheet_check(sheet: GeneratedSheet | None) -> dict[str, Any]:
    if sheet is None:
        return {
            "ok": False,
            "path": None,
            "exists": False,
            "size_bytes": 0,
            "jpeg_complete": False,
            "width": 0,
            "height": 0,
            "visual_reason": "sheet missing",
        }
    path = sheet.path
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    jpeg_complete = False
    if exists and size >= 4:
        with path.open("rb") as file:
            head = file.read(2)
            file.seek(-2, 2)
            tail = file.read(2)
        jpeg_complete = head == b"\xff\xd8" and tail == b"\xff\xd9"
    image = cv2.imread(str(path), cv2.IMREAD_COLOR) if exists else None
    decoded = image is not None
    height = int(image.shape[0]) if image is not None else 0
    width = int(image.shape[1]) if image is not None else 0
    dimensions_match = width == sheet.width and height == sheet.height
    ok = (
        exists
        and size >= 1024
        and jpeg_complete
        and decoded
        and sheet.width >= 320
        and sheet.height >= 180
        and dimensions_match
    )
    reason = ""
    if not ok:
        reason = (
            f"sheet check failed: exists={exists}, size={size}, "
            f"jpeg_complete={jpeg_complete}, decoded={decoded}, "
            f"dimensions_match={dimensions_match}"
        )
    return {
        "ok": ok,
        "path": path,
        "exists": exists,
        "size_bytes": size,
        "jpeg_complete": jpeg_complete,
        "width": width,
        "height": height,
        "declared_width": sheet.width,
        "declared_height": sheet.height,
        "visual_reason": reason,
    }


def _visual_check(path: Path) -> dict[str, Any]:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return {
            **_empty_visual_check(),
            "visual_reason": "OpenCV could not decode frame",
        }
    luma = cv2.resize(image, (64, 64), interpolation=cv2.INTER_AREA)
    mean_luma = float(np.mean(luma))
    luma_stddev = float(np.std(luma))
    dark_pixel_ratio = float(np.count_nonzero(luma < 16) / luma.size)
    visual_ok = (
        mean_luma >= _MIN_MEAN_LUMA
        and luma_stddev >= _MIN_LUMA_STDDEV
        and dark_pixel_ratio <= _MAX_DARK_PIXEL_RATIO
    )
    reason = ""
    if not visual_ok:
        reason = (
            "low visual signal: "
            f"mean_luma={mean_luma:.2f}, "
            f"luma_stddev={luma_stddev:.2f}, "
            f"dark_pixel_ratio={dark_pixel_ratio:.3f}"
        )
    return {
        "visual_ok": visual_ok,
        "mean_luma": round(mean_luma, 2),
        "luma_stddev": round(luma_stddev, 2),
        "dark_pixel_ratio": round(dark_pixel_ratio, 3),
        "visual_reason": reason,
    }


def _empty_visual_check() -> dict[str, Any]:
    return {
        "visual_ok": False,
        "mean_luma": 0.0,
        "luma_stddev": 0.0,
        "dark_pixel_ratio": 1.0,
        "visual_reason": "visual check skipped",
    }


def _frame_set_check(frames: list[Any]) -> dict[str, Any]:
    if len(frames) < 2:
        return {
            "ok": True,
            "diversity_ok": True,
            "reason": "",
            "pairwise": [],
        }

    images: list[tuple[int, np.ndarray]] = []
    for index, frame in enumerate(frames, start=1):
        image = cv2.imread(str(frame.path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            continue
        resized = cv2.resize(image, (160, 90), interpolation=cv2.INTER_AREA)
        images.append((index, resized))

    pairwise: list[dict[str, Any]] = []
    diversity_ok = True
    for left_offset, (left_index, left_image) in enumerate(images):
        for right_index, right_image in images[left_offset + 1 :]:
            diff = cv2.absdiff(left_image, right_image)
            mean_abs_diff = float(np.mean(diff))
            correlation = float(
                np.corrcoef(left_image.reshape(-1), right_image.reshape(-1))[0, 1]
            )
            pair_ok = (
                mean_abs_diff >= _MIN_PAIRWISE_MEAN_ABS_DIFF
                or correlation <= _MAX_PAIRWISE_CORRELATION
            )
            diversity_ok = diversity_ok and pair_ok
            pairwise.append(
                {
                    "left": left_index,
                    "right": right_index,
                    "mean_abs_diff": round(mean_abs_diff, 3),
                    "correlation": round(correlation, 5),
                    "ok": pair_ok,
                }
            )

    reason = ""
    if not diversity_ok:
        reason = (
            "near-duplicate preview frames: "
            f"min_pairwise_mean_abs_diff={_MIN_PAIRWISE_MEAN_ABS_DIFF:.1f}, "
            f"max_pairwise_correlation={_MAX_PAIRWISE_CORRELATION:.2f}"
        )
    return {
        "ok": diversity_ok,
        "diversity_ok": diversity_ok,
        "reason": reason,
        "pairwise": pairwise,
    }


def _all_results_good(results: list[dict[str, Any]]) -> bool:
    return bool(results) and all(item.get("quality_ok") for item in results)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {_json_key(key): _json_value(key, item) for key, item in value.items()}
    return value


def _json_key(key: object) -> str:
    text = str(key)
    if text.endswith("_bytes"):
        return f"{text[:-6]}_mb"
    return text


def _json_value(key: object, value: object) -> Any:
    if str(key).endswith("_bytes") and isinstance(value, int | float):
        return round(_bytes_to_mb(value), 2)
    return _jsonable(value)


def _bytes_to_mb(value: int | float) -> float:
    return value / (1024 * 1024)


if __name__ == "__main__":
    main()
