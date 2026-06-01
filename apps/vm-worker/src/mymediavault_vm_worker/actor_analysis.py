from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Protocol

import cv2
import numpy as np


DEFAULT_MODELS_DIR = Path(".local/models")
DEFAULT_MANIFEST_PATH = Path(__file__).parents[2] / "models" / "face_models.json"
COMMENT_PATTERN = re.compile(r"//.*$", re.MULTILINE)


@dataclass(frozen=True)
class ActorAnalysisConfig:
    detector_score_threshold: float = 0.6
    detector_nms_threshold: float = 0.3
    detector_top_k: int = 5000
    min_face_size_pixels: int = 24
    min_face_area_ratio: float = 0.0003
    within_torrent_cosine_threshold: float = 0.34
    min_relative_cluster_frequency: float = 0.75
    min_relative_cluster_quality: float = 0.9
    actor_candidate_cosine_threshold: float = 0.43
    actor_match_cosine_threshold: float = 0.28
    actor_match_average_cosine_threshold: float = 0.38
    actor_match_min_fraction: float = 0.5
    actor_match_ambiguity_margin: float = 0.04
    min_cluster_distinct_frames: int = 2
    max_main_actors_per_torrent: int = 3
    max_exemplars_per_actor: int = 12
    max_exemplars_per_torrent: int = 2
    near_duplicate_cosine_threshold: float = 0.95


@dataclass(frozen=True)
class FaceModels:
    yunet_path: Path
    sface_path: Path
    yunet_version: str
    sface_version: str

    @property
    def version(self) -> str:
        return f"{self.yunet_version}+{self.sface_version}"

    @classmethod
    def from_manifest(
        cls,
        *,
        models_dir: Path = DEFAULT_MODELS_DIR,
        manifest_path: Path = DEFAULT_MANIFEST_PATH,
    ) -> FaceModels:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        models = manifest["models"]
        return cls(
            yunet_path=models_dir / models["yunet"]["filename"],
            sface_path=models_dir / models["sface"]["filename"],
            yunet_version=models["yunet"]["version"],
            sface_version=models["sface"]["version"],
        )

    def require_files(self) -> None:
        for path in (self.yunet_path, self.sface_path):
            if not path.is_file():
                raise FileNotFoundError(
                    f"Missing face model {path}. Run scripts/download_face_models.py."
                )


@dataclass(frozen=True)
class FaceObservation:
    frame_key: str
    embedding: np.ndarray
    detector_score: float
    quality_score: float
    box: tuple[int, int, int, int]


@dataclass(frozen=True)
class FaceCluster:
    observations: tuple[FaceObservation, ...]
    centroid: np.ndarray
    quality_score: float

    @property
    def distinct_frame_count(self) -> int:
        return len({observation.frame_key for observation in self.observations})


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


class ActorFrameAnalyzer(Protocol):
    @property
    def config(self) -> ActorAnalysisConfig: ...

    def analyze_frames(self, frame_paths: Iterable[Path]) -> list[FaceObservation]: ...

    def main_clusters(
        self, observations: Iterable[FaceObservation]
    ) -> list[FaceCluster]: ...


