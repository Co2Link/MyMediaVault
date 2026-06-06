from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from mymediavault_vm_worker.actor.config import DEFAULT_MODELS_DIR
from mymediavault_vm_worker.actor.worker import (
    DEFAULT_ACTOR_ANALYSIS_LEASE_SECONDS,
    DEFAULT_ACTOR_ANALYSIS_MAX_ATTEMPTS,
    DEFAULT_ACTOR_ANALYSIS_POLL_INTERVAL_SECONDS,
)
from mymediavault_vm_worker.preview.core.models import (
    DEFAULT_ANCHOR_RETRY_RANGE_MB,
    DEFAULT_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS,
    DEFAULT_EXTRACT_FRAMES_PER_ANCHOR,
    DEFAULT_MAX_SELECTOR_CANDIDATES_PER_ANCHOR,
    DEFAULT_MIN_SELECTOR_CANDIDATES_PER_ANCHOR,
    DEFAULT_TORRENT_CACHE_MAX_MB,
)

DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_MAX_CONCURRENCY = 20
DEFAULT_STALE_PROCESSING_MINUTES = 120
DEFAULT_PREVIEW_SESSION_FAIRNESS_SECONDS = 2 * 60 * 60
DEFAULT_PREVIEW_FAILURE_LIMIT = 3
DEFAULT_EXTERNAL_FAILURE_COOLDOWN_SECONDS = 300
DEFAULT_PREVIEW_CACHE_DIR = Path("/var/cache/mymediavault/vm-worker")
DEFAULT_DEBUG_LOG_PATH = Path(".local/logs/vm-worker-debug.log")
DEFAULT_DEBUG_LOG_ROTATION = "100 MB"
DEFAULT_DEBUG_LOG_RETENTION = "7 days"
DEFAULT_METADATA_DHT_TIMEOUT_SECONDS = 600
SPARSE_CONTINUATION_LOG_INTERVAL_SECONDS = 10 * 60
class PreviewWorkerSettings(BaseSettings):
    mongodb_uri: str = Field(alias="MONGODB_URI")
    mongodb_database: str = Field(default="mymediavault", alias="MMV_MONGODB_DB_NAME")
    mongodb_server_selection_timeout_ms: int = Field(
        default=10000, alias="MMV_MONGODB_SERVER_SELECTION_TIMEOUT_MS"
    )
    r2_endpoint: str | None = Field(default=None, alias="R2_ENDPOINT")
    r2_access_key_id: str | None = Field(default=None, alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str | None = Field(default=None, alias="R2_SECRET_ACCESS_KEY")
    r2_bucket_name: str = Field(default="torrent-raw", alias="R2_BUCKET_NAME")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    preview_worker_enabled: bool = Field(
        default=True, alias="MMV_PREVIEW_WORKER_ENABLED"
    )
    actor_analysis_worker_enabled: bool = Field(
        default=True, alias="MMV_ACTOR_ANALYSIS_WORKER_ENABLED"
    )
    actor_analysis_models_dir: Path = Field(
        default=DEFAULT_MODELS_DIR, alias="MMV_ACTOR_ANALYSIS_MODELS_DIR"
    )
    actor_analysis_poll_interval_seconds: float = Field(
        default=DEFAULT_ACTOR_ANALYSIS_POLL_INTERVAL_SECONDS,
        alias="MMV_ACTOR_ANALYSIS_POLL_INTERVAL_SECONDS",
    )
    actor_analysis_lease_seconds: int = Field(
        default=DEFAULT_ACTOR_ANALYSIS_LEASE_SECONDS,
        alias="MMV_ACTOR_ANALYSIS_LEASE_SECONDS",
    )
    actor_analysis_max_attempts: int = Field(
        default=DEFAULT_ACTOR_ANALYSIS_MAX_ATTEMPTS,
        alias="MMV_ACTOR_ANALYSIS_MAX_ATTEMPTS",
    )
    preview_worker_max_concurrency: int = Field(
        default=DEFAULT_MAX_CONCURRENCY, alias="MMV_PREVIEW_WORKER_MAX_CONCURRENCY"
    )
    preview_worker_poll_interval_seconds: float = Field(
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        alias="MMV_PREVIEW_WORKER_POLL_INTERVAL_SECONDS",
    )
    preview_repair_stale_processing_minutes: int = Field(
        default=DEFAULT_STALE_PROCESSING_MINUTES,
        alias="MMV_PREVIEW_REPAIR_STALE_PROCESSING_MINUTES",
    )
    preview_extract_frames_per_anchor: int = Field(
        default=DEFAULT_EXTRACT_FRAMES_PER_ANCHOR,
        alias="MMV_PREVIEW_EXTRACT_FRAMES_PER_ANCHOR",
    )
    preview_min_selector_candidates_per_anchor: int = Field(
        default=DEFAULT_MIN_SELECTOR_CANDIDATES_PER_ANCHOR,
        alias="MMV_PREVIEW_MIN_SELECTOR_CANDIDATES_PER_ANCHOR",
    )
    preview_max_selector_candidates_per_anchor: int = Field(
        default=DEFAULT_MAX_SELECTOR_CANDIDATES_PER_ANCHOR,
        alias="MMV_PREVIEW_MAX_SELECTOR_CANDIDATES_PER_ANCHOR",
    )
    preview_anchor_retry_range_mb: tuple[float, ...] = Field(
        default=DEFAULT_ANCHOR_RETRY_RANGE_MB,
        alias="MMV_PREVIEW_ANCHOR_RETRY_RANGE_MB",
    )
    preview_download_progress_timeout_seconds: float = Field(
        default=DEFAULT_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS,
        alias="MMV_PREVIEW_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS",
    )
    preview_session_fairness_seconds: float = Field(
        default=DEFAULT_PREVIEW_SESSION_FAIRNESS_SECONDS,
        alias="MMV_PREVIEW_SESSION_FAIRNESS_SECONDS",
    )
    preview_failure_limit: int = Field(
        default=DEFAULT_PREVIEW_FAILURE_LIMIT,
        alias="MMV_PREVIEW_FAILURE_LIMIT",
    )
    preview_external_failure_cooldown_seconds: int = Field(
        default=DEFAULT_EXTERNAL_FAILURE_COOLDOWN_SECONDS,
        alias="MMV_PREVIEW_EXTERNAL_FAILURE_COOLDOWN_SECONDS",
    )
    preview_cache_dir: Path = Field(
        default=DEFAULT_PREVIEW_CACHE_DIR,
        alias="MMV_PREVIEW_CACHE_DIR",
    )
    preview_cache_max_mb: float = Field(
        default=DEFAULT_TORRENT_CACHE_MAX_MB,
        alias="MMV_PREVIEW_CACHE_MAX_MB",
    )
    vm_worker_debug_log_path: Path = Field(
        default=DEFAULT_DEBUG_LOG_PATH, alias="MMV_VM_WORKER_DEBUG_LOG_PATH"
    )
    vm_worker_debug_log_rotation: str = Field(
        default=DEFAULT_DEBUG_LOG_ROTATION,
        alias="MMV_VM_WORKER_DEBUG_LOG_ROTATION",
    )
    vm_worker_debug_log_retention: str = Field(
        default=DEFAULT_DEBUG_LOG_RETENTION,
        alias="MMV_VM_WORKER_DEBUG_LOG_RETENTION",
    )
    metadata_fetch_timeout_seconds: int = Field(
        default=20, alias="MMV_TORRENT_FETCH_TIMEOUT_SECONDS"
    )
    metadata_resolver_urls: list[str] = Field(
        default_factory=lambda: ["https://itorrents.org/torrent/{info_hash}.torrent"],
        alias="MMV_TORRENT_RESOLVER_URLS",
    )
    metadata_dht_fallback_enabled: bool = Field(
        default=True, alias="MMV_TORRENT_DHT_FALLBACK_ENABLED"
    )
    metadata_dht_timeout_seconds: int = Field(
        default=DEFAULT_METADATA_DHT_TIMEOUT_SECONDS,
        alias="MMV_TORRENT_DHT_TIMEOUT_SECONDS",
    )
    torrent_provider: str = Field(default="http", alias="MMV_TORRENT_PROVIDER")

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", populate_by_name=True
    )

    @model_validator(mode="after")
    def validate_storage_credentials(self) -> PreviewWorkerSettings:
        credentials = [
            self.r2_endpoint,
            self.r2_access_key_id,
            self.r2_secret_access_key,
        ]
        if any(credentials) and not all(credentials):
            msg = "R2_ENDPOINT, R2_ACCESS_KEY_ID, and R2_SECRET_ACCESS_KEY must be set together"
            raise ValueError(msg)
        if (
            not self.preview_worker_enabled
            and not self.actor_analysis_worker_enabled
        ):
            msg = "At least one VM-worker pipeline must be enabled"
            raise ValueError(msg)
        if self.preview_worker_enabled and not (self.openai_api_key or "").strip():
            msg = "OPENAI_API_KEY must be set for torrent-preview Pydantic AI frame selection"
            raise ValueError(msg)
        if self.preview_extract_frames_per_anchor < 1:
            msg = "MMV_PREVIEW_EXTRACT_FRAMES_PER_ANCHOR must be at least 1"
            raise ValueError(msg)
        if self.preview_min_selector_candidates_per_anchor < 1:
            msg = "MMV_PREVIEW_MIN_SELECTOR_CANDIDATES_PER_ANCHOR must be at least 1"
            raise ValueError(msg)
        if (
            self.preview_min_selector_candidates_per_anchor
            > self.preview_max_selector_candidates_per_anchor
        ):
            msg = (
                "MMV_PREVIEW_MIN_SELECTOR_CANDIDATES_PER_ANCHOR must be less than "
                "or equal to MMV_PREVIEW_MAX_SELECTOR_CANDIDATES_PER_ANCHOR"
            )
            raise ValueError(msg)
        if (
            self.preview_max_selector_candidates_per_anchor
            > self.preview_extract_frames_per_anchor
        ):
            msg = (
                "MMV_PREVIEW_MAX_SELECTOR_CANDIDATES_PER_ANCHOR must be less than "
                "or equal to MMV_PREVIEW_EXTRACT_FRAMES_PER_ANCHOR"
            )
            raise ValueError(msg)
        previous_retry_range = 32.0
        for value in self.preview_anchor_retry_range_mb:
            if value <= previous_retry_range:
                msg = (
                    "MMV_PREVIEW_ANCHOR_RETRY_RANGE_MB values must be greater "
                    "than 32 and strictly increasing"
                )
                raise ValueError(msg)
            previous_retry_range = value
        if self.preview_download_progress_timeout_seconds <= 0:
            msg = "MMV_PREVIEW_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS must be greater than 0"
            raise ValueError(msg)
        if self.preview_session_fairness_seconds <= 0:
            msg = "MMV_PREVIEW_SESSION_FAIRNESS_SECONDS must be greater than 0"
            raise ValueError(msg)
        if self.preview_failure_limit <= 0:
            msg = "MMV_PREVIEW_FAILURE_LIMIT must be greater than 0"
            raise ValueError(msg)
        if self.preview_external_failure_cooldown_seconds <= 0:
            msg = "MMV_PREVIEW_EXTERNAL_FAILURE_COOLDOWN_SECONDS must be greater than 0"
            raise ValueError(msg)
        if self.preview_cache_max_mb <= 0:
            msg = "MMV_PREVIEW_CACHE_MAX_MB must be greater than 0"
            raise ValueError(msg)
        if not self.metadata_resolver_urls:
            msg = "MMV_TORRENT_RESOLVER_URLS must include at least one resolver URL"
            raise ValueError(msg)
        if self.torrent_provider not in {"fake", "http"}:
            msg = "MMV_TORRENT_PROVIDER must be fake or http"
            raise ValueError(msg)
        if self.actor_analysis_poll_interval_seconds <= 0:
            msg = "MMV_ACTOR_ANALYSIS_POLL_INTERVAL_SECONDS must be greater than 0"
            raise ValueError(msg)
        if self.actor_analysis_lease_seconds <= 0:
            msg = "MMV_ACTOR_ANALYSIS_LEASE_SECONDS must be greater than 0"
            raise ValueError(msg)
        if self.actor_analysis_max_attempts <= 0:
            msg = "MMV_ACTOR_ANALYSIS_MAX_ATTEMPTS must be greater than 0"
            raise ValueError(msg)
        return self

