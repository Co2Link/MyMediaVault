from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Protocol


@dataclass(frozen=True)
class TorrentFileMetadata:
    path: str
    size_bytes: int


@dataclass(frozen=True)
class TorrentMetadata:
    name: str
    size_bytes: int
    files: tuple[TorrentFileMetadata, ...]
    raw: bytes


class TorrentMetadataProvider(Protocol):
    def fetch(self, info_hash: str) -> TorrentMetadata: ...


class FakeTorrentMetadataProvider:
    def __init__(self, fixtures: dict[str, TorrentMetadata] | None = None) -> None:
        self.fixtures = fixtures or {}

    def fetch(self, info_hash: str) -> TorrentMetadata:
        normalized = info_hash.lower()
        if normalized in self.fixtures:
            return self.fixtures[normalized]
        files = (TorrentFileMetadata(path=f"{normalized[:8]}.mp4", size_bytes=1024),)
        return TorrentMetadata(
            name=f"Fixture {normalized[:8]}",
            size_bytes=sum(file.size_bytes for file in files),
            files=files,
            raw=f"d4:info{normalized}e".encode(),
        )


class TorrentMetadataProviderError(RuntimeError):
    pass


class HttpTorrentMetadataProvider:
    def __init__(self, resolver_urls: list[str], timeout_seconds: float) -> None:
        self.resolver_urls = resolver_urls
        self.timeout_seconds = timeout_seconds

    def fetch(self, info_hash: str) -> TorrentMetadata:
        from app.torrents.parser import TorrentParseError, parse_torrent

        normalized = info_hash.lower()
        if not self.resolver_urls:
            raise TorrentMetadataProviderError("No torrent resolver URLs are configured")

        last_error: Exception | None = None
        for resolver_url in self.resolver_urls:
            try:
                raw = self._fetch_bytes(self._resolve_url(resolver_url, normalized))
                metadata = parse_torrent(raw)
                return TorrentMetadata(
                    name=metadata.name,
                    size_bytes=metadata.size_bytes,
                    files=metadata.files,
                    raw=raw,
                )
            except (HTTPError, URLError, TimeoutError, TorrentParseError, ValueError) as exc:
                last_error = exc
                continue

        raise TorrentMetadataProviderError("Unable to fetch a valid .torrent payload") from last_error

    def _resolve_url(self, resolver_url: str, info_hash: str) -> str:
        if "{info_hash}" in resolver_url:
            return resolver_url.format(info_hash=info_hash)
        base = resolver_url.rstrip("/")
        return f"{base}/{info_hash}"

    def _fetch_bytes(self, url: str) -> bytes:
        request = Request(url, headers={"User-Agent": "MyMediaVault/0.1"})
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = response.read()
        if not payload:
            raise ValueError("Torrent resolver returned an empty response body")
        return payload
