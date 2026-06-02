from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest

from mymediavault_vm_worker.preview.core.models import (
    BYTES_PER_MB,
    PreviewEngineConfig,
    SelectedFile,
    _default_torrent_cache_dir,
)
from mymediavault_vm_worker.preview.torrent.client import (
    LibtorrentTorrentClient,
    _ActiveTorrent,
    _add_torrent_with_resume_fallback,
    _bootstrap_dht,
    _collect_relevant_alerts,
    _cache_diagnostics,
    _download_output_dir,
    _load_resume_data,
    _listen_interfaces,
    _request_dht_peers,
    _register_active_cache_entry,
    _session_settings,
    _set_param_trackers,
    _path_disk_usage,
    _prune_torrent_cache,
    _resume_data_path,
    _unregister_active_cache_entry,
)
from mymediavault_vm_worker.preview.torrent.metadata import TorrentMetadata


def test_download_output_dir_uses_info_hash_cache_entry(tmp_path) -> None:
    metadata = TorrentMetadata(
        info_hash="abc123",
        name="sample",
        files=[],
        piece_length=16_384,
        piece_count=1,
        total_size=0,
    )
    config = PreviewEngineConfig(torrent_cache_dir=tmp_path / "cache")

    assert _download_output_dir(tmp_path / "workspace", metadata, config) == (
        tmp_path / "cache" / "abc123"
    )


def test_download_output_dir_uses_default_temp_cache(tmp_path) -> None:
    metadata = TorrentMetadata(
        info_hash="abc123",
        name="sample",
        files=[],
        piece_length=16_384,
        piece_count=1,
        total_size=0,
    )
    config = PreviewEngineConfig()

    assert config.torrent_cache_dir == _default_torrent_cache_dir()
    assert _download_output_dir(tmp_path / "workspace", metadata, config) == (
        _default_torrent_cache_dir() / "abc123"
    )


def test_engine_config_rejects_disabled_cache() -> None:
    kwargs: dict[str, Any] = {"torrent_cache_dir": None}

    with pytest.raises(ValueError, match="torrent_cache_dir"):
        PreviewEngineConfig(**kwargs)


def test_prune_torrent_cache_removes_oldest_entries_first(tmp_path) -> None:
    cache_dir = tmp_path / "cache"
    old_entry = cache_dir / "old"
    new_entry = cache_dir / "new"
    old_entry.mkdir(parents=True)
    new_entry.mkdir(parents=True)
    (old_entry / "media.bin").write_bytes(b"0" * 4096)
    (new_entry / "media.bin").write_bytes(b"1" * 4096)
    old_time = time.time() - 60
    new_time = time.time()
    os.utime(old_entry, (old_time, old_time))
    os.utime(new_entry, (new_time, new_time))
    config = PreviewEngineConfig(
        torrent_cache_dir=cache_dir,
        torrent_cache_max_mb=max(1, _path_disk_usage(new_entry)) / BYTES_PER_MB,
    )

    _prune_torrent_cache(config)

    assert not old_entry.exists()
    assert new_entry.exists()


def test_prune_torrent_cache_preserves_active_entry(tmp_path) -> None:
    cache_dir = tmp_path / "cache"
    active_entry = cache_dir / "active"
    old_entry = cache_dir / "old"
    active_entry.mkdir(parents=True)
    old_entry.mkdir(parents=True)
    (active_entry / "media.bin").write_bytes(b"0" * 4096)
    (old_entry / "media.bin").write_bytes(b"1" * 4096)
    active_time = time.time() - 120
    old_time = time.time() - 60
    os.utime(active_entry, (active_time, active_time))
    os.utime(old_entry, (old_time, old_time))
    config = PreviewEngineConfig(
        torrent_cache_dir=cache_dir,
        torrent_cache_max_mb=max(1, _path_disk_usage(active_entry)) / BYTES_PER_MB,
    )

    _prune_torrent_cache(config, preserve=active_entry)

    assert active_entry.exists()
    assert not old_entry.exists()


