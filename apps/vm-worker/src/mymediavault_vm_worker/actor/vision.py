from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path

import cv2
import numpy as np

from mymediavault_vm_worker.actor.config import ActorAnalysisConfig, FaceModels
from mymediavault_vm_worker.actor.math import cosine_similarity, normalize_embedding
from mymediavault_vm_worker.actor.models import FaceCluster, FaceObservation, ProfileCandidate
from mymediavault_vm_worker.actor.selection import cluster_observations, select_main_clusters

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
                        landmarks=_face_landmarks(face),
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
        size: int = 512,
    ) -> bytes:
        image = cv2.imread(str(frame_path))
        if image is None:
            raise ValueError(f"Unable to decode preview frame: {frame_path}")
        crop, _ = _profile_crop(image, observation)
        if crop.size == 0:
            raise ValueError(f"Unable to crop detected face from: {frame_path}")
        resized = cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)
        encoded, jpeg = cv2.imencode(".jpg", resized)
        if not encoded:
            raise ValueError(f"Unable to encode actor profile image from: {frame_path}")
        return jpeg.tobytes()

    def profile_candidates(
        self,
        *,
        frame_paths_by_key: dict[str, Path],
        cluster: FaceCluster,
        observations: Iterable[FaceObservation],
    ) -> list[ProfileCandidate]:
        observations = list(observations)
        observations_by_frame: dict[str, list[FaceObservation]] = {}
        for observation in observations:
            observations_by_frame.setdefault(observation.frame_key, []).append(observation)
        candidates: list[ProfileCandidate] = []
        profile_observations = [
            observation
            for observation in observations
            if cosine_similarity(observation.embedding, cluster.centroid)
            >= self._config.profile_candidate_cosine_threshold
        ]
        for observation in profile_observations:
            frame_path = frame_paths_by_key[observation.frame_key]
            image = cv2.imread(str(frame_path))
            if image is None:
                raise ValueError(f"Unable to decode preview frame: {frame_path}")
            crop, bounds = _profile_crop(image, observation)
            components, flags = _profile_score(
                image,
                observation=observation,
                crop_bounds=bounds,
                frame_observations=observations_by_frame[observation.frame_key],
                min_preferred_face_pixels=self._config.min_preferred_profile_face_pixels,
            )
            if "edge-clipped" in flags:
                continue
            resized = cv2.resize(crop, (512, 512), interpolation=cv2.INTER_AREA)
            encoded, jpeg = cv2.imencode(".jpg", resized)
            if not encoded:
                raise ValueError(
                    f"Unable to encode actor profile image from: {frame_path}"
                )
            candidates.append(
                ProfileCandidate(
                    frame_key=observation.frame_key,
                    jpeg=jpeg.tobytes(),
                    score=round(sum(components.values()), 6),
                    flags=tuple(flags),
                    components=components,
                )
            )
        return sorted(candidates, key=profile_candidate_sort_key, reverse=True)[
            : self._config.max_profile_candidates_per_cluster
        ]

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


def _face_landmarks(face: np.ndarray) -> tuple[tuple[float, float], ...]:
    return tuple(
        (float(face[index]), float(face[index + 1])) for index in range(4, 14, 2)
    )


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


