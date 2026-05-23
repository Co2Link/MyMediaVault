from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from torrent_preview import (
    GeneratedFrame,
    GeneratedSheet,
    PreviewArtifact,
    PreviewDiagnostics,
    PreviewResult,
    SelectedFile,
)

from mymediavault_preview_worker import (
    MongoPreviewJobLease,
    MongoPreviewJobSource,
    PreviewWorkerSettings,
    _success_update,
)


def test_settings_require_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_claim_queries_retry_partial_and_failed_until_max_attempts() -> None:
    source = MongoPreviewJobSource(blob_store=object(), stale_processing_minutes=120, max_attempts=3)  # type: ignore[arg-type]

    queries = source._claim_queries(
        artifact_version="preview-v5",
        artifact_fingerprint="sha256:current",
    )

    assert queries[0]["previewAttempts"] == {"$lt": 3}
    assert queries[1]["previewStatus"] == {"$in": ["failed", "partial"]}
    assert queries[1]["previewAttempts"] == {"$lt": 3}
    stale_query = queries[2]
    assert stale_query["previewStatus"] == "succeeded"
    assert {"previewDiagnostics.artifactVersion": {"$ne": "preview-v5"}} in stale_query[
        "$or"
    ]
    assert {
        "previewDiagnostics.artifactFingerprint": {"$ne": "sha256:current"}
    } in stale_query["$or"]


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
        diagnostics=PreviewDiagnostics(
            selected_file=SelectedFile(index=0, path="movie.mkv", length=123),
            downloaded_bytes=456,
            elapsed_seconds=7.8,
            torrent_cache_enabled=True,
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


def test_job_lease_uploads_v4_artifacts(tmp_path: Path) -> None:
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
