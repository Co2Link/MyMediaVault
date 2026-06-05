# Actor Identification Implementation Plan

This plan implements [ADR 001](decisions/001-asynchronous-actor-identification.md)
in stages. Each stage has a verification gate so recognition quality is proven
before persistence and UI complexity are added.

## Scope

The first release adds asynchronous main-actor identification from durable
torrent preview frames using OpenCV YuNet and SFace. It reuses global actors
across torrents, creates generated actors for unmatched qualifying clusters,
keeps manual assignments separate from detected assignments, and exposes an
admin-only per-torrent reanalysis button.

Out of scope:

- Automatic actor merges.
- Admin actor-merge UI.
- User suppression of detected actor assignments.
- GPU inference.
- Approximate vector search.
- Persisting every detected face occurrence.
- Automatically reconsidering unresolved historical torrents whenever a new
  actor is discovered.

## Stage 1: Offline Analyzer

Implement the production analyzer and evaluation harness before database or UI
integration.

Tasks:

1. Add OpenCV runtime dependencies to `apps/vm-worker` with `uv`.
2. Add a committed model manifest with pinned YuNet and SFace URLs, versions,
   and SHA-256 checksums.
3. Add a local model-download command that verifies checksums and writes
   untracked ONNX artifacts.
4. Update the VM-worker Docker build to fetch and verify the same model files.
5. Implement one internal analyzer module for detection, alignment, embedding,
   quality scoring, within-torrent clustering, centroid shortlisting, and
   exemplar-level acceptance.
6. Implement a deterministic offline evaluation command that reads
   `tmp/previews/*/frame_*.jpg`, excludes sheets, and compares predicted identity
   partitions against `tmp/GT.json`.
7. Tune configurable thresholds against the strict regression corpus, then add
   broader fixtures separately.

Verification gate:

```bash
cd apps/vm-worker
uv run python scripts/download_face_models.py --output .local/models
uv run python scripts/evaluate_actor_identification.py \
  --previews ../../tmp/previews \
  --ground-truth ../../tmp/GT.json \
  --models-dir .local/models \
  --output .local/actor-profile-evaluation/identity.json \
  --profile-output .local/actor-profile-evaluation
```

The strict corpus requires zero false merges, 100 percent recall, and zero
unnecessary identity splits.

Add focused unit tests for clustering, ambiguity handling, main-actor filtering,
centroid calculation, exemplar retention, and deterministic evaluation output.

## Stage 2: Shared Persistence Model

Extend the shared MongoDB model and read paths.

Tasks:

1. Replace torrent `actorIds` with `systemActorIds` and `userActorIds`.
2. Preserve existing assignments as `userActorIds` during compatibility reads
   or migration.
3. Return the stable deduplicated union in normal video read models.
4. Extend actor documents with versioned centroid and capped exemplar data.
5. Keep embeddings out of public read types and web responses.
6. Update actor deletion to remove both torrent-assignment sources. Embedded
   biometric evidence disappears with the actor record.
7. Preserve actor records and actor-owned exemplars when deleting torrents.
8. Update indexes only where polling or assignment lookups require them.

Verification gate:

- Core unit tests cover assignment union behavior, mutation ownership, deletion
  cascades, and migration compatibility.
- Existing actor and video tests remain green.

## Stage 3: VM-Worker Pipeline

Add a third sequential loop to the existing VM-worker executable.

Tasks:

1. Mirror the new torrent and actor fields in Beanie models.
2. Add actor-analysis settings, including enablement, model paths, thresholds,
   algorithm version, lease duration, and maximum attempts.
3. Claim one qualifying torrent at a time after durable preview upload.
4. Analyze only complete previews with durable frames.
5. Lazily claim rows with no fingerprint or a stale fingerprint.
6. Repair expired processing leases back to `pending`.
7. Retry unexpected transient failures immediately up to three attempts.
8. Load preview frames from the existing private blob store.
9. Match clusters against active-model actor centroids and exemplars.
10. Create unmatched, well-supported actors with UUID-based names and one
    generated `512x512` JPEG profile crop.
11. Atomically replace a torrent's `systemActorIds` only after successful
    analysis. Preserve previous assignments while a replacement run is pending
    or failed.
12. Reject stale completion when preview replacement, lease repair, or an admin
    reset changed the claimed torrent state while CPU analysis was running.
13. Persist compact diagnostics only: face count, qualifying-cluster count,
    assigned actor IDs, unresolved-cluster count, elapsed time, fingerprint,
    and concise errors.

Verification gate:

- Worker unit tests cover claims, stale-lease repair, immediate bounded retries,
  lazy backfill, fingerprint staleness, complete-preview eligibility, successful
  empty results, conservative ambiguity handling, and preservation of previous
  assignments on failure.
- Offline evaluator still passes unchanged.

## Stage 4: Admin And Video UI

Keep UI changes narrow.

Tasks:

1. Read the relevant installed Next.js documentation before editing routes,
   server actions, or pages.
2. Add an admin-only `Reanalyze actors` button to each torrent management row.
3. Queue only the selected torrent by resetting its analysis state to
   `pending`.
4. Show actor-analysis status, last-attempt time, and a concise error in torrent
   management.
5. Split video actor editing into read-only detected actors and editable
   manually assigned actors.
6. Keep video cards, actor pages, and search on the deduplicated visible union.

Verification gate:

- Web unit tests cover the action and provenance-aware picker behavior.
- E2E tests cover manual assignment coexistence, detected-actor display, and
  selected-torrent-only reanalysis queueing.

## Stage 5: Documentation And Deployment

Update active docs when the runtime behavior lands.

Tasks:

1. Update `docs/overview.md`, `docs/worker.md`, `docs/data-model.md`,
   `docs/web-app.md`, `docs/testing.md`, `docs/local-development.md`, and
   `docs/deployment.md`.
2. Document biometric retention: actor records and exemplars remain until an
   admin explicitly deletes the actor.
3. Document model setup, checksum verification, CPU runtime requirements, and
   worker configuration.
4. Ensure Docker images include the pinned ONNX files without committing them
   to Git.
5. Validate Terraform formatting even though the first release should not need
   a database-tier change.

Final verification:

```bash
cd apps/vm-worker
uv run pytest
uv run python scripts/evaluate_actor_identification.py \
  --previews ../../tmp/previews \
  --ground-truth ../../tmp/GT.json \
  --models-dir .local/models

cd ../../packages/core
npm run test

cd ../../apps/web
npm run build
npm run test

cd ../e2e
npm run test:local

cd ../../infra/terraform/envs/dev
terraform fmt -check -recursive ../..
terraform init -backend=false
terraform validate
```

The optional profile output writes ignored local `512x512` selections,
annotated contact sheets, and a Markdown score-breakdown report. Visually review
the report before deployment. Display scoring is intentionally separate from
biometric quality and remains portable across the published `linux/amd64` and
`linux/arm64` worker images. Reliable closed-eye scoring remains deferred until
an ARM64-compatible landmark model is selected.

## Follow-Up Triggers

Revisit the design only when measurements justify the complexity:

- Add Azure vector candidate search when exact centroid scans become a measured
  bottleneck.
- Increase actor-analysis concurrency only with a global index-write lock and a
  final match recheck before actor creation.
- Add admin actor merge if generated duplicates become operationally common.
- Consider GPU inference only if sequential CPU throughput fails backlog
  requirements.
