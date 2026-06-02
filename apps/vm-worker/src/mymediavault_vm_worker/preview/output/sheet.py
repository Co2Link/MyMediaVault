"""Thumbnail-sheet rendering for preview results."""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from mymediavault_vm_worker.preview.core.models import (
    DEFAULT_SHEET_RECIPE,
    ExtractedFrame,
    GeneratedSheet,
)


class ThumbnailSheetRenderer:
    """Render selected preview frames into one contact-sheet image."""

    def __init__(
        self,
        *,
        tile_width: int = 320,
        tile_height: int = 180,
    ) -> None:
        if tile_width < 64:
            msg = "ThumbnailSheetRenderer.tile_width must be at least 64"
            raise ValueError(msg)
        if tile_height < 64:
            msg = "ThumbnailSheetRenderer.tile_height must be at least 64"
            raise ValueError(msg)
        self._tile_width = tile_width
        self._tile_height = tile_height

    def artifact_recipe(self) -> dict[str, int | str]:
        """Return the stable recipe fields that affect sheet artifacts."""

        return {
            **DEFAULT_SHEET_RECIPE,
            "tile_width": self._tile_width,
            "tile_height": self._tile_height,
        }

    def render(
        self,
        *,
        frames: list[ExtractedFrame],
        target_frames: int,
        output_dir: Path,
    ) -> GeneratedSheet:
        """Render a JPEG sheet from real extracted frames."""

        if not frames:
            msg = "ThumbnailSheetRenderer requires at least one frame"
            raise ValueError(msg)
        output_dir.mkdir(parents=True, exist_ok=True)

        columns = min(_columns_for_target(target_frames), max(1, len(frames)))
        rows = math.ceil(len(frames) / columns)
        padding = 10
        gap = 6
        width = padding * 2 + columns * self._tile_width + (columns - 1) * gap
        height = padding * 2 + rows * self._tile_height + (rows - 1) * gap
        canvas = np.full((height, width, 3), 245, dtype=np.uint8)
        for index, frame in enumerate(frames):
            row = index // columns
            column = index % columns
            x = padding + column * (self._tile_width + gap)
            y = padding + row * (self._tile_height + gap)
            _draw_tile(
                canvas,
                frame,
                x=x,
                y=y,
                width=self._tile_width,
                height=self._tile_height,
            )

        output_path = output_dir / "preview_sheet.jpg"
        if not cv2.imwrite(str(output_path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 88]):
            msg = f"Failed to write preview sheet at {output_path}"
            raise OSError(msg)
        return GeneratedSheet(
            path=output_path,
            width=width,
            height=height,
        )


def _columns_for_target(target_frames: int) -> int:
    if target_frames == 16:
        return 4
    return 3


def _draw_tile(
    canvas: np.ndarray,
    frame: ExtractedFrame,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    image = cv2.imread(str(frame.path), cv2.IMREAD_COLOR)
    if image is None:
        image = np.full((height, width, 3), 32, dtype=np.uint8)
    tile = _fit_image(image, width, height)
    canvas[y : y + height, x : x + width] = tile
    cv2.rectangle(canvas, (x, y), (x + width - 1, y + height - 1), (70, 70, 70), 1)
    label = _format_duration(frame.timestamp_seconds)
    text_scale = 0.52
    text_thickness = 1
    (text_width, text_height), baseline = cv2.getTextSize(
        label, cv2.FONT_HERSHEY_SIMPLEX, text_scale, text_thickness
    )
    label_padding_x = 7
    label_padding_y = 5
    label_x = x + width - text_width - label_padding_x - 4
    label_y = y + height - label_padding_y - baseline
    cv2.rectangle(
        canvas,
        (label_x - label_padding_x, label_y - text_height - label_padding_y),
        (x + width - 1, y + height - 1),
        (8, 8, 8),
        -1,
    )
    _put_text(
        canvas,
        label,
        (label_x, label_y),
        scale=text_scale,
        color=(255, 255, 255),
        thickness=text_thickness,
    )


def _fit_image(image: np.ndarray, width: int, height: int) -> np.ndarray:
    source_height, source_width = image.shape[:2]
    if source_width <= 0 or source_height <= 0:
        return np.full((height, width, 3), 32, dtype=np.uint8)
    scale = min(width / source_width, height / source_height)
    resized_width = max(1, int(source_width * scale))
    resized_height = max(1, int(source_height * scale))
    resized = cv2.resize(
        image,
        (resized_width, resized_height),
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
    )
    tile = np.full((height, width, 3), 18, dtype=np.uint8)
    x = (width - resized_width) // 2
    y = (height - resized_height) // 2
    tile[y : y + resized_height, x : x + resized_width] = resized
    return tile


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _put_text(
    canvas: np.ndarray,
    text: str,
    origin: tuple[int, int],
    *,
    scale: float,
    color: tuple[int, int, int],
    thickness: int,
) -> None:
    cv2.putText(
        canvas,
        text,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )
