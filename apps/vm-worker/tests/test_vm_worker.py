from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
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
    FakeTorrentMetadataResolver,
    MongoPreviewJobLease,
    MongoPreviewJobSource,
    PreviewWorkerSettings,
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


def test_settings_reject_unsupported_target_frames() -> None:
    with pytest.raises(ValidationError, match="MMV_PREVIEW_TARGET_FRAMES"):
        PreviewWorkerSettings(
            mongodb_uri="mongodb://127.0.0.1:27017/mymediavault",
            openai_api_key="test-key",
            preview_target_frames=7,
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
    source = MongoPreviewJobSource(blob_store=object(), stale_processing_minutes=120, max_attempts=3)  # type: ignore[arg-type]

    queries = source._claim_queries(
        artifact_version="preview-v5",
        artifact_fingerprint="sha256:current",
    )

    assert queries[0]["previewAttempts"] == {"$lt": 3}
    assert queries[1]["previewStatus"] == {"$in": ["failed", "partial"]}
    assert queries[1]["previewAttempts"] == {"$lt": 3}


def test_artifact_stale_query_includes_completed_statuses_and_missing_fields() -> None:
    source = MongoPreviewJobSource(blob_store=object(), stale_processing_minutes=120, max_attempts=3)  # type: ignore[arg-type]

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
    source = MongoPreviewJobSource(blob_store=object(), stale_processing_minutes=120, max_attempts=3)  # type: ignore[arg-type]

    plans = source._claim_plans(
        artifact_version="preview-v5",
        artifact_fingerprint="sha256:current",
    )

    assert [reset_attempts for _, reset_attempts in plans] == [False, True, False]
    assert plans[1][0]["previewStatus"] == {"$in": ["succeeded", "failed", "partial"]}


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
    source = MongoPreviewJobSource(blob_store=object(), stale_processing_minutes=120, max_attempts=3)  # type: ignore[arg-type]

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
    assert update["previewDiagnostics"]["artifactVersion"] == "preview-v6"
    assert update["previewDiagnostics"]["artifactFingerprint"] == "sha256:current"
    assert "previewFrames" not in update
    assert "previewSheet" not in update


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
