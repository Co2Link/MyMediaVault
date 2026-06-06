from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Literal

from mymediavault_vm_worker.actor.config import ActorAnalysisConfig
from mymediavault_vm_worker.actor.math import cosine_similarity
from mymediavault_vm_worker.actor.models import (
    ActorExemplar,
    ActorIdentity,
    FaceCluster,
    FaceObservation,
    TorrentAssignment,
)

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
        assigned_cluster_indices: list[int] = []
        for cluster_index, cluster in enumerate(cluster_list):
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
            if actor.actor_id not in actor_ids:
                actor_ids.append(actor.actor_id)
                assigned_cluster_indices.append(cluster_index)
        return TorrentAssignment(
            torrent_key=torrent_key,
            actor_ids=tuple(actor_ids),
            unresolved_cluster_count=unresolved_cluster_count,
            detected_face_count=detected_face_count,
            qualifying_cluster_count=len(cluster_list),
            assigned_cluster_indices=tuple(assigned_cluster_indices),
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

    def match(
        self, cluster: FaceCluster
    ) -> ActorIdentity | Literal["ambiguous"] | None:
        return self._match(cluster)

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




_AMBIGUOUS: Literal["ambiguous"] = "ambiguous"
