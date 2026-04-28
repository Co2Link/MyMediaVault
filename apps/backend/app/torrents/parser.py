from collections.abc import Iterable, Mapping
from typing import Any, cast

import bencode2

from app.torrents.provider import TorrentFileMetadata, TorrentMetadata


class TorrentParseError(ValueError):
    pass


def _decode_text(value: bytes | str) -> str:
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")


def _get(mapping: Mapping[Any, Any], key: bytes) -> object | None:
    return mapping.get(key) or mapping.get(key.decode())


def _to_int(value: object | None) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, bytes):
        return int(value.decode())
    if isinstance(value, str):
        return int(value)
    return 0


def parse_torrent(raw: bytes) -> TorrentMetadata:
    try:
        decoded = bencode2.bdecode(raw)
    except Exception as exc:  # pragma: no cover - package error types vary
        raise TorrentParseError("Torrent payload is not valid bencode") from exc
    if not isinstance(decoded, dict):
        raise TorrentParseError("Torrent payload root must be a dictionary")
    decoded_mapping = cast(Mapping[Any, Any], decoded)
    info = _get(decoded_mapping, b"info")
    if not isinstance(info, dict):
        raise TorrentParseError("Torrent payload is missing info dictionary")
    info_mapping = cast(Mapping[Any, Any], info)

    name_raw = _get(info_mapping, b"name") or b"unknown"
    name = _decode_text(name_raw) if isinstance(name_raw, bytes | str) else "unknown"
    files: list[TorrentFileMetadata] = []
    multi_files = _get(info_mapping, b"files")
    if isinstance(multi_files, Iterable) and not isinstance(multi_files, bytes | str | dict):
        for index, item in enumerate(multi_files):
            if not isinstance(item, dict):
                continue
            item_mapping = cast(Mapping[Any, Any], item)
            length = _to_int(_get(item_mapping, b"length"))
            path_parts = _get(item_mapping, b"path")
            if isinstance(path_parts, Iterable) and not isinstance(path_parts, bytes | str | dict):
                path = "/".join(_decode_text(part) for part in path_parts if isinstance(part, bytes | str))
            else:
                path = f"{name}/{index}"
            files.append(TorrentFileMetadata(path=path, size_bytes=length))
    else:
        length = _to_int(_get(info_mapping, b"length"))
        files.append(TorrentFileMetadata(path=name, size_bytes=length))

    return TorrentMetadata(name=name, size_bytes=sum(file.size_bytes for file in files), files=tuple(files), raw=raw)
