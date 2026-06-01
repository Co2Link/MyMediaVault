# ADR 001: Asynchronous Actor Identification

- Status: Accepted
- Date: 2026-06-01

## Context

MyMediaVault stores a canonical torrent once and shares its metadata across all
user-owned videos that reference it. The VM worker already generates durable
preview frames for each torrent. Those frames are selected to be useful for
actor identification, but `torrent-preview` intentionally does not perform
identity recognition or own application state.

The application should identify the main actors visible in a torrent's preview
frames, reuse an actor identity across future torrents, and allow admins to
replace generated names such as `actor-<uuid>` with real names. Actor analysis
must remain asynchronous and must not overwrite user-managed assignments.

Preview frames may include incidental faces. Main actors usually occur more
frequently, but a torrent may contain multiple main actors. A false global merge
is more damaging than an unresolved face cluster because it incorrectly links
multiple torrents to one identity.

## Decision

### Application Boundary

Actor identification belongs in MyMediaVault, not in `torrent-preview`.
`torrent-preview` remains responsible for producing actor-identification-friendly
frames and its temporary artifact lifecycle. MyMediaVault consumes the durable
frame blobs after upload.

Add a third bounded pipeline to the existing VM-worker process:

```text
durable preview frames
  -> face detection
  -> face embedding
  -> within-torrent clustering
  -> main-actor filtering
  -> global actor matching or creation
  -> torrent assignment persistence
```

Run actor analysis sequentially in the first release. Metadata and preview work
remain concurrent. Sequential analysis avoids duplicate actor creation races
without distributed locks or automatic actor merges.

### Face Analysis

Use OpenCV YuNet for face detection and OpenCV SFace for aligned face
embeddings. Keep this implementation behind a small worker-internal analyzer
boundary so it can be replaced later without changing queue orchestration.

Pin model URLs, versions, and SHA-256 checksums in a committed manifest. Keep
ONNX files out of Git. Download and verify them during the VM-worker Docker
build and through a local setup command. Runtime job processing must not
download models.

Use CPU inference initially and record elapsed time in actor-analysis
diagnostics.

### Main Actor Policy

Analyze persisted `frame_*.jpg` artifacts only. Exclude `preview_sheet.jpg`.
Process previews whose status is `succeeded`, and `partial` previews with at
least two persisted frames.

Within one torrent:

- Cluster face embeddings before matching them globally.
- Require a main-actor cluster to appear in at least two distinct preview
  frames.
- Reject secondary clusters whose distinct-frame frequency or face quality is
  weak relative to the torrent's dominant cluster.
- Keep at most three main actor clusters per torrent.
- Rank qualifying clusters using distinct-frame frequency and face quality.
- Require multi-frame cluster evidence before accepting an existing global
  identity.
- Leave ambiguous clusters unassigned and record concise diagnostics.

Thresholds and the analysis algorithm version are configuration inputs to the
actor-analysis fingerprint.

### Actor Identity

Actors are global reusable identities with stable UUIDs. For a newly discovered
actor:

- Use the UUID as the database ID.
- Default the name to `actor-<uuid>`.
- Extract the highest-quality face into a padded square `256x256` JPEG profile
  image.
- Store the profile image in the existing private blob store under the actor
  namespace.

The worker sets an actor name and profile image only during actor creation. It
must never rename actors, delete actors, or replace profile images. Admin edits
operate on the same stable actor record and survive preview regeneration and
reanalysis.

Actors without biometric exemplars remain visible and manually assignable but
are excluded from automatic matching.

### Assignments

Split the torrent's current actor attribution into two persisted arrays:

- `systemActorIds`: written only by actor analysis.
- `userActorIds`: written only by user-facing mutations.

Normal read models expose the stable deduplicated union of both arrays. Video
edit UI presents detected actors as read-only and manual assignments as
editable. Manual assignments remain shared torrent metadata and must not become
biometric matching evidence.

Do not add user suppression of detected assignments in the first release.

### Biometric Index

Store a capped biometric index directly inside each actor record:

- One normalized centroid for candidate selection.
- Up to 12 retained SFace exemplars.
- At most two retained exemplars from any one torrent.
- Model version, embedding, quality score, and optional source provenance for
  each exemplar.
- An exemplar-set revision for concurrency-controlled updates.

