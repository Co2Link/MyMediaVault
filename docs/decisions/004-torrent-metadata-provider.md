# Decision: Torrent Metadata Provider

Status: accepted; production provider still pending.

The domain depends on a `TorrentMetadataProvider` protocol rather than directly
depending on a network protocol implementation. Tests use deterministic fixtures.

The current route dependency returns `FakeTorrentMetadataProvider`, which is
useful for deterministic development and tests but is not a real metadata source.
A future production adapter can use a maintained BitTorrent or torrent-source
library without leaking provider-specific behavior into video services or UI
components.

Provider implementations must return normalized torrent metadata plus raw
`.torrent` bytes so `process_torrent_metadata` can store the raw payload and
replace the canonical torrent file list atomically.
