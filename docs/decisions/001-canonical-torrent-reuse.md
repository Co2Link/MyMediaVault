# Decision: Canonical Torrent Reuse

Torrent records are canonical by normalized info hash. The backend enforces a
unique database constraint on `torrents.info_hash` and uses transaction-safe
lookup/create behavior when users add videos.

Each user-owned `Video` stores personal title, description, rating, and tag
assignments. Multiple users can reference the same `Torrent` without sharing
personal video fields.
