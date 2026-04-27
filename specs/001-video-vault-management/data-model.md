# Data Model: Video Vault Management

## Overview

The model separates user-owned video records from canonical torrent records.
Torrent metadata is shared by info hash; video details, ratings, and tag
assignments are user-specific. Raw torrent files are stored outside relational
tables and referenced by blob key.

## Entities

### User

Represents an authenticated person using the app.

**Fields**:

- `id`: UUID primary key
- `external_subject`: string, unique, identity-provider subject for normal usage
- `display_name`: string, optional
- `email`: string, optional
- `is_admin`: boolean, default false
- `created_at`: datetime
- `updated_at`: datetime

**Relationships**:

- One user owns many videos.

**Validation rules**:

- `external_subject` must be unique when present.
- Test-mode users may use deterministic synthetic subjects.
- `is_admin` controls access to tag-management operations.

### Torrent

Canonical torrent record shared across all users by unique info hash.

**Fields**:

- `id`: UUID primary key
- `info_hash`: string, unique, normalized lowercase hex or supported canonical form
- `name`: string, nullable until metadata succeeds
- `size_bytes`: integer, nullable until metadata succeeds
- `raw_blob_key`: string, nullable until raw torrent source is stored
- `metadata_status`: enum `pending`, `processing`, `succeeded`, `failed`
- `metadata_error`: string, nullable, sanitized user-safe failure summary
- `metadata_attempts`: integer, default 0
- `metadata_last_attempt_at`: datetime, nullable
- `created_at`: datetime
- `updated_at`: datetime

**Relationships**:

- One torrent has many torrent files.
- One torrent has many user-owned videos.

**Validation rules**:

- `info_hash` is required and globally unique.
- The database must enforce uniqueness on `info_hash`.
- `size_bytes` must be non-negative when present.
- `raw_blob_key` is required before `metadata_status` becomes `succeeded`.

### TorrentFile

File entry extracted from torrent metadata.

**Fields**:

- `id`: UUID primary key
- `torrent_id`: foreign key to Torrent
- `path`: string
- `size_bytes`: integer
- `position`: integer, preserves torrent file order

**Relationships**:

- Many torrent files belong to one torrent.

**Validation rules**:

- `path` is required after metadata succeeds.
- `size_bytes` must be non-negative.
- `(torrent_id, position)` must be unique.

### Video

User-owned collection item linked to a canonical torrent.

**Fields**:

- `id`: UUID primary key
- `user_id`: foreign key to User
- `torrent_id`: foreign key to Torrent
- `title`: string, optional
- `description`: string, optional
- `rating`: integer, optional
- `created_at`: datetime
- `updated_at`: datetime

**Relationships**:

- Many videos belong to one user.
- Many videos reference one torrent.
- Many videos have many tags through VideoTag.

**Validation rules**:

- `rating`, when present, must be an integer from 1 to 5.
- `(user_id, torrent_id)` must be unique for the MVP to prevent duplicate
  personal entries for the same torrent.
- Queries must always scope videos by `user_id` except admin-only diagnostics.

### Tag

Administrator-managed shared label available for video organization.

**Fields**:

- `id`: UUID primary key
- `name`: string, unique, case-insensitive
- `created_at`: datetime
- `updated_at`: datetime

**Relationships**:

- Many tags attach to many videos through VideoTag.

**Validation rules**:

- `name` is required after trimming whitespace.
- Tag names must be unique case-insensitively.
- Deleting a tag removes VideoTag associations and preserves videos.

### VideoTag

Join entity between videos and tags.

**Fields**:

- `video_id`: foreign key to Video
- `tag_id`: foreign key to Tag
- `created_at`: datetime

**Relationships**:

- One row links one video to one tag.

**Validation rules**:

- `(video_id, tag_id)` must be unique.
- Tag assignment must verify the video belongs to the acting user.

### TorrentProcessingJob

Tracks background torrent metadata retrieval attempts.

**Fields**:

- `id`: UUID primary key
- `torrent_id`: foreign key to Torrent
- `status`: enum `queued`, `running`, `succeeded`, `failed`
- `error`: string, nullable, sanitized failure details
- `started_at`: datetime, nullable
- `finished_at`: datetime, nullable
- `created_at`: datetime

**Relationships**:

- Many jobs may reference one torrent over time.

**Validation rules**:

- Only one active `queued` or `running` job may exist per torrent.
- Failures must not delete the Torrent or any Video linked to it.

## State Transitions

### Torrent Metadata

```text
pending -> processing -> succeeded
pending -> processing -> failed
failed -> processing -> succeeded
failed -> processing -> failed
```

- `pending`: torrent record exists, metadata work has not started.
- `processing`: a background job is currently retrieving and parsing metadata.
- `succeeded`: raw torrent file is stored, metadata fields are populated, and
  torrent files are stored.
- `failed`: retrieval or parsing failed; videos remain visible with a failed
  metadata status.

### TorrentProcessingJob

```text
queued -> running -> succeeded
queued -> running -> failed
```

## Indexes and Constraints

- Unique index on `torrents.info_hash`.
- Unique index on `videos(user_id, torrent_id)`.
- Case-insensitive unique index on `tags.name`.
- Unique index on `video_tags(video_id, tag_id)`.
- Unique index on `torrent_files(torrent_id, position)`.
- Search indexes for:
  - `videos.user_id`
  - `videos.title`
  - `videos.rating`
  - `torrents.info_hash`
  - `torrents.name`
  - `tags.name`

## Derived Views

### Collection Item Summary

Combines Video, Torrent, and Tags for collection listing:

- video id
- display title: video title if present, otherwise torrent name if available
- user rating
- tag names
- torrent info hash
- torrent metadata status
- torrent size
- created and updated timestamps

### Video Detail

Combines full Video details, Torrent metadata, TorrentFile rows, and Tag rows.

## Test Data Requirements

- Deterministic users: one standard user, one second standard user, one admin.
- Fixture torrent with successful metadata and multiple files.
- Fixture torrent with failed metadata.
- Duplicate info hash fixture for canonical reuse tests.
- Tags for create, rename, delete, and assignment scenarios.
