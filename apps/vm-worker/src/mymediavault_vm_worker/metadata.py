from __future__ import annotations

import asyncio
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger

class MetadataResolutionError(Exception):
    def __init__(
        self,
        message: str,
        *,
        failure_kind: str,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_kind = failure_kind
        self.diagnostics = diagnostics or {}


class FakeTorrentMetadataResolver:
    async def fetch(self, info_hash: str) -> dict[str, Any]:
        name = f"Fake Torrent {info_hash[:8]}"
        raw = _fake_torrent_payload(name)
        metadata = parse_torrent(raw)
        metadata["resolverDiagnostics"] = [{"url": "fake", "kind": "success"}]
        return metadata


class HttpTorrentMetadataResolver:
    def __init__(self, *, resolver_urls: list[str], timeout_seconds: int) -> None:
        self._resolver_urls = resolver_urls
        self._timeout_seconds = max(1, timeout_seconds)

    async def fetch(self, info_hash: str) -> dict[str, Any]:
        resolver_results: list[dict[str, Any]] = []
        for resolver_url in self._resolver_urls:
            url = self._resolve_url(resolver_url, info_hash)
            try:
                raw = await asyncio.to_thread(self._fetch_url, url)
                metadata = parse_torrent(raw)
                metadata["resolverDiagnostics"] = resolver_results + [
                    {"url": url, "kind": "success"}
                ]
                return metadata
            except MetadataResolutionError as error:
                resolver_results.append(
                    {
                        "url": url,
                        "kind": error.failure_kind,
                        "error": str(error),
                        **error.diagnostics,
                    }
                )

        failure_kind = (
            "transient"
            if any(result["kind"] == "transient" for result in resolver_results)
            else "permanent"
        )
        raise MetadataResolutionError(
            "Unable to fetch a valid .torrent payload from configured resolvers.",
            failure_kind=failure_kind,
            diagnostics={"resolvers": resolver_results},
        )

    def _fetch_url(self, url: str) -> bytes:
        request = urllib.request.Request(
            url, headers={"User-Agent": "MyMediaVault/0.1"}
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout_seconds
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            failure_kind = (
                "transient" if error.code in TRANSIENT_HTTP_STATUSES else "permanent"
            )
            raise MetadataResolutionError(
                f"Resolver returned {error.code}",
                failure_kind=failure_kind,
                diagnostics={"status": error.code},
            ) from error
        except TimeoutError as error:
            raise MetadataResolutionError(
                "Resolver request timed out.",
                failure_kind="transient",
            ) from error
        except OSError as error:
            raise MetadataResolutionError(
                str(error) or "Resolver request failed.",
                failure_kind="transient",
            ) from error

        if not raw:
            raise MetadataResolutionError(
                "Resolver returned an empty response.",
                failure_kind="transient",
            )
        return raw

    @staticmethod
    def _resolve_url(resolver_url: str, info_hash: str) -> str:
        return (
            resolver_url.replace("{info_hash}", info_hash)
            if "{info_hash}" in resolver_url
            else f"{resolver_url.rstrip('/')}/{info_hash}"
        )


class DhtTorrentMetadataResolver:
    def __init__(self, *, timeout_seconds: int) -> None:
        self._timeout_seconds = max(10, timeout_seconds)

    async def fetch(self, info_hash: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._fetch_sync, info_hash)

    def _fetch_sync(self, info_hash: str) -> dict[str, Any]:
        normalized = info_hash.strip().lower()
        if len(normalized) != 40 or any(
            char not in "0123456789abcdef" for char in normalized
        ):
            raise MetadataResolutionError(
                "Info hash must be 40 hexadecimal characters for DHT fallback.",
                failure_kind="permanent",
            )

        try:
            import libtorrent as lt
        except ImportError as error:
            raise MetadataResolutionError(
                "libtorrent is not available for DHT fallback.",
                failure_kind="transient",
            ) from error

        with tempfile.TemporaryDirectory(prefix="mmv-metadata-") as temp_dir:
            session = lt.session(
                {
                    "enable_dht": True,
                    "enable_lsd": False,
                    "enable_upnp": False,
                    "enable_natpmp": False,
                    "listen_interfaces": "0.0.0.0:6881",
                    "user_agent": "MyMediaVault/0.1",
                }
            )
            handle = session.add_torrent(
                {
                    "url": f"magnet:?xt=urn:btih:{normalized}",
                    "save_path": temp_dir,
                }
            )
            deadline = datetime.now(UTC) + timedelta(seconds=self._timeout_seconds)
            while datetime.now(UTC) < deadline:
                if handle.has_metadata():
                    torrent_info = handle.torrent_file()
                    generated = lt.create_torrent(torrent_info).generate()
                    raw = bytes(lt.bencode(generated))
                    metadata = parse_torrent(raw)
                    metadata["resolverDiagnostics"] = [
                        {"url": f"dht:{normalized}", "kind": "success"}
                    ]
                    session.remove_torrent(handle)
                    return metadata
                for alert in session.pop_alerts():
                    if "metadata" in str(alert).lower():
                        logger.debug("DHT metadata alert: {}", alert)
                time.sleep(1)
            session.remove_torrent(handle)
        raise MetadataResolutionError(
            "DHT metadata fetch timed out.",
            failure_kind="transient",
            diagnostics={"dht": {"timeoutSeconds": self._timeout_seconds}},
        )


TRANSIENT_HTTP_STATUSES = {408, 409, 425, 429, *range(500, 600)}


def parse_torrent(raw: bytes) -> dict[str, Any]:
    decoded, offset = _bdecode(raw, 0)
    if offset != len(raw) or not isinstance(decoded, dict):
        raise MetadataResolutionError(
            "Torrent payload is not a valid bencoded dictionary.",
            failure_kind="transient",
        )
    info = decoded.get(b"info")
    if not isinstance(info, dict):
        raise MetadataResolutionError(
            "Torrent payload is missing an info dictionary.",
            failure_kind="permanent",
        )

    name = _decode_text(info.get(b"name") or info.get(b"name.utf-8") or b"unknown")
    files_value = info.get(b"files")
    files: list[dict[str, Any]]
    if isinstance(files_value, list):
        files = []
        for index, file_record in enumerate(files_value):
            if not isinstance(file_record, dict):
                continue
            path_value = file_record.get(b"path.utf-8") or file_record.get(b"path")
            path = (
                "/".join(_decode_text(segment) for segment in path_value)
                if isinstance(path_value, list)
                else f"{name}/{index}"
            )
            files.append(
                {
                    "path": path,
                    "sizeBytes": _to_int(file_record.get(b"length")),
                    "position": len(files),
                }
            )
    else:
        files = [
            {
                "path": name,
                "sizeBytes": _to_int(info.get(b"length")),
                "position": 0,
            }
        ]

    total_size = sum(file["sizeBytes"] for file in files)
    if not files or total_size <= 0:
        raise MetadataResolutionError(
            "Torrent payload has no usable files.",
            failure_kind="permanent",
        )
    return {
        "name": name,
        "sizeBytes": total_size,
        "files": files,
        "raw": raw,
    }


def _fake_torrent_payload(name: str) -> bytes:
    encoded_name = name.encode()
    return (
        b"d4:infod"
        b"6:lengthi1048576e"
        b"4:name"
        + str(len(encoded_name)).encode()
        + b":"
        + encoded_name
        + b"6:pieces0:"
        b"ee"
    )


def _combine_metadata_errors(
    http_error: MetadataResolutionError,
    dht_error: MetadataResolutionError,
) -> MetadataResolutionError:
    failure_kind = (
        "transient"
        if "transient" in {http_error.failure_kind, dht_error.failure_kind}
        else "permanent"
    )
    return MetadataResolutionError(
        f"{http_error} DHT fallback failed: {dht_error}",
        failure_kind=failure_kind,
        diagnostics={
            "http": http_error.diagnostics,
            "dht": {
                "kind": dht_error.failure_kind,
                "error": str(dht_error),
                **dht_error.diagnostics,
            },
        },
    )


def _bdecode(data: bytes, offset: int) -> tuple[Any, int]:
    if offset >= len(data):
        raise MetadataResolutionError(
            "Unexpected end of bencoded payload.",
            failure_kind="transient",
        )
    token = data[offset : offset + 1]
    if token == b"i":
        end = data.index(b"e", offset)
        return int(data[offset + 1 : end]), end + 1
    if token == b"l":
        values = []
        offset += 1
        while data[offset : offset + 1] != b"e":
            value, offset = _bdecode(data, offset)
            values.append(value)
        return values, offset + 1
    if token == b"d":
        values: dict[bytes, Any] = {}
        offset += 1
        while data[offset : offset + 1] != b"e":
            key, offset = _bdecode(data, offset)
            value, offset = _bdecode(data, offset)
            if isinstance(key, bytes):
                values[key] = value
        return values, offset + 1
    if token.isdigit():
        colon = data.index(b":", offset)
        length = int(data[offset:colon])
        start = colon + 1
        end = start + length
        return data[start:end], end
    raise MetadataResolutionError(
        "Unsupported bencode token.",
        failure_kind="transient",
    )


def _decode_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return "unknown"


def _to_int(value: Any) -> int:
    return value if isinstance(value, int) else 0

