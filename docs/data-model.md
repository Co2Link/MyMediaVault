# Data Model

The backend uses SQLModel models in `apps/backend/app/core/models.py` and the
initial Alembic migration in `apps/backend/alembic/versions/001_initial_video_vault.py`.

## Entity Relationships

```mermaid
erDiagram
  User ||--o{ Video : owns
  Torrent ||--o{ Video : referenced_by
  Torrent ||--o{ TorrentFile : contains
  Torrent ||--o{ TorrentProcessingJob : processed_by
  Video ||--o{ VideoTag : has
  Tag ||--o{ VideoTag : labels
```

## Tables

- `users`: local projection of Entra users keyed by unique `external_subject`.
- `torrents`: canonical torrent metadata keyed by unique normalized `info_hash`.
- `torrent_files`: ordered file list for a torrent, unique by
  `(torrent_id, position)`.
- `videos`: user-owned collection item with private title, description, and
  rating; unique by `(user_id, torrent_id)`.
- `tags`: global tag catalog keyed by unique tag name.
- `video_tags`: many-to-many links between videos and tags.
- `torrent_processing_jobs`: audit records for metadata processing attempts.

## Important Constraints

Canonical torrent reuse is enforced by `torrents.info_hash`. User isolation is
enforced by querying videos with both `video.id` and `video.user_id`; multiple
users may reference the same torrent while keeping private video fields.

Rating is optional and constrained to 1 through 5 at the API schema and service
validation layers. Tag names are trimmed, whitespace-normalized, non-empty, and
unique.

## Metadata State

`Torrent.metadata_status` tracks `pending`, `processing`, `succeeded`, or
`failed`. Failed metadata processing stores `metadata_error`; successful
processing stores `name`, `size_bytes`, `raw_blob_key`, and ordered files.
