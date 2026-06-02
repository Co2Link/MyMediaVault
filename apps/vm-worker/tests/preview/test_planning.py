from __future__ import annotations

from mymediavault_vm_worker.preview.planning.layout import PreviewLayoutBuilder


def test_preview_layout_builder_starts_with_head_and_tail() -> None:
    layout = PreviewLayoutBuilder().build_layout(
        file_size=1_000,
        anchor_range_bytes=200,
        edge_range_bytes=50,
        target_frames=3,
    )

    assert layout is not None
    assert layout.anchors == (0.25, 0.5, 0.75)
    assert layout.ranges[0].start == 0
    assert layout.ranges[-1].end == 1_000
    assert layout.ranges[0].end == 50
    assert layout.ranges[-1].start == 950


def test_preview_layout_builder_uses_fixed_ranges_per_anchor() -> None:
    layout = PreviewLayoutBuilder().build_layout(
        file_size=10 * 1024 * 1024 * 1024,
        anchor_range_bytes=32 * 1024 * 1024,
        edge_range_bytes=8 * 1024 * 1024,
        target_frames=9,
    )

    assert layout is not None
    assert layout.anchors == (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
    assert layout.total_bytes == (9 * 32 * 1024 * 1024) + (2 * 8 * 1024 * 1024)


def test_preview_layout_builder_uses_full_file_when_ranges_cover_file() -> None:
    layout = PreviewLayoutBuilder().build_layout(
        file_size=100,
        anchor_range_bytes=200,
        edge_range_bytes=200,
        target_frames=3,
    )

    assert layout is not None
    assert layout.anchors == (0.25, 0.5, 0.75)
    assert layout.ranges[0].start == 0
    assert layout.ranges[0].end == 100
