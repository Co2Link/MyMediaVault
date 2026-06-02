from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from mymediavault_vm_worker.preview.core.models import ExtractedFrame
from mymediavault_vm_worker.preview.scoring.quality import QualityFrameScorer


def test_quality_scorer_rejects_high_frequency_decode_damage(tmp_path: Path) -> None:
    damaged = tmp_path / "damaged.jpg"
    _write_decode_damage(damaged)

    scored = QualityFrameScorer().score([_frame(damaged)])

    assert scored[0].score == 0.0


def test_quality_scorer_accepts_clear_frame(tmp_path: Path) -> None:
    clear = tmp_path / "clear.jpg"
    _write_clear_frame(clear)

    scored = QualityFrameScorer().score([_frame(clear)])

    assert scored[0].score > 0.0


def test_quality_scorer_rejects_large_false_color_regions(tmp_path: Path) -> None:
    damaged = tmp_path / "false-color.jpg"
    _write_false_color_damage(damaged)

    scored = QualityFrameScorer().score([_frame(damaged)])

    assert scored[0].score == 0.0


def _write_decode_damage(path: Path) -> None:
    rng = np.random.default_rng(7)
    image = rng.integers(0, 256, size=(360, 640, 3), dtype=np.uint8)
    assert cv2.imwrite(str(path), image)


def _write_clear_frame(path: Path) -> None:
    image = np.full((360, 640, 3), (118, 118, 118), dtype=np.uint8)
    cv2.rectangle(image, (80, 70), (560, 310), (170, 170, 170), -1)
    cv2.circle(image, (320, 180), 80, (82, 82, 82), -1)
    cv2.putText(
        image,
        "clear",
        (220, 195),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.5,
        (240, 240, 240),
        4,
    )
    assert cv2.imwrite(str(path), image)


def _write_false_color_damage(path: Path) -> None:
    image = np.full((360, 640, 3), (120, 130, 145), dtype=np.uint8)
    cv2.rectangle(image, (0, 160), (360, 360), (255, 0, 255), -1)
    assert cv2.imwrite(str(path), image)


def _frame(path: Path) -> ExtractedFrame:
    return ExtractedFrame(
        path=path,
        score=0.0,
        width=640,
        height=360,
        timestamp_seconds=1.0,
        anchor_index=0,
        anchor_ratio=0.5,
        decode_method="test",
    )
