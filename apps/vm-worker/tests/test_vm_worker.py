from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from loguru import logger
from pydantic import ValidationError
from torrent_preview import (
    AnchorRetryAttemptDiagnostics,
    AnchorRetryDiagnostics,
    GeneratedFrame,
    GeneratedSheet,
    PreviewArtifact,
    PreviewDiagnostics,
    PreviewResult,
    SelectedFile,
)

from mymediavault_vm_worker import (
    DhtTorrentMetadataResolver,
    FakeTorrentMetadataResolver,
    MetadataWorker,
    MongoPreviewJobLease,
    MongoPreviewJobSource,
    PreviewWorkerSettings,
    Torrent,
    _configure_vm_worker_logging,
    _fake_torrent_payload,
    _preview_next_attempt_at,
    _success_update,
    parse_torrent,
)


def _preview_diagnostics(**overrides: object) -> PreviewDiagnostics:
    values = {
        "torrent_cache_dir": ".cache/torrent-preview",
        "torrent_cache_max_mb": 512.0,
        "torrent_cache_entry_exists_before": False,
        "resume_data_exists_before": False,
    }
    values.update(overrides)
    return PreviewDiagnostics(**values)


def test_settings_require_openai_api_key_for_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        PreviewWorkerSettings(
            mongodb_uri="mongodb://127.0.0.1:27017/mymediavault", _env_file=None
        )


def test_settings_reject_blank_openai_api_key() -> None:
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        PreviewWorkerSettings(
            mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
            openai_api_key=" ",
            _env_file=None,
        )


def test_settings_allow_metadata_only_without_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = PreviewWorkerSettings(
        mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
        preview_worker_enabled=False,
        _env_file=None,
    )

    assert settings.metadata_worker_enabled is True
    assert settings.preview_worker_enabled is False
    assert settings.metadata_worker_max_concurrency == 10
    assert settings.metadata_dht_timeout_seconds == 600


def test_fake_metadata_resolver_returns_valid_torrent_payload() -> None:
    metadata = asyncio.run(
        FakeTorrentMetadataResolver().fetch("abcdef0123456789abcdef0123456789abcdef01")
    )

    assert metadata["name"] == "Fake Torrent abcdef01"
    assert metadata["sizeBytes"] == 1048576
    assert metadata["files"] == [
        {"path": "Fake Torrent abcdef01", "sizeBytes": 1048576, "position": 0}
    ]
    assert metadata["resolverDiagnostics"] == [{"url": "fake", "kind": "success"}]


def test_dht_metadata_resolver_uses_supported_libtorrent_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
            create_torrent=lambda torrent_info: SimpleNamespace(
                generate=lambda: object()
            ),
            bencode=lambda generated: raw,
        ),
    )

    metadata = DhtTorrentMetadataResolver(timeout_seconds=10)._fetch_sync(
        "abcdef0123456789abcdef0123456789abcdef01"
    )

    assert metadata["name"] == "DHT Torrent"
    assert session.params is not None
    assert session.params["save_path"]
    assert "paused" not in session.params
    assert "upload_mode" not in session.params


def test_metadata_worker_repairs_expired_processing_leases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCollection:
        def __init__(self) -> None:
            self.query: dict[str, object] | None = None
            self.update: dict[str, object] | None = None

        async def update_many(
            self, query: dict[str, object], update: dict[str, object]
        ) -> SimpleNamespace:
            self.query = query
            self.update = update
            return SimpleNamespace(modified_count=1)

    collection = FakeCollection()
    monkeypatch.setattr(Torrent, "get_pymongo_collection", lambda: collection)
    worker = MetadataWorker(
        settings=PreviewWorkerSettings(
            mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
            preview_worker_enabled=False,
            _env_file=None,
        ),
        blob_store=object(),
    )

    asyncio.run(worker._repair_stale_processing())

    assert collection.query is not None
    assert collection.query["metadataStatus"] == "processing"
    assert isinstance(collection.query["$or"], list)
    assert {"metadataLeaseUntil": None} in collection.query["$or"]
    assert {"metadataLeaseUntil": {"$exists": False}} in collection.query["$or"]
    assert any(
        isinstance(item.get("metadataLeaseUntil"), dict)
        and isinstance(item["metadataLeaseUntil"].get("$lt"), datetime)
        for item in collection.query["$or"]
    )
    assert collection.update == {
        "$set": {
            "metadataStatus": "pending",
            "metadataError": "Metadata processing lease expired and was requeued.",
            "metadataNextAttemptAt": None,
            "metadataLeaseUntil": None,
        }
    }


