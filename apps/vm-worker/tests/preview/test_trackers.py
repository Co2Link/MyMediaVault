from __future__ import annotations

from mymediavault_vm_worker.preview.torrent.client import (
    _dedupe_trackers,
    _parse_tracker_list,
)


def test_parse_tracker_list_accepts_whitespace_separated_urls() -> None:
    content = """
    udp://tracker.example:6969/announce

    https://tracker.example/announce http://tracker.example/announce
    not-a-url
    """

    assert _parse_tracker_list(content) == (
        "udp://tracker.example:6969/announce",
        "https://tracker.example/announce",
        "http://tracker.example/announce",
    )


def test_dedupe_trackers_preserves_order() -> None:
    assert _dedupe_trackers(
        (
            " udp://tracker.example:6969/announce ",
            "udp://tracker.example:6969/announce",
            "udp://other.example:6969/announce",
        )
    ) == (
        "udp://tracker.example:6969/announce",
        "udp://other.example:6969/announce",
    )
