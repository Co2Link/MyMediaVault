"""Thin command-line wrapper around the public library API."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import TypeAlias

from mymediavault_vm_worker.preview import (
    PreviewEngine,
    PreviewEngineConfig,
    PreviewRequest,
    PreviewResult,
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
    _default_torrent_cache_dir,
)

Jsonable: TypeAlias = (
    str | int | float | bool | None | list["Jsonable"] | dict[str, "Jsonable"]
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a preview sheet from a .torrent file"
    )
    parser.add_argument("torrent", type=Path, help="Path to a .torrent file")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("previews"),
        help="Local output directory for selected frames and preview sheet",
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
    parser.add_argument(
        "--torrent-cache-dir",
        type=Path,
        default=_default_torrent_cache_dir(),
        help="Cache directory for torrent preview range downloads.",
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
    args = parser.parse_args()
    summary = asyncio.run(_run(args))
    print(json.dumps(_jsonable(summary), indent=2, sort_keys=True))


async def _run(args: argparse.Namespace) -> dict[str, object]:
    request = PreviewRequest(torrent_bytes=args.torrent.read_bytes())
    config = PreviewEngineConfig(
        target_frames=args.target_frames,
        anchor_range_mb=args.anchor_range_mb,
        edge_range_mb=args.edge_range_mb,
        max_time_seconds=args.max_time_seconds,
        max_download_time_seconds=args.max_download_time_seconds,
        download_progress_timeout_seconds=args.download_progress_timeout_seconds,
        max_decode_time_seconds=args.max_decode_time_seconds,
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
    async with PreviewEngine(config=config) as engine:
        async with engine.preview_artifact(request) as result:
            stored = _copy_artifacts(result, args.output_dir)
            return {
                **asdict(result),
                "artifact": stored,
                "artifact_version": engine.artifact_version,
                "artifact_fingerprint": engine.artifact_fingerprint,
            }


def _copy_artifacts(result: PreviewResult, output_dir: Path) -> dict[str, object]:
    artifact = result.artifact
    target_dir = output_dir / result.info_hash
    target_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, object]] = []
    for index, frame in enumerate(artifact.frames, start=1):
        destination = target_dir / f"frame_{index:03d}.jpg"
        shutil.copy2(frame.path, destination)
        frames.append(
            {
                "path": str(destination),
                "width": frame.width,
                "height": frame.height,
                "timestamp_seconds": frame.timestamp_seconds,
            }
        )
    sheet = None
    if artifact.sheet is not None:
        destination = target_dir / "preview_sheet.jpg"
        shutil.copy2(artifact.sheet.path, destination)
        sheet = {
            "path": str(destination),
            "width": artifact.sheet.width,
            "height": artifact.sheet.height,
            "mime_type": artifact.sheet.mime_type,
        }
    return {"frames": frames, "sheet": sheet}


def _jsonable(value: object) -> Jsonable:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {_json_key(key): _json_value(key, item) for key, item in value.items()}
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _json_key(key: object) -> str:
    text = str(key)
    if text.endswith("_bytes"):
        return f"{text[:-6]}_mb"
    return text


def _json_value(key: object, value: object) -> Jsonable:
    if str(key).endswith("_bytes") and isinstance(value, int | float):
        return round(value / (1024 * 1024), 2)
    return _jsonable(value)


if __name__ == "__main__":
    main()