def _profile_crop(
    image: np.ndarray,
    observation: FaceObservation,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    x, y, width, height = observation.box
    side = max(width, height) / 0.60
    center_x = x + width / 2
    eye_y = (
        sum(point[1] for point in observation.landmarks[:2]) / 2
        if len(observation.landmarks) >= 2
        else y + height * 0.4
    )
    left = int(round(center_x - side / 2))
    top = int(round(eye_y - side * 0.38))
    right = int(round(left + side))
    bottom = int(round(top + side))
    image_height, image_width = image.shape[:2]
    pad_left = max(0, -left)
    pad_top = max(0, -top)
    pad_right = max(0, right - image_width)
    pad_bottom = max(0, bottom - image_height)
    if pad_left or pad_top or pad_right or pad_bottom:
        extended = cv2.copyMakeBorder(
            image,
            pad_top,
            pad_bottom,
            pad_left,
            pad_right,
            cv2.BORDER_REPLICATE,
        )
        blurred = cv2.GaussianBlur(extended, (0, 0), sigmaX=32, sigmaY=32)
        blurred[
            pad_top : pad_top + image_height,
            pad_left : pad_left + image_width,
        ] = image
        image = blurred
    return (
        image[
            top + pad_top : bottom + pad_top,
            left + pad_left : right + pad_left,
        ],
        (left, top, right, bottom),
    )


def _profile_score(
    image: np.ndarray,
    *,
    observation: FaceObservation,
    crop_bounds: tuple[int, int, int, int],
    frame_observations: Iterable[FaceObservation],
    min_preferred_face_pixels: int = 72,
) -> tuple[dict[str, float], list[str]]:
    x, y, width, height = observation.box
    image_height, image_width = image.shape[:2]
    face = image[y : y + height, x : x + width]
    sharpness = (
        float(cv2.Laplacian(face, cv2.CV_64F).var()) if face.size else 0.0
    )
    luminance = float(cv2.cvtColor(face, cv2.COLOR_BGR2GRAY).mean()) if face.size else 0
    lighting = max(0.0, 1.0 - abs(luminance - 128.0) / 128.0)
    components = {
        "detectorConfidence": observation.detector_score,
        "sharpness": min(1.0, math.log1p(sharpness) / 10.0),
        "faceResolution": min(0.5, min(width, height) / 256.0 * 0.5),
        "lighting": lighting * 0.25,
    }
    flags: list[str] = []
    if min(width, height) < min_preferred_face_pixels:
        flags.append("low-resolution")
    if x <= 0 or y <= 0 or x + width >= image_width or y + height >= image_height:
        components["edgeClippingPenalty"] = -1.0
        flags.append("edge-clipped")
    if luminance < 45:
        flags.append("low-light")
    elif luminance > 215:
        flags.append("overexposed")
    if len(observation.landmarks) >= 5:
        right_eye, left_eye, nose, right_mouth, left_mouth = observation.landmarks
        eye_span = max(1.0, abs(left_eye[0] - right_eye[0]))
        roll_degrees = abs(
            math.degrees(
                math.atan2(left_eye[1] - right_eye[1], left_eye[0] - right_eye[0])
            )
        )
        roll_penalty = min(0.45, max(0.0, roll_degrees - 8.0) / 45.0 * 0.45)
        if roll_penalty:
            components["rollPenalty"] = -roll_penalty
            flags.append("head-roll")
        eye_mid_x = (right_eye[0] + left_eye[0]) / 2
        mouth_mid_y = (right_mouth[1] + left_mouth[1]) / 2
        yaw_ratio = abs(nose[0] - eye_mid_x) / eye_span
        pitch_ratio = (nose[1] - (right_eye[1] + left_eye[1]) / 2) / max(
            1.0, mouth_mid_y - (right_eye[1] + left_eye[1]) / 2
        )
        pose_penalty = min(
            0.6,
            max(0.0, yaw_ratio - 0.18) * 1.4
            + max(0.0, abs(pitch_ratio - 0.55) - 0.25) * 0.8,
        )
        if pose_penalty:
            components["posePenalty"] = -pose_penalty
            flags.append("non-frontal")
    left, top, right, bottom = crop_bounds
    crop_width = max(1, right - left)
    crop_height = max(1, bottom - top)
    padded_area = crop_width * crop_height - (
        max(0, min(right, image_width) - max(left, 0))
        * max(0, min(bottom, image_height) - max(top, 0))
    )
    padding_ratio = padded_area / (crop_width * crop_height)
    if padding_ratio:
        components["paddingPenalty"] = -min(0.35, padding_ratio * 0.7)
        flags.append("padded")
    additional_faces = sum(
        1
        for other in frame_observations
        if other is not observation
        and _box_center_inside(other.box, left=left, top=top, right=right, bottom=bottom)
    )
    if additional_faces:
        components["additionalFacePenalty"] = -min(0.75, additional_faces * 0.5)
        flags.append("multi-face")
    return components, flags


def profile_candidate_sort_key(candidate: ProfileCandidate) -> tuple[bool, bool, float]:
    flags = set(candidate.flags)
    preferred_frontal = not flags.intersection(
        {"head-roll", "low-resolution", "non-frontal"}
    )
    single_face = "multi-face" not in flags
    return preferred_frontal, single_face, candidate.score


def _box_center_inside(
    box: tuple[int, int, int, int],
    *,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> bool:
    x, y, width, height = box
    center_x = x + width / 2
    center_y = y + height / 2
    return left <= center_x <= right and top <= center_y <= bottom


