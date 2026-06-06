from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mymediavault_vm_worker.actor.identity import InMemoryActorIndex
from mymediavault_vm_worker.actor.models import TorrentAssignment

COMMENT_PATTERN = re.compile(r"//.*$", re.MULTILINE)


def evaluate_fixture_partitions(
    *,
    previews_dir: Path,
    ground_truth_path: Path,
    analyzer: Any,
) -> dict[str, Any]:
    ground_truth = _load_ground_truth(ground_truth_path)
    expected_by_torrent = {
        torrent_key: expected_actor
        for expected_actor, torrent_keys in ground_truth.items()
        for torrent_key in torrent_keys
    }
    index = InMemoryActorIndex(config=analyzer.config)
    assignments: dict[str, TorrentAssignment] = {}
    for torrent_dir in sorted(path for path in previews_dir.iterdir() if path.is_dir()):
        observations = analyzer.analyze_frames(torrent_dir.glob("frame_*.jpg"))
        assignments[torrent_dir.name] = index.assign(
            torrent_key=torrent_dir.name,
            clusters=analyzer.main_clusters(observations),
            detected_face_count=len(observations),
        )

    predicted_primary = {
        torrent_key: assignment.actor_ids[0] if assignment.actor_ids else None
        for torrent_key, assignment in assignments.items()
    }
    false_merges = _false_merges(
        predicted_primary=predicted_primary,
        expected_by_torrent=expected_by_torrent,
    )
    missed_torrents = sorted(
        torrent_key
        for torrent_key in expected_by_torrent
        if predicted_primary.get(torrent_key) is None
    )
    identity_splits = _identity_splits(
        ground_truth=ground_truth,
        predicted_primary=predicted_primary,
    )
    correct_torrent_count = sum(
        predicted_primary.get(torrent_key) is not None
        for torrent_key in expected_by_torrent
    )
    return {
        "passed": not false_merges and not missed_torrents and not identity_splits,
        "torrentCount": len(assignments),
        "expectedTorrentCount": len(expected_by_torrent),
        "generatedActorCount": len(index.actors),
        "recall": correct_torrent_count / len(expected_by_torrent),
        "falseMerges": false_merges,
        "missedTorrents": missed_torrents,
        "identitySplits": identity_splits,
        "assignments": {
            torrent_key: {
                "actorIds": list(assignment.actor_ids),
                "detectedFaceCount": assignment.detected_face_count,
                "qualifyingClusterCount": assignment.qualifying_cluster_count,
                "unresolvedClusterCount": assignment.unresolved_cluster_count,
            }
            for torrent_key, assignment in assignments.items()
        },
    }




def _load_ground_truth(path: Path) -> dict[str, list[str]]:
    value = json.loads(COMMENT_PATTERN.sub("", path.read_text(encoding="utf-8")))
    return {
        str(actor_id): [str(torrent_key) for torrent_key in torrent_keys]
        for actor_id, torrent_keys in value.items()
    }


def _false_merges(
    *,
    predicted_primary: dict[str, str | None],
    expected_by_torrent: dict[str, str],
) -> list[dict[str, Any]]:
    expected_by_predicted: dict[str, set[str]] = {}
    for torrent_key, predicted_actor in predicted_primary.items():
        expected_actor = expected_by_torrent.get(torrent_key)
        if predicted_actor is None or expected_actor is None:
            continue
        expected_by_predicted.setdefault(predicted_actor, set()).add(expected_actor)
    return [
        {"predictedActorId": actor_id, "expectedActorIds": sorted(expected_actor_ids)}
        for actor_id, expected_actor_ids in sorted(expected_by_predicted.items())
        if len(expected_actor_ids) > 1
    ]


def _identity_splits(
    *,
    ground_truth: dict[str, list[str]],
    predicted_primary: dict[str, str | None],
) -> list[dict[str, Any]]:
    results = []
    for expected_actor, torrent_keys in sorted(ground_truth.items()):
        predicted_actor_ids = {
            predicted_primary.get(torrent_key)
            for torrent_key in torrent_keys
            if predicted_primary.get(torrent_key) is not None
        }
        if len(predicted_actor_ids) > 1:
            results.append(
                {
                    "expectedActorId": expected_actor,
                    "predictedActorIds": sorted(predicted_actor_ids),
                }
            )
    return results

