"""Image helpers for frame-selection model input."""

from __future__ import annotations

import base64
import os

import cv2

from mymediavault_vm_worker.preview.core.models import ExtractedFrame

_THUMBNAIL_MAX_WIDTH = 320
_JPEG_QUALITY = 78


def thumbnail_data_url(frame: ExtractedFrame) -> str | None:
    return frame_thumbnail_data_url(frame.path)


def frame_thumbnail_data_url(path: str | os.PathLike[str]) -> str | None:
    """Encode an image path as a small JPEG data URL for vision requests."""

    image = cv2.imread(os.fspath(path), cv2.IMREAD_COLOR)
    if image is None:
        return None
    height, width = image.shape[:2]
    if width > _THUMBNAIL_MAX_WIDTH:
        scale = _THUMBNAIL_MAX_WIDTH / width
        image = cv2.resize(
            image,
            (_THUMBNAIL_MAX_WIDTH, max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    ok, encoded = cv2.imencode(
        ".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY]
    )
    if not ok:
        return None
    payload = base64.b64encode(encoded.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{payload}"
