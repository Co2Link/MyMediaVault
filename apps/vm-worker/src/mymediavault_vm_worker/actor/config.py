from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODELS_DIR = Path(".local/models")
DEFAULT_MANIFEST_PATH = Path(__file__).parents[3] / "models" / "face_models.json"

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
    max_profile_candidates_per_cluster: int = 5
    profile_replacement_margin: float = 0.1
    min_preferred_profile_face_pixels: int = 72
    profile_candidate_cosine_threshold: float = 0.25


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

