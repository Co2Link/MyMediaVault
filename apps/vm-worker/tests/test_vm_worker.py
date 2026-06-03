from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from loguru import logger
from pydantic import ValidationError

from mymediavault_vm_worker import (
    DhtTorrentMetadataResolver,
    FakeTorrentMetadataResolver,
    PreviewWorkerSettings,
    Torrent,
    TorrentProcessingScheduler,
    _configure_vm_worker_logging,
    _fake_torrent_payload,
    _is_best_effort_preview_complete,
    _is_external_preview_failure,
    _is_permanent_preview_failure,
    _made_useful_progress,
    _success_update,
    parse_torrent,
)
from mymediavault_vm_worker.preview import (
    GeneratedFrame,
    GeneratedSheet,
    PreviewArtifact,
    PreviewDiagnostics,
    PreviewResult,
    SelectedFile,
)

_migration_spec = importlib.util.spec_from_file_location(
    "migrate_processing_queue_v1",
    Path(__file__).parents[1] / "scripts" / "migrate_processing_queue_v1.py",
)
assert _migration_spec is not None and _migration_spec.loader is not None
_migration_module = importlib.util.module_from_spec(_migration_spec)
_migration_spec.loader.exec_module(_migration_module)
_processing_state = _migration_module._processing_state


def _settings(**overrides: object) -> PreviewWorkerSettings:
    return PreviewWorkerSettings(
        mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
        openai_api_key="test-key",
        _env_file=None,
        **overrides,
    )


def _diagnostics(**overrides: object) -> PreviewDiagnostics:
    values = {
        "torrent_cache_dir": ".cache/torrent-preview",
        "torrent_cache_max_mb": 512.0,
        "torrent_cache_entry_exists_before": False,
        "resume_data_exists_before": False,
    }
    values.update(overrides)
    return PreviewDiagnostics(**values)


def _result(*, status: str, reason: str, warnings: list[str] | None = None) -> PreviewResult:
    return PreviewResult(
        info_hash="abc",
        status=status,  # type: ignore[arg-type]
        status_reason=reason,
        artifact=PreviewArtifact(frames=[], sheet=None),
        diagnostics=_diagnostics(warnings=warnings or []),
    )


def test_settings_require_openai_api_key_for_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        PreviewWorkerSettings(mongodb_uri="mongodb://localhost/mymediavault", _env_file=None)


def test_settings_expose_single_scheduler_tuning() -> None:
    settings = _settings()
    assert settings.preview_worker_max_concurrency == 20
    assert settings.preview_session_fairness_seconds == 7200
    assert settings.preview_failure_limit == 3
    assert settings.preview_external_failure_cooldown_seconds == 300
    assert settings.preview_cache_dir == Path("/var/cache/mymediavault/vm-worker")


def test_fake_metadata_resolver_returns_valid_torrent_payload() -> None:
    metadata = asyncio.run(FakeTorrentMetadataResolver().fetch("abcdef0123456789abcdef0123456789abcdef01"))
    assert metadata["name"] == "Fake Torrent abcdef01"
    assert metadata["sizeBytes"] == 1048576