def test_prune_torrent_cache_preserves_all_registered_active_entries(tmp_path) -> None:
    cache_dir = tmp_path / "cache"
    first_active_entry = cache_dir / "first-active"
    second_active_entry = cache_dir / "second-active"
    old_entry = cache_dir / "old"
    first_active_entry.mkdir(parents=True)
    second_active_entry.mkdir(parents=True)
    old_entry.mkdir(parents=True)
    (first_active_entry / "media.bin").write_bytes(b"0" * 4096)
    (second_active_entry / "media.bin").write_bytes(b"1" * 4096)
    (old_entry / "media.bin").write_bytes(b"2" * 4096)
    config = PreviewEngineConfig(
        torrent_cache_dir=cache_dir,
        torrent_cache_max_mb=max(1, _path_disk_usage(first_active_entry))
        * 2
        / BYTES_PER_MB,
    )

    _register_active_cache_entry(first_active_entry)
    _register_active_cache_entry(second_active_entry)
    try:
        _prune_torrent_cache(config)
    finally:
        _unregister_active_cache_entry(first_active_entry)
        _unregister_active_cache_entry(second_active_entry)

    assert first_active_entry.exists()
    assert second_active_entry.exists()
    assert not old_entry.exists()


def test_load_resume_data_from_cache_entry(tmp_path) -> None:
    class Params:
        ti = "torrent-info"
        save_path = "save-path"
        upload_limit = 123

        def __init__(self) -> None:
            self.trackers: list[str] = []

    class Lt:
        @staticmethod
        def read_resume_data(data: bytes) -> Params:
            assert data == b"resume"
            return Params()

    cache_entry = tmp_path / "cache" / "abc123"
    cache_entry.mkdir(parents=True)
    _resume_data_path(cache_entry).write_bytes(b"resume")
    params = Params()
    params.trackers.append("tracker")
    config = PreviewEngineConfig(torrent_cache_dir=tmp_path / "cache")

    loaded = _load_resume_data(Lt(), params, cache_entry, config)

    assert loaded is not params
    assert loaded.ti == "torrent-info"
    assert loaded.save_path == "save-path"
    assert loaded.upload_limit == 123
    assert loaded.trackers == ["tracker"]


def test_set_param_trackers_handles_copy_returning_tracker_lists() -> None:
    class Params:
        def __init__(self) -> None:
            self._trackers: list[str] = []

        @property
        def trackers(self) -> list[str]:
            return list(self._trackers)

        @trackers.setter
        def trackers(self, value: list[str]) -> None:
            self._trackers = value

    params = Params()

    _set_param_trackers(params, ("udp://tracker.example/announce",))

    assert params.trackers == ["udp://tracker.example/announce"]


def test_add_torrent_discards_bad_resume_data_and_retries_base_params(tmp_path) -> None:
    class Session:
        def __init__(self) -> None:
            self.added: list[object] = []

        def add_torrent(self, params: object) -> str:
            self.added.append(params)
            if params == "resume":
                msg = "mismatching info-hash [libtorrent:30]"
                raise RuntimeError(msg)
            return "handle"

    metadata = TorrentMetadata(
        info_hash="abc123",
        name="sample",
        files=[],
        piece_length=16_384,
        piece_count=1,
        total_size=0,
    )
    cache_entry = tmp_path / "cache" / "abc123"
    cache_entry.mkdir(parents=True)
    resume_path = _resume_data_path(cache_entry)
    resume_path.write_bytes(b"stale")
    session = Session()

    handle = _add_torrent_with_resume_fallback(
        session,
        "resume",
        "base",
        cache_entry,
        metadata,
    )

    assert handle == "handle"
    assert session.added == ["resume", "base"]
    assert not resume_path.exists()


def test_cache_diagnostics_describes_configured_cache(tmp_path) -> None:
    metadata = TorrentMetadata(
        info_hash="abc123",
        name="sample",
        files=[],
        piece_length=16_384,
        piece_count=1,
        total_size=0,
    )
    config = PreviewEngineConfig(torrent_cache_dir=tmp_path / "cache")

    diagnostics = _cache_diagnostics(metadata, config)

    assert diagnostics.torrent_cache_dir == str(tmp_path / "cache")
    assert diagnostics.torrent_cache_max_mb == 32768
    assert diagnostics.torrent_cache_entry_exists_before is False
    assert diagnostics.resume_data_exists_before is False


def test_collect_relevant_alerts_keeps_tracker_and_dht_messages() -> None:
    class TrackerAlert:
        def __str__(self) -> str:
            return "tracker.example announce timed out"

    class DhtAlert:
        def __str__(self) -> str:
            return "DHT bootstrap complete"

    class OtherAlert:
        def __str__(self) -> str:
            return "piece finished"

    class Session:
        @staticmethod
        def pop_alerts() -> list[object]:
            return [TrackerAlert(), DhtAlert(), OtherAlert()]

    tracker_alerts: list[str] = []
    dht_alerts: list[str] = []

    _collect_relevant_alerts(Session(), object(), tracker_alerts, dht_alerts)

    assert tracker_alerts == ["TrackerAlert: tracker.example announce timed out"]
    assert dht_alerts == ["DhtAlert: DHT bootstrap complete"]


