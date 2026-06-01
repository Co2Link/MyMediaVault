from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import time
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import numpy as np
from loguru import logger
from pymongo import ReturnDocument

from .actor_analysis import (
    ActorAnalysisConfig,
    ActorExemplar,
    ActorIdentity,
    FaceCluster,
    FaceObservation,
    InMemoryActorIndex,
)

ACTOR_ANALYSIS_ALGORITHM_VERSION = "actor-analysis-v1"
DEFAULT_ACTOR_ANALYSIS_MAX_ATTEMPTS = 3
DEFAULT_ACTOR_ANALYSIS_LEASE_SECONDS = 1800
DEFAULT_ACTOR_ANALYSIS_POLL_INTERVAL_SECONDS = 5.0


class ActorBlobStore(Protocol):
    def get_bytes(self, key: str) -> bytes: ...

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> str: ...

    async def delete_if_exists(self, key: str) -> None: ...


class RuntimeActorAnalyzer(Protocol):
    @property
    def config(self) -> ActorAnalysisConfig: ...

    def analyze_frames(self, frame_paths: list[Path]) -> list[FaceObservation]: ...

    def main_clusters(
        self, observations: list[FaceObservation]
    ) -> list[FaceCluster]: ...

    def profile_crop(
        self,
        *,
        frame_path: Path,
        observation: FaceObservation,
        size: int = 256,
        padding_ratio: float = 0.35,
    ) -> bytes: ...


@dataclass(frozen=True)
class FrameAnalysis:
    clusters: tuple[FaceCluster, ...]
    detected_face_count: int
    profile_jpegs_by_frame_key: dict[str, bytes]


