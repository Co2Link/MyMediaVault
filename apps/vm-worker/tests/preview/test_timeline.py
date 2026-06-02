from __future__ import annotations

from mymediavault_vm_worker.preview.selection.timeline import timeline_anchors


def test_timeline_anchors_for_three_frames() -> None:
    assert timeline_anchors(3) == (0.25, 0.5, 0.75)


def test_timeline_anchors_for_nine_frames() -> None:
    assert timeline_anchors(9) == (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def test_timeline_anchors_for_sixteen_frames() -> None:
    anchors = timeline_anchors(16)

    assert len(anchors) == 16
    assert anchors[0] == 0.058824
    assert anchors[-1] == 0.941176
