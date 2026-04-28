import pytest

from app.torrents.parser import TorrentParseError, parse_torrent


def test_parse_single_file_torrent() -> None:
    metadata = parse_torrent(b"d4:infod6:lengthi123e4:name9:video.mp4ee")
    assert metadata.name == "video.mp4"
    assert metadata.size_bytes == 123
    assert metadata.files[0].path == "video.mp4"


def test_parse_invalid_torrent() -> None:
    with pytest.raises(TorrentParseError):
        parse_torrent(b"not bencode")


def test_parse_non_utf8_name_uses_replacement_character() -> None:
    metadata = parse_torrent(b"d4:infod6:lengthi1e4:name1:\xffee")
    assert metadata.files[0].path
