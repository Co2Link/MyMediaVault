from __future__ import annotations

from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from mymediavault_vm_worker.actor_analysis import (
    ActorAnalysisConfig,
    FaceCluster,
    FaceObservation,
    InMemoryActorIndex,
    TorrentAssignment,
    YuNetSFaceAnalyzer,
    cosine_similarity,
    evaluate_fixture_partitions,
    normalize_embedding,
    normalized_mean,
    select_main_clusters,
)


def _observation(
    frame_key: str,
    embedding: tuple[float, ...],
    *,
    quality_score: float = 1.0,
) -> FaceObservation:
    return FaceObservation(
        frame_key=frame_key,
        embedding=normalize_embedding(np.array(embedding, dtype=np.float32)),
        detector_score=0.9,
        quality_score=quality_score,
        box=(10, 10, 30, 30),
    )


def _cluster(*observations: FaceObservation) -> FaceCluster:
    return FaceCluster(
        observations=observations,
        centroid=normalized_mean(value.embedding for value in observations),
        quality_score=sum(value.quality_score for value in observations)
        / len(observations),
    )


def test_select_main_clusters_filters_weak_incidental_faces() -> None:
    dominant = _cluster(
        _observation("frame_001.jpg", (1.0, 0.0), quality_score=1.0),
        _observation("frame_002.jpg", (1.0, 0.0), quality_score=1.0),
        _observation("frame_003.jpg", (1.0, 0.0), quality_score=1.0),
    )
    infrequent = _cluster(
        _observation("frame_001.jpg", (0.0, 1.0), quality_score=1.0),
        _observation("frame_002.jpg", (0.0, 1.0), quality_score=1.0),
    )
    low_quality = _cluster(
        _observation("frame_001.jpg", (-1.0, 0.0), quality_score=0.8),
        _observation("frame_002.jpg", (-1.0, 0.0), quality_score=0.8),
        _observation("frame_003.jpg", (-1.0, 0.0), quality_score=0.8),
    )

    selected = select_main_clusters(
        [infrequent, low_quality, dominant],
        config=ActorAnalysisConfig(),
    )

    assert selected == [dominant]


def test_index_reuses_identity_with_multi_frame_evidence() -> None:
    index = InMemoryActorIndex(config=ActorAnalysisConfig())
    first = _cluster(
        _observation("frame_001.jpg", (1.0, 0.0)),
        _observation("frame_002.jpg", (0.99, 0.01)),
    )
    matching = _cluster(
        _observation("frame_001.jpg", (0.98, 0.02)),
        _observation("frame_002.jpg", (0.97, 0.03)),
    )

    created = index.assign(
        torrent_key="torrent-1", clusters=[first], detected_face_count=2
    )
    reused = index.assign(
        torrent_key="torrent-2",
        clusters=[matching],
        detected_face_count=2,
    )

    assert created.actor_ids == ("actor-1",)
    assert reused.actor_ids == ("actor-1",)
    assert len(index.actors) == 1


def test_index_leaves_ambiguous_cluster_unassigned() -> None:
    config = ActorAnalysisConfig(actor_match_ambiguity_margin=0.1)
    index = InMemoryActorIndex(config=config)
    index.assign(
        torrent_key="torrent-1",
        clusters=[
            _cluster(
                _observation("frame_001.jpg", (1.0, 0.0)),
                _observation("frame_002.jpg", (0.99, 0.01)),
            )
        ],
        detected_face_count=2,
    )
    index.assign(
        torrent_key="torrent-2",
        clusters=[
            _cluster(
                _observation("frame_001.jpg", (0.0, 1.0)),
                _observation("frame_002.jpg", (0.01, 0.99)),
            )
        ],
        detected_face_count=2,
    )

    assignment = index.assign(
        torrent_key="torrent-3",
        clusters=[
            _cluster(
                _observation("frame_001.jpg", (0.7, 0.7)),
                _observation("frame_002.jpg", (0.71, 0.69)),
            )
        ],
        detected_face_count=2,
    )

    assert assignment == TorrentAssignment(
        torrent_key="torrent-3",
        actor_ids=(),
        unresolved_cluster_count=1,
        detected_face_count=2,
        qualifying_cluster_count=1,
    )


def test_actor_exemplars_are_capped_per_torrent() -> None:
    config = ActorAnalysisConfig(near_duplicate_cosine_threshold=1.1)
    index = InMemoryActorIndex(config=config)
    index.assign(
        torrent_key="torrent-1",
        clusters=[
            _cluster(
                _observation("frame_001.jpg", (1.0, 0.0)),
                _observation("frame_002.jpg", (0.99, 0.01)),
                _observation("frame_003.jpg", (0.98, 0.02)),
            )
        ],
        detected_face_count=3,
    )

    assert len(index.actors[0].exemplars) == 2


def test_profile_crop_returns_square_jpeg(tmp_path: Path) -> None:
    frame_path = tmp_path / "frame.jpg"
    image = np.zeros((100, 160, 3), dtype=np.uint8)
    image[20:80, 50:110] = 255
    assert cv2.imwrite(str(frame_path), image)
    analyzer = object.__new__(YuNetSFaceAnalyzer)

    result = analyzer.profile_crop(
        frame_path=frame_path,
        observation=_observation("frame.jpg", (1.0, 0.0)),
    )

    decoded = cv2.imdecode(np.frombuffer(result, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[:2] == (256, 256)


def test_cosine_similarity_uses_normalized_embeddings() -> None:
    assert cosine_similarity(np.array([2.0, 0.0]), np.array([4.0, 0.0])) == 1.0


def test_fixture_evaluator_compares_identity_partitions(tmp_path: Path) -> None:
    previews_dir = tmp_path / "previews"
    for torrent_key in ("torrent-1", "torrent-2", "torrent-3"):
        torrent_dir = previews_dir / torrent_key
        torrent_dir.mkdir(parents=True)
        (torrent_dir / "frame_001.jpg").touch()
    ground_truth_path = tmp_path / "GT.json"
    ground_truth_path.write_text(
        '{"expected-1": ["torrent-1", "torrent-2"], "expected-2": ["torrent-3"]}',
        encoding="utf-8",
    )

    class FakeAnalyzer:
        config = ActorAnalysisConfig()

        @staticmethod
        def analyze_frames(frame_paths: Iterable[Path]) -> list[FaceObservation]:
            frame_path = next(iter(frame_paths))
            return [_observation(frame_path.parent.name, (1.0, 0.0))]

        @staticmethod
        def main_clusters(observations: Iterable[FaceObservation]) -> list[FaceCluster]:
            torrent_key = next(iter(observations)).frame_key
            embedding = (1.0, 0.0) if torrent_key != "torrent-3" else (0.0, 1.0)
            return [
                _cluster(
                    _observation("frame_001.jpg", embedding),
                    _observation("frame_002.jpg", embedding),
                )
            ]

    result = evaluate_fixture_partitions(
        previews_dir=previews_dir,
        ground_truth_path=ground_truth_path,
        analyzer=FakeAnalyzer(),
    )

    assert result["passed"] is True
    assert result["generatedActorCount"] == 2
