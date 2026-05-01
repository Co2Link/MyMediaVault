# Decision: Torrent Metadata Provider

Status: accepted.

The domain depends on a `TorrentMetadataProvider` protocol rather than directly
depending on a network protocol implementation. Tests use deterministic fixtures.

The current route dependency returns `FakeTorrentMetadataProvider` for
deterministic development and tests. Production metadata resolution uses a
direct HTTP `.torrent` fetch provider keyed by info hash. This avoids the cost
and operational complexity of a full torrent client because the product only
needs the raw `.torrent` payload, not downloaded media content.

Provider implementations must return normalized torrent metadata plus raw
`.torrent` bytes so `process_torrent_metadata` can store the raw payload and
replace the canonical torrent file list atomically.
