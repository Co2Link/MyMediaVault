from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from mymediavault_vm_worker.actor_analysis import (
    ActorAnalysisConfig,
    ActorExemplar,
    ActorIdentity,
    FaceCluster,
    FaceObservation,
    ProfileCandidate,
    normalized_mean,
)
from mymediavault_vm_worker.actor_worker import ActorAnalysisWorker, FrameAnalysis


def _observation(
    frame_key: str = "frame_001.jpg",
    embedding: tuple[float, ...] = (1.0, 0.0),
) -> FaceObservation:
    return FaceObservation(
        frame_key=frame_key,
        embedding=np.asarray(embedding, dtype=np.float32),
        detector_score=0.9,
        quality_score=1.0,
        box=(10, 10, 30, 30),
    )


def _cluster(*observations: FaceObservation) -> FaceCluster:
    return FaceCluster(
        observations=observations,
        centroid=normalized_mean(value.embedding for value in observations),
        quality_score=1.0,
    )


class FakeAnalyzer:
    config = ActorAnalysisConfig()

    def __init__(self, clusters: list[FaceCluster], *, profile_score: float = 1.5) -> None:
        self._clusters = clusters
        self._profile_score = profile_score

    def analyze_frames(self, frame_paths: list[Path]) -> list[FaceObservation]:
        del frame_paths
        return [
            observation
            for cluster in self._clusters
            for observation in cluster.observations
        ]

    def main_clusters(self, observations: list[FaceObservation]) -> list[FaceCluster]:
        del observations
        return self._clusters

    def profile_candidates(
        self,
        *,
        frame_paths_by_key: dict[str, Path],
        cluster: FaceCluster,
        observations: list[FaceObservation],
    ) -> list[ProfileCandidate]:
        del frame_paths_by_key, observations
        return [
            ProfileCandidate(
                frame_key=cluster.observations[0].frame_key,
                jpeg=b"profile-jpeg",
                score=self._profile_score,
                flags=("non-frontal",),
                components={"detectorConfidence": 0.9, "sharpness": 0.6},
            )
        ]


class FakeBlobStore:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes, str]] = []
        self.deletes: list[str] = []

    @staticmethod
    def get_bytes(key: str) -> bytes:
        del key
        return b"preview-jpeg"

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        self.uploads.append((key, data, content_type))
        return key

    async def delete_if_exists(self, key: str) -> None:
        self.deletes.append(key)


class FakeCursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self._documents = documents

    async def to_list(self, *, length: int | None) -> list[dict[str, Any]]:
        del length
        return self._documents


class FakeCollection:
    def __init__(
        self,
        documents: list[dict[str, Any]] | None = None,
        *,
        matched_counts: list[int] | None = None,
    ) -> None:
        self.documents = documents or []
        self.updates: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.inserts: list[dict[str, Any]] = []
        self.matched_counts = matched_counts or []

    def find(self, _query: dict[str, Any]) -> FakeCursor:
        return FakeCursor(self.documents)

    async def insert_one(self, document: dict[str, Any]) -> None:
        self.inserts.append(document)
        self.documents.append(document)

    async def update_one(
        self, query: dict[str, Any], update: dict[str, Any]
    ) -> SimpleNamespace:
        self.updates.append((query, update))
        matched_count = self.matched_counts.pop(0) if self.matched_counts else 1
        return SimpleNamespace(matched_count=matched_count)

    async def update_many(
        self, query: dict[str, Any], update: dict[str, Any]
    ) -> SimpleNamespace:
        self.updates.append((query, update))
        return SimpleNamespace(modified_count=1)


class FakeDatabase:
    def __init__(
        self,
        *,
        torrents: FakeCollection | None = None,
        actors: FakeCollection | None = None,
    ) -> None:
        self.collections = {
            "torrents": torrents or FakeCollection(),
            "actors": actors or FakeCollection(),
        }

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections[name]


def _torrent(**overrides: Any) -> dict[str, Any]:
    value = {
        "_id": "torrent-1",
        "previewFrames": [
            {"key": "previews/abc/frame_001.jpg"},
            {"key": "previews/abc/frame_002.jpg"},
        ],
        "previewDiagnostics": {"artifactFingerprint": "sha256:preview"},
        "actorAnalysisAttempts": 1,
    }
    value.update(overrides)
    return value


