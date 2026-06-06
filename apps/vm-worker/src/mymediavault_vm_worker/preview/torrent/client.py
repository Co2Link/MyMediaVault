"""Torrent client boundary and libtorrent implementation."""

from __future__ import annotations

import asyncio
import importlib
import os
import shutil
import threading
import time
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from mymediavault_vm_worker.preview.logging import BoundLogger, bind_log

from mymediavault_vm_worker.preview.core.exceptions import TorrentDownloadError
from mymediavault_vm_worker.preview.core.models import (
    BYTES_PER_MB,
    PreviewDiagnostics,
    PreviewEngineConfig,
    SelectedFile,
)
from mymediavault_vm_worker.preview.planning.base import ByteRange, DownloadLayout
from mymediavault_vm_worker.preview.torrent.metadata import TorrentMetadata

_METADATA_BOOTSTRAP_PIECES_PER_EDGE = 16
_DOWNLOAD_PROGRESS_STEP_BYTES = 32 * BYTES_PER_MB
_DOWNLOAD_PROGRESS_STEP_PIECES = 2
_MAX_RELEVANT_ALERTS = 20
_DEFAULT_LISTEN_PORT = 6881
_ACTIVE_CACHE_ENTRIES: set[Path] = set()
_ACTIVE_CACHE_ENTRIES_LOCK = threading.Lock()
_DHT_BOOTSTRAP_ROUTERS = (
    ("router.bittorrent.com", 6881),
    ("router.utorrent.com", 6881),
    ("dht.transmissionbt.com", 6881),
)


class _TorrentStatusFields(TypedDict):
    download_rate: int | None
    num_peers: int | None
    num_seeds: int | None
    state: str | None


@dataclass(frozen=True)
class PreviewRangeDownload:
    """Result of downloading planned preview ranges."""

    media_path: Path
    downloaded_bytes: int
    selected_file_complete: bool
    planned_pieces_complete: bool
    diagnostics: PreviewDiagnostics
    decode_ready: bool = True


@dataclass
class _ActiveTorrent:
    """A torrent handle retained only while its scheduler session owns a slot."""

    info_hash: str
    handle: Any
    output_dir: Path
    media_path: Path
    selected_file: SelectedFile
    requested_piece_indexes: set[int]
    config: PreviewEngineConfig
    downloaded_bytes: int
    complete_piece_count: int


class TorrentClient(ABC):
    """Boundary for torrent runtime implementations."""

    @abstractmethod
    async def start(self) -> None:
        """Start the shared torrent runtime."""

    @abstractmethod
    async def close(self) -> None:
        """Close the shared torrent runtime."""

    def diagnostics(
        self, metadata: TorrentMetadata, config: PreviewEngineConfig
    ) -> PreviewDiagnostics:
        """Return best-effort diagnostics for the last client activity."""

        return _cache_diagnostics(metadata, config)

    async def release(self, info_hash: str, config: PreviewEngineConfig) -> None:
        """Save and release a torrent handle when its scheduler slot is yielded."""

        del info_hash, config

    @abstractmethod
    async def download(
        self,
        torrent_bytes: bytes,
        metadata: TorrentMetadata,
        selected_file: SelectedFile,
        layout: DownloadLayout,
        output_dir: Path,
        config: PreviewEngineConfig,
        timeout_seconds: float,
        min_complete_piece_count: int | None = None,
    ) -> PreviewRangeDownload:
        """Download planned preview ranges for the selected torrent file."""


