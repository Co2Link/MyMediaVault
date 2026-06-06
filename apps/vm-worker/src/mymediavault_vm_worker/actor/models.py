from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from mymediavault_vm_worker.actor.math import normalized_mean

@dataclass(frozen=True)
class FaceObservation:
    frame_key: str
    embedding: np.ndarray
    detector_score: float
    quality_score: float
    box: tuple[int, int, int, int]
    landmarks: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class FaceCluster:
    observations: tuple[FaceObservation, ...]
    centroid: np.ndarray
    quality_score: float

    @property
    def distinct_frame_count(self) -> int:
        return len({observation.frame_key for observation in self.observations})


@dataclass(frozen=True)
class ProfileCandidate:
    frame_key: str
    jpeg: bytes
    score: float
    flags: tuple[str, ...]
    components: dict[str, float]


@dataclass(frozen=True)
class ActorExemplar:
    torrent_key: str
    frame_key: str
    embedding: np.ndarray
    quality_score: float


@dataclass
class ActorIdentity:
    actor_id: str
    exemplars: list[ActorExemplar] = field(default_factory=list)

    @property
    def centroid(self) -> np.ndarray:
        return normalized_mean(exemplar.embedding for exemplar in self.exemplars)


@dataclass(frozen=True)
class TorrentAssignment:
    torrent_key: str
    actor_ids: tuple[str, ...]
    unresolved_cluster_count: int
    detected_face_count: int
    qualifying_cluster_count: int
    assigned_cluster_indices: tuple[int, ...] = ()


