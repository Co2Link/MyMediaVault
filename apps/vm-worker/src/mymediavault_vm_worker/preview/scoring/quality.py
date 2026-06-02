"""Simple dependency-light frame quality scoring."""

from __future__ import annotations

import math
from dataclasses import replace

import cv2
import numpy as np

from mymediavault_vm_worker.preview.core.models import ExtractedFrame
from mymediavault_vm_worker.preview.scoring.base import FrameScorer

_MIN_MEAN_LUMA = 24.0
_MIN_LUMA_STDDEV = 8.0
_MAX_DARK_PIXEL_RATIO = 0.90
_CORRUPTION_CHECK_SIZE = (320, 180)
_MIN_FLAT_BLOCK_RATIO = 0.12
_MAX_LAPLACIAN_VARIANCE = 800.0
_MAX_EDGE_DENSITY = 14.0
_MAX_FALSE_COLOR_RATIO = 0.05


class QualityFrameScorer(FrameScorer):
    """Score frames using byte entropy and basic image dimensions."""

    def score(self, frames: list[ExtractedFrame]) -> list[ExtractedFrame]:
        return [replace(frame, score=_score_frame(frame)) for frame in frames]


def _score_frame(frame: ExtractedFrame) -> float:
    try:
        data = frame.path.read_bytes()
    except OSError:
        return 0.0
    if not data:
        return 0.0

    visual_signal = _visual_signal(frame)
    if visual_signal <= 0:
        return 0.0
    damage_signal = _damage_signal(frame)
    if damage_signal <= 0:
        return 0.0
    entropy = _byte_entropy(data) / 8.0
    dimensions = (
        min(1.0, max(0.0, (frame.width * frame.height) / (640 * 360)))
        if frame.width and frame.height
        else 0.5
    )
    size_signal = min(1.0, len(data) / 120_000)
    return round(
        (entropy * 0.45)
        + (dimensions * 0.20)
        + (size_signal * 0.10)
        + (visual_signal * 0.20)
        + (damage_signal * 0.05),
        6,
    )


def _visual_signal(frame: ExtractedFrame) -> float:
    image = cv2.imread(str(frame.path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return 0.0
    luma = cv2.resize(image, (64, 64), interpolation=cv2.INTER_AREA)
    mean_luma = float(np.mean(luma))
    luma_stddev = float(np.std(luma))
    dark_pixel_ratio = float(np.count_nonzero(luma < 16) / luma.size)
    if (
        mean_luma < _MIN_MEAN_LUMA
        or luma_stddev < _MIN_LUMA_STDDEV
        or dark_pixel_ratio > _MAX_DARK_PIXEL_RATIO
    ):
        return 0.0
    mean_signal = min(1.0, mean_luma / 96.0)
    contrast_signal = min(1.0, luma_stddev / 32.0)
    dark_signal = max(0.0, 1.0 - dark_pixel_ratio)
    return (mean_signal + contrast_signal + dark_signal) / 3.0


def _damage_signal(frame: ExtractedFrame) -> float:
    image = cv2.imread(str(frame.path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return 0.0
    image = cv2.resize(image, _CORRUPTION_CHECK_SIZE, interpolation=cv2.INTER_AREA)
    flat_block_ratio = _flat_block_ratio(image)
    laplacian_variance = float(cv2.Laplacian(image, cv2.CV_64F).var())
    edge_density = _edge_density(image)
    if (
        flat_block_ratio < _MIN_FLAT_BLOCK_RATIO
        and laplacian_variance > _MAX_LAPLACIAN_VARIANCE
        and edge_density > _MAX_EDGE_DENSITY
    ):
        return 0.0
    if _false_color_ratio(frame) > _MAX_FALSE_COLOR_RATIO:
        return 0.0
    return 1.0


def _flat_block_ratio(image: np.ndarray) -> float:
    block_variances: list[float] = []
    height, width = image.shape[:2]
    for y in range(0, height - 7, 8):
        for x in range(0, width - 7, 8):
            block_variances.append(float(np.var(image[y : y + 8, x : x + 8])))
    if not block_variances:
        return 0.0
    flat_count = sum(variance < 20.0 for variance in block_variances)
    return flat_count / len(block_variances)


def _edge_density(image: np.ndarray) -> float:
    pixels = image.astype(np.float32)
    vertical = np.abs(np.diff(pixels, axis=1))
    horizontal = np.abs(np.diff(pixels, axis=0))
    return float(np.mean(vertical) + np.mean(horizontal))


def _false_color_ratio(frame: ExtractedFrame) -> float:
    image = cv2.imread(str(frame.path), cv2.IMREAD_COLOR)
    if image is None:
        return 1.0
    image = cv2.resize(image, _CORRUPTION_CHECK_SIZE, interpolation=cv2.INTER_AREA)
    hue, saturation, value = cv2.split(cv2.cvtColor(image, cv2.COLOR_BGR2HSV))
    bright_saturated = (saturation >= 90) & (value >= 130)
    magenta_damage = (hue >= 135) & (hue <= 175) & bright_saturated
    cyan_damage = (hue >= 80) & (hue <= 105) & bright_saturated
    return float(np.mean(magenta_damage | cyan_damage))


def _byte_entropy(data: bytes) -> float:
    counts = [0] * 256
    for byte in data:
        counts[byte] += 1
    total = len(data)
    entropy = 0.0
    for count in counts:
        if count:
            probability = count / total
            entropy -= probability * math.log2(probability)
    return entropy
