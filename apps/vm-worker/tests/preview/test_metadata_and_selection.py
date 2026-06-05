from __future__ import annotations

from dataclasses import fields

import pytest

from mymediavault_vm_worker.preview import (
    PREVIEW_ARTIFACT_VERSION,
    PreviewEngineConfig,
    PreviewRequest,
)
from mymediavault_vm_worker.preview.core.models import _default_torrent_cache_dir
from mymediavault_vm_worker.preview.core.exceptions import NoVideoFileError
from mymediavault_vm_worker.preview.selection.media import select_largest_video_file
from mymediavault_vm_worker.preview.torrent.metadata import parse_torrent_metadata

from .conftest import bencode, torrent_bytes


def test_preview_request_only_requires_torrent_bytes() -> None:
    assert [field.name for field in fields(PreviewRequest)] == ["torrent_bytes"]
    with pytest.raises(ValueError, match="torrent_bytes"):
        PreviewRequest(torrent_bytes=b"")


def test_engine_config_defaults_match_sheet_preview_acceptance() -> None:
    config = PreviewEngineConfig()

    assert config.max_concurrent_downloads == 10
    assert config.max_concurrent_decodes == 2
    assert config.anchor_range_mb == 32
    assert config.anchor_range_bytes == 32 * 1024 * 1024
    assert config.anchor_retry_range_mb == (64.0, 128.0, 256.0, 384.0, 512.0, 768.0)
    assert config.edge_range_mb == 32
    assert config.edge_range_bytes == 32 * 1024 * 1024
    assert config.max_time_seconds == 3600.0
    assert config.max_download_time_seconds == 1800.0
    assert config.download_progress_timeout_seconds == 300.0
    assert config.max_decode_time_seconds == 90.0
    assert config.torrent_cache_dir == _default_torrent_cache_dir()
    assert config.torrent_cache_max_mb == 32768
    assert config.torrent_cache_max_bytes == 32 * 1024 * 1024 * 1024
    assert config.use_default_trackers is True
    assert config.default_tracker_fetch_timeout_seconds == 3.0
    assert config.target_frames == 9
    assert config.extract_frames_per_anchor == 7
    assert config.min_selector_candidates_per_anchor == 2
    assert config.max_selector_candidates_per_anchor == 4
    assert config.anchor_window_seconds == 30.0
    assert config.artifact_fingerprint().startswith("sha256:")


def test_engine_config_artifact_fingerprint_tracks_preview_recipe() -> None:
    config = PreviewEngineConfig(target_frames=9)
    changed = PreviewEngineConfig(target_frames=3)

    assert config.artifact_recipe()["artifact_version"] == PREVIEW_ARTIFACT_VERSION
    assert (
        config.artifact_fingerprint()
        == PreviewEngineConfig(target_frames=9).artifact_fingerprint()
    )
    assert config.artifact_fingerprint() != changed.artifact_fingerprint()


def test_engine_config_restricts_target_frames() -> None:
    with pytest.raises(ValueError, match="target_frames"):
        PreviewEngineConfig(target_frames=5)


def test_engine_config_validates_selector_candidate_thresholds() -> None:
    with pytest.raises(ValueError, match="min_selector_candidates_per_anchor"):
        PreviewEngineConfig(
            min_selector_candidates_per_anchor=5,
            max_selector_candidates_per_anchor=4,
        )
    with pytest.raises(ValueError, match="max_selector_candidates_per_anchor"):
        PreviewEngineConfig(
            extract_frames_per_anchor=3,
            max_selector_candidates_per_anchor=4,
        )


def test_engine_config_rejects_non_widening_anchor_retry_ranges() -> None:
    with pytest.raises(ValueError, match="anchor_retry_range_mb"):
        PreviewEngineConfig(anchor_retry_range_mb=(16.0,))
    with pytest.raises(ValueError, match="anchor_retry_range_mb"):
        PreviewEngineConfig(anchor_retry_range_mb=(64.0, 64.0))


def test_parse_torrent_metadata_derives_info_hash_and_files() -> None:
    raw = torrent_bytes(
        [
            ("extras/readme.txt", 100),
            ("video/small.mp4", 1_000),
            ("video/big.mkv", 5_000),
        ]
    )

    metadata = parse_torrent_metadata(raw)

    assert len(metadata.info_hash) == 40
    assert metadata.name == "sample"
    assert metadata.total_size == 6_100
    assert metadata.piece_count == 1
    assert [file.offset for file in metadata.files] == [0, 100, 1_100]
    assert metadata.trackers == ("https://tracker.invalid/announce",)


def test_parse_torrent_metadata_collects_announce_list_trackers() -> None:
    raw = bencode(
        {
            b"announce": b"https://tracker.example/announce",
            b"announce-list": [
                [b"https://tracker.example/announce"],
                [b"udp://tracker.example:6969/announce"],
            ],
            b"info": {
                b"name": b"movie.mp4",
                b"length": 1_000,
                b"piece length": 16_384,
                b"pieces": b"0" * 20,
            },
        }
    )

    metadata = parse_torrent_metadata(raw)

    assert metadata.trackers == (
        "https://tracker.example/announce",
        "udp://tracker.example:6969/announce",
    )


def test_select_largest_video_file_ignores_non_video_files() -> None:
    metadata = parse_torrent_metadata(
        torrent_bytes(
            [
                ("movie/sample.txt", 99_999),
                ("movie/trailer.mp4", 1_000),
                ("movie/main.mkv", 5_000),
            ]
        )
    )

    selected = select_largest_video_file(metadata.files)

    assert selected.path == "movie/main.mkv"
    assert selected.length == 5_000


def test_select_largest_video_file_prefers_torrent_name_match_over_unrelated_size() -> (
    None
):
    metadata = parse_torrent_metadata(
        torrent_bytes(
            [
                ("fc2-ppv-4363353-main.mp4", 4_000),
                ("fc2-ppv-881581-bundled.mp4", 5_000),
            ]
        )
    )

    selected = select_largest_video_file(
        metadata.files, torrent_name="fc2-ppv-4363353-HD"
    )

    assert selected.path == "fc2-ppv-4363353-main.mp4"


def test_select_largest_video_file_errors_for_audio_or_text_only() -> None:
    metadata = parse_torrent_metadata(torrent_bytes([("sample/readme.txt", 1_000)]))

    with pytest.raises(NoVideoFileError, match="No supported video"):
        select_largest_video_file(metadata.files)


def test_parse_torrent_metadata_sanitizes_relative_paths() -> None:
    metadata = parse_torrent_metadata(torrent_bytes([("../unsafe/./movie.mp4", 1_000)]))

    assert metadata.files[0].path == "unsafe/movie.mp4"