class YuNetSFaceAnalyzer:
    def __init__(
        self,
        *,
        models: FaceModels,
        config: ActorAnalysisConfig | None = None,
    ) -> None:
        models.require_files()
        self._config = config or ActorAnalysisConfig()
        self._detector = cv2.FaceDetectorYN.create(
            str(models.yunet_path),
            "",
            (320, 320),
            self._config.detector_score_threshold,
            self._config.detector_nms_threshold,
            self._config.detector_top_k,
        )
        self._recognizer = cv2.FaceRecognizerSF.create(str(models.sface_path), "")

    @property
    def config(self) -> ActorAnalysisConfig:
        return self._config

    def analyze_frames(self, frame_paths: Iterable[Path]) -> list[FaceObservation]:
        observations: list[FaceObservation] = []
        for path in sorted(frame_paths):
            image = cv2.imread(str(path))
            if image is None:
                raise ValueError(f"Unable to decode preview frame: {path}")
            height, width = image.shape[:2]
            self._detector.setInputSize((width, height))
            _, faces = self._detector.detect(image)
            if faces is None:
                continue
            for face in faces:
                box = _face_box(face, width=width, height=height)
                if not self._is_large_enough(box, width=width, height=height):
                    continue
                aligned = self._recognizer.alignCrop(image, face)
                embedding = normalize_embedding(self._recognizer.feature(aligned))
                observations.append(
                    FaceObservation(
                        frame_key=path.name,
                        embedding=embedding,
                        detector_score=float(face[-1]),
                        quality_score=_quality_score(
                            image,
                            box=box,
                            detector_score=float(face[-1]),
                        ),
                        box=box,
                    )
                )
        return observations

    def main_clusters(
        self, observations: Iterable[FaceObservation]
    ) -> list[FaceCluster]:
        clusters = cluster_observations(
            observations,
            cosine_threshold=self._config.within_torrent_cosine_threshold,
        )
        return select_main_clusters(clusters, config=self._config)

    def profile_crop(
        self,
        *,
        frame_path: Path,
        observation: FaceObservation,
        size: int = 256,
        padding_ratio: float = 0.35,
    ) -> bytes:
        image = cv2.imread(str(frame_path))
        if image is None:
            raise ValueError(f"Unable to decode preview frame: {frame_path}")
        height, width = image.shape[:2]
        x, y, box_width, box_height = observation.box
        side = max(box_width, box_height) * (1 + padding_ratio * 2)
        center_x = x + box_width / 2
        center_y = y + box_height / 2
        left = max(0, int(round(center_x - side / 2)))
        top = max(0, int(round(center_y - side / 2)))
        right = min(width, int(round(center_x + side / 2)))
        bottom = min(height, int(round(center_y + side / 2)))
        crop = image[top:bottom, left:right]
        if crop.size == 0:
            raise ValueError(f"Unable to crop detected face from: {frame_path}")
        resized = cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)
        encoded, jpeg = cv2.imencode(".jpg", resized)
        if not encoded:
            raise ValueError(f"Unable to encode actor profile image from: {frame_path}")
        return jpeg.tobytes()

    def _is_large_enough(
        self,
        box: tuple[int, int, int, int],
        *,
        width: int,
        height: int,
    ) -> bool:
        _, _, box_width, box_height = box
        return (
            min(box_width, box_height) >= self._config.min_face_size_pixels
            and box_width * box_height / (width * height)
            >= self._config.min_face_area_ratio
        )


def select_main_clusters(
    clusters: Iterable[FaceCluster],
    *,
    config: ActorAnalysisConfig,
) -> list[FaceCluster]:
    qualifying = [
        cluster
        for cluster in clusters
        if cluster.distinct_frame_count >= config.min_cluster_distinct_frames
    ]
    qualifying.sort(
        key=lambda cluster: (
            cluster.distinct_frame_count,
            cluster.quality_score,
            len(cluster.observations),
        ),
        reverse=True,
    )
    if not qualifying:
        return []
    dominant = qualifying[0]
    return [
        cluster
        for cluster in qualifying
        if (
            cluster.distinct_frame_count / dominant.distinct_frame_count
            >= config.min_relative_cluster_frequency
            and cluster.quality_score / dominant.quality_score
            >= config.min_relative_cluster_quality
        )
    ][: config.max_main_actors_per_torrent]