def test_metadata_worker_claims_only_pending_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCollection:
        def __init__(self) -> None:
            self.query: dict[str, object] | None = None

        async def find_one_and_update(
            self, query: dict[str, object], *args: object, **kwargs: object
        ) -> None:
            self.query = query

    collection = FakeCollection()
    monkeypatch.setattr(Torrent, "get_pymongo_collection", lambda: collection)
    worker = MetadataWorker(
        settings=PreviewWorkerSettings(
            mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
            preview_worker_enabled=False,
            _env_file=None,
        ),
        blob_store=object(),
    )

    assert asyncio.run(worker._claim_one()) is None
    assert collection.query is not None
    assert collection.query["metadataStatus"] == "pending"


def test_metadata_worker_contains_unexpected_job_errors() -> None:
    worker = MetadataWorker(
        settings=PreviewWorkerSettings(
            mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
            preview_worker_enabled=False,
            _env_file=None,
        ),
        blob_store=object(),
    )
    torrent = SimpleNamespace(id="torrent-1")
    worker._repair_stale_processing = AsyncMock()  # type: ignore[method-assign]
    worker._claim_one = AsyncMock(return_value=torrent)  # type: ignore[method-assign]
    worker._process = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

    async def fail(claimed: object, error: Exception) -> None:
        assert claimed is torrent
        assert str(error) == "Unexpected metadata processing failure."

    worker._fail = AsyncMock(side_effect=fail)  # type: ignore[method-assign]

    asyncio.run(worker._run_claimed(torrent))  # type: ignore[arg-type]

    worker._fail.assert_awaited_once()


def test_metadata_worker_limits_concurrent_jobs() -> None:
    worker = MetadataWorker(
        settings=PreviewWorkerSettings(
            mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
            preview_worker_enabled=False,
            metadata_worker_max_concurrency=10,
            _env_file=None,
        ),
        blob_store=object(),
    )
    jobs = [SimpleNamespace(id=f"torrent-{index}") for index in range(11)]
    blocker = asyncio.Event()
    started: list[object] = []
    worker._repair_stale_processing = AsyncMock()  # type: ignore[method-assign]
    worker._claim_one = AsyncMock(side_effect=jobs)  # type: ignore[method-assign]

    async def run_claimed(claimed: object) -> None:
        started.append(claimed)
        await blocker.wait()

    worker._run_claimed = AsyncMock(side_effect=run_claimed)  # type: ignore[method-assign]

    async def run_until_full() -> None:
        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(started) == 10
        assert worker._claim_one.await_count == 10
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run_until_full())


def test_settings_reject_unsupported_target_frames() -> None:
    with pytest.raises(ValidationError, match="MMV_PREVIEW_TARGET_FRAMES"):
        PreviewWorkerSettings(
            mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
            openai_api_key="test-key",
            preview_target_frames=7,
            _env_file=None,
        )


def test_settings_default_wider_anchor_retry_ladder() -> None:
    settings = PreviewWorkerSettings(
        mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
        openai_api_key="test-key",
        _env_file=None,
    )

    assert settings.preview_anchor_retry_range_mb == (
        64.0,
        128.0,
        256.0,
        384.0,
        512.0,
        768.0,
    )


def test_settings_reject_non_widening_anchor_retry_ladder() -> None:
    with pytest.raises(ValidationError, match="MMV_PREVIEW_ANCHOR_RETRY_RANGE_MB"):
        PreviewWorkerSettings(
            mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
            openai_api_key="test-key",
            preview_anchor_retry_range_mb=(64.0, 64.0),
            _env_file=None,
        )


def test_settings_accept_preview_progress_timeout_override() -> None:
    settings = PreviewWorkerSettings(
        mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
        openai_api_key="test-key",
        preview_download_progress_timeout_seconds=900,
        _env_file=None,
    )

    assert settings.preview_download_progress_timeout_seconds == 900


def test_settings_default_preview_retry_delays() -> None:
    settings = PreviewWorkerSettings(
        mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
        openai_api_key="test-key",
        _env_file=None,
    )

    assert settings.preview_retry_delays == [
        "15m",
        "1h",
        "2h",
        "4h",
        "8h",
        "12h",
        "1d",
        "1d",
        "1d",
    ]
    assert settings.preview_retry_delays_seconds == [
        15 * 60,
        60 * 60,
        2 * 60 * 60,
        4 * 60 * 60,
        8 * 60 * 60,
        12 * 60 * 60,
        24 * 60 * 60,
        24 * 60 * 60,
        24 * 60 * 60,
    ]


