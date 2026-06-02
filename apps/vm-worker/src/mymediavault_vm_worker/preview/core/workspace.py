"""Temporary workspace management."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


class PreviewWorkspace:
    """Creates temporary directories for one preview and cleans them on exit."""

    def __init__(self, info_hash: str, *, root: Path | None = None) -> None:
        self.info_hash = info_hash
        self._root = root
        self._temp_dir: tempfile.TemporaryDirectory[str] | None = None
        self.path: Path | None = None

    def __enter__(self) -> PreviewWorkspace:
        if self._root is None:
            self._temp_dir = tempfile.TemporaryDirectory(
                prefix=f"torrent-preview-{self.info_hash[:12]}-"
            )
            self.path = Path(self._temp_dir.name)
        else:
            self.path = self._root / self.info_hash
            self.path.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            return
        if self.path is not None:
            shutil.rmtree(self.path, ignore_errors=True)

    @property
    def media_dir(self) -> Path:
        return self._require_path() / "media"

    @property
    def frames_dir(self) -> Path:
        return self._require_path() / "frames"

    def _require_path(self) -> Path:
        if self.path is None:
            msg = "PreviewWorkspace must be entered before paths are used"
            raise RuntimeError(msg)
        return self.path
