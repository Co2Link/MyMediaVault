from __future__ import annotations

import cv2
import numpy as np
import pytest

from mymediavault_vm_worker.preview import ExtractedFrame
from mymediavault_vm_worker.preview.output.sheet import ThumbnailSheetRenderer


def test_thumbnail_sheet_renderer_writes_compact_grid(tmp_path) -> None:
    frames = [_frame(tmp_path, index) for index in range(3)]
    renderer = ThumbnailSheetRenderer(tile_width=160, tile_height=90)

    sheet = renderer.render(
        frames=frames,
        target_frames=3,
        output_dir=tmp_path / "rendered",
    )

    image = cv2.imread(str(sheet.path), cv2.IMREAD_COLOR)
    assert image is not None
    assert (sheet.width, sheet.height) == (512, 110)
    assert image.shape[:2] == (sheet.height, sheet.width)


def test_thumbnail_sheet_renderer_compacts_partial_rows(tmp_path) -> None:
    frames = [_frame(tmp_path, index) for index in range(5)]
    renderer = ThumbnailSheetRenderer(tile_width=160, tile_height=90)

    sheet = renderer.render(
        frames=frames,
        target_frames=9,
        output_dir=tmp_path / "rendered",
    )

    assert (sheet.width, sheet.height) == (512, 206)


def test_thumbnail_sheet_renderer_uses_four_columns_for_sixteen_frames(
    tmp_path,
) -> None:
    frames = [_frame(tmp_path, index) for index in range(7)]
    renderer = ThumbnailSheetRenderer(tile_width=160, tile_height=90)

    sheet = renderer.render(
        frames=frames,
        target_frames=16,
        output_dir=tmp_path / "rendered",
    )

    assert (sheet.width, sheet.height) == (678, 206)


def test_thumbnail_sheet_renderer_rejects_empty_frames(tmp_path) -> None:
    with pytest.raises(ValueError, match="at least one frame"):
        ThumbnailSheetRenderer().render(
            frames=[],
            target_frames=9,
            output_dir=tmp_path,
        )


def _frame(tmp_path, index: int) -> ExtractedFrame:
    path = tmp_path / f"frame-{index}.jpg"
    image = np.full((360, 640, 3), 40 + index * 20, dtype=np.uint8)
    image[:, index * 40 : index * 40 + 160] = 180
    assert cv2.imwrite(str(path), image)
    return ExtractedFrame(
        path=path,
        score=0.8,
        width=640,
        height=360,
        timestamp_seconds=10.0 + index * 40,
        anchor_index=index,
        anchor_ratio=(index + 1) / 10,
        decode_method="anchor-window",
    )
