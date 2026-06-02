"""Byte-range planning interfaces."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ByteRange:
    """A half-open byte range relative to the selected media file."""

    start: int
    end: int

    @property
    def length(self) -> int:
        return max(0, self.end - self.start)


@dataclass(frozen=True)
class TimelineAnchor:
    """A timeline anchor with its original target index."""

    index: int
    ratio: float


@dataclass(frozen=True)
class DownloadLayout:
    """Planned preview byte ranges for one selected media file."""

    ranges: list[ByteRange]
    anchors: tuple[float, ...] = ()

    @property
    def total_bytes(self) -> int:
        return sum(item.length for item in self.ranges)
