"""Shared torrent runtime wrapper."""

from __future__ import annotations

from mymediavault_vm_worker.preview.core.models import PreviewEngineConfig
from mymediavault_vm_worker.preview.torrent.client import (
    LibtorrentTorrentClient,
    TorrentClient,
)


class TorrentSession:
    """Owns the default shared torrent client for a PreviewEngine."""

    def __init__(self, client: TorrentClient | None = None) -> None:
        self.client = client or LibtorrentTorrentClient()

    async def start(self) -> None:
        await self.client.start()

    async def close(self) -> None:
        await self.client.close()

    async def maintain(self, config: PreviewEngineConfig) -> set[str]:
        return await self.client.maintain(config)

    async def release_warm(self, info_hash: str, config: PreviewEngineConfig) -> None:
        await self.client.release_warm(info_hash, config)