def test_dht_metadata_resolver_uses_supported_libtorrent_params(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeHandle:
        @staticmethod
        def has_metadata() -> bool:
            return True

        @staticmethod
        def torrent_file() -> object:
            return object()

    class FakeSession:
        def __init__(self) -> None:
            self.params: dict[str, object] | None = None

        def add_torrent(self, params: dict[str, object]) -> FakeHandle:
            self.params = params
            return FakeHandle()

        @staticmethod
        def remove_torrent(handle: FakeHandle) -> None:
            del handle

        @staticmethod
        def pop_alerts() -> list[object]:
            return []

    session = FakeSession()
    raw = _fake_torrent_payload("DHT Torrent")
    monkeypatch.setitem(
        sys.modules,
        "libtorrent",
        SimpleNamespace(
            session=lambda settings: session,
            create_torrent=lambda torrent_info: SimpleNamespace(generate=lambda: object()),
            bencode=lambda generated: raw,
        ),
    )
    metadata = DhtTorrentMetadataResolver(timeout_seconds=10)._fetch_sync("abcdef0123456789abcdef0123456789abcdef01")
    assert metadata["name"] == "DHT Torrent"
    assert session.params is not None
    assert "paused" not in session.params


def test_parse_torrent_reads_single_file_payload() -> None:
    raw = b"d4:infod6:lengthi123e4:name9:movie.mkv6:pieces0:ee"
    metadata = parse_torrent(raw)
    assert metadata["files"] == [{"path": "movie.mkv", "sizeBytes": 123, "position": 0}]


def test_processing_queue_migration_is_idempotent() -> None:
    assert _processing_state({"processingState": "complete", "previewFrames": []}) == "complete"
    assert _processing_state({"processingState": "running"}) == "queued"


def test_scheduler_claims_available_fifo_work(monkeypatch: pytest.MonkeyPatch) -> None:
    class Collection:
        query: dict[str, object] | None = None
        update: dict[str, object] | None = None

        async def find_one_and_update(self, query: dict[str, object], update: dict[str, object], **kwargs: object) -> None:
            self.query = query
            self.update = update
            assert kwargs["sort"] == [("processingQueuedAt", 1), ("_id", 1)]
            return None

    collection = Collection()
    monkeypatch.setattr(Torrent, "get_pymongo_collection", lambda: collection)
    scheduler = TorrentProcessingScheduler(settings=_settings(), blob_store=object(), engine=object())  # type: ignore[arg-type]
    assert asyncio.run(scheduler._claim_one()) is None
    assert collection.query is not None
    assert collection.query["processingState"] == {"$in": ["queued", "partial"]}
    assert {"processingAvailableAt": {"$exists": False}} in collection.query["$or"]  # type: ignore[operator]


def test_scheduler_requeues_external_failure_with_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    class Collection:
        update: dict[str, object] | None = None

        async def update_one(self, query: dict[str, object], update: dict[str, object]) -> None:
            assert query == {"_id": "torrent-1", "processingState": "running"}
            self.update = update

    collection = Collection()
    monkeypatch.setattr(Torrent, "get_pymongo_collection", lambda: collection)
    scheduler = TorrentProcessingScheduler(settings=_settings(), blob_store=object(), engine=object())  # type: ignore[arg-type]
    torrent = SimpleNamespace(id="torrent-1", infoHash="abc", processingFailureCount=0)
    asyncio.run(scheduler._fail_or_requeue(torrent, "quota"))
    values = collection.update["$set"]  # type: ignore[index]
    assert values["processingState"] == "queued"
    assert values["processingFailureCount"] == 1
    assert isinstance(values["processingAvailableAt"], datetime)


def test_scheduler_requeues_metadata_failure_with_metadata_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    class Collection:
        update: dict[str, object] | None = None

        async def update_one(self, query: dict[str, object], update: dict[str, object]) -> None:
            assert query == {"_id": "torrent-1", "processingState": "running"}
            self.update = update

    collection = Collection()
    monkeypatch.setattr(Torrent, "get_pymongo_collection", lambda: collection)
    scheduler = TorrentProcessingScheduler(settings=_settings(), blob_store=object(), engine=object())  # type: ignore[arg-type]
    torrent = SimpleNamespace(id="torrent-1", infoHash="abc", processingFailureCount=0)
    asyncio.run(scheduler._fail_or_requeue(torrent, "metadata unavailable", outcome="metadata_unavailable"))
    values = collection.update["$set"]  # type: ignore[index]
    assert values["processingState"] == "queued"
    assert values["processingLastOutcome"] == "metadata_unavailable"
    assert values["processingFailureCount"] == 1
    assert isinstance(values["processingAvailableAt"], datetime)


def test_failure_classification_keeps_sparse_downloads_eligible() -> None:
    assert not _is_external_preview_failure(_result(status="failed", reason="No media bytes were downloaded"))
    assert _is_external_preview_failure(
        _result(status="failed", reason="quota", warnings=["Preview decode/ranking failed: quota"])
    )
    assert _is_permanent_preview_failure(_result(status="failed", reason="No video file was found"))


def test_useful_progress_tracks_bytes_and_completed_pieces() -> None:
    no_progress = _result(status="failed", reason="No media bytes were downloaded")
    assert not _made_useful_progress(no_progress, last_downloaded_bytes=0, last_complete_piece_count=0)

    byte_progress = _result(status="failed", reason="No accepted frames")
    object.__setattr__(byte_progress.diagnostics, "downloaded_bytes", 1)
    assert _made_useful_progress(byte_progress, last_downloaded_bytes=0, last_complete_piece_count=0)

    piece_progress = _result(status="failed", reason="No accepted frames")
    object.__setattr__(piece_progress.diagnostics, "last_complete_piece_count", 1)
    assert _made_useful_progress(piece_progress, last_downloaded_bytes=0, last_complete_piece_count=0)


def test_best_effort_preview_completes_once_selected_file_is_fully_downloaded() -> None:
    selected_file = SelectedFile(index=0, path="movie.mkv", length=123)
    result = PreviewResult(
        info_hash="abc",
        status="partial",
        status_reason="Only 1 frame",
        artifact=PreviewArtifact(
            frames=[GeneratedFrame(path=Path("frame.jpg"), width=10, height=10, timestamp_seconds=1)],
            sheet=GeneratedSheet(path=Path("sheet.jpg"), width=10, height=10),
        ),
        diagnostics=_diagnostics(selected_file=selected_file, downloaded_bytes=123),
    )
    assert _is_best_effort_preview_complete(result)
    assert not _is_best_effort_preview_complete(
        PreviewResult(
            info_hash="abc",
            status="partial",
            status_reason="Only 1 frame",
            artifact=result.artifact,
            diagnostics=_diagnostics(selected_file=selected_file, downloaded_bytes=122),
        )
    )


def test_success_update_preserves_partial_artifacts_for_scheduler() -> None:
    result = PreviewResult(
        info_hash="abc",
        status="partial",
        status_reason="Only 1 frame",
        artifact=PreviewArtifact(
            frames=[GeneratedFrame(path=Path("frame.jpg"), width=10, height=10, timestamp_seconds=1)],
            sheet=GeneratedSheet(path=Path("sheet.jpg"), width=10, height=10),
        ),
        diagnostics=_diagnostics(selected_file=SelectedFile(index=0, path="movie.mkv", length=123)),
    )
    update = _success_update(
        result,
        stored_frames=[{"key": "previews/abc/frame_001.jpg", "width": 10, "height": 10, "timestampSeconds": 1}],
        stored_sheet=None,
        artifact_version="preview-v9",
        artifact_fingerprint="sha256:test",
    )["$set"]
    assert update["processingState"] == "running"
    assert update["previewFrames"][0]["key"] == "previews/abc/frame_001.jpg"
    assert update["actorAnalysisStatus"] == "pending"


def test_vm_worker_logging_keeps_console_info_and_json_debug_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    debug_log_path = tmp_path / "debug.log"
    settings = _settings(vm_worker_debug_log_path=debug_log_path)
    _configure_vm_worker_logging(settings)
    try:
        logger.bind(openai_api_key="sk-proj-secret123456789").debug("debug message with sk-proj-secret123456789")
        logger.info("visible info")
    finally:
        logger.remove()
    assert "visible info" in capsys.readouterr().out
    records = [json.loads(line)["record"] for line in debug_log_path.read_text().splitlines()]
    record = next(item for item in records if item["message"].startswith("debug message"))
    assert record["message"] == "debug message with sk-[redacted]"
