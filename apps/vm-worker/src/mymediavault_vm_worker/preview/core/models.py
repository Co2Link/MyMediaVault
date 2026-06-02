"""Public data models for torrent-preview."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Literal

PreviewStatus = Literal["succeeded", "partial", "failed"]
BYTES_PER_MB = 1024 * 1024
PREVIEW_ARTIFACT_VERSION = "preview-v9"
PREVIEW_FINGERPRINT_SCHEMA_VERSION = 1
DEFAULT_TRACKER_LIST_URL = (
    "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_all.txt"
)
DEFAULT_SHEET_RECIPE = {
    "renderer": "thumbnail-sheet",
    "renderer_version": "sheet-v4",
    "tile_width": 320,
    "tile_height": 180,
}
DEFAULT_MAX_CONCURRENT_DOWNLOADS = 10
DEFAULT_MAX_CONCURRENT_DECODES = 2
DEFAULT_ANCHOR_RANGE_MB = 32
DEFAULT_EDGE_RANGE_MB = 32
DEFAULT_MAX_TIME_SECONDS = 3600.0
DEFAULT_MAX_DOWNLOAD_TIME_SECONDS = 1800.0
DEFAULT_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS = 600.0
DEFAULT_MAX_DECODE_TIME_SECONDS = 90.0
DEFAULT_TARGET_FRAMES = 9
SUPPORTED_TARGET_FRAMES = frozenset({3, 9, 16})
DEFAULT_ANCHOR_WINDOW_SECONDS = 30.0
DEFAULT_TORRENT_CACHE_MAX_MB = 32768
DEFAULT_USE_DEFAULT_TRACKERS = True
DEFAULT_TRACKER_FETCH_TIMEOUT_SECONDS = 3.0
DEFAULT_TRACKER_TTL_SECONDS = 24 * 60 * 60
DEFAULT_LLM_MODEL = "gpt-5.4-mini"
DEFAULT_LLM_TIMEOUT_SECONDS = 8.0
DEFAULT_ANCHOR_CANDIDATES_PER_ANCHOR = 5
DEFAULT_ANCHOR_RETRY_RANGE_MB = (64.0, 128.0, 256.0, 384.0, 512.0, 768.0)
DEFAULT_WARM_SWARM_MAX_HANDLES = 40
DEFAULT_WARM_SWARM_IDLE_SECONDS = 2 * 60 * 60
DEFAULT_WARM_SWARM_DOWNLOAD_LIMIT_BYTES_PER_SECOND = 64 * 1024


def _default_torrent_cache_dir() -> Path:
    """Return the default cross-platform torrent cache directory."""

    return Path(tempfile.gettempdir()) / "torrent-preview-cache"


@dataclass(frozen=True)
class SelectedFile:
    """A torrent file selected for preview generation."""

    index: int
    path: str
    length: int
    offset: int = 0


@dataclass(frozen=True)
class PreviewRequest:
    """A request to generate preview frames from raw .torrent bytes."""

    torrent_bytes: bytes

    def __post_init__(self) -> None:
        if not self.torrent_bytes:
            msg = "PreviewRequest.torrent_bytes must not be empty"
            raise ValueError(msg)


@dataclass(frozen=True)
class PreviewEngineConfig:
    """Shared runtime settings for a long-lived PreviewEngine."""

    max_concurrent_downloads: int = DEFAULT_MAX_CONCURRENT_DOWNLOADS
    max_concurrent_decodes: int = DEFAULT_MAX_CONCURRENT_DECODES
    anchor_range_mb: float = DEFAULT_ANCHOR_RANGE_MB
    edge_range_mb: float = DEFAULT_EDGE_RANGE_MB
    max_time_seconds: float = DEFAULT_MAX_TIME_SECONDS
    max_download_time_seconds: float = DEFAULT_MAX_DOWNLOAD_TIME_SECONDS
    download_progress_timeout_seconds: float = DEFAULT_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS
    max_decode_time_seconds: float = DEFAULT_MAX_DECODE_TIME_SECONDS
    target_frames: int = DEFAULT_TARGET_FRAMES
    anchor_window_seconds: float = DEFAULT_ANCHOR_WINDOW_SECONDS
    trackers: tuple[str, ...] = ()
    upload_rate_limit: int | None = None
    torrent_cache_dir: Path = field(default_factory=_default_torrent_cache_dir)
    torrent_cache_max_mb: float = DEFAULT_TORRENT_CACHE_MAX_MB
    use_default_trackers: bool = DEFAULT_USE_DEFAULT_TRACKERS
    default_tracker_list_url: str = DEFAULT_TRACKER_LIST_URL
    default_tracker_fetch_timeout_seconds: float = DEFAULT_TRACKER_FETCH_TIMEOUT_SECONDS
    default_tracker_ttl_seconds: float = DEFAULT_TRACKER_TTL_SECONDS
    llm_model: str = DEFAULT_LLM_MODEL
    llm_timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS
    anchor_candidates_per_anchor: int = DEFAULT_ANCHOR_CANDIDATES_PER_ANCHOR
    anchor_retry_range_mb: tuple[float, ...] = DEFAULT_ANCHOR_RETRY_RANGE_MB
    warm_swarm_max_handles: int = DEFAULT_WARM_SWARM_MAX_HANDLES
    warm_swarm_idle_seconds: float = DEFAULT_WARM_SWARM_IDLE_SECONDS
    warm_swarm_download_limit_bytes_per_second: int = (
        DEFAULT_WARM_SWARM_DOWNLOAD_LIMIT_BYTES_PER_SECOND
    )

    def __post_init__(self) -> None:
        positive_ints = {
            "max_concurrent_downloads": self.max_concurrent_downloads,
            "max_concurrent_decodes": self.max_concurrent_decodes,
            "target_frames": self.target_frames,
            "anchor_candidates_per_anchor": self.anchor_candidates_per_anchor,
            "warm_swarm_download_limit_bytes_per_second": (
                self.warm_swarm_download_limit_bytes_per_second
            ),
        }
        for name, value in positive_ints.items():
            if value < 1:
                msg = f"PreviewEngineConfig.{name} must be at least 1"
                raise ValueError(msg)
        if self.target_frames not in SUPPORTED_TARGET_FRAMES:
            supported = ", ".join(
                str(value) for value in sorted(SUPPORTED_TARGET_FRAMES)
            )
            msg = f"PreviewEngineConfig.target_frames must be one of {supported}"
            raise ValueError(msg)
        if self.anchor_range_mb <= 0:
            msg = "PreviewEngineConfig.anchor_range_mb must be greater than 0"
            raise ValueError(msg)
        if self.edge_range_mb <= 0:
            msg = "PreviewEngineConfig.edge_range_mb must be greater than 0"
            raise ValueError(msg)
        if self.torrent_cache_max_mb <= 0:
            msg = "PreviewEngineConfig.torrent_cache_max_mb must be greater than 0"
            raise ValueError(msg)
        if self.torrent_cache_dir is None:
            msg = "PreviewEngineConfig.torrent_cache_dir must be a Path"
            raise ValueError(msg)
        if self.max_time_seconds <= 0:
            msg = "PreviewEngineConfig.max_time_seconds must be greater than 0"
            raise ValueError(msg)
        if self.max_download_time_seconds <= 0:
            msg = "PreviewEngineConfig.max_download_time_seconds must be greater than 0"
            raise ValueError(msg)
        if self.download_progress_timeout_seconds <= 0:
            msg = "PreviewEngineConfig.download_progress_timeout_seconds must be greater than 0"
            raise ValueError(msg)
        if self.warm_swarm_max_handles < 0:
            msg = "PreviewEngineConfig.warm_swarm_max_handles must be non-negative"
            raise ValueError(msg)
        if self.warm_swarm_idle_seconds <= 0:
            msg = "PreviewEngineConfig.warm_swarm_idle_seconds must be greater than 0"
            raise ValueError(msg)
        if self.warm_swarm_download_limit_bytes_per_second < 1:
            msg = (
                "PreviewEngineConfig.warm_swarm_download_limit_bytes_per_second "
                "must be at least 1"
            )
            raise ValueError(msg)
        if self.max_decode_time_seconds <= 0:
            msg = "PreviewEngineConfig.max_decode_time_seconds must be greater than 0"
            raise ValueError(msg)
        if self.anchor_window_seconds <= 0:
            msg = "PreviewEngineConfig.anchor_window_seconds must be greater than 0"
            raise ValueError(msg)
        if self.default_tracker_fetch_timeout_seconds <= 0:
            msg = "PreviewEngineConfig.default_tracker_fetch_timeout_seconds must be greater than 0"
            raise ValueError(msg)
        if self.default_tracker_ttl_seconds <= 0:
            msg = (
                "PreviewEngineConfig.default_tracker_ttl_seconds must be greater than 0"
            )
            raise ValueError(msg)
        if not self.llm_model:
            msg = "PreviewEngineConfig.llm_model must not be empty"
            raise ValueError(msg)
        if self.llm_timeout_seconds <= 0:
            msg = "PreviewEngineConfig.llm_timeout_seconds must be greater than 0"
            raise ValueError(msg)
        if self.upload_rate_limit is not None and self.upload_rate_limit < 1:
            msg = "PreviewEngineConfig.upload_rate_limit must be at least 1 when set"
            raise ValueError(msg)
        previous_retry_range = self.anchor_range_mb
        for value in self.anchor_retry_range_mb:
            if value <= previous_retry_range:
                msg = (
                    "PreviewEngineConfig.anchor_retry_range_mb values must be "
                    "greater than anchor_range_mb and strictly increasing"
                )
                raise ValueError(msg)
            previous_retry_range = value

    @property
    def anchor_range_bytes(self) -> int:
        """Byte window planned around each timeline anchor."""

        return max(1, int(self.anchor_range_mb * BYTES_PER_MB))

    @property
    def edge_range_bytes(self) -> int:
        """Byte window planned at the head and tail of the selected file."""

        return max(1, int(self.edge_range_mb * BYTES_PER_MB))

    @property
    def torrent_cache_max_bytes(self) -> int:
        """Maximum persistent torrent cache budget in bytes."""

        return max(1, int(self.torrent_cache_max_mb * BYTES_PER_MB))

    def artifact_recipe(
        self,
        *,
        sheet_recipe: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Return the normalized recipe used to generate preview artifacts."""

        return {
            "artifact_version": PREVIEW_ARTIFACT_VERSION,
            "fingerprint_schema_version": PREVIEW_FINGERPRINT_SCHEMA_VERSION,
            "download": {
                "anchor_range_mb": self.anchor_range_mb,
                "anchor_retry_range_mb": self.anchor_retry_range_mb,
                "edge_range_mb": self.edge_range_mb,
            },
            "decode": {
                "decoder": "ffmpeg-anchor-v3",
                "target_frames": self.target_frames,
                "anchor_window_seconds": self.anchor_window_seconds,
                "anchor_candidates_per_anchor": self.anchor_candidates_per_anchor,
            },
            "planning": {
                "layout": "planned-preview-ranges-v1",
            },
            "ranking": {
                "scorer": "quality-v1",
                "ranker": "pydantic-ai-anchor-acceptance-v1",
                "llm_model": self.llm_model,
            },
            "sheet": dict(sheet_recipe or DEFAULT_SHEET_RECIPE),
        }

    def artifact_fingerprint(
        self,
        *,
        sheet_recipe: Mapping[str, object] | None = None,
    ) -> str:
        """Return a stable short hash for the preview artifact recipe."""

        payload = json.dumps(
            self.artifact_recipe(sheet_recipe=sheet_recipe),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(payload).hexdigest()[:16]}"