def _worker(
    *,
    analyzer: FakeAnalyzer | None = None,
    database: FakeDatabase | None = None,
    blob_store: FakeBlobStore | None = None,
) -> ActorAnalysisWorker:
    return ActorAnalysisWorker(
        database=database or FakeDatabase(),
        blob_store=blob_store or FakeBlobStore(),
        analyzer=analyzer or FakeAnalyzer([]),
        model_version="model-v1",
    )


def test_claim_plans_prioritize_pending_then_stale_then_failed_retry() -> None:
    plans = _worker()._claim_plans()

    assert len(plans) == 3
    assert [reset_attempts for _, reset_attempts in plans] == [False, True, False]
    assert {"actorAnalysisStatus": "succeeded"} in plans[1][0]["$and"]
    assert {"actorAnalysisStatus": "failed"} in plans[2][0]["$and"]
    assert {"actorAnalysisAttempts": {"$lt": 3}} in plans[2][0]["$and"][2]["$or"]


def test_eligible_query_requires_durable_preview_frames() -> None:
    assert _worker()._eligible_query() == {
        "processingState": "complete",
        "previewFrames.0": {"$exists": True},
    }


def test_stale_fingerprint_uses_preview_artifact_fingerprint() -> None:
    stale = _worker()._stale_fingerprint_query()

    concat = stale["$expr"]["$ne"][1]["$concat"]
    assert concat[0].startswith("sha256:")
    assert concat[0].endswith(":preview:")
    assert concat[1] == {"$ifNull": ["$previewDiagnostics.artifactFingerprint", ""]}


def test_repairs_expired_actor_analysis_leases() -> None:
    torrents = FakeCollection()
    worker = _worker(database=FakeDatabase(torrents=torrents))

    asyncio.run(worker._repair_stale_processing())

    query, update = torrents.updates[0]
    assert query["actorAnalysisStatus"] == "processing"
    assert {"actorAnalysisLeaseUntil": {"$exists": False}} in query["$or"]
    assert update["$set"]["actorAnalysisStatus"] == "pending"


def test_process_creates_uuid_actor_and_replaces_system_assignments() -> None:
    torrents = FakeCollection()
    actors = FakeCollection()
    blob_store = FakeBlobStore()
    analyzer = FakeAnalyzer(
        [
            _cluster(
                _observation("frame_001.jpg"),
                _observation("frame_002.jpg", (0.99, 0.01)),
            )
        ]
    )
    worker = _worker(
        analyzer=analyzer,
        database=FakeDatabase(torrents=torrents, actors=actors),
        blob_store=blob_store,
    )

    asyncio.run(worker._process(_torrent()))

    created = actors.inserts[0]
    actor_id = created["_id"]
    assert created["name"] == f"actor-{actor_id}"
    assert created["faceCentroids"][0]["modelVersion"] == "model-v1"
    assert len(created["faceExemplars"]) == 1
    assert len(blob_store.uploads) == 1
    assert blob_store.uploads[0][0].startswith(
        f"actors/{actor_id}/profile-system-"
    )
    assert blob_store.uploads[0][0].endswith(".jpg")
    assert blob_store.uploads[0][1:] == (b"profile-jpeg", "image/jpeg")
    assert created["profileImageSource"] == "system"
    assert created["profileImageVersion"] == "profile-v2"
    assert created["profileImageScore"] == 1.5
    assert created["profileImageFlags"] == ["non-frontal"]
    assert torrents.updates[0][0] == {
        "_id": "torrent-1",
        "actorAnalysisStatus": "processing",
        "processingUpdatedAt": None,
    }
    assert torrents.updates[0][1]["$set"]["systemActorIds"] == [actor_id]
    assert torrents.updates[0][1]["$set"]["actorAnalysisStatus"] == "succeeded"


def test_process_empty_result_succeeds_with_no_system_assignments() -> None:
    torrents = FakeCollection()
    worker = _worker(database=FakeDatabase(torrents=torrents))

    asyncio.run(worker._process(_torrent()))

    values = torrents.updates[0][1]["$set"]
    assert values["systemActorIds"] == []
    assert values["actorAnalysisStatus"] == "succeeded"