class LibtorrentTorrentClient(TorrentClient):
    """Best-effort libtorrent-backed planned range downloader."""

    def __init__(self) -> None:
        self._lt: Any | None = None
        self._session: Any | None = None
        self._default_trackers: tuple[str, ...] = ()
        self._default_trackers_fetched_at = 0.0
        self._active_torrents: dict[str, _ActiveTorrent] = {}
        self._active_torrents_lock = threading.Lock()

    async def start(self) -> None:
        if self._session is not None:
            return
        try:
            self._lt = importlib.import_module("libtorrent")
        except ImportError as exc:
            msg = "libtorrent Python bindings are required for real torrent downloads"
            raise TorrentDownloadError(msg) from exc
        session_factory = getattr(self._lt, "session")
        self._session = session_factory(_session_settings())
        _bootstrap_dht(self._session)

    def diagnostics(
        self, metadata: TorrentMetadata, config: PreviewEngineConfig
    ) -> PreviewDiagnostics:
        return _cache_diagnostics(metadata, config)

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)
        self._session = None

    async def release(self, info_hash: str, config: PreviewEngineConfig) -> None:
        await asyncio.to_thread(self._release_active_torrent, info_hash, config)

    async def download(
        self,
        torrent_bytes: bytes,
        metadata: TorrentMetadata,
        selected_file: SelectedFile,
        layout: DownloadLayout,
        output_dir: Path,
        config: PreviewEngineConfig,
        timeout_seconds: float,
        min_complete_piece_count: int | None = None,
    ) -> PreviewRangeDownload:
        if self._session is None or self._lt is None:
            await self.start()
        if self._session is None or self._lt is None:
            msg = "libtorrent session is not available"
            raise TorrentDownloadError(msg)

        output_dir = _download_output_dir(output_dir, metadata, config)
        return await asyncio.to_thread(
            self._download_sync,
            torrent_bytes,
            metadata,
            selected_file,
            layout,
            output_dir,
            config,
            timeout_seconds,
            min_complete_piece_count,
        )

    def _download_sync(
        self,
        torrent_bytes: bytes,
        metadata: TorrentMetadata,
        selected_file: SelectedFile,
        layout: DownloadLayout,
        output_dir: Path,
        config: PreviewEngineConfig,
        timeout_seconds: float,
        min_complete_piece_count: int | None,
    ) -> PreviewRangeDownload:
        lt = self._lt
        session = self._session
        if lt is None or session is None:
            msg = "libtorrent session is not available"
            raise TorrentDownloadError(msg)

        cache_entry_exists_before = output_dir.exists()
        resume_data_exists_before = _resume_data_path(output_dir).exists()
        _touch_cache_entry(output_dir, config)
        _prune_torrent_cache(config, preserve=output_dir)
        base_params = self._build_add_torrent_params(
            lt, torrent_bytes, metadata, output_dir, config
        )
        tracker_count = _tracker_count(base_params)
        active = self._get_active_torrent(metadata.info_hash)
        if active is None:
            params = _load_resume_data(lt, base_params, output_dir, config)
            handle = _add_torrent_with_resume_fallback(
                session, params, base_params, output_dir, metadata
            )
        else:
            handle = active.handle
            bind_log(
                info_hash=metadata.info_hash,
                downloaded_bytes=active.downloaded_bytes,
                complete_piece_count=active.complete_piece_count,
                active_session_count=self._active_torrent_count(),
            ).debug("Reused active torrent session")
        if active is not None and min_complete_piece_count is not None:
            layout = DownloadLayout(
                ranges=[ByteRange(start=0, end=selected_file.length)],
                anchors=layout.anchors,
            )
        _register_active_cache_entry(output_dir)
        _request_dht_peers(lt, session, metadata.info_hash)
        start_time = time.monotonic()
        media_path = _expected_media_path(output_dir, metadata, selected_file)
        requested_piece_indexes: set[int] = set()
        downloaded = 0
        complete_piece_count = 0
        try:
            download_logger = bind_log(
                info_hash=metadata.info_hash,
                selected_file=selected_file.path,
            )
            download_logger.bind(
                ranges=[(item.start, item.end) for item in layout.ranges],
                timeout_seconds=round(timeout_seconds, 2),
                progress_timeout_seconds=round(
                    config.download_progress_timeout_seconds, 2
                ),
                progress_step_bytes=_DOWNLOAD_PROGRESS_STEP_BYTES,
                progress_step_pieces=_DOWNLOAD_PROGRESS_STEP_PIECES,
            ).debug("Starting planned preview range download")
            requested_piece_indexes = self._prioritize_selected_ranges(
                handle, metadata, selected_file, layout, download_logger
            )
            progress_step_bytes = min(
                max(1, layout.total_bytes), _DOWNLOAD_PROGRESS_STEP_BYTES
            )
            last_logged_downloaded = -1
            last_logged_complete_count = -1
            selected_file_complete_logged = False
            last_progress_downloaded = -1
            last_progress_time = start_time
            tracker_alerts: list[str] = []
            dht_alerts: list[str] = []
            last_diagnostics = _cache_diagnostics(
                metadata,
                config,
                cache_entry_exists_before=cache_entry_exists_before,
                resume_data_exists_before=resume_data_exists_before,
                tracker_count=tracker_count,
            )
            while time.monotonic() - start_time < timeout_seconds:
                _collect_relevant_alerts(session, handle, tracker_alerts, dht_alerts)
                now = time.monotonic()
                downloaded = _safe_selected_file_progress(
                    handle, selected_file, media_path
                )
                complete_piece_count = _completed_piece_count(
                    handle, requested_piece_indexes
                )
                pieces_complete = _pieces_complete(handle, requested_piece_indexes)
                useful_byte_progress = (
                    downloaded - last_progress_downloaded >= progress_step_bytes
                )
                if useful_byte_progress:
                    last_progress_time = now
                    last_progress_downloaded = downloaded
                last_diagnostics = _download_diagnostics(
                    metadata=metadata,
                    config=config,
                    cache_entry_exists_before=cache_entry_exists_before,
                    resume_data_exists_before=resume_data_exists_before,
                    handle=handle,
                    complete_piece_count=complete_piece_count,
                    requested_piece_count=len(requested_piece_indexes),
                    planned_pieces_complete=pieces_complete,
                    tracker_count=tracker_count,
                    tracker_alerts=tracker_alerts,
                    dht_alerts=dht_alerts,
                )
                should_log_progress = (
                    last_logged_downloaded < 0
                    or downloaded - last_logged_downloaded >= progress_step_bytes
                    or complete_piece_count - last_logged_complete_count
                    >= _DOWNLOAD_PROGRESS_STEP_PIECES
                    or pieces_complete
                )
                if should_log_progress:
                    download_logger.bind(
                        downloaded_bytes=downloaded,
                        planned_range_bytes=layout.total_bytes,
                        complete_piece_count=complete_piece_count,
                        requested_piece_count=len(requested_piece_indexes),
                        media_path=str(media_path),
                        media_exists=media_path.exists(),
                        **_torrent_status_fields(handle),
                    ).debug("Torrent download progress")
                    last_logged_downloaded = downloaded
                    last_logged_complete_count = complete_piece_count
                reached_decode_checkpoint = (
                    min_complete_piece_count is None
                    or complete_piece_count > min_complete_piece_count
                    or downloaded >= selected_file.length
                )
                if pieces_complete and reached_decode_checkpoint:
                    if not media_path.exists():
                        msg = (
                            f"Planned pieces completed for {selected_file.path}, "
                            f"but expected media path does not exist: {media_path}"
                        )
                        raise TorrentDownloadError(msg)
                    download_logger.bind(
                        downloaded_bytes=downloaded,
                        complete_piece_count=complete_piece_count,
                        requested_piece_count=len(requested_piece_indexes),
                        media_path=str(media_path),
                        complete=downloaded >= selected_file.length,
                        pieces_complete=pieces_complete,
                    ).debug("Finished planned preview range download")
                    return PreviewRangeDownload(
                        media_path=media_path,
                        downloaded_bytes=downloaded,
                        selected_file_complete=downloaded >= selected_file.length,
                        planned_pieces_complete=pieces_complete,
                        diagnostics=last_diagnostics,
                    )
                if pieces_complete and not reached_decode_checkpoint:
                    last_progress_time = now
                if (
                    downloaded >= selected_file.length
                    and not selected_file_complete_logged
                ):
                    download_logger.bind(
                        downloaded_bytes=downloaded,
                        complete_piece_count=complete_piece_count,
                        requested_piece_count=len(requested_piece_indexes),
                    ).debug(
                        "Selected file byte progress complete; waiting for planned piece confirmation"
                    )
                    selected_file_complete_logged = True
                if now - last_progress_time >= config.download_progress_timeout_seconds:
                    download_logger.bind(
                        downloaded_bytes=downloaded,
                        complete_piece_count=complete_piece_count,
                        requested_piece_count=len(requested_piece_indexes),
                        media_path=str(media_path),
                        media_exists=media_path.exists(),
                        tracker_alerts=tracker_alerts[-5:],
                        dht_alerts=dht_alerts[-5:],
                        **_torrent_status_fields(handle),
                    ).debug("Torrent download progress stalled")
                    break
                time.sleep(1.0)
            _collect_relevant_alerts(session, handle, tracker_alerts, dht_alerts)
            downloaded = _safe_selected_file_progress(handle, selected_file, media_path)
            complete_piece_count = _completed_piece_count(
                handle, requested_piece_indexes
            )
            pieces_complete = _pieces_complete(handle, requested_piece_indexes)
            last_diagnostics = _download_diagnostics(
                metadata=metadata,
                config=config,
                cache_entry_exists_before=cache_entry_exists_before,
                resume_data_exists_before=resume_data_exists_before,
                handle=handle,
                complete_piece_count=complete_piece_count,
                requested_piece_count=len(requested_piece_indexes),
                planned_pieces_complete=pieces_complete,
                tracker_count=tracker_count,
                tracker_alerts=tracker_alerts,
                dht_alerts=dht_alerts,
            )
            if downloaded < 1:
                msg = f"No media bytes were downloaded for {selected_file.path}"
                raise TorrentDownloadError(msg, diagnostics=last_diagnostics)
            decode_ready = (
                min_complete_piece_count is None
                or complete_piece_count > min_complete_piece_count
                or downloaded >= selected_file.length
            )
            if not pieces_complete:
                download_logger.bind(
                    downloaded_bytes=downloaded,
                    complete_piece_count=complete_piece_count,
                    requested_piece_count=len(requested_piece_indexes),
                    media_path=str(media_path),
                    media_exists=media_path.exists(),
                    tracker_alerts=tracker_alerts[-5:],
                    dht_alerts=dht_alerts[-5:],
                    **_torrent_status_fields(handle),
                ).debug(
                    "Planned pieces incomplete after timeout; returning available preview range data"
                )
            if not media_path.exists():
                msg = (
                    f"Downloaded media bytes for {selected_file.path}, but expected "
                    f"media path does not exist: {media_path}"
                )
                raise TorrentDownloadError(msg, diagnostics=last_diagnostics)
            download_logger.bind(
                downloaded_bytes=downloaded,
                complete_piece_count=complete_piece_count,
                requested_piece_count=len(requested_piece_indexes),
                media_path=str(media_path),
                complete=downloaded >= selected_file.length,
                pieces_complete=pieces_complete,
                decode_ready=decode_ready,
            ).debug("Finished planned preview range download")
            return PreviewRangeDownload(
                media_path=media_path,
                downloaded_bytes=downloaded,
                selected_file_complete=downloaded >= selected_file.length,
                planned_pieces_complete=pieces_complete,
                diagnostics=last_diagnostics,
                decode_ready=decode_ready,
            )
        finally:
            _save_resume_data(lt, session, handle, output_dir, config)
            _touch_cache_entry(output_dir, config)
            _prune_torrent_cache(config, preserve=output_dir)
            self._retain_active_torrent(
                _ActiveTorrent(
                    info_hash=metadata.info_hash,
                    handle=handle,
                    output_dir=output_dir,
                    media_path=media_path,
                    selected_file=selected_file,
                    requested_piece_indexes=requested_piece_indexes,
                    config=config,
                    downloaded_bytes=downloaded,
                    complete_piece_count=complete_piece_count,
                ),
            )

    def _close_sync(self) -> None:
        for active in self._take_all_active_torrents():
            self._release_torrent(active, reason="shutdown", config=None)

    def _release_active_torrent(
        self, info_hash: str, config: PreviewEngineConfig
    ) -> None:
        active = self._take_active_torrent(info_hash)
        if active is not None:
            self._release_torrent(active, reason="slot_released", config=config)

    def _retain_active_torrent(self, active: _ActiveTorrent) -> None:
        with self._active_torrents_lock:
            self._active_torrents[active.info_hash] = active

    def _release_torrent(
        self,
        active: _ActiveTorrent,
        *,
        reason: str,
        config: PreviewEngineConfig | None,
    ) -> None:
        lt = self._lt
        session = self._session
        if lt is not None and session is not None:
            _save_resume_data(
                lt, session, active.handle, active.output_dir, config or active.config
            )
        if session is not None:
            _remove_torrent(session, active.handle)
        _unregister_active_cache_entry(active.output_dir)
        bind_log(
            info_hash=active.info_hash,
            reason=reason,
            downloaded_bytes=active.downloaded_bytes,
            complete_piece_count=active.complete_piece_count,
            requested_piece_count=len(active.requested_piece_indexes),
            active_session_count=self._active_torrent_count(),
        ).debug("Released torrent session")

    def _get_active_torrent(self, info_hash: str) -> _ActiveTorrent | None:
        with self._active_torrents_lock:
            return self._active_torrents.get(info_hash)

    def _take_active_torrent(self, info_hash: str) -> _ActiveTorrent | None:
        with self._active_torrents_lock:
            return self._active_torrents.pop(info_hash, None)

    def _take_all_active_torrents(self) -> list[_ActiveTorrent]:
        with self._active_torrents_lock:
            items = list(self._active_torrents.values())
            self._active_torrents.clear()
            return items

    def _active_torrent_count(self) -> int:
        with self._active_torrents_lock:
            return len(self._active_torrents)

    def _build_add_torrent_params(
        self,
        lt: Any,
        torrent_bytes: bytes,
        metadata: TorrentMetadata,
        output_dir: Path,
        config: PreviewEngineConfig,
    ) -> Any:
        try:
            torrent_info = lt.torrent_info(lt.bdecode(torrent_bytes))
        except Exception as exc:
            msg = "libtorrent could not parse torrent bytes"
            raise TorrentDownloadError(msg) from exc

        params = lt.add_torrent_params()
        params.ti = torrent_info
        params.save_path = str(output_dir)
        if config.upload_rate_limit is not None:
            params.upload_limit = config.upload_rate_limit
        trackers = _dedupe_trackers(
            (*metadata.trackers, *self._load_default_trackers(config), *config.trackers)
        )
        _set_param_trackers(params, trackers)
        return params

    def _load_default_trackers(self, config: PreviewEngineConfig) -> tuple[str, ...]:
        if not config.use_default_trackers:
            return ()
        now = time.monotonic()
        if (
            self._default_trackers
            and now - self._default_trackers_fetched_at
            < config.default_tracker_ttl_seconds
        ):
            return self._default_trackers
        try:
            trackers = _fetch_tracker_list(
                config.default_tracker_list_url,
                timeout_seconds=config.default_tracker_fetch_timeout_seconds,
            )
        except Exception as exc:
            bind_log(
                tracker_list_url=config.default_tracker_list_url,
                error=str(exc),
            ).debug("Failed to fetch default tracker list")
            return self._default_trackers
        self._default_trackers = trackers
        self._default_trackers_fetched_at = now
        bind_log(
            tracker_list_url=config.default_tracker_list_url,
            tracker_count=len(trackers),
        ).debug("Fetched default tracker list")
        return trackers

    def _prioritize_selected_ranges(
        self,
        handle: Any,
        metadata: TorrentMetadata,
        selected_file: SelectedFile,
        layout: DownloadLayout,
        download_logger: BoundLogger,
    ) -> set[int]:
        try:
            file_count = len(metadata.files)
            priorities = [0 for _ in range(file_count)]
            priorities[selected_file.index] = 7
            handle.prioritize_files(priorities)
        except Exception:
            pass

        if metadata.piece_length < 1:
            return set()
        piece_indexes: set[int] = set()
        for byte_range in layout.ranges:
            global_start = selected_file.offset + byte_range.start
            global_end = selected_file.offset + max(
                byte_range.start, byte_range.end - 1
            )
            piece_start = global_start // metadata.piece_length
            piece_end = global_end // metadata.piece_length
            piece_indexes.update(range(piece_start, piece_end + 1))
        if metadata.piece_count > 0:
            try:
                priorities = [0 for _ in range(metadata.piece_count)]
                for piece_index in piece_indexes:
                    priorities[piece_index] = 7
                handle.prioritize_pieces(priorities)
            except Exception:
                pass
        else:
            for piece_index in piece_indexes:
                try:
                    handle.piece_priority(piece_index, 7)
                except Exception:
                    pass
        ordered_piece_indexes = _ordered_piece_indexes(layout, metadata, selected_file)
        for order, piece_index in enumerate(ordered_piece_indexes):
            try:
                handle.set_piece_deadline(piece_index, order * 250)
            except Exception:
                pass
        download_logger.bind(
            piece_count=len(piece_indexes),
            first_deadline_piece_indexes=ordered_piece_indexes[:12],
            first_piece_indexes=sorted(piece_indexes)[:12],
            last_piece_indexes=sorted(piece_indexes)[-12:],
        ).debug("Prioritized torrent pieces for selected ranges")
        return piece_indexes