class ActorAnalysisWorker:
    def __init__(
        self,
        *,
        database: Any,
        blob_store: ActorBlobStore,
        analyzer: RuntimeActorAnalyzer,
        model_version: str,
        poll_interval_seconds: float = DEFAULT_ACTOR_ANALYSIS_POLL_INTERVAL_SECONDS,
        lease_seconds: int = DEFAULT_ACTOR_ANALYSIS_LEASE_SECONDS,
        max_attempts: int = DEFAULT_ACTOR_ANALYSIS_MAX_ATTEMPTS,
    ) -> None:
        self._torrents = database["torrents"]
        self._actors = database["actors"]
        self._blob_store = blob_store
        self._analyzer = analyzer
        self._model_version = model_version
        self._poll_interval_seconds = max(0.5, poll_interval_seconds)
        self._lease_seconds = max(60, lease_seconds)
        self._max_attempts = max(1, max_attempts)
        self._stopping = False
        self._fingerprint_prefix = self._build_fingerprint_prefix()

    async def run(self) -> None:
        logger.info(
            "Actor analysis worker started with model_version={} algorithm_version={} max_attempts={}",
            self._model_version,
            ACTOR_ANALYSIS_ALGORITHM_VERSION,
            self._max_attempts,
        )
        while not self._stopping:
            await self._repair_stale_processing()
            torrent = await self._claim_one()
            if torrent is None:
                await asyncio.sleep(self._poll_interval_seconds)
                continue
            await self._run_claimed(torrent)

    def stop(self) -> None:
        self._stopping = True

    async def _run_claimed(self, torrent: dict[str, Any]) -> None:
        try:
            await self._process(torrent)
        except Exception as error:
            logger.exception(
                "Unexpected actor analysis failure for torrent {}",
                torrent["_id"],
            )
            await self._fail(torrent, error)

    async def _claim_one(self) -> dict[str, Any] | None:
        for query, reset_attempts in self._claim_plans():
            now = datetime.now(UTC)
            lease_until = now + timedelta(seconds=self._lease_seconds)
            attempt_update = (
                {
                    "$set": {
                        "actorAnalysisStatus": "processing",
                        "actorAnalysisAttempts": 1,
                        "actorAnalysisLastAttemptAt": now,
                        "actorAnalysisLeaseUntil": lease_until,
                        "actorAnalysisError": None,
                    }
                }
                if reset_attempts
                else {
                    "$set": {
                        "actorAnalysisStatus": "processing",
                        "actorAnalysisLastAttemptAt": now,
                        "actorAnalysisLeaseUntil": lease_until,
                        "actorAnalysisError": None,
                    },
                    "$inc": {"actorAnalysisAttempts": 1},
                }
            )
            document = await self._torrents.find_one_and_update(
                query,
                attempt_update,
                sort=[("actorAnalysisUpdatedAt", 1), ("updatedAt", 1), ("_id", 1)],
                return_document=ReturnDocument.AFTER,
            )
            if document is not None:
                return document
        return None

    def _claim_plans(self) -> list[tuple[dict[str, Any], bool]]:
        base = self._eligible_query()
        available_lease = self._available_lease_query()
        available_attempt = {
            "$or": [
                {"actorAnalysisAttempts": {"$lt": self._max_attempts}},
                {"actorAnalysisAttempts": {"$exists": False}},
            ]
        }
        return [
            (
                {
                    "$and": [
                        base,
                        available_lease,
                        available_attempt,
                        {
                            "$or": [
                                {"actorAnalysisStatus": "pending"},
                                {"actorAnalysisStatus": {"$exists": False}},
                            ]
                        },
                    ]
                },
                False,
            ),
            (
                {
                    "$and": [
                        base,
                        available_lease,
                        {"actorAnalysisStatus": "succeeded"},
                        self._stale_fingerprint_query(),
                    ]
                },
                True,
            ),
            (
                {
                    "$and": [
                        base,
                        available_lease,
                        available_attempt,
                        {"actorAnalysisStatus": "failed"},
                    ]
                },
                False,
            ),
        ]

    def _eligible_query(self) -> dict[str, Any]:
        return {
            "$or": [
                {
                    "previewStatus": "succeeded",
                    "previewFrames.0": {"$exists": True},
                },
                {
                    "previewStatus": "partial",
                    "previewFrames.1": {"$exists": True},
                },
            ]
        }

    @staticmethod
    def _available_lease_query() -> dict[str, Any]:
        now = datetime.now(UTC)
        return {
            "$or": [
                {"actorAnalysisLeaseUntil": None},
                {"actorAnalysisLeaseUntil": {"$lt": now}},
                {"actorAnalysisLeaseUntil": {"$exists": False}},
            ]
        }

    def _stale_fingerprint_query(self) -> dict[str, Any]:
        return {
            "$expr": {
                "$ne": [
                    {"$ifNull": ["$actorAnalysisFingerprint", ""]},
                    {
                        "$concat": [
                            self._fingerprint_prefix,
                            {
                                "$ifNull": [
                                    "$previewDiagnostics.artifactFingerprint",
                                    "",
                                ]
                            },
                        ]
                    },
                ]
            }
        }

    async def _repair_stale_processing(self) -> None:
        now = datetime.now(UTC)
        result = await self._torrents.update_many(
            {
                "actorAnalysisStatus": "processing",
                "$or": [
                    {"actorAnalysisLeaseUntil": None},
                    {"actorAnalysisLeaseUntil": {"$lt": now}},
                    {"actorAnalysisLeaseUntil": {"$exists": False}},
                ],
            },
            {
                "$set": {
                    "actorAnalysisStatus": "pending",
                    "actorAnalysisLeaseUntil": None,
                    "actorAnalysisError": "Actor analysis lease expired and was requeued.",
                }
            },
        )
        if result.modified_count:
            logger.info("Requeued {} stale actor analysis jobs", result.modified_count)

    async def _process(self, torrent: dict[str, Any]) -> None:
        started_at = time.monotonic()
        frame_analysis = await asyncio.to_thread(self._analyze_frames, torrent)
        actor_documents = await self._load_active_actor_documents()
        actors_by_id = {str(actor["_id"]): actor for actor in actor_documents}
        identities = [self._to_identity(actor) for actor in actor_documents]
        index = InMemoryActorIndex(
            config=self._analyzer.config,
            actors=identities,
            actor_id_factory=lambda: str(uuid4()),
        )
        assignment = index.assign(
            torrent_key=str(torrent["_id"]),
            clusters=frame_analysis.clusters,
            detected_face_count=frame_analysis.detected_face_count,
        )
        identities_by_id = {identity.actor_id: identity for identity in index.actors}
        for actor_id in assignment.actor_ids:
            await self._persist_identity(
                identity=identities_by_id[actor_id],
                original=actors_by_id.get(actor_id),
                profile_jpegs_by_frame_key=frame_analysis.profile_jpegs_by_frame_key,
            )

        now = datetime.now(UTC)
        fingerprint = self._fingerprint_for(torrent)
        result = await self._torrents.update_one(
            {
                "_id": torrent["_id"],
                "actorAnalysisStatus": "processing",
                "previewUpdatedAt": torrent.get("previewUpdatedAt"),
            },
            {
                "$set": {
                    "systemActorIds": list(assignment.actor_ids),
                    "actorAnalysisStatus": "succeeded",
                    "actorAnalysisUpdatedAt": now,
                    "actorAnalysisLeaseUntil": None,
                    "actorAnalysisFingerprint": fingerprint,
                    "actorAnalysisError": None,
                    "actorAnalysisDiagnostics": {
                        "detectedFaceCount": assignment.detected_face_count,
                        "qualifyingClusterCount": assignment.qualifying_cluster_count,
                        "assignedActorIds": list(assignment.actor_ids),
                        "unresolvedClusterCount": assignment.unresolved_cluster_count,
                        "elapsedSeconds": round(time.monotonic() - started_at, 3),
                        "fingerprint": fingerprint,
                    },
                }
            },
        )
        if result.matched_count != 1:
            logger.info(
                "Discarded stale actor analysis result for torrent {}",
                torrent["_id"],
            )
            return
        logger.info(
            "Actor analysis succeeded for torrent {} with {} assigned actors",
            torrent["_id"],
            len(assignment.actor_ids),
        )

    async def _fail(self, torrent: dict[str, Any], error: Exception) -> None:
        message = (str(error) or error.__class__.__name__)[:500]
        await self._torrents.update_one(
            {"_id": torrent["_id"], "actorAnalysisStatus": "processing"},
            {
                "$set": {
                    "actorAnalysisStatus": "failed",
                    "actorAnalysisUpdatedAt": datetime.now(UTC),
                    "actorAnalysisLeaseUntil": None,
                    "actorAnalysisError": message,
                    "actorAnalysisDiagnostics": {"error": message},
                }
            },
        )

    def _analyze_frames(self, torrent: dict[str, Any]) -> FrameAnalysis:
        with tempfile.TemporaryDirectory(prefix="mmv-actor-analysis-") as temp_dir:
            root = Path(temp_dir)
            paths: list[Path] = []
            source_by_local_name: dict[str, str] = {}
            for index, frame in enumerate(torrent.get("previewFrames", []), start=1):
                source_key = str(frame["key"])
                path = root / f"frame_{index:03d}.jpg"
                path.write_bytes(self._blob_store.get_bytes(source_key))
                paths.append(path)
                source_by_local_name[path.name] = source_key

            observations = self._analyzer.analyze_frames(paths)
            clusters = self._analyzer.main_clusters(observations)
            profile_jpegs_by_frame_key: dict[str, bytes] = {}
            for cluster in clusters:
                best = max(
                    cluster.observations,
                    key=lambda observation: observation.quality_score,
                )
                source_key = source_by_local_name[best.frame_key]
                profile_jpegs_by_frame_key[source_key] = self._analyzer.profile_crop(
                    frame_path=root / best.frame_key,
                    observation=best,
                )

            return FrameAnalysis(
                clusters=tuple(
                    FaceCluster(
                        observations=tuple(
                            replace(
                                observation,
                                frame_key=source_by_local_name[observation.frame_key],
                            )
                            for observation in cluster.observations
                        ),
                        centroid=cluster.centroid,
                        quality_score=cluster.quality_score,
                    )
                    for cluster in clusters
                ),
                detected_face_count=len(observations),
                profile_jpegs_by_frame_key=profile_jpegs_by_frame_key,
            )

    async def _load_active_actor_documents(self) -> list[dict[str, Any]]:
        cursor = self._actors.find(
            {"faceExemplars": {"$elemMatch": {"modelVersion": self._model_version}}}
        )
        return await cursor.to_list(length=None)

    def _to_identity(self, actor: dict[str, Any]) -> ActorIdentity:
        return ActorIdentity(
            actor_id=str(actor["_id"]),
            exemplars=[
                ActorExemplar(
                    torrent_key=str(exemplar.get("sourceTorrentId") or ""),
                    frame_key=str(exemplar.get("sourceFrameKey") or ""),
                    embedding=np.asarray(exemplar["embedding"], dtype=np.float32),
                    quality_score=float(exemplar["qualityScore"]),
                )
                for exemplar in actor.get("faceExemplars", [])
                if exemplar.get("modelVersion") == self._model_version
            ],
        )

    async def _persist_identity(
        self,
        *,
        identity: ActorIdentity,
        original: dict[str, Any] | None,
        profile_jpegs_by_frame_key: dict[str, bytes],
    ) -> None:
        exemplars, centroids = self._evidence_values(identity, original)
        if original is None:
            profile_image_key = (
                f"actors/{identity.actor_id}/profile-{identity.actor_id}.jpg"
            )
            profile_jpeg = self._profile_jpeg(identity, profile_jpegs_by_frame_key)
            await self._blob_store.put_bytes(
                profile_image_key,
                profile_jpeg,
                "image/jpeg",
            )
            now = datetime.now(UTC)
            try:
                await self._actors.insert_one(
                    {
                        "_id": identity.actor_id,
                        "name": f"actor-{identity.actor_id}",
                        "description": None,
                        "profileImageKey": profile_image_key,
                        "profileImageMimeType": "image/jpeg",
                        "faceExemplars": exemplars,
                        "faceCentroids": centroids,
                        "faceExemplarRevision": 1,
                        "createdAt": now,
                        "updatedAt": now,
                    }
                )
            except Exception:
                await self._blob_store.delete_if_exists(profile_image_key)
                raise
            return

        revision = int(original.get("faceExemplarRevision", 0))
        revision_filter: dict[str, Any] = {"_id": identity.actor_id}
        if revision == 0:
            revision_filter["$or"] = [
                {"faceExemplarRevision": 0},
                {"faceExemplarRevision": {"$exists": False}},
            ]
        else:
            revision_filter["faceExemplarRevision"] = revision
        result = await self._actors.update_one(
            revision_filter,
            {
                "$set": {
                    "faceExemplars": exemplars,
                    "faceCentroids": centroids,
                    "updatedAt": datetime.now(UTC),
                },
                "$inc": {"faceExemplarRevision": 1},
            },
        )
        if result.matched_count != 1:
            msg = f"Actor {identity.actor_id} biometric evidence changed concurrently."
            raise RuntimeError(msg)

    def _evidence_values(
        self,
        identity: ActorIdentity,
        original: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        old_exemplars = [
            exemplar
            for exemplar in (original or {}).get("faceExemplars", [])
            if exemplar.get("modelVersion") != self._model_version
        ]
        old_centroids = [
            centroid
            for centroid in (original or {}).get("faceCentroids", [])
            if centroid.get("modelVersion") != self._model_version
        ]
        exemplars = [
            *old_exemplars,
            *[
                {
                    "modelVersion": self._model_version,
                    "embedding": exemplar.embedding.tolist(),
                    "qualityScore": exemplar.quality_score,
                    "sourceTorrentId": exemplar.torrent_key or None,
                    "sourceFrameKey": exemplar.frame_key or None,
                }
                for exemplar in identity.exemplars
            ],
        ]
        centroids = [
            *old_centroids,
            {
                "modelVersion": self._model_version,
                "embedding": identity.centroid.tolist(),
            },
        ]
        return exemplars, centroids

    @staticmethod
    def _profile_jpeg(
        identity: ActorIdentity,
        profile_jpegs_by_frame_key: dict[str, bytes],
    ) -> bytes:
        for exemplar in sorted(
            identity.exemplars,
            key=lambda value: value.quality_score,
            reverse=True,
        ):
            profile_jpeg = profile_jpegs_by_frame_key.get(exemplar.frame_key)
            if profile_jpeg is not None:
                return profile_jpeg
        msg = f"Missing profile crop for new actor {identity.actor_id}."
        raise RuntimeError(msg)

    def _build_fingerprint_prefix(self) -> str:
        value = json.dumps(
            {
                "algorithmVersion": ACTOR_ANALYSIS_ALGORITHM_VERSION,
                "analysisConfig": asdict(self._analyzer.config),
                "modelVersion": self._model_version,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        digest = hashlib.sha256(value).hexdigest()
        return f"sha256:{digest}:preview:"

    def _fingerprint_for(self, torrent: dict[str, Any]) -> str:
        preview_diagnostics = torrent.get("previewDiagnostics") or {}
        return self._fingerprint_prefix + str(
            preview_diagnostics.get("artifactFingerprint") or ""
        )
