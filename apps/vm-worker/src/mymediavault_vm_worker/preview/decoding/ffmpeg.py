"""ffmpeg-backed frame extraction."""

from __future__ import annotations

import asyncio
import contextlib
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from mymediavault_vm_worker.preview.logging import bind_log

from mymediavault_vm_worker.preview.decoding.base import FrameDecoder
from mymediavault_vm_worker.preview.core.exceptions import FrameDecodeError
from mymediavault_vm_worker.preview.core.models import ExtractedFrame
from mymediavault_vm_worker.preview.planning.base import TimelineAnchor


_PROCESS_CLEANUP_TIMEOUT_SECONDS = 2.0
_FFPROBE_TIMEOUT_SECONDS = 10.0
_SHOWINFO_PTS_RE = re.compile(r"pts_time:(?P<timestamp>-?\d+(?:\.\d+)?)")
_ANCHOR_SEEK_PADDING_SECONDS = 2.0
_ANCHOR_TIMESTAMP_TOLERANCE_SECONDS = 1.0
_ANCHOR_TIMEOUT_CAP_SECONDS = 5.0
_ANCHOR_CANDIDATE_SPACING_SECONDS = 3.0
_STDERR_EXCERPT_MAX_CHARS = 500
_DECODE_ERROR_PATTERNS = (
    "error while decoding",
    "corrupt",
    "invalid data found",
    "concealing",
    "decode_slice_header error",
    "reference picture missing",
    "missing picture in access unit",
    "bytestream overread",
)


@dataclass(frozen=True)
class _FrameCandidate:
    path: Path
    timestamp_seconds: float
    anchor_index: int | None
    anchor_ratio: float | None
    decode_method: str


class _SubprocessTimeoutError(Exception):
    """Raised when an ffmpeg or ffprobe subprocess exceeds its budget."""