def _safe_file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _safe_selected_file_progress(
    handle: Any, selected_file: SelectedFile, path: Path
) -> int:
    try:
        progress = handle.file_progress()
        return int(progress[selected_file.index])
    except Exception:
        return _safe_file_size(path)


def _torrent_status_fields(handle: Any) -> _TorrentStatusFields:
    try:
        status = handle.status()
    except Exception:
        return {
            "download_rate": None,
            "num_peers": None,
            "num_seeds": None,
            "state": None,
        }
    return {
        "download_rate": _optional_int(getattr(status, "download_rate", None)),
        "num_peers": _optional_int(getattr(status, "num_peers", None)),
        "num_seeds": _optional_int(getattr(status, "num_seeds", None)),
        "state": str(getattr(status, "state", "")),
    }


def _set_download_limit(handle: Any, limit: int | None) -> None:
    try:
        handle.set_download_limit(-1 if limit is None else limit)
    except Exception:
        pass


def _remove_torrent(session: Any, handle: Any) -> None:
    try:
        session.remove_torrent(handle)
    except Exception:
        pass


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _fetch_tracker_list(url: str, *, timeout_seconds: float) -> tuple[str, ...]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "torrent-preview"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        content = response.read(256 * 1024)
    return _parse_tracker_list(content.decode("utf-8", errors="replace"))