@pytest.mark.parametrize("delay", ["0m", "1h30m", " 1h", "1.5h", "900", "-1h"])
def test_settings_reject_invalid_preview_retry_delay(delay: str) -> None:
    with pytest.raises(ValidationError, match="MMV_PREVIEW_RETRY_DELAYS"):
        PreviewWorkerSettings(
            mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
            openai_api_key="test-key",
            preview_retry_delays=[delay],
            _env_file=None,
        )


def test_settings_allow_empty_preview_retry_delays() -> None:
    settings = PreviewWorkerSettings(
        mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
        openai_api_key="test-key",
        preview_retry_delays=[],
        _env_file=None,
    )

    assert settings.preview_retry_delays_seconds == []


def test_settings_reject_non_positive_preview_progress_timeout() -> None:
    with pytest.raises(
        ValidationError, match="MMV_PREVIEW_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS"
    ):
        PreviewWorkerSettings(
            mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
            openai_api_key="test-key",
            preview_download_progress_timeout_seconds=0,
            _env_file=None,
        )


def test_parse_torrent_reads_single_file_payload() -> None:
    raw = b"d4:infod6:lengthi123e4:name9:movie.mkv6:pieces0:ee"

    metadata = parse_torrent(raw)

    assert metadata["name"] == "movie.mkv"
    assert metadata["sizeBytes"] == 123
    assert metadata["files"] == [
        {"path": "movie.mkv", "sizeBytes": 123, "position": 0}
    ]
    assert metadata["raw"] == raw


def test_claim_queries_retry_partial_and_failed_until_max_attempts() -> None:
    source = MongoPreviewJobSource(
        blob_store=object(),
        stale_processing_minutes=120,
        retry_delays_seconds=[900, 3600],
    )  # type: ignore[arg-type]

    queries = source._claim_queries(
        artifact_version="preview-v5",
        artifact_fingerprint="sha256:current",
    )

    assert queries[0]["previewAttempts"] == {"$lt": 3}
    assert queries[1]["previewStatus"] == {"$in": ["failed", "partial"]}
    assert queries[1]["previewAttempts"] == {"$lt": 3}
    assert {"previewNextAttemptAt": {"$exists": False}} in queries[1]["$or"]


def test_claim_queries_allow_one_attempt_when_retry_schedule_is_empty() -> None:
    source = MongoPreviewJobSource(
        blob_store=object(), stale_processing_minutes=120, retry_delays_seconds=[]
    )  # type: ignore[arg-type]

    queries = source._claim_queries(
        artifact_version="preview-v5",
        artifact_fingerprint="sha256:current",
    )

    assert queries[0]["previewAttempts"] == {"$lt": 1}
    assert queries[1]["previewAttempts"] == {"$lt": 1}


def test_artifact_stale_query_includes_completed_statuses_and_missing_fields() -> None:
    source = MongoPreviewJobSource(
        blob_store=object(),
        stale_processing_minutes=120,
        retry_delays_seconds=[900, 3600],
    )  # type: ignore[arg-type]

    stale_query = source._artifact_stale_query(
        artifact_version="preview-v5",
        artifact_fingerprint="sha256:current",
    )

    assert stale_query["previewStatus"] == {
        "$in": ["succeeded", "failed", "partial"]
    }
    assert {"previewDiagnostics.artifactVersion": {"$exists": False}} in stale_query[
        "$or"
    ]
    assert {"previewDiagnostics.artifactVersion": {"$ne": "preview-v5"}} in stale_query[
        "$or"
    ]
    assert {
        "previewDiagnostics.artifactFingerprint": {"$exists": False}
    } in stale_query["$or"]
    assert {
        "previewDiagnostics.artifactFingerprint": {"$ne": "sha256:current"}
    } in stale_query["$or"]


def test_claim_plans_reset_attempts_for_artifact_stale_rows() -> None:
    source = MongoPreviewJobSource(
        blob_store=object(),
        stale_processing_minutes=120,
        retry_delays_seconds=[900, 3600],
    )  # type: ignore[arg-type]

    plans = source._claim_plans(
        artifact_version="preview-v5",
        artifact_fingerprint="sha256:current",
    )

    assert [reset_attempts for _, reset_attempts, _ in plans] == [False, True, False]
    assert [claim_reason for _, _, claim_reason in plans] == [
        "pending",
        "artifact_stale",
        "retry",
    ]
    assert plans[1][0]["previewStatus"] == {"$in": ["succeeded", "failed", "partial"]}