class FFmpegFrameDecoder(FrameDecoder):
    """Extract frames using the external ffmpeg executable."""

    def __init__(
        self,
        ffmpeg_path: str = "ffmpeg",
        ffprobe_path: str = "ffprobe",
        max_frame_width: int | None = None,
    ) -> None:
        if max_frame_width is not None and max_frame_width < 1:
            msg = "FFmpegFrameDecoder.max_frame_width must be at least 1 when set"
            raise ValueError(msg)
        self._ffmpeg_path = ffmpeg_path
        self._ffprobe_path = ffprobe_path
        self._max_frame_width = max_frame_width

    async def extract_frames(
        self,
        media_path: Path,
        output_dir: Path,
        target_frames: int,
        timeout_seconds: float,
        anchors: tuple[TimelineAnchor | float, ...],
        anchor_window_seconds: float = 30.0,
        extract_frames_per_anchor: int = 1,
    ) -> list[ExtractedFrame]:
        if shutil.which(self._ffmpeg_path) is None:
            msg = f"ffmpeg executable not found: {self._ffmpeg_path}"
            raise FrameDecodeError(msg)
        if extract_frames_per_anchor < 1:
            msg = "extract_frames_per_anchor must be at least 1"
            raise ValueError(msg)

        output_dir.mkdir(parents=True, exist_ok=True)
        duration = await self._probe_duration(media_path)
        if not anchors:
            return []
        if duration is None or duration <= 0:
            return []
        frame_candidates = await self._extract_anchor_frames(
            media_path,
            output_dir,
            anchors,
            duration,
            timeout_seconds,
            anchor_window_seconds,
            extract_frames_per_anchor,
        )
        return await self._candidates_to_frames(frame_candidates)

    async def _extract_anchor_frames(
        self,
        media_path: Path,
        output_dir: Path,
        anchors: tuple[TimelineAnchor | float, ...],
        duration: float,
        timeout_seconds: float,
        anchor_window_seconds: float,
        extract_frames_per_anchor: int,
    ) -> list[_FrameCandidate]:
        frame_candidates: list[_FrameCandidate] = []
        deadline = time.monotonic() + timeout_seconds
        for enumerated_index, anchor in enumerate(anchors):
            if isinstance(anchor, TimelineAnchor):
                anchor_index = anchor.index
                anchor_ratio = anchor.ratio
            else:
                anchor_index = enumerated_index
                anchor_ratio = anchor
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return frame_candidates
            remaining_anchors = max(1, len(anchors) - anchor_index)
            window_start = _anchor_window_start(
                duration,
                anchor_ratio,
                anchor_window_seconds,
            )
            timestamps = _anchor_candidate_timestamps(
                duration,
                anchor_ratio,
                anchor_window_seconds,
                extract_frames_per_anchor,
            )
            if not timestamps:
                continue
            anchor_timeout = min(
                _ANCHOR_TIMEOUT_CAP_SECONDS * len(timestamps),
                max(0.1, remaining / remaining_anchors),
            )
            pattern = output_dir / f"candidate_anchor_{anchor_index:03d}_%04d.jpg"
            _remove_existing_anchor_candidates(pattern)
            frame_candidates.extend(
                await self._extract_anchor_frames_by_seek(
                    media_path,
                    output_dir,
                    anchor_index=anchor_index,
                    anchor_ratio=anchor_ratio,
                    timestamps=timestamps,
                    window_start=window_start,
                    window_seconds=anchor_window_seconds,
                    duration=duration,
                    timeout_seconds=anchor_timeout,
                )
            )
        bind_log(
            media_path=str(media_path),
            anchor_count=len(anchors),
            extracted_frame_count=len(frame_candidates),
        ).debug("Finished ffmpeg anchor frame extraction")
        return frame_candidates

    async def _extract_anchor_frames_by_seek(
        self,
        media_path: Path,
        output_dir: Path,
        *,
        anchor_index: int,
        anchor_ratio: float,
        timestamps: list[float],
        window_start: float,
        window_seconds: float,
        duration: float,
        timeout_seconds: float,
    ) -> list[_FrameCandidate]:
        frame_candidates: list[_FrameCandidate] = []
        if timeout_seconds <= 0:
            return frame_candidates
        deadline = time.monotonic() + timeout_seconds
        for candidate_index, timestamp in enumerate(timestamps, start=1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return frame_candidates
            per_candidate_timeout = min(
                _ANCHOR_TIMEOUT_CAP_SECONDS,
                max(0.1, remaining),
            )
            path = output_dir / (
                f"candidate_anchor_{anchor_index:03d}_seek_{candidate_index:04d}.jpg"
            )
            command = [
                self._ffmpeg_path,
                "-hide_banner",
                "-loglevel",
                "info",
                "-y",
                "-ss",
                f"{timestamp:.3f}",
                "-fflags",
                "+genpts+discardcorrupt",
                "-err_detect",
                "explode",
                "-i",
                str(media_path),
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                _filter_chain("showinfo", self._max_frame_width),
                "-frames:v",
                "1",
                str(path),
            ]
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await _communicate_with_timeout(
                    process,
                    per_candidate_timeout,
                    label="ffmpeg single-frame anchor extraction",
                )
            except _SubprocessTimeoutError:
                bind_log(
                    media_path=str(media_path),
                    anchor_index=anchor_index,
                    anchor_ratio=anchor_ratio,
                    timestamp=round(timestamp, 3),
                    timeout_seconds=round(per_candidate_timeout, 2),
                ).debug("ffmpeg single-frame anchor extraction timed out")
                continue
            matched_decode_error = _matched_decode_error(stderr)
            if process.returncode != 0 or matched_decode_error is not None:
                bind_log(
                    media_path=str(media_path),
                    anchor_index=anchor_index,
                    anchor_ratio=anchor_ratio,
                    timestamp=round(timestamp, 3),
                    returncode=process.returncode,
                    decode_error_pattern=matched_decode_error,
                    stderr_excerpt=_stderr_excerpt(stderr),
                ).debug("Skipping single-frame anchor candidate after ffmpeg decode error")
                continue
            if not path.exists() or path.stat().st_size < 1:
                continue
            decoded_timestamps = _parse_showinfo_timestamps(
                stderr,
                window_start=timestamp,
                window_seconds=window_seconds,
            )
            decoded_timestamp = _decoded_timestamp_for_candidate(decoded_timestamps, 0)
            if decoded_timestamp is None:
                bind_log(
                    media_path=str(media_path),
                    anchor_index=anchor_index,
                    anchor_ratio=anchor_ratio,
                    candidate=str(path),
                ).debug("Skipping single-frame anchor candidate without decoded timestamp")
                continue
            if not _timestamp_in_anchor_window(
                decoded_timestamp,
                window_start=window_start,
                window_seconds=window_seconds,
            ):
                bind_log(
                    media_path=str(media_path),
                    anchor_index=anchor_index,
                    anchor_ratio=anchor_ratio,
                    expected_start=round(window_start, 3),
                    expected_end=round(window_start + window_seconds, 3),
                    decoded_timestamp=round(decoded_timestamp, 3),
                    candidate=str(path),
                ).debug("Skipping single-frame anchor candidate outside requested timestamp window")
                continue
            frame_candidates.append(
                _FrameCandidate(
                    path=path,
                    timestamp_seconds=min(duration, decoded_timestamp),
                    anchor_index=anchor_index,
                    anchor_ratio=anchor_ratio,
                    decode_method="anchor-seek",
                )
            )
        return frame_candidates

    async def _candidates_to_frames(
        self, frame_candidates: list[_FrameCandidate]
    ) -> list[ExtractedFrame]:
        frames: list[ExtractedFrame] = []
        for candidate in frame_candidates:
            width, height = await self._probe_dimensions(candidate.path)
            frames.append(
                ExtractedFrame(
                    path=candidate.path,
                    score=0.0,
                    width=width,
                    height=height,
                    timestamp_seconds=candidate.timestamp_seconds,
                    anchor_index=candidate.anchor_index,
                    anchor_ratio=candidate.anchor_ratio,
                    decode_method=candidate.decode_method,
                )
            )
        return frames

    async def _probe_duration(self, media_path: Path) -> float | None:
        if shutil.which(self._ffprobe_path) is None:
            return None
        command = [
            self._ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await _communicate_with_timeout(
                process,
                _FFPROBE_TIMEOUT_SECONDS,
                label="ffprobe duration",
            )
        except _SubprocessTimeoutError:
            bind_log(media_path=str(media_path)).debug("ffprobe duration timed out")
            return None
        if process.returncode != 0:
            return None
        try:
            return float(stdout.decode("utf-8", errors="replace").strip())
        except ValueError:
            return None

    async def _probe_dimensions(self, image_path: Path) -> tuple[int, int]:
        if shutil.which(self._ffprobe_path) is None:
            return 0, 0
        command = [
            self._ffprobe_path,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            str(image_path),
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await _communicate_with_timeout(
                process,
                _FFPROBE_TIMEOUT_SECONDS,
                label="ffprobe dimensions",
            )
        except _SubprocessTimeoutError:
            bind_log(image_path=str(image_path)).debug("ffprobe dimensions timed out")
            return 0, 0
        if process.returncode != 0:
            return 0, 0
        raw = stdout.decode("utf-8", errors="replace").strip()
        try:
            width_text, height_text = raw.split("x", maxsplit=1)
            return int(width_text), int(height_text)
        except ValueError:
            return 0, 0


def _anchor_candidate_timestamps(
    duration: float,
    anchor_ratio: float,
    window_seconds: float,
    count: int,
) -> list[float]:
    if count < 1:
        return []
    target = max(0.0, min(duration, duration * anchor_ratio))
    window_start = _anchor_window_start(duration, anchor_ratio, window_seconds)
    window_end = min(duration, window_start + window_seconds)
    if window_end <= window_start:
        return [window_start]
    spacing = min(
        _ANCHOR_CANDIDATE_SPACING_SECONDS,
        max(0.001, (window_end - window_start) / max(1, count + 1)),
    )
    center = (count - 1) / 2
    latest = max(0.0, duration - 0.001)
    timestamps: list[float] = []
    for index in range(count):
        timestamp = target + ((index - center) * spacing)
        timestamp = max(window_start, min(window_end, latest, timestamp))
        if all(abs(timestamp - existing) > 0.001 for existing in timestamps):
            timestamps.append(timestamp)
    return timestamps


def _anchor_window_start(
    duration: float,
    anchor_ratio: float,
    window_seconds: float,
) -> float:
    target = max(0.0, min(duration, duration * anchor_ratio))
    return max(0.0, target - (window_seconds / 2))


def _scale_filter(max_frame_width: int | None) -> str | None:
    if max_frame_width is None:
        return None
    return f"scale='min({max_frame_width},iw)':-2"


def _filter_chain(base_filter: str, max_frame_width: int | None) -> str:
    filters = [base_filter]
    scale_filter = _scale_filter(max_frame_width)
    if scale_filter is not None:
        filters.append(scale_filter)
    return ",".join(filters)


def _parse_showinfo_timestamps(
    stderr: bytes, *, window_start: float, window_seconds: float
) -> list[float]:
    text = stderr.decode("utf-8", errors="replace")
    timestamps: list[float] = []
    for match in _SHOWINFO_PTS_RE.finditer(text):
        raw_timestamp = float(match.group("timestamp"))
        if 0 <= raw_timestamp <= window_seconds + _ANCHOR_TIMESTAMP_TOLERANCE_SECONDS:
            timestamps.append(window_start + raw_timestamp)
        else:
            timestamps.append(raw_timestamp)
    return timestamps


def _decoded_timestamp_for_candidate(
    timestamps: list[float], candidate_index: int
) -> float | None:
    if candidate_index >= len(timestamps):
        return None
    return timestamps[candidate_index]


def _remove_existing_anchor_candidates(pattern: Path) -> None:
    for path in pattern.parent.glob(pattern.name.replace("%04d", "*")):
        path.unlink()


def _matched_decode_error(stderr: bytes) -> str | None:
    text = stderr.decode("utf-8", errors="replace").lower()
    for pattern in _DECODE_ERROR_PATTERNS:
        if pattern in text:
            return pattern
    return None


def _stderr_excerpt(stderr: bytes) -> str:
    text = stderr.decode("utf-8", errors="replace")
    compact = " ".join(text.split())
    if len(compact) <= _STDERR_EXCERPT_MAX_CHARS:
        return compact
    return compact[: _STDERR_EXCERPT_MAX_CHARS - 3] + "..."


def _timestamp_in_anchor_window(
    timestamp: float, *, window_start: float, window_seconds: float
) -> bool:
    return (
        window_start - _ANCHOR_TIMESTAMP_TOLERANCE_SECONDS
        <= timestamp
        <= window_start + window_seconds + _ANCHOR_TIMESTAMP_TOLERANCE_SECONDS
    )


async def _communicate_with_timeout(
    process: asyncio.subprocess.Process,
    timeout_seconds: float,
    *,
    label: str,
) -> tuple[bytes, bytes]:
    communicate_task = asyncio.create_task(process.communicate())
    try:
        return await asyncio.wait_for(
            asyncio.shield(communicate_task),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        _kill_process(process)
        try:
            await asyncio.wait_for(
                asyncio.shield(communicate_task),
                timeout=_PROCESS_CLEANUP_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            communicate_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await communicate_task
            await _wait_for_process_exit(process)
        msg = f"{label} timed out after {timeout_seconds:.1f}s"
        raise _SubprocessTimeoutError(msg) from exc


def _kill_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.kill()


async def _wait_for_process_exit(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        await asyncio.wait_for(
            process.wait(),
            timeout=_PROCESS_CLEANUP_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        bind_log(pid=process.pid).warning(
            "Timed out waiting for ffmpeg subprocess to exit after kill"
        )