def test_collect_relevant_alerts_caps_repeated_diagnostics() -> None:
    class TrackerAlert:
        def __init__(self, index: int) -> None:
            self.index = index

        def __str__(self) -> str:
            return f"tracker announce failed {self.index}"

    class Session:
        @staticmethod
        def pop_alerts() -> list[object]:
            return [TrackerAlert(index) for index in range(25)]

    tracker_alerts: list[str] = []

    _collect_relevant_alerts(Session(), object(), tracker_alerts, [])

    assert len(tracker_alerts) == 20
    assert tracker_alerts[0] == "TrackerAlert: tracker announce failed 5"
    assert tracker_alerts[-1] == "TrackerAlert: tracker announce failed 24"


def test_collect_relevant_alerts_ignores_other_torrent_handles() -> None:
    matching_handle = object()
    other_handle = object()

    class MatchingTrackerAlert:
        handle = matching_handle

        def __str__(self) -> str:
            return "matching tracker announce failed"

    class OtherTrackerAlert:
        handle = other_handle

        def __str__(self) -> str:
            return "other tracker announce failed"

    class Session:
        @staticmethod
        def pop_alerts() -> list[object]:
            return [OtherTrackerAlert(), MatchingTrackerAlert()]

    tracker_alerts: list[str] = []

    _collect_relevant_alerts(Session(), matching_handle, tracker_alerts, [])

    assert tracker_alerts == ["MatchingTrackerAlert: matching tracker announce failed"]


def test_session_settings_listens_on_non_loopback_interfaces() -> None:
    assert "listen_interfaces" in _session_settings()


def test_listen_interfaces_prefers_non_loopback_device_names(tmp_path) -> None:
    _write_interface(tmp_path, "lo", "unknown")
    _write_interface(tmp_path, "eth0", "up")
    _write_interface(tmp_path, "docker0", "down")

    assert _listen_interfaces(tmp_path) == "eth0:6881"


def test_listen_interfaces_falls_back_to_wildcards_without_devices(tmp_path) -> None:
    _write_interface(tmp_path, "lo", "unknown")

    assert _listen_interfaces(tmp_path) == "0.0.0.0:6881,[::]:6881"


def test_bootstrap_dht_starts_session_and_adds_routers() -> None:
    class Session:
        def __init__(self) -> None:
            self.started = False
            self.routers: list[tuple[str, int]] = []

        def start_dht(self) -> None:
            self.started = True

        def add_dht_router(self, host: str, port: int) -> None:
            self.routers.append((host, port))

    session = Session()

    _bootstrap_dht(session)

    assert session.started is True
    assert ("router.bittorrent.com", 6881) in session.routers
    assert ("dht.transmissionbt.com", 6881) in session.routers


def test_request_dht_peers_uses_info_hash_digest() -> None:
    class LT:
        @staticmethod
        def sha1_hash(value: bytes) -> bytes:
            return value

    class Session:
        def __init__(self) -> None:
            self.digest: bytes | None = None

        def dht_get_peers(self, digest: bytes) -> None:
            self.digest = digest

    session = Session()

    _request_dht_peers(
        LT(),
        session,
        "f73f3045b59b32fdb5905a7233619c6fd9617cd3",
    )

    assert session.digest == bytes.fromhex("f73f3045b59b32fdb5905a7233619c6fd9617cd3")


def test_active_torrent_is_released_when_scheduler_yields_slot(tmp_path) -> None:
    class Handle:
        def __init__(self) -> None:
            self.downloaded = 0

    class Session:
        def __init__(self) -> None:
            self.removed: list[object] = []

        def remove_torrent(self, handle: object) -> None:
            self.removed.append(handle)

    handle = Handle()
    session = Session()
    client = LibtorrentTorrentClient()
    client._session = session
    config = PreviewEngineConfig(torrent_cache_dir=tmp_path / "cache")
    output_dir = config.torrent_cache_dir / "abc123"
    output_dir.mkdir(parents=True)
    active = _ActiveTorrent(
        info_hash="abc123",
        handle=handle,
        output_dir=output_dir,
        media_path=output_dir / "movie.mp4",
        selected_file=SelectedFile(index=0, path="movie.mp4", length=100),
        requested_piece_indexes={0},
        config=config,
        downloaded_bytes=0,
        complete_piece_count=0,
    )

    client._retain_active_torrent(active)
    client._release_active_torrent("abc123", config)

    assert session.removed == [handle]


def _write_interface(root: Path, name: str, operstate: str) -> None:
    path = root / name
    path.mkdir()
    (path / "operstate").write_text(operstate, encoding="utf-8")
