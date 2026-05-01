# Backend Design

The backend is a FastAPI application in `apps/backend/app`. `app/main.py` builds
the application, configures CORS, registers exception handlers, loads Entra
OpenID configuration when production auth is configured, and exposes `/health`.

## Module Layout

- `api/routers`: HTTP routes for videos and admin tag management.
- `auth`: Entra token validation, user upsert, and admin authorization helpers.
- `core`: settings, database session setup, exception mapping, and SQLModel models.
- `videos`: video schemas, validation, search, create, read, and update behavior.
- `torrents`: canonical torrent lookup and metadata processing.
- `tags`: admin tag CRUD service.
- `storage`: local filesystem and Azure Blob raw torrent storage adapters.

## Authentication and Authorization

All application routes depend on `get_current_user`. The dependency validates a
bearer token through `fastapi-azure-auth`, then upserts a local `User` using the
Entra `oid` or `sub`. Admin access is granted when the user object ID appears in
`MMV_ADMIN_OBJECT_IDS` or a token role matches `MMV_ADMIN_ROLE_NAMES`.

Tests override `get_current_user` in-process instead of relying on test-only
headers.

## Video and Torrent Flow

`POST /videos` accepts an info hash plus optional title, description, rating, and
tag IDs. The service normalizes the info hash, enforces one video per
`(user_id, torrent_id)`, stores user-private fields on `Video`, and stores shared
torrent metadata on `Torrent` and `TorrentFile`.

Torrent metadata processing writes raw `.torrent` bytes to the configured
`BlobStore`, replaces the torrent file list, and records processing jobs. Status
values are `pending`, `processing`, `succeeded`, and `failed`.

## API Routes

All application routes except `/health` require an Entra bearer token.

- `GET /health`: returns `{ "status": "ok", "commit": "<sha>" }`.
- `POST /videos`: creates a user-owned video and returns `202 Accepted` with
  `VideoDetail`. Body fields are `infoHash`, optional `title`, `description`,
  `rating`, and `tagIds`.
- `GET /videos`: returns `VideoListResponse`. Query parameters are `q`, `tag`,
  `rating`, `status`, `limit` (1-100), and `offset`.
- `GET /videos/{video_id}`: returns the requesting user's `VideoDetail`.
- `PATCH /videos/{video_id}`: updates private video fields and tag IDs.
- `GET /admin/tags`: lists tags sorted by name.
- `POST /admin/tags`: creates a tag from `{ "name": "Drama" }`.
- `PATCH /admin/tags/{tag_id}`: renames a tag.
- `DELETE /admin/tags/{tag_id}`: deletes a tag and its video links.

Video responses use camelCase JSON aliases such as `displayTitle`, `infoHash`,
`torrentName`, `metadataStatus`, `createdAt`, `updatedAt`, `sizeBytes`, and
`metadataError`. The generated FastAPI OpenAPI document at `/openapi.json`
remains the contract source of truth, with assertions in
`apps/backend/tests/contract`.

## Configuration

Settings use the `MMV_` prefix and load `.env` in `apps/backend`. Important
values include `MMV_DATABASE_URL`, `MMV_CORS_ORIGINS`,
`MMV_AZURE_STORAGE_CONNECTION_STRING`, `MMV_AZURE_BLOB_CONTAINER`,
`MMV_ENTRA_TENANT_ID`, `MMV_ENTRA_CLIENT_ID`, `MMV_ENTRA_OPENAPI_CLIENT_ID`,
`MMV_ENTRA_API_SCOPE`, and `MMV_COMMIT_SHA`.
