"""Torrent metadata parsing and info-hash derivation."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import cast

from mymediavault_vm_worker.preview.core.exceptions import TorrentMetadataError
from mymediavault_vm_worker.preview.core.models import SelectedFile

BValue = bytes | int | list["BValue"] | dict[bytes, "BValue"]


@dataclass(frozen=True)
class TorrentMetadata:
    """Parsed torrent metadata needed by the preview pipeline."""

    info_hash: str
    name: str
    files: list[SelectedFile]
    piece_length: int
    piece_count: int
    total_size: int
    trackers: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ParsedValue:
    value: BValue
    start: int
    end: int


class _BencodeParser:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def parse(self) -> tuple[BValue, tuple[int, int]]:
        parsed = self._parse_value(0)
        if parsed.end != len(self._data):
            msg = "Torrent contains trailing data after bencode payload"
            raise TorrentMetadataError(msg)
        if not isinstance(parsed.value, dict):
            msg = "Torrent root must be a bencoded dictionary"
            raise TorrentMetadataError(msg)
        info_span = self._find_info_span(0)
        return parsed.value, info_span

    def _parse_value(self, pos: int) -> _ParsedValue:
        if pos >= len(self._data):
            msg = "Unexpected end of bencode payload"
            raise TorrentMetadataError(msg)
        token = self._data[pos : pos + 1]
        if token == b"i":
            return self._parse_int(pos)
        if token == b"l":
            return self._parse_list(pos)
        if token == b"d":
            return self._parse_dict(pos)
        if token.isdigit():
            return self._parse_bytes(pos)
        msg = f"Invalid bencode token at byte {pos}"
        raise TorrentMetadataError(msg)

    def _parse_int(self, pos: int) -> _ParsedValue:
        end = self._data.find(b"e", pos)
        if end == -1:
            msg = "Unterminated bencode integer"
            raise TorrentMetadataError(msg)
        raw = self._data[pos + 1 : end]
        try:
            value = int(raw)
        except ValueError as exc:
            msg = f"Invalid bencode integer at byte {pos}"
            raise TorrentMetadataError(msg) from exc
        return _ParsedValue(value=value, start=pos, end=end + 1)

    def _parse_bytes(self, pos: int) -> _ParsedValue:
        colon = self._data.find(b":", pos)
        if colon == -1:
            msg = "Invalid bencode byte string length"
            raise TorrentMetadataError(msg)
        raw_length = self._data[pos:colon]
        try:
            length = int(raw_length)
        except ValueError as exc:
            msg = f"Invalid bencode byte string length at byte {pos}"
            raise TorrentMetadataError(msg) from exc
        start = colon + 1
        end = start + length
        if end > len(self._data):
            msg = "Bencode byte string extends past end of payload"
            raise TorrentMetadataError(msg)
        return _ParsedValue(value=self._data[start:end], start=pos, end=end)

    def _parse_list(self, pos: int) -> _ParsedValue:
        items: list[BValue] = []
        cursor = pos + 1
        while cursor < len(self._data) and self._data[cursor : cursor + 1] != b"e":
            item = self._parse_value(cursor)
            items.append(item.value)
            cursor = item.end
        if cursor >= len(self._data):
            msg = "Unterminated bencode list"
            raise TorrentMetadataError(msg)
        return _ParsedValue(value=items, start=pos, end=cursor + 1)

    def _parse_dict(self, pos: int) -> _ParsedValue:
        values: dict[bytes, BValue] = {}
        cursor = pos + 1
        while cursor < len(self._data) and self._data[cursor : cursor + 1] != b"e":
            key = self._parse_bytes(cursor)
            if not isinstance(key.value, bytes):
                msg = "Bencode dictionary key must be bytes"
                raise TorrentMetadataError(msg)
            value = self._parse_value(key.end)
            values[key.value] = value.value
            cursor = value.end
        if cursor >= len(self._data):
            msg = "Unterminated bencode dictionary"
            raise TorrentMetadataError(msg)
        return _ParsedValue(value=values, start=pos, end=cursor + 1)

    def _find_info_span(self, pos: int) -> tuple[int, int]:
        if self._data[pos : pos + 1] != b"d":
            msg = "Torrent root must be a bencoded dictionary"
            raise TorrentMetadataError(msg)
        cursor = pos + 1
        while cursor < len(self._data) and self._data[cursor : cursor + 1] != b"e":
            key = self._parse_bytes(cursor)
            value = self._parse_value(key.end)
            if key.value == b"info":
                return value.start, value.end
            cursor = value.end
        msg = "Torrent is missing required info dictionary"
        raise TorrentMetadataError(msg)


def parse_torrent_metadata(torrent_bytes: bytes) -> TorrentMetadata:
    """Parse torrent metadata and derive the SHA-1 info hash from raw bytes."""

    root, info_span = _BencodeParser(torrent_bytes).parse()
    root_dict = _expect_dict(root, "torrent root")
    info = _expect_dict(root_dict.get(b"info"), "torrent info")
    info_hash = hashlib.sha1(torrent_bytes[info_span[0] : info_span[1]]).hexdigest()

    name = _safe_relative_path(
        [_decode_text(_expect_bytes(info.get(b"name"), "info.name"))]
    )
    piece_length = _expect_int(info.get(b"piece length"), "info.piece length")
    files = _parse_files(info, name)
    total_size = sum(file.length for file in files)
    piece_count = _piece_count(info.get(b"pieces"), total_size, piece_length)
    return TorrentMetadata(
        info_hash=info_hash,
        name=name,
        files=files,
        piece_length=piece_length,
        piece_count=piece_count,
        total_size=total_size,
        trackers=_parse_trackers(root_dict),
    )


def _parse_trackers(root: dict[bytes, BValue]) -> tuple[str, ...]:
    trackers: list[str] = []
    announce = root.get(b"announce")
    if isinstance(announce, bytes):
        trackers.append(_decode_text(announce))
    announce_list = root.get(b"announce-list")
    if isinstance(announce_list, list):
        for tier in announce_list:
            if isinstance(tier, list):
                trackers.extend(
                    _decode_text(item) for item in tier if isinstance(item, bytes)
                )
            elif isinstance(tier, bytes):
                trackers.append(_decode_text(tier))
    return _dedupe_trackers(trackers)


def _dedupe_trackers(trackers: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for tracker in trackers:
        tracker = tracker.strip()
        if not tracker or tracker in seen:
            continue
        seen.add(tracker)
        result.append(tracker)
    return tuple(result)


def _parse_files(info: dict[bytes, BValue], name: str) -> list[SelectedFile]:
    multi_files = info.get(b"files")
    if multi_files is None:
        length = _expect_int(info.get(b"length"), "info.length")
        return [SelectedFile(index=0, path=name, length=length, offset=0)]

    raw_files = _expect_list(multi_files, "info.files")
    files: list[SelectedFile] = []
    offset = 0
    for index, raw_file in enumerate(raw_files):
        file_dict = _expect_dict(raw_file, f"info.files[{index}]")
        length = _expect_int(file_dict.get(b"length"), f"info.files[{index}].length")
        path_parts = _expect_list(file_dict.get(b"path"), f"info.files[{index}].path")
        decoded_parts = [
            _decode_text(_expect_bytes(part, "path component")) for part in path_parts
        ]
        relative_path = _safe_relative_path(decoded_parts)
        if not relative_path:
            relative_path = f"file-{index}"
        files.append(
            SelectedFile(index=index, path=relative_path, length=length, offset=offset)
        )
        offset += length
    return files


def _expect_dict(value: object, field_name: str) -> dict[bytes, BValue]:
    if not isinstance(value, dict):
        msg = f"{field_name} must be a dictionary"
        raise TorrentMetadataError(msg)
    return cast("dict[bytes, BValue]", value)


def _expect_list(value: object, field_name: str) -> list[BValue]:
    if not isinstance(value, list):
        msg = f"{field_name} must be a list"
        raise TorrentMetadataError(msg)
    return cast("list[BValue]", value)


def _expect_bytes(value: object, field_name: str) -> bytes:
    if not isinstance(value, bytes):
        msg = f"{field_name} must be bytes"
        raise TorrentMetadataError(msg)
    return value


def _expect_int(value: object, field_name: str) -> int:
    if not isinstance(value, int):
        msg = f"{field_name} must be an integer"
        raise TorrentMetadataError(msg)
    if value < 0:
        msg = f"{field_name} must not be negative"
        raise TorrentMetadataError(msg)
    return value


def _piece_count(value: BValue | None, total_size: int, piece_length: int) -> int:
    if isinstance(value, bytes) and value:
        return max(1, len(value) // 20)
    if piece_length < 1:
        return 0
    return math.ceil(total_size / piece_length)


def _safe_relative_path(parts: list[str]) -> str:
    clean_parts: list[str] = []
    for part in parts:
        normalized = part.strip().replace("\\", "/")
        for piece in normalized.split("/"):
            if piece and piece not in {".", ".."}:
                clean_parts.append(piece)
    return "/".join(clean_parts)


def _decode_text(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")
