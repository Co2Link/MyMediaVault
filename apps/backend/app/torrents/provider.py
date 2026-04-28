from dataclasses import dataclass
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