@dataclass(frozen=True)
class PreviewContext:
    """Context supplied to frame handlers."""

    info_hash: str
    selected_file: SelectedFile


@dataclass(frozen=True)
class ExtractedFrame:
    """Internal decoded frame candidate generated by the library."""

    path: Path
    score: float
    width: int
    height: int
    timestamp_seconds: float
    anchor_index: int | None = None
    anchor_ratio: float | None = None
    decode_method: str = "unknown"
    accepted_by_llm: bool = False


@dataclass(frozen=True)
class GeneratedFrame:
    """A generated preview frame valid inside ``preview_artifact``."""

    path: Path
    width: int
    height: int
    timestamp_seconds: float


@dataclass(frozen=True)
class GeneratedSheet:
    """A generated preview sheet valid inside ``preview_artifact``."""

    path: Path
    width: int
    height: int
    mime_type: str = "image/jpeg"


@dataclass(frozen=True)
class PreviewArtifact:
    """Generated preview media returned to the caller."""

    frames: list[GeneratedFrame]
    sheet: GeneratedSheet | None


@dataclass(frozen=True)
class LLMSelectionDiagnostics:
    """Summary of one LLM frame acceptance call."""

    model: str
    candidate_frame_count: int
    selected_frame_count: int
    target_frame_count: int
    reason: str | None = None


