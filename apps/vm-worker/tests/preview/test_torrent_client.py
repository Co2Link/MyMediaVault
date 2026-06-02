from __future__ import annotations

from mymediavault_vm_worker.preview.core.models import SelectedFile
from mymediavault_vm_worker.preview.planning.base import ByteRange, DownloadLayout
from mymediavault_vm_worker.preview.torrent.client import _ordered_piece_indexes
from mymediavault_vm_worker.preview.torrent.metadata import TorrentMetadata


def test_ordered_piece_indexes_bootstraps_head_and_tail_metadata() -> None:
    metadata = TorrentMetadata(
        info_hash="abc123",
        name="sample",
        files=[],
        piece_length=10,
        piece_count=10,
        total_size=100,
    )
    selected_file = SelectedFile(index=0, path="movie.mp4", length=100)
    layout = DownloadLayout(
        ranges=[
            ByteRange(0, 30),
            ByteRange(40, 60),
            ByteRange(70, 100),
        ],
    )

    assert _ordered_piece_indexes(layout, metadata, selected_file) == [
        0,
        9,
        1,
        8,
        2,
        7,
        4,
        5,
    ]