The centroid is the normalized mean of retained embeddings for one face-model
version. Recompute it whenever that retained exemplar set changes. Use the
centroid only to shortlist candidates. Perform final identity acceptance
against retained exemplars using aggregate multi-frame evidence.

Retained exemplars are actor-owned identity evidence. Torrent deletion and
preview regeneration preserve accepted exemplar embeddings. If a referenced
preview frame is deleted, clear or omit the invalid source reference while
retaining optional origin metadata. Delete exemplars when the actor is
explicitly deleted or when the capped set replaces them with better evidence.

Store embeddings only in MongoDB. Do not return them through web APIs.

Use exact application-side cosine matching initially. The deployed Azure Cosmos
DB for MongoDB vCore cluster can store vector arrays, but the current free tier
has vector-index restrictions and local development uses ordinary MongoDB.
Keep matching behind an internal boundary so a future Azure vector candidate
search can replace centroid scanning without changing acceptance semantics.

### Queue State

Store actor-analysis queue state directly on each torrent, matching the
existing torrent-centric worker design:

```text
systemActorIds
userActorIds
actorAnalysisStatus
actorAnalysisAttempts
actorAnalysisLastAttemptAt
actorAnalysisUpdatedAt
actorAnalysisLeaseUntil
actorAnalysisFingerprint
actorAnalysisError
actorAnalysisDiagnostics
```

Use `pending`, `processing`, `succeeded`, and `failed` statuses. A successful run
with no qualifying main actors is `succeeded` with an empty `systemActorIds`
array.

The fingerprint includes:

- The preview artifact fingerprint.
- YuNet and SFace model versions.
- Detection, clustering, main-actor, and matching thresholds.
- The actor-analysis algorithm version.

Qualifying torrents with no fingerprint are lazily backfilled. Preview
regeneration and fingerprint changes cause lazy reanalysis through normal
polling.

Use an explicit processing lease and repair stale claims back to `pending`.
Retry unexpected transient failures immediately up to three total attempts.
Do not add a retry-schedule timestamp. Deterministic outcomes such as no
qualifying face cluster succeed without retries.

Apply successful completion only when the torrent is still processing the
claimed preview generation. Preview replacement, lease repair, or an admin
reset invalidates stale in-flight completion so older CPU work cannot overwrite
the newer queue decision.

### Admin Operations

Add an admin-only `Reanalyze actors` button on each torrent management row. The
button resets only the selected torrent to `pending`, clears exhausted failure
state, and preserves existing visible system assignments until replacement
analysis succeeds.

Do not reanalyze historical torrents whenever a new actor is created. Previously
unresolved torrents remain unchanged until their preview changes or an admin
queues that torrent explicitly.

Actor deletion remains explicit. Deleting an actor removes it from all system
and user assignments, removes its embedded exemplars and centroid with the actor
record, and deletes its profile image. Torrent deletion does not delete actor
records.

Automatic actor merging and admin merge UI are out of scope for the first
release.

### Model Upgrades

Store the face-model version on exemplars and centroids. Match only against
evidence produced by the active model version. When models change, retain actor
records and profile images, preserve old evidence temporarily, and lazily build
new-version evidence as torrents are reanalyzed. Never combine embeddings from
different model versions in one centroid.

## Validation

Build an offline evaluator before queue and UI integration. It must use the
same analyzer and matching policy as production, read each torrent folder under
`tmp/previews`, exclude contact sheets, and compare generated identity
partitions against `tmp/GT.json`.

The supplied 14-torrent fixture set is a strict regression gate:

- Zero false global merges.
- 100 percent recall for expected cross-torrent identities.
- No unnecessary identity splits.

Production remains conservative even though the fixture gate is strict:
ambiguous real-world clusters stay unassigned instead of forcing a match.
Broader fixtures should be added separately to reduce overfitting.

## Consequences

- Actor identity remains durable when previews regenerate or source torrents
  are deleted.
- Admin naming and profile-image edits survive automated work.
- The first release favors correctness and operational simplicity over maximum
  actor-analysis throughput.
- Exact matching remains portable between local MongoDB and deployed MongoDB
  vCore.
- Biometric embeddings become retained private application data and are deleted
  through explicit actor deletion.
- A future actor-merge operation may be needed if real-world use produces
  duplicate global actors.