@dataclass(frozen=True)
class AnchorRetryAttemptDiagnostics:
    """Summary of one supplemental anchor retry pass."""

    range_mb: float
    target_anchor_indexes: list[int]
    decoded_candidate_counts_by_anchor: dict[int, int]
    llm_visible_candidate_counts_by_anchor: dict[int, int]
    remaining_missing_anchor_indexes: list[int]
    downloaded_bytes: int
    planned_pieces_complete: bool | None = None


@dataclass(frozen=True)
class AnchorRetryDiagnostics:
    """Summary of bounded in-attempt anchor retry behavior."""

    range_mb_ladder: tuple[float, ...]
    initial_missing_anchor_indexes: list[int]
    final_missing_anchor_indexes: list[int]
    attempts: list[AnchorRetryAttemptDiagnostics] = field(default_factory=list)

    @property
    def attempt_count(self) -> int:
        """Number of supplemental retry download/decode passes attempted."""

        return len(self.attempts)


@dataclass(frozen=True)
class PreviewDiagnostics:
    """Best-effort diagnostic data for preview troubleshooting."""

    torrent_cache_dir: str
    torrent_cache_max_mb: float
    torrent_cache_entry_exists_before: bool
    resume_data_exists_before: bool
    warnings: list[str] = field(default_factory=list)
    selected_file: SelectedFile | None = None
    downloaded_bytes: int = 0
    elapsed_seconds: float = 0.0
    resume_data_saved: bool | None = None
    last_download_rate: int | None = None
    last_num_peers: int | None = None
    last_num_seeds: int | None = None
    last_torrent_state: str | None = None
    last_complete_piece_count: int | None = None
    last_requested_piece_count: int | None = None
    planned_pieces_complete: bool | None = None
    tracker_count: int | None = None
    tracker_alerts: list[str] = field(default_factory=list)
    dht_alerts: list[str] = field(default_factory=list)
    llm: LLMSelectionDiagnostics | None = None
    anchor_retry: AnchorRetryDiagnostics | None = None


@dataclass(frozen=True)
class PreviewResult:
    """Structured result for one torrent preview attempt."""

    info_hash: str
    status: PreviewStatus
    status_reason: str | None
    artifact: PreviewArtifact
    diagnostics: PreviewDiagnostics

    def __post_init__(self) -> None:
        if self.status == "succeeded" and self.status_reason is not None:
            msg = "PreviewResult.status_reason must be None for succeeded results"
            raise ValueError(msg)
        if self.status != "succeeded" and not self.status_reason:
            msg = (
                "PreviewResult.status_reason is required for partial and failed results"
            )
            raise ValueError(msg)
        if self.status == "failed":
            if self.artifact.frames or self.artifact.sheet is not None:
                msg = "failed PreviewResult must not contain generated artifacts"
                raise ValueError(msg)
            return
        if not self.artifact.frames or self.artifact.sheet is None:
            msg = (
                "succeeded and partial PreviewResult values require frames and a sheet"
            )
            raise ValueError(msg)