def test_existing_admin_name_and_profile_survive_reanalysis() -> None:
    actors = FakeCollection(
        [
            {
                "_id": "actor-existing",
                "name": "Real Name",
                "profileImageKey": "actors/actor-existing/admin.jpg",
                "faceExemplarRevision": 1,
                "faceExemplars": [
                    {
                        "modelVersion": "model-v1",
                        "embedding": [1.0, 0.0],
                        "qualityScore": 1.0,
                        "sourceTorrentId": "torrent-old",
                        "sourceFrameKey": "previews/old/frame_001.jpg",
                    }
                ],
                "faceCentroids": [
                    {"modelVersion": "model-v1", "embedding": [1.0, 0.0]}
                ],
            }
        ]
    )
    analyzer = FakeAnalyzer(
        [
            _cluster(
                _observation("frame_001.jpg"),
                _observation("frame_002.jpg", (0.99, 0.01)),
            )
        ]
    )
    worker = _worker(analyzer=analyzer, database=FakeDatabase(actors=actors))

    asyncio.run(worker._process(_torrent()))

    values = actors.updates[0][1]["$set"]
    assert "name" not in values
    assert "profileImageKey" not in values
    assert len(values["faceExemplars"]) <= 12


def test_existing_system_profile_is_replaced_by_meaningfully_better_candidate() -> None:
    actors = FakeCollection(
        [
            {
                "_id": "actor-existing",
                "name": "actor-existing",
                "profileImageKey": "actors/actor-existing/profile-system-old.jpg",
                "profileImageSource": "system",
                "profileImageVersion": "profile-v2",
                "profileImageScore": 1.0,
                "faceExemplarRevision": 1,
                "faceExemplars": [
                    {
                        "modelVersion": "model-v1",
                        "embedding": [1.0, 0.0],
                        "qualityScore": 1.0,
                    }
                ],
                "faceCentroids": [
                    {"modelVersion": "model-v1", "embedding": [1.0, 0.0]}
                ],
            }
        ]
    )
    blob_store = FakeBlobStore()
    analyzer = FakeAnalyzer(
        [_cluster(_observation("frame_001.jpg"), _observation("frame_002.jpg"))],
        profile_score=1.5,
    )

    asyncio.run(
        _worker(
            analyzer=analyzer,
            database=FakeDatabase(actors=actors),
            blob_store=blob_store,
        )._process(_torrent())
    )

    assert len(blob_store.uploads) == 1
    assert blob_store.deletes == ["actors/actor-existing/profile-system-old.jpg"]
    profile_update = actors.updates[1]
    assert profile_update[0]["profileImageKey"] == "actors/actor-existing/profile-system-old.jpg"
    assert profile_update[1]["$set"]["profileImageVersion"] == "profile-v2"
    assert profile_update[1]["$set"]["profileImageScore"] == 1.5


def test_existing_system_profile_is_not_replaced_below_improvement_margin() -> None:
    actors = FakeCollection(
        [
            {
                "_id": "actor-existing",
                "profileImageKey": "actors/actor-existing/profile-system-old.jpg",
                "profileImageSource": "system",
                "profileImageVersion": "profile-v2",
                "profileImageScore": 1.45,
                "faceExemplarRevision": 1,
                "faceExemplars": [
                    {
                        "modelVersion": "model-v1",
                        "embedding": [1.0, 0.0],
                        "qualityScore": 1.0,
                    }
                ],
                "faceCentroids": [
                    {"modelVersion": "model-v1", "embedding": [1.0, 0.0]}
                ],
            }
        ]
    )
    blob_store = FakeBlobStore()
    analyzer = FakeAnalyzer(
        [_cluster(_observation("frame_001.jpg"), _observation("frame_002.jpg"))],
        profile_score=1.5,
    )

    asyncio.run(
        _worker(
            analyzer=analyzer,
            database=FakeDatabase(actors=actors),
            blob_store=blob_store,
        )._process(_torrent())
    )

    assert blob_store.uploads == []
    assert len(actors.updates) == 1


def test_outdated_system_profile_is_replaced_without_comparing_scores() -> None:
    actors = FakeCollection(
        [
            {
                "_id": "actor-existing",
                "profileImageKey": "actors/actor-existing/profile-system-old.jpg",
                "profileImageSource": "system",
                "profileImageVersion": "profile-v1",
                "profileImageScore": 3.0,
                "faceExemplarRevision": 1,
                "faceExemplars": [
                    {
                        "modelVersion": "model-v1",
                        "embedding": [1.0, 0.0],
                        "qualityScore": 1.0,
                    }
                ],
                "faceCentroids": [
                    {"modelVersion": "model-v1", "embedding": [1.0, 0.0]}
                ],
            }
        ]
    )
    blob_store = FakeBlobStore()
    analyzer = FakeAnalyzer(
        [_cluster(_observation("frame_001.jpg"), _observation("frame_002.jpg"))],
        profile_score=1.5,
    )

    asyncio.run(
        _worker(
            analyzer=analyzer,
            database=FakeDatabase(actors=actors),
            blob_store=blob_store,
        )._process(_torrent())
    )

    assert len(blob_store.uploads) == 1
    assert actors.updates[1][1]["$set"]["profileImageVersion"] == "profile-v2"