class InMemoryActorIndex:
    def __init__(
        self,
        *,
        config: ActorAnalysisConfig | None = None,
        actors: Iterable[ActorIdentity] = (),
        actor_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._config = config or ActorAnalysisConfig()
        self._actors = list(actors)
        self._actor_id_factory = actor_id_factory

    @property
    def actors(self) -> tuple[ActorIdentity, ...]:
        return tuple(self._actors)

    def assign(
        self,
        *,
        torrent_key: str,
        clusters: Iterable[FaceCluster],
        detected_face_count: int,
    ) -> TorrentAssignment:
        actor_ids: list[str] = []
        unresolved_cluster_count = 0
        cluster_list = list(clusters)
        for cluster in cluster_list:
            match = self._match(cluster)
            if match is None:
                actor = ActorIdentity(actor_id=self._new_actor_id())
                self._actors.append(actor)
            elif not isinstance(match, ActorIdentity):
                unresolved_cluster_count += 1
                continue
            else:
                actor = match
            self._retain_exemplars(
                actor=actor,
                torrent_key=torrent_key,
                observations=cluster.observations,
            )
            actor_ids.append(actor.actor_id)
        return TorrentAssignment(
            torrent_key=torrent_key,
            actor_ids=tuple(dict.fromkeys(actor_ids)),
            unresolved_cluster_count=unresolved_cluster_count,
            detected_face_count=detected_face_count,
            qualifying_cluster_count=len(cluster_list),
        )

    def _match(
        self, cluster: FaceCluster
    ) -> ActorIdentity | Literal["ambiguous"] | None:
        candidates: list[tuple[float, ActorIdentity]] = []
        for actor in self._actors:
            centroid_similarity = cosine_similarity(cluster.centroid, actor.centroid)
            if centroid_similarity < self._config.actor_candidate_cosine_threshold:
                continue
            observation_scores = [
                max(
                    cosine_similarity(observation.embedding, exemplar.embedding)
                    for exemplar in actor.exemplars
                )
                for observation in cluster.observations
            ]
            matching_fraction = sum(
                score >= self._config.actor_match_cosine_threshold
                for score in observation_scores
            ) / len(observation_scores)
            if matching_fraction < self._config.actor_match_min_fraction:
                continue
            average_similarity = sum(observation_scores) / len(observation_scores)
            if average_similarity < self._config.actor_match_average_cosine_threshold:
                continue
            candidates.append((average_similarity, actor))
        candidates.sort(key=lambda value: value[0], reverse=True)
        if not candidates:
            return None
        if (
            len(candidates) > 1
            and candidates[0][0] - candidates[1][0]
            < self._config.actor_match_ambiguity_margin
        ):
            return _AMBIGUOUS
        return candidates[0][1]

    def _retain_exemplars(
        self,
        *,
        actor: ActorIdentity,
        torrent_key: str,
        observations: Iterable[FaceObservation],
    ) -> None:
        candidates = sorted(
            observations,
            key=lambda observation: observation.quality_score,
            reverse=True,
        )
        per_torrent_count = sum(
            exemplar.torrent_key == torrent_key for exemplar in actor.exemplars
        )
        for observation in candidates:
            if per_torrent_count >= self._config.max_exemplars_per_torrent:
                break
            if any(
                cosine_similarity(observation.embedding, exemplar.embedding)
                >= self._config.near_duplicate_cosine_threshold
                for exemplar in actor.exemplars
            ):
                continue
            exemplar = ActorExemplar(
                torrent_key=torrent_key,
                frame_key=observation.frame_key,
                embedding=observation.embedding,
                quality_score=observation.quality_score,
            )
            if len(actor.exemplars) < self._config.max_exemplars_per_actor:
                actor.exemplars.append(exemplar)
                per_torrent_count += 1
                continue
            lowest_index = min(
                range(len(actor.exemplars)),
                key=lambda index: actor.exemplars[index].quality_score,
            )
            lowest = actor.exemplars[lowest_index]
            if lowest.quality_score >= exemplar.quality_score:
                continue
            actor.exemplars[lowest_index] = exemplar
            if lowest.torrent_key == torrent_key:
                per_torrent_count -= 1
            per_torrent_count += 1

    def _new_actor_id(self) -> str:
        if self._actor_id_factory is not None:
            return self._actor_id_factory()
        return f"actor-{len(self._actors) + 1}"


def cluster_observations(
    observations: Iterable[FaceObservation],
    *,
    cosine_threshold: float,
) -> list[FaceCluster]:
    clusters: list[list[FaceObservation]] = []
    for observation in sorted(
        observations,
        key=lambda value: value.quality_score,
        reverse=True,
    ):
        best_index: int | None = None
        best_similarity = -1.0
        for index, cluster in enumerate(clusters):
            similarity = cosine_similarity(
                observation.embedding,
                normalized_mean(value.embedding for value in cluster),
            )
            if similarity >= cosine_threshold and similarity > best_similarity:
                best_index = index
                best_similarity = similarity
        if best_index is None:
            clusters.append([observation])
        else:
            clusters[best_index].append(observation)
    return [
        FaceCluster(
            observations=tuple(cluster),
            centroid=normalized_mean(value.embedding for value in cluster),
            quality_score=sum(value.quality_score for value in cluster) / len(cluster),
        )
        for cluster in clusters
    ]


def evaluate_fixture_partitions(
    *,
    previews_dir: Path,
    ground_truth_path: Path,
    analyzer: ActorFrameAnalyzer,
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


def normalize_embedding(value: np.ndarray) -> np.ndarray:
    embedding = np.asarray(value, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(embedding))
    if norm == 0:
        raise ValueError("Face embedding must not be zero.")
    return embedding / norm


def normalized_mean(values: Iterable[np.ndarray]) -> np.ndarray:
    embeddings = [normalize_embedding(value) for value in values]
    if not embeddings:
        raise ValueError("At least one face embedding is required.")
    return normalize_embedding(np.mean(embeddings, axis=0))


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.dot(normalize_embedding(left), normalize_embedding(right)))


def _face_box(
    face: np.ndarray,
    *,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    x, y, box_width, box_height = (int(round(float(value))) for value in face[:4])
    x = max(0, x)
    y = max(0, y)
    box_width = max(0, min(width - x, box_width))
    box_height = max(0, min(height - y, box_height))
    return x, y, box_width, box_height


def _quality_score(
    image: np.ndarray,
    *,
    box: tuple[int, int, int, int],
    detector_score: float,
) -> float:
    x, y, width, height = box
    crop = image[y : y + height, x : x + width]
    if crop.size == 0:
        return detector_score
    sharpness = float(cv2.Laplacian(crop, cv2.CV_64F).var())
    return detector_score + min(1.0, math.log1p(sharpness) / 10.0)


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


_AMBIGUOUS: Literal["ambiguous"] = "ambiguous"