def test_vm_worker_logging_keeps_console_info_and_json_debug_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    debug_log_path = tmp_path / "debug.log"
    settings = PreviewWorkerSettings(
        mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
        openai_api_key="test-key",
        vm_worker_debug_log_path=debug_log_path,
        _env_file=None,
    )
    _configure_vm_worker_logging(settings)
    try:
        logger.bind(
            mongodb_uri="mongodb://user:password@example.invalid/mymediavault",
            openai_api_key="sk-proj-secret123456789",
        ).debug("debug message with sk-proj-secret123456789")
        logger.info("visible info")
    finally:
        logger.remove()

    captured = capsys.readouterr()
    assert "visible info" in captured.out
    assert "debug message" not in captured.out

    records = [
        json.loads(line)["record"]
        for line in debug_log_path.read_text(encoding="utf-8").splitlines()
    ]
    debug_record = next(
        record for record in records if record["message"].startswith("debug message")
    )
    assert debug_record["level"]["name"] == "DEBUG"
    assert debug_record["message"] == "debug message with sk-[redacted]"
    assert debug_record["extra"]["mongodb_uri"] == "[redacted]"
    assert debug_record["extra"]["openai_api_key"] == "[redacted]"


def test_artifact_stale_claim_resets_attempts_to_one(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCollection:
        def __init__(self) -> None:
            self.update: dict[str, object] | None = None

        async def find_one_and_update(
            self, _query: object, update: dict[str, object], **_kwargs: object
        ) -> None:
            self.update = update
            return None

    collection = FakeCollection()
    monkeypatch.setattr(
        "mymediavault_vm_worker.Torrent.get_pymongo_collection",
        lambda: collection,
    )
    source = MongoPreviewJobSource(
        blob_store=object(),
        stale_processing_minutes=120,
        retry_delays_seconds=[900, 3600],
    )  # type: ignore[arg-type]

    asyncio.run(source._claim_one({}, reset_attempts=True))

    assert collection.update is not None
    assert "$inc" not in collection.update
    assert collection.update["$set"]["previewAttempts"] == 1  # type: ignore[index]


def test_success_update_persists_preview_result_artifact_fields() -> None:
    result = PreviewResult(
        status="succeeded",
        status_reason=None,
        info_hash="abc",
        artifact=PreviewArtifact(
            frames=[
                GeneratedFrame(
                    path=Path("frame.jpg"),
                    width=1920,
                    height=1080,
                    timestamp_seconds=12.5,
                )
            ],
            sheet=GeneratedSheet(path=Path("sheet.jpg"), width=960, height=540),
        ),
        diagnostics=_preview_diagnostics(
            selected_file=SelectedFile(index=0, path="movie.mkv", length=123),
            downloaded_bytes=456,
            elapsed_seconds=7.8,
        ),
    )

    update = _success_update(
        result,
        stored_frames=[
            {
                "key": "previews/abc/frame_001.jpg",
                "width": 1920,
                "height": 1080,
                "timestampSeconds": 12.5,
            }
        ],
        stored_sheet={
            "key": "previews/abc/preview_sheet.jpg",
            "width": 960,
            "height": 540,
            "mimeType": "image/jpeg",
        },
        artifact_version="preview-v6",
        artifact_fingerprint="sha256:current",
    )["$set"]

    assert update["previewStatus"] == "succeeded"
    assert update["previewDiagnostics"]["artifactVersion"] == "preview-v6"
    assert update["previewDiagnostics"]["artifactFingerprint"] == "sha256:current"
    assert update["previewDiagnostics"]["selectedFilePath"] == "movie.mkv"
    assert update["previewFrames"][0]["key"] == "previews/abc/frame_001.jpg"
    assert update["previewSheet"]["key"] == "previews/abc/preview_sheet.jpg"


def test_success_update_serializes_integer_diagnostic_keys_as_strings(
    tmp_path: Path,
) -> None:
    frame_path = tmp_path / "frame.jpg"
    sheet_path = tmp_path / "sheet.jpg"
    result = PreviewResult(
        status="partial",
        status_reason="Only 1 of 3 target anchors produced LLM-accepted frames",
        info_hash="abc",
        artifact=PreviewArtifact(
            frames=[
                GeneratedFrame(
                    path=frame_path,
                    width=1920,
                    height=1080,
                    timestamp_seconds=12.5,
                )
            ],
            sheet=GeneratedSheet(path=sheet_path, width=960, height=540),
        ),
        diagnostics=_preview_diagnostics(
            anchor_retry=AnchorRetryDiagnostics(
                range_mb_ladder=(64.0, 128.0),
                initial_missing_anchor_indexes=[1],
                final_missing_anchor_indexes=[1],
                attempts=[
                    AnchorRetryAttemptDiagnostics(
                        range_mb=64.0,
                        target_anchor_indexes=[1],
                        decoded_candidate_counts_by_anchor={1: 2},
                        llm_visible_candidate_counts_by_anchor={1: 0},
                        remaining_missing_anchor_indexes=[1],
                        downloaded_bytes=123,
                    )
                ],
            )
        ),
    )

    update = _success_update(
        result,
        stored_frames=[],
        stored_sheet=None,
        artifact_version="preview-v7",
        artifact_fingerprint="sha256:current",
    )["$set"]

    retry_attempt = update["previewDiagnostics"]["details"]["anchor_retry"][
        "attempts"
    ][0]
    assert retry_attempt["decoded_candidate_counts_by_anchor"] == {"1": 2}
    assert retry_attempt["llm_visible_candidate_counts_by_anchor"] == {"1": 0}


def test_success_update_can_preserve_existing_artifacts_when_no_replacement() -> None:
    result = PreviewResult(
        status="failed",
        status_reason="No replacement artifacts were generated.",
        info_hash="abc",
        artifact=PreviewArtifact(frames=[], sheet=None),
        diagnostics=_preview_diagnostics(),
    )

    update = _success_update(
        result,
        stored_frames=[],
        stored_sheet=None,
        artifact_version="preview-v6",
        artifact_fingerprint="sha256:current",
        replace_artifacts=False,
    )["$set"]

    assert update["previewStatus"] == "failed"
    assert update["previewNextAttemptAt"] is None
    assert update["previewDiagnostics"]["artifactVersion"] == "preview-v6"
    assert update["previewDiagnostics"]["artifactFingerprint"] == "sha256:current"
    assert "previewFrames" not in update
    assert "previewSheet" not in update


def test_preview_next_attempt_at_uses_progressive_retry_delays() -> None:
    now = datetime(2026, 5, 29, tzinfo=UTC)

    first_retry = _preview_next_attempt_at(
        status="failed",
        attempts=1,
        max_attempts=3,
        retry_delays_seconds=[900, 3600],
        now=now,
    )
    second_retry = _preview_next_attempt_at(
        status="partial",
        attempts=2,
        max_attempts=3,
        retry_delays_seconds=[900, 3600],
        now=now,
    )

    assert first_retry == now + timedelta(seconds=900)
    assert second_retry == now + timedelta(seconds=3600)
    assert (
        _preview_next_attempt_at(
            status="failed",
            attempts=3,
            max_attempts=3,
            retry_delays_seconds=[900, 3600],
            now=now,
        )
        is None
    )


def test_job_lease_uploads_preview_artifacts(tmp_path: Path) -> None:
    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(b"frame")
    sheet_path = tmp_path / "sheet.jpg"
    sheet_path.write_bytes(b"sheet")

    class FakeBlobStore:
        def __init__(self) -> None:
            self.uploads: list[tuple[str, Path, str]] = []

        async def put_file(self, key: str, path: Path, content_type: str) -> str:
            self.uploads.append((key, path, content_type))
            return key

    blob_store = FakeBlobStore()
    lease = MongoPreviewJobLease(
        torrent=SimpleNamespace(
            id="torrent-1",
            rawBlobKey=None,
            previewFrames=[],
            previewSheet=None,
        ),
        blob_store=blob_store,  # type: ignore[arg-type]
        artifact_version="preview-v6",
        artifact_fingerprint="sha256:current",
        max_attempts=3,
        retry_delays_seconds=[900, 3600],
    )

    frames = asyncio.run(lease._store_frames(
        "abc",
        [GeneratedFrame(path=frame_path, width=640, height=360, timestamp_seconds=1.25)],
    ))
    sheet = asyncio.run(lease._store_sheet(
        "abc", GeneratedSheet(path=sheet_path, width=640, height=360)
    ))

    assert frames[0]["key"] == "previews/abc/frame_001.jpg"
    assert sheet is not None
    assert sheet["key"] == "previews/abc/preview_sheet.jpg"
    assert blob_store.uploads == [
        ("previews/abc/frame_001.jpg", frame_path, "image/jpeg"),
        ("previews/abc/preview_sheet.jpg", sheet_path, "image/jpeg"),
    ]
