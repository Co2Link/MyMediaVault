# Application Features

MyMediaVault currently focuses on authenticated personal video collection
management backed by shared torrent metadata.

## Authentication

Users sign in through Entra ID. The frontend uses MSAL to acquire API access
tokens, and the backend validates bearer tokens before serving collection data.
Users are created or updated locally from Entra claims on authenticated requests.

## Personal Video Collection

Users can add a video by torrent info hash with optional title, description, and
rating. Each user has a private collection entry, so personal fields are not
shared even when multiple users reference the same torrent.

## Canonical Torrent Metadata

Torrent records are reused by normalized info hash. Metadata processing stores
shared torrent name, size, file list, raw torrent blob key, status, attempts, and
errors. `POST /videos` enqueues metadata processing and returns immediately; the
backend resolves the raw `.torrent` payload asynchronously, stores only that
payload, and derives shared metadata from it. The provider interface supports
deterministic local fixtures or a production HTTP resolver source.

## Search and Detail Editing

The collection page supports text search across personal title, description,
torrent name, and info hash. Video details can be opened from search results and
edited for title, description, and rating. Detail pages show metadata status and
torrent file entries when available.

## Tags and Administration

Tags are a global catalog managed through admin-only routes and UI. Admin users
can list, create, rename, and delete tags. Videos can store tag links through the
backend API, though the current add/detail UI does not yet expose full tag
assignment controls.

## End-to-End Coverage

Playwright tests cover authenticated add-video, collection search, and admin tag
flows against a local stack using a real Entra test account.