def test_legacy_generated_profile_is_inferred_as_system_managed() -> None:
    worker = _worker()

    assert worker._is_system_profile(
        actor_id="actor-existing",
        actor={
            "profileImageKey": "actors/actor-existing/profile-actor-existing.jpg"
        },
    )
    assert not worker._is_system_profile(
        actor_id="actor-existing",
        actor={"profileImageKey": "actors/actor-existing/profile-admin.jpg"},
    )


def test_lost_profile_update_race_deletes_abandoned_upload() -> None:
    actors = FakeCollection(
        [
            {
                "_id": "actor-existing",
                "profileImageKey": "actors/actor-existing/profile-system-old.jpg",
                "profileImageSource": "system",
                "profileImageVersion": "profile-v2",
                "profileImageScore": 1.0,
                "faceExemplarRevision": 1,
                "faceExemplars": [
                    {
                        "modelVersion": "model-v1",
                        "embedding": [1.0, 0.0],
                        "qualityScore": 1.0,
                    }
                ],
                "faceCentroids": [
                    {"modelVersion": "model-v1", "embedding": [1.0, 0.0]}
                ],
            }
        ],
        matched_counts=[1, 0],
    )
    blob_store = FakeBlobStore()
    analyzer = FakeAnalyzer(
        [_cluster(_observation("frame_001.jpg"), _observation("frame_002.jpg"))]
    )

    asyncio.run(
        _worker(
            analyzer=analyzer,
            database=FakeDatabase(actors=actors),
            blob_store=blob_store,
        )._process(_torrent())
    )

    assert len(blob_store.uploads) == 1
    assert blob_store.deletes == [blob_store.uploads[0][0]]


def test_outdated_profile_refresh_selects_best_assigned_torrent_candidate() -> None:
    assigned = _torrent(_id="torrent-assigned")
    torrents = FakeCollection([assigned])
    worker = _worker(database=FakeDatabase(torrents=torrents))
    identity = ActorIdentity(
        actor_id="actor-existing",
        exemplars=[
            ActorExemplar(
                torrent_key="torrent-assigned",
                frame_key="previews/assigned/frame_001.jpg",
                embedding=np.asarray((1.0, 0.0), dtype=np.float32),
                quality_score=1.0,
            )
        ],
    )
    cluster = _cluster(_observation("previews/assigned/frame_001.jpg"))
    assigned_candidate = ProfileCandidate(
        frame_key="previews/assigned/frame_001.jpg",
        jpeg=b"assigned-profile",
        score=2.0,
        flags=(),
        components={},
    )
    worker._analyze_frames = lambda torrent: FrameAnalysis(
        clusters=(cluster,),
        detected_face_count=1,
        profile_candidates_by_cluster_index={0: assigned_candidate},
    )

    candidate, torrent_id = asyncio.run(
        worker._best_refresh_candidate(
            actor_id="actor-existing",
            identity=identity,
            current_candidate=ProfileCandidate(
                frame_key="previews/current/frame_001.jpg",
                jpeg=b"current-profile",
                score=1.0,
                flags=(),
                components={},
            ),
            current_torrent_id="torrent-current",
        )
    )

    assert candidate == assigned_candidate
    assert torrent_id == "torrent-assigned"


def test_failure_preserves_previous_system_assignments() -> None:
    torrents = FakeCollection()
    worker = _worker(database=FakeDatabase(torrents=torrents))

    asyncio.run(
        worker._fail(
            _torrent(systemActorIds=["actor-existing"]),
            RuntimeError("boom"),
        )
    )

    values = torrents.updates[0][1]["$set"]
    assert torrents.updates[0][0] == {
        "_id": "torrent-1",
        "actorAnalysisStatus": "processing",
    }
    assert values["actorAnalysisStatus"] == "failed"
    assert values["actorAnalysisError"] == "boom"
    assert "systemActorIds" not in values
