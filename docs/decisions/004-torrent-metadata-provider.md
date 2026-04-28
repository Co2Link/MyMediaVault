# Decision: Torrent Metadata Provider

The domain depends on a `TorrentMetadataProvider` protocol rather than directly
depending on a network protocol implementation. Tests use deterministic fixtures.

The production adapter can use a maintained BitTorrent or torrent-source library
without leaking provider-specific behavior into video services or UI components.
