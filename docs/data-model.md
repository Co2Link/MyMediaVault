# Data Model

The active schema lives in `packages/core/src/db.ts` as Mongoose models and is
applied in local development through the shared Mongoose connection.

## Entity Relationships

```mermaid
erDiagram
  User ||--o{ Video : owns
  Torrent ||--o{ Video : referenced_by
  Torrent ||--o{ TorrentFile : contains
  Torrent }o--o{ Actor : features
  Video ||--o{ VideoTag : has
  Tag ||--o{ VideoTag : labels
```

## Collections

- `users`: local projection of Entra users keyed by internal ID, with unique
  `email` and optional unique `entraOid`.
- `accounts`: Auth.js OAuth account documents that store Entra access and
  refresh tokens for server-side photo fetches and sign-in bookkeeping.
- `sessions`: Auth.js database sessions keyed by unique `sessionToken`.
- `verification_tokens`: Auth.js verification token storage.
- `torrents`: canonical torrent metadata keyed by unique normalized `infoHash`.
- `actors`: shared actor catalog keyed by stable UUID with a unique actor name.
  Actor records store a name, optional description, private profile-image blob
  metadata and provenance, versioned face centroids, and capped private
  exemplars.
- `videos`: user-owned collection item with private title, description, and
  rating; unique by `(userId, torrentId)`.
- `tags`: global tag catalog keyed by unique tag name.
- `video_tags`: many-to-many links between videos and tags, replaced from the
  add and detail forms when a user saves tag selections.

## Important Constraints

Canonical torrent reuse is enforced by `torrents.infoHash`. User isolation is
enforced by querying videos with both `video._id` and `video.userId`; multiple
users may reference the same torrent while keeping private video fields.
Deleting the last video that references a torrent removes the orphan torrent
record, stored raw blob, and stored preview artifacts. Admin torrent deletion
cascades through dependent videos and their tag links before removing the
torrent blob and preview artifacts. Tag selections are validated against the
global `tags` catalog before write operations, so the add/detail forms can only
attach tags that already exist.

Rating is optional and constrained to 1 through 5 in validation code before
write operations. Tag names are trimmed, whitespace-normalized, non-empty, and
unique.

Actor names are trimmed, whitespace-normalized, non-empty, and unique. Actor
profile images are stored in the configured blob store under private object
keys and are served through authenticated web route handlers. Torrent actor
attribution is split between worker-owned `systemActorIds` and user-owned
`userActorIds`, so all videos that reference the same canonical torrent share
the same visible deduplicated union without automated analysis overwriting
manual curation. The legacy `actorIds` field remains a compatibility read
fallback until an existing torrent is updated. Deleting an actor removes its ID
from every attribution source before deleting the actor's profile image blob.

Worker-created actors use UUID IDs and default names such as `actor-<uuid>`.
Admins may replace that name and profile image without changing identity.
Automatic analysis never renames an existing actor or replaces an admin-managed
profile image. It may replace a system-managed image with a meaningfully better
deterministic crop. Actor profile metadata stores `profileImageSource`, the
generated `profileImageVersion`, system score and compact flags, optional source
torrent/frame provenance, and the profile update time. Admin uploads leave the
generated version unset. Each actor retains up to 12 SFace exemplars with at
most two from any one torrent. The normalized centroid is recomputed whenever
retained exemplars change. Exemplars and centroids are versioned by face-model
recipe and remain private MongoDB fields. Torrent deletion preserves
actor-owned evidence; only explicit actor deletion removes it.

## Torrent Processing State

`Torrent.processingState` tracks `queued`, `running`, `partial`, `complete`,
`exhausted`, or `cancelled`. Metadata resolution and preview generation share
this lifecycle. Successful metadata acquisition stores `name`, `sizeBytes`,
`rawBlobKey`, and ordered files. Preview output stores a contact sheet in
`previewSheet` and up to nine frame records in `previewFrames`; both store
private R2 object keys and dimensions. Partial artifacts stay visible while the
torrent remains eligible for improvement. A complete artifact means every
target anchor has one selected frame. When the selected media file is fully
downloaded but fewer than the target frames can be selected, the worker marks
the torrent `exhausted` with `processingLastOutcome` set to
`insufficient_preview_frames` while preserving any current artifact.

`processingQueuedAt` preserves FIFO order. `processingAvailableAt` is null for
normal download work and records one fixed cooldown after resolver or external
service failures. `processingLeaseUntil` supports crash recovery.
`processingPhase`, `processingFailureCount`, `processingLastOutcome`,
`processingLastError`, and `processingDiagnostics` keep the scheduler easy to
debug without introducing a second state machine.

`previewDiagnostics` stores the preview artifact contract version and
fingerprint, selected file, downloaded bytes, elapsed time, status reason,
warnings, decoded candidate counts, clean selector candidate counts, eligible
and missing anchor indexes, and low-level torrent diagnostics. Engine-specific
diagnostic details, including bounded anchor retry summaries, live in the mixed
`details` payload.
Sparse downloads retain their active libtorrent handle only while they own a
slot. Under queue pressure they save resume data, release the handle, and join
the FIFO tail. Admin `Queue again` preserves artifacts while clearing cooldown
and failure state. Complete previews are queued again when the recorded artifact
version or fingerprint differs from the worker recipe.

## Actor Analysis State

`Torrent.actorAnalysisStatus` tracks `pending`, `processing`, `succeeded`, or
`failed`. The sequential VM-worker actor pipeline claims complete durable
preview frames, stores detected assignments in `systemActorIds`, and leaves
`userActorIds` untouched. A successful analysis with no qualifying main actor
stores an empty system list.

`actorAnalysisAttempts`, attempt/update timestamps, `actorAnalysisLeaseUntil`,
`actorAnalysisFingerprint`, `actorAnalysisError`, and compact diagnostics record
queue state. Replacing preview artifacts queues downstream analysis while
preserving previous system assignments until replacement analysis succeeds.
Expired leases return to `pending`; unexpected failures retry immediately up to
three total attempts. Admin torrent management can reset one selected torrent
to `pending`.