def _parse_tracker_list(content: str) -> tuple[str, ...]:
    return _dedupe_trackers(
        item.strip()
        for item in content.split()
        if item.startswith(("udp://", "http://", "https://"))
    )


def _dedupe_trackers(trackers: Iterable[object]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for tracker in trackers:
        if not isinstance(tracker, str):
            continue
        tracker = tracker.strip()
        if not tracker or tracker in seen:
            continue
        seen.add(tracker)
        result.append(tracker)
    return tuple(result)


def _tracker_count(params: Any) -> int:
    return len(_param_trackers(params))


def _param_trackers(params: Any) -> tuple[str, ...]:
    try:
        trackers = getattr(params, "trackers")
    except Exception:
        return ()
    try:
        return tuple(str(tracker) for tracker in trackers if str(tracker).strip())
    except Exception:
        return ()


def _set_param_trackers(params: Any, trackers: Iterable[str]) -> None:
    values = list(trackers)
    try:
        params.trackers = values
        return
    except Exception:
        pass
    try:
        params.trackers.extend(values)
        return
    except Exception:
        pass
    for tracker in values:
        try:
            params.trackers.append(tracker)
        except Exception:
            return


def _session_settings() -> dict[str, object]:
    return {
        "enable_dht": True,
        "enable_lsd": True,
        "enable_upnp": True,
        "enable_natpmp": True,
        "listen_interfaces": _listen_interfaces(),
    }


def _bootstrap_dht(session: Any) -> None:
    try:
        session.start_dht()
    except Exception:
        pass
    for host, port in _DHT_BOOTSTRAP_ROUTERS:
        try:
            session.add_dht_router(host, port)
        except Exception:
            continue


def _request_dht_peers(lt: Any, session: Any, info_hash: str) -> None:
    try:
        digest = lt.sha1_hash(bytes.fromhex(info_hash))
    except Exception:
        return
    try:
        session.dht_get_peers(digest)
    except Exception:
        return


def _listen_interfaces(
    interface_root: Path = Path("/sys/class/net"),
    *,
    port: int = _DEFAULT_LISTEN_PORT,
) -> str:
    names = _non_loopback_interface_names(interface_root)
    if names:
        return ",".join(f"{name}:{port}" for name in names)
    return f"0.0.0.0:{port},[::]:{port}"


def _non_loopback_interface_names(interface_root: Path) -> tuple[str, ...]:
    try:
        entries = sorted(interface_root.iterdir(), key=lambda path: path.name)
    except OSError:
        return ()
    names: list[str] = []
    for entry in entries:
        name = entry.name
        if name == "lo":
            continue
        if _interface_is_down(entry):
            continue
        names.append(name)
    return tuple(names)


def _interface_is_down(interface_path: Path) -> bool:
    try:
        return (interface_path / "operstate").read_text(encoding="utf-8").strip() == (
            "down"
        )
    except OSError:
        return False


def _collect_relevant_alerts(
    session: Any, handle: Any, tracker_alerts: list[str], dht_alerts: list[str]
) -> None:
    try:
        alerts = session.pop_alerts()
    except Exception:
        return
    for alert in alerts:
        if not _alert_matches_handle(alert, handle):
            continue
        message = _alert_message(alert)
        category = _alert_category(message)
        if category == "tracker":
            _append_capped_alert(tracker_alerts, message)
            continue
        if category == "dht":
            _append_capped_alert(dht_alerts, message)


def _alert_matches_handle(alert: object, handle: Any) -> bool:
    try:
        alert_handle = getattr(alert, "handle")
    except Exception:
        return True
    if alert_handle is None:
        return True
    try:
        return bool(alert_handle == handle)
    except Exception:
        return True


def _alert_message(alert: object) -> str:
    class_name = alert.__class__.__name__
    text = str(alert).strip()
    if text and text != class_name:
        return f"{class_name}: {text}"[:500]
    return class_name[:500]


def _alert_category(message: str) -> str | None:
    lower = message.lower()
    if "tracker" in lower or "announce" in lower:
        return "tracker"
    if "dht" in lower:
        return "dht"
    return None


def _append_capped_alert(alerts: list[str], message: str) -> None:
    if not message or (alerts and alerts[-1] == message):
        return
    alerts.append(message)
    del alerts[:-_MAX_RELEVANT_ALERTS]


def _download_diagnostics(
    *,
    metadata: TorrentMetadata,
    config: PreviewEngineConfig,
    cache_entry_exists_before: bool,
    resume_data_exists_before: bool,
    handle: Any,
    complete_piece_count: int,
    requested_piece_count: int,
    planned_pieces_complete: bool,
    tracker_count: int | None = None,
    tracker_alerts: list[str] | None = None,
    dht_alerts: list[str] | None = None,
) -> PreviewDiagnostics:
    fields = _torrent_status_fields(handle)
    return _cache_diagnostics(
        metadata,
        config,
        cache_entry_exists_before=cache_entry_exists_before,
        resume_data_exists_before=resume_data_exists_before,
        last_download_rate=fields.get("download_rate"),
        last_num_peers=fields.get("num_peers"),
        last_num_seeds=fields.get("num_seeds"),
        last_torrent_state=fields.get("state"),
        last_complete_piece_count=complete_piece_count,
        last_requested_piece_count=requested_piece_count,
        planned_pieces_complete=planned_pieces_complete,
        tracker_count=tracker_count,
        tracker_alerts=tracker_alerts,
        dht_alerts=dht_alerts,
    )


def _cache_diagnostics(
    metadata: TorrentMetadata,
    config: PreviewEngineConfig,
    *,
    cache_entry_exists_before: bool | None = None,
    resume_data_exists_before: bool | None = None,
    resume_data_saved: bool | None = None,
    last_download_rate: int | None = None,
    last_num_peers: int | None = None,
    last_num_seeds: int | None = None,
    last_torrent_state: str | None = None,
    last_complete_piece_count: int | None = None,
    last_requested_piece_count: int | None = None,
    planned_pieces_complete: bool | None = None,
    tracker_count: int | None = None,
    tracker_alerts: list[str] | None = None,
    dht_alerts: list[str] | None = None,
) -> PreviewDiagnostics:
    cache_entry = config.torrent_cache_dir / metadata.info_hash
    if cache_entry_exists_before is None:
        cache_entry_exists_before = cache_entry.exists()
    if resume_data_exists_before is None:
        resume_data_exists_before = _resume_data_path(cache_entry).exists()
    return PreviewDiagnostics(
        torrent_cache_dir=str(config.torrent_cache_dir),
        torrent_cache_max_mb=config.torrent_cache_max_mb,
        torrent_cache_entry_exists_before=cache_entry_exists_before,
        resume_data_exists_before=resume_data_exists_before,
        resume_data_saved=resume_data_saved,
        last_download_rate=last_download_rate,
        last_num_peers=last_num_peers,
        last_num_seeds=last_num_seeds,
        last_torrent_state=last_torrent_state,
        last_complete_piece_count=last_complete_piece_count,
        last_requested_piece_count=last_requested_piece_count,
        planned_pieces_complete=planned_pieces_complete,
        tracker_count=tracker_count,
        tracker_alerts=list(tracker_alerts or []),
        dht_alerts=list(dht_alerts or []),
    )


def _ordered_piece_indexes(
    layout: DownloadLayout, metadata: TorrentMetadata, selected_file: SelectedFile
) -> list[int]:
    range_piece_groups: list[list[int]] = []
    seen: set[int] = set()
    for byte_range in layout.ranges:
        global_start = selected_file.offset + byte_range.start
        global_end = selected_file.offset + max(byte_range.start, byte_range.end - 1)
        piece_start = global_start // metadata.piece_length
        piece_end = global_end // metadata.piece_length
        group: list[int] = []
        for piece_index in range(piece_start, piece_end + 1):
            if piece_index not in seen:
                group.append(piece_index)
                seen.add(piece_index)
        if byte_range.end >= selected_file.length:
            group.reverse()
        if group:
            range_piece_groups.append(group)

    if len(range_piece_groups) > 2:
        bootstrap_groups = [
            range_piece_groups[0][:_METADATA_BOOTSTRAP_PIECES_PER_EDGE],
            range_piece_groups[-1][:_METADATA_BOOTSTRAP_PIECES_PER_EDGE],
        ]
        bootstrap_seen = {
            piece_index for group in bootstrap_groups for piece_index in group
        }
        remaining_groups = [
            [piece_index for piece_index in group if piece_index not in bootstrap_seen]
            for group in range_piece_groups
        ]
        return _round_robin_piece_groups(bootstrap_groups) + _round_robin_piece_groups(
            remaining_groups
        )
    return _round_robin_piece_groups(range_piece_groups)


def _round_robin_piece_groups(range_piece_groups: list[list[int]]) -> list[int]:
    ordered: list[int] = []
    max_group_size = max((len(group) for group in range_piece_groups), default=0)
    for index in range(max_group_size):
        for group in range_piece_groups:
            if index < len(group):
                ordered.append(group[index])
    return ordered


def _pieces_complete(handle: Any, piece_indexes: set[int]) -> bool:
    if not piece_indexes:
        return False
    return all(_has_piece(handle, piece_index) for piece_index in piece_indexes)


def _completed_piece_count(handle: Any, piece_indexes: set[int]) -> int:
    return sum(1 for piece_index in piece_indexes if _has_piece(handle, piece_index))


def _has_piece(handle: Any, piece_index: int) -> bool:
    try:
        return bool(handle.have_piece(piece_index))
    except Exception:
        pass
    try:
        pieces = handle.status(handle.query_pieces).pieces
        return bool(pieces[piece_index])
    except Exception:
        return False


def _expected_media_path(
    output_dir: Path,
    metadata: TorrentMetadata,
    selected_file: SelectedFile,
) -> Path:
    direct_path = output_dir / selected_file.path
    rooted_path = output_dir / metadata.name / selected_file.path
    if direct_path.exists():
        return direct_path
    if rooted_path.exists():
        return rooted_path
    return rooted_path if len(metadata.files) > 1 else direct_path


def _download_output_dir(
    output_dir: Path, metadata: TorrentMetadata, config: PreviewEngineConfig
) -> Path:
    del output_dir
    return config.torrent_cache_dir / metadata.info_hash


def _touch_cache_entry(path: Path, config: PreviewEngineConfig) -> None:
    del config
    try:
        path.mkdir(parents=True, exist_ok=True)
        now = time.time()
        os.utime(path, (now, now))
    except OSError:
        return


def _register_active_cache_entry(path: Path) -> None:
    resolved = _safe_resolve(path)
    if resolved is None:
        return
    with _ACTIVE_CACHE_ENTRIES_LOCK:
        _ACTIVE_CACHE_ENTRIES.add(resolved)


def _unregister_active_cache_entry(path: Path) -> None:
    with _ACTIVE_CACHE_ENTRIES_LOCK:
        _ACTIVE_CACHE_ENTRIES.discard(_safe_resolve(path))


def _active_cache_entries() -> set[Path]:
    with _ACTIVE_CACHE_ENTRIES_LOCK:
        return set(_ACTIVE_CACHE_ENTRIES)


def _resume_data_path(output_dir: Path) -> Path:
    return output_dir / ".fastresume"


def _load_resume_data(
    lt: Any, params: Any, output_dir: Path, config: PreviewEngineConfig
) -> Any:
    del config
    resume_path = _resume_data_path(output_dir)
    if not resume_path.exists():
        return params
    try:
        resume_params = lt.read_resume_data(resume_path.read_bytes())
    except Exception:
        return params
    _merge_add_torrent_params(params, resume_params)
    return resume_params


def _add_torrent_with_resume_fallback(
    session: Any,
    params: Any,
    base_params: Any,
    output_dir: Path,
    metadata: TorrentMetadata,
) -> Any:
    try:
        return session.add_torrent(params)
    except Exception as exc:
        if params is base_params:
            raise
        resume_path = _resume_data_path(output_dir)
        try:
            resume_path.unlink(missing_ok=True)
        except OSError:
            pass
        bind_log(
            info_hash=metadata.info_hash,
            resume_data_path=str(resume_path),
            error=str(exc),
        ).debug("Discarded unusable torrent resume data")
        return session.add_torrent(base_params)


def _merge_add_torrent_params(source: Any, destination: Any) -> None:
    for attr in ("ti", "save_path", "upload_limit"):
        try:
            setattr(destination, attr, getattr(source, attr))
        except Exception:
            continue
    _set_param_trackers(destination, _param_trackers(source))


def _save_resume_data(
    lt: Any,
    session: Any,
    handle: Any,
    output_dir: Path,
    config: PreviewEngineConfig,
    *,
    timeout_seconds: float = 2.0,
) -> None:
    del config
    write_resume_data_buf = getattr(lt, "write_resume_data_buf", None)
    save_alert_type = getattr(lt, "save_resume_data_alert", None)
    failed_alert_type = getattr(lt, "save_resume_data_failed_alert", None)
    if write_resume_data_buf is None or save_alert_type is None:
        return
    try:
        handle.save_resume_data()
    except Exception:
        return

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            alerts = session.pop_alerts()
        except Exception:
            return
        for alert in alerts:
            if failed_alert_type is not None and isinstance(alert, failed_alert_type):
                return
            if isinstance(alert, save_alert_type):
                try:
                    resume_bytes = write_resume_data_buf(alert.params)
                    _resume_data_path(output_dir).write_bytes(bytes(resume_bytes))
                except (AttributeError, OSError, TypeError):
                    return
                return
        time.sleep(0.1)


def _prune_torrent_cache(
    config: PreviewEngineConfig, *, preserve: Path | None = None
) -> None:
    cache_dir = config.torrent_cache_dir
    try:
        entries = [entry for entry in cache_dir.iterdir() if entry.is_dir()]
    except OSError:
        return

    sized_entries = [
        (_path_disk_usage(entry), _safe_mtime(entry), entry) for entry in entries
    ]
    total_size = sum(size for size, _, _ in sized_entries)
    if total_size <= config.torrent_cache_max_bytes:
        return

    preserved_entries = _active_cache_entries()
    if preserve is not None:
        preserve_resolved = _safe_resolve(preserve)
        if preserve_resolved is not None:
            preserved_entries.add(preserve_resolved)
    for size, _, entry in sorted(sized_entries, key=lambda item: item[1]):
        if _safe_resolve(entry) in preserved_entries:
            continue
        shutil.rmtree(entry, ignore_errors=True)
        total_size -= size
        if total_size <= config.torrent_cache_max_bytes:
            break


def _path_disk_usage(path: Path) -> int:
    total = 0
    try:
        iterator = path.rglob("*")
        for item in iterator:
            try:
                stat = item.stat()
            except OSError:
                continue
            blocks = getattr(stat, "st_blocks", 0)
            total += int(blocks) * 512 if blocks else stat.st_size
    except OSError:
        return 0
    return total


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _safe_resolve(path: Path | None) -> Path | None:
    if path is None:
        return None
    try:
        return path.resolve()
    except OSError:
        return path
