"""Custom exceptions raised by torrent-preview."""

from __future__ import annotations

from mymediavault_vm_worker.preview.core.models import PreviewDiagnostics


class PreviewError(Exception):
    """Base class for torrent-preview errors."""


class TorrentMetadataError(PreviewError):
    """Raised when torrent bytes cannot be parsed into usable metadata."""


class NoVideoFileError(PreviewError):
    """Raised when no supported video file can be selected from a torrent."""


class TorrentDownloadError(PreviewError):
    """Raised when planned torrent preview ranges cannot be downloaded."""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: PreviewDiagnostics | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


class FrameDecodeError(PreviewError):
    """Raised when frames cannot be decoded from downloaded media data."""


class FrameStorageError(PreviewError):
    """Raised when selected frames cannot be handled by the configured handler."""
