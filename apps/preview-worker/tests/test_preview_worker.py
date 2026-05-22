from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError
from torrent_preview import (
    ExtractedFrame,
    PreviewContext,
    PreviewDiagnostics,
    PreviewOutput,
    PreviewResult,
    RenderedSheet,
    SelectedFile,
    StoredFrame,
    StoredSheet,
)

from mymediavault_preview_worker import (
    MongoPreviewJobSource,
    PreviewWorkerSettings,
    R2PreviewOutputHandler,
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


def test_stale_artifact_query_uses_library_artifact_contract() -> None:
    source = MongoPreviewJobSource(blob_store=object(), stale_processing_minutes=120)  # type: ignore[arg-type]

    queries = source._claim_queries(
        artifact_version="preview-v5",
        artifact_fingerprint="sha256:current",
    )

    stale_query = queries[1]
    assert stale_query["previewStatus"] == {"$in": ["succeeded", "partial"]}
    assert {"previewDiagnostics.artifactVersion": {"$ne": "preview-v5"}} in stale_query[
        "$or"
    ]
    assert {
        "previewDiagnostics.artifactFingerprint": {"$ne": "sha256:current"}
    } in stale_query["$or"]


def test_success_update_persists_preview_result_artifact_fields() -> None:
    result = PreviewResult(
        artifact_version="preview-v5",
        artifact_fingerprint="sha256:current",
        status="succeeded",
        info_hash="abc",
        selected_file=SelectedFile(index=0, path="movie.mkv", length=123),
        frames=[
            StoredFrame(
                uri="previews/abc/frame.jpg",
                score=0.9,
                width=1920,
                height=1080,
                timestamp_seconds=12.5,
                metadata={"accepted_by_llm": "true"},
            )
        ],
        sheet=StoredSheet(
            uri="previews/abc/preview_sheet.jpg",
            width=960,
            height=540,
            mime_type="image/jpeg",
            metadata={"kind": "sheet"},
        ),
        downloaded_bytes=456,
        elapsed_seconds=7.8,
        attempts=2,
        strategy_name="progressive-range-v1",
        failure_reason=None,
        warnings=[],
        diagnostics=PreviewDiagnostics(torrent_cache_enabled=True),
    )

    update = _success_update(result)["$set"]

    assert update["previewStatus"] == "succeeded"
    assert update["previewDiagnostics"]["artifactVersion"] == "preview-v5"
    assert update["previewDiagnostics"]["artifactFingerprint"] == "sha256:current"
    assert update["previewDiagnostics"]["selectedFilePath"] == "movie.mkv"
    assert update["previewFrames"][0]["metadata"]["accepted_by_llm"] == "true"
    assert update["previewSheet"]["key"] == "previews/abc/preview_sheet.jpg"


def test_r2_output_handler_preserves_llm_acceptance_metadata(tmp_path: Path) -> None:
    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(b"frame")

    class FakeBlobStore:
        def __init__(self) -> None:
            self.uploads: list[tuple[str, Path, str]] = []

        async def put_file(self, key: str, path: Path, content_type: str) -> str:
            self.uploads.append((key, path, content_type))
            return key

    blob_store = FakeBlobStore()
    handler = R2PreviewOutputHandler(blob_store)  # type: ignore[arg-type]
    output = PreviewOutput(
        artifact_version="preview-v5",
        artifact_fingerprint="sha256:current",
        frames=[
            ExtractedFrame(
                path=frame_path,
                score=0.8,
                width=640,
                height=360,
                timestamp_seconds=1.25,
                anchor_index=0,
                anchor_ratio=0.1,
                decode_method="anchor-window",
                accepted_by_llm=True,
            )
        ],
        sheet=RenderedSheet(path=frame_path, width=640, height=360),
        status="succeeded",
        target_frames=1,
        failure_reason=None,
    )
    context = PreviewContext(
        info_hash="abc",
        selected_file=SelectedFile(index=0, path="movie.mkv", length=123),
    )

    stored = asyncio.run(handler.handle(context, output))

    assert stored.frames[0].metadata["accepted_by_llm"] == "true"
    assert blob_store.uploads[0][0].startswith("previews/abc/frame_001_")
