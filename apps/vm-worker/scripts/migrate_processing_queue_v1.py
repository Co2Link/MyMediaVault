"""One-way migration from split metadata/preview scheduling to worker 1.0."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pymongo import MongoClient

LEGACY_FIELDS = [
    "metadataStatus",
    "metadataError",
    "metadataFailureKind",
    "metadataAttempts",
    "metadataLastAttemptAt",
    "metadataNextAttemptAt",
    "metadataLeaseUntil",
    "metadataStartedAt",
    "metadataFinishedAt",
    "metadataDiagnostics",
    "previewStatus",
    "previewAttempts",
    "previewLastAttemptAt",
    "previewNextAttemptAt",
    "previewUpdatedAt",
]


def _processing_state(torrent: dict[str, Any]) -> str:
    current_state = torrent.get("processingState")
    if current_state in {"queued", "partial", "complete", "exhausted", "cancelled"}:
        return current_state
    if current_state == "running":
        return "queued"
    if torrent.get("metadataFailureKind") == "permanent":
        return "exhausted"
    frame_count = len(torrent.get("previewFrames") or [])
    if torrent.get("previewStatus") == "succeeded" and frame_count >= 9:
        return "complete"
    if frame_count:
        return "partial"
    return "queued"


def migrate(*, uri: str, database_name: str, backup_path: Path, dry_run: bool) -> None:
    client = MongoClient(uri)
    torrents = client[database_name]["torrents"]
    documents = list(torrents.find({}))
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(
        json.dumps(documents, default=str, indent=2),
        encoding="utf-8",
    )
    now = datetime.now(UTC)
    counts: dict[str, int] = {}
    for torrent in documents:
        state = _processing_state(torrent)
        counts[state] = counts.get(state, 0) + 1
        if dry_run:
            continue
        torrents.update_one(
            {"_id": torrent["_id"]},
            {
                "$set": {
                    "processingState": state,
                    "processingPhase": None,
                    "processingQueuedAt": now if state in {"queued", "partial"} else None,
                    "processingAvailableAt": None,
                    "processingLeaseUntil": None,
                    "processingFailureCount": 0,
                    "processingLastOutcome": "migrated_to_worker_1_0",
                    "processingLastError": (
                        torrent.get("metadataError")
                        or torrent.get("previewDiagnostics", {}).get("statusReason")
                    ),
                    "processingUpdatedAt": now,
                    "processingDiagnostics": {"migration": "worker-1.0.0"},
                },
                "$unset": {field: "" for field in LEGACY_FIELDS},
            },
        )
    print(json.dumps({"dryRun": dry_run, "torrents": len(documents), "states": counts}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database")
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    file_values = dotenv_values(args.env_file) if args.env_file.exists() else {}
    uri = os.getenv("MONGODB_URI") or file_values.get("MONGODB_URI")
    if not uri:
        raise SystemExit("MONGODB_URI is required")
    database_name = (
        args.database
        or os.getenv("MMV_MONGODB_DB_NAME")
        or file_values.get("MMV_MONGODB_DB_NAME")
        or "mymediavault"
    )
    migrate(uri=uri, database_name=database_name, backup_path=args.backup, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
