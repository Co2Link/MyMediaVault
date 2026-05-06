# Decision: Canonical Torrent Reuse

Status: accepted.

Torrent records are canonical by normalized info hash. The application enforces
a unique database constraint on `torrents.info_hash` and uses transaction-safe
lookup/create behavior when users add videos.

Each user-owned `Video` stores personal title, description, rating, and tag
assignments. Multiple users can reference the same `Torrent` without sharing
personal video fields.

The application also enforces one collection item per `(user_id, torrent_id)`.
If a user adds an already-owned torrent, the write path returns a conflict
instead of creating duplicate private video rows.
