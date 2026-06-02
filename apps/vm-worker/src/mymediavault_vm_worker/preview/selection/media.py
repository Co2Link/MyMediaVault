"""Media file selection."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from mymediavault_vm_worker.preview.core.exceptions import NoVideoFileError
from mymediavault_vm_worker.preview.core.models import SelectedFile

_MATCH_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

VIDEO_EXTENSIONS = {
    ".3gp",
    ".avi",
    ".flv",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".mts",
    ".ogm",
    ".ogv",
    ".ts",
    ".webm",
    ".wmv",
}


def select_largest_video_file(
    files: list[SelectedFile], *, torrent_name: str | None = None
) -> SelectedFile:
    """Select the best supported video, using size to break name-score ties."""

    candidates = [file for file in files if _is_video(file)]
    if not candidates:
        msg = "No supported video file was found in torrent metadata"
        raise NoVideoFileError(msg)
    name_tokens = _match_tokens(torrent_name or "")
    return max(
        candidates,
        key=lambda file: (_shared_token_score(name_tokens, file.path), file.length),
    )


def _is_video(file: SelectedFile) -> bool:
    suffix = PurePosixPath(file.path.lower()).suffix
    return suffix in VIDEO_EXTENSIONS and file.length > 0


def _match_tokens(value: str) -> set[str]:
    return {
        token
        for token in _MATCH_TOKEN_PATTERN.findall(value.lower())
        if len(token) >= 3
    }


def _shared_token_score(name_tokens: set[str], path: str) -> int:
    return sum(len(token) for token in name_tokens & _match_tokens(path))
