"""Planned preview range layout."""

from __future__ import annotations

from mymediavault_vm_worker.preview.planning.base import (
    ByteRange,
    DownloadLayout,
    TimelineAnchor,
)
from mymediavault_vm_worker.preview.selection.timeline import timeline_anchors


class PreviewLayoutBuilder:
    """Build head, tail, and preview-anchor byte windows."""

    def build_layout(
        self,
        file_size: int,
        anchor_range_bytes: int,
        edge_range_bytes: int,
        target_frames: int,
    ) -> DownloadLayout | None:
        if file_size < 1:
            return None
        anchors = timeline_anchors(target_frames)
        anchor_range_bytes = max(1, min(file_size, anchor_range_bytes))
        edge_range_bytes = max(1, min(file_size, edge_range_bytes))
        if anchor_range_bytes >= file_size and edge_range_bytes >= file_size:
            return DownloadLayout(
                ranges=[ByteRange(0, file_size)],
                anchors=anchors,
            )

        return DownloadLayout(
            ranges=_merge_ranges(
                [
                    *_edge_ranges(file_size, edge_range_bytes),
                    *_ranges_for_anchors(file_size, anchor_range_bytes, anchors),
                ]
            ),
            anchors=anchors,
        )

    def build_anchor_layout(
        self,
        file_size: int,
        anchor_range_bytes: int,
        anchors: tuple[TimelineAnchor, ...],
    ) -> DownloadLayout | None:
        if file_size < 1:
            return None
        anchor_range_bytes = max(1, min(file_size, anchor_range_bytes))
        return DownloadLayout(
            ranges=_merge_ranges(
                _ranges_for_anchors(
                    file_size,
                    anchor_range_bytes,
                    tuple(anchor.ratio for anchor in anchors),
                )
            ),
            anchors=tuple(anchor.ratio for anchor in anchors),
        )


def _edge_ranges(file_size: int, range_size: int) -> list[ByteRange]:
    return [
        ByteRange(start=0, end=min(file_size, range_size)),
        ByteRange(start=max(0, file_size - range_size), end=file_size),
    ]


def _ranges_for_anchors(
    file_size: int, segment_size: int, anchors: tuple[float, ...]
) -> list[ByteRange]:
    ranges: list[ByteRange] = []
    for anchor in anchors:
        if anchor <= 0:
            start = 0
        elif anchor >= 1:
            start = max(0, file_size - segment_size)
        else:
            center = int(file_size * anchor)
            start = min(
                max(0, center - (segment_size // 2)),
                max(0, file_size - segment_size),
            )
        ranges.append(ByteRange(start=start, end=min(file_size, start + segment_size)))
    return ranges


def _merge_ranges(ranges: list[ByteRange]) -> list[ByteRange]:
    ordered = sorted(ranges, key=lambda item: item.start)
    merged: list[ByteRange] = []
    for item in ordered:
        if not merged or item.start > merged[-1].end:
            merged.append(item)
            continue
        previous = merged[-1]
        merged[-1] = ByteRange(start=previous.start, end=max(previous.end, item.end))
    return merged
