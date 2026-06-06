from __future__ import annotations

from collections.abc import Iterable

from mymediavault_vm_worker.actor.config import ActorAnalysisConfig
from mymediavault_vm_worker.actor.math import cosine_similarity, normalized_mean
from mymediavault_vm_worker.actor.models import FaceCluster, FaceObservation

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


