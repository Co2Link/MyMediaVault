# Worker

## Target VM Worker

MyMediaVault uses a single long-running VM worker process for dev metadata,
preview processing, and actor identification. The worker runs on the manually managed Oracle Cloud VM that
supports UDP/DHT BitTorrent access. The VM worker replaces the former Azure
Container Apps metadata job.

The combined worker lives in `apps/vm-worker`. It keeps metadata, preview, and
actor analysis as separate internal pipelines because they have different
readiness rules, failure modes, retry behavior, and resource costs.

Metadata processing uses the `torrents` collection as its queue. Torrent
documents carry metadata status, retry timing, lease timing, and diagnostics
directly, so there is no separate metadata job collection.
Metadata resolution attempts configured HTTP `.torrent` resolvers first for a
fast path, trying all configured resolvers in each attempt. Transient failures
are retried with explicit delays of 1, 2, 4, 8, 16, and 32 minutes. Permanent
failures remain failed until an admin or maintenance action manually requeues
metadata. Expired processing leases are automatically returned to pending
state, and unexpected per-torrent failures are recorded as transient failures
without stopping the metadata loop. Metadata claims run with bounded
concurrency so slow DHT lookups do not block unrelated metadata rows.
DHT/qBittorrent-like metadata fetching is the fallback path after HTTP
resolvers fail.

Run locally:

```bash
cd apps/vm-worker
cp .env.example .env
uv run mymediavault-vm-worker
```

VM worker environment:

| Variable | Purpose |
| --- | --- |
| `MONGODB_URI` | MongoDB connection for metadata and preview polling. |
| `MMV_MONGODB_DB_NAME` | Database name. |
| `MMV_MONGODB_SERVER_SELECTION_TIMEOUT_MS` | Mongo driver server-selection timeout. |
| `R2_ENDPOINT` | Cloudflare R2 S3-compatible endpoint. |
| `R2_ACCESS_KEY_ID` | Cloudflare R2 access key ID. |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 secret access key. |
| `R2_BUCKET_NAME` | R2 bucket for raw torrents and preview artifacts. |
| `OPENAI_API_KEY` | Required by the preview ranking path. |
| `MMV_METADATA_WORKER_ENABLED` | Enables the metadata pipeline. |
| `MMV_METADATA_WORKER_MAX_CONCURRENCY` | Maximum concurrent metadata tasks. Defaults to `10`. |
| `MMV_PREVIEW_WORKER_ENABLED` | Enables the preview pipeline. |
| `MMV_ACTOR_ANALYSIS_WORKER_ENABLED` | Enables sequential actor identification. Defaults to `true`. |
| `MMV_ACTOR_ANALYSIS_MODELS_DIR` | Directory containing checksum-verified YuNet and SFace ONNX files. Defaults to `.local/models`. |
| `MMV_ACTOR_ANALYSIS_POLL_INTERVAL_SECONDS` | Idle actor-analysis polling interval. Defaults to `5`. |
| `MMV_ACTOR_ANALYSIS_LEASE_SECONDS` | Actor-analysis processing lease. Defaults to `1800`. |
| `MMV_ACTOR_ANALYSIS_MAX_ATTEMPTS` | Immediate actor-analysis attempt limit. Defaults to `3`. |
| `MMV_TORRENT_PROVIDER` | `http` for resolver/DHT processing, or `fake` for deterministic local metadata. |
| `MMV_TORRENT_RESOLVER_URLS` | JSON list of HTTP resolver URL templates. |
| `MMV_TORRENT_FETCH_TIMEOUT_SECONDS` | Per-resolver HTTP timeout. |
| `MMV_TORRENT_METADATA_RETRY_DELAYS_SECONDS` | JSON list of transient retry delays. |
| `MMV_TORRENT_DHT_FALLBACK_ENABLED` | Enables libtorrent DHT metadata fallback. |
| `MMV_TORRENT_DHT_TIMEOUT_SECONDS` | DHT metadata fallback timeout. Defaults to `600`. |
| `MMV_PREVIEW_WORKER_MAX_CONCURRENCY` | Maximum concurrent preview tasks. |
| `MMV_PREVIEW_WORKER_POLL_INTERVAL_SECONDS` | Idle preview polling interval. |
| `MMV_PREVIEW_REPAIR_STALE_PROCESSING_MINUTES` | Stale preview processing threshold. |
| `MMV_PREVIEW_TARGET_FRAMES` | Target preview frame count. |
| `MMV_PREVIEW_ANCHOR_RETRY_RANGE_MB` | JSON list of widened MiB-sized anchor retry ranges for sparse preview downloads. Defaults to `[64,128,256,384,512,768]`. |
| `MMV_PREVIEW_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS` | Seconds to wait for useful preview download progress before demoting a stalled sparse swarm or decoding available data. Defaults to `120`. |
| `MMV_PREVIEW_WARM_SWARM_MAX_HANDLES` | Maximum stalled sparse-swarm handles retained for low-rate background downloads. Defaults to `40`; set `0` to disable warming. |
| `MMV_PREVIEW_WARM_SWARM_IDLE_SECONDS` | Seconds without useful warm-swarm progress before eviction. Defaults to `7200`. |
| `MMV_PREVIEW_WARM_SWARM_DOWNLOAD_LIMIT_BYTES_PER_SECOND` | Per-torrent warm-swarm download-rate limit. Defaults to `65536`. |
| `MMV_PREVIEW_RETRY_DELAYS` | JSON list of retry delays using positive integer `m`, `h`, or `d` durations. Total attempts equal one initial attempt plus the number of delays. Defaults to `["15m","1h","2h","4h","8h","12h","1d","1d","1d"]`. |
| `MMV_VM_WORKER_DEBUG_LOG_PATH` | Rotated JSON Lines debug log path. Defaults to `.local/logs/vm-worker-debug.log` for native runs; the Docker image sets `/var/log/mymediavault/vm-worker/debug.log`. |
| `MMV_VM_WORKER_DEBUG_LOG_ROTATION` | Debug log rotation size. Defaults to `100 MB`. |
| `MMV_VM_WORKER_DEBUG_LOG_RETENTION` | Debug log retention period. Defaults to `7 days`. |

## Responsibilities

- Poll torrent documents that need metadata, preview, or actor-analysis work.
- Fetch the raw `.torrent` payload through the configured provider.
- Store the raw torrent in Cloudflare R2.
- Write parsed torrent metadata and file lists back to the database.
- Repair stale metadata and preview processing leases.
- Generate preview artifacts after metadata succeeds.
- Identify main actors from durable preview frames and persist reusable global
  identities with capped biometric evidence.

## Triggers

- Long-running VM worker process. Metadata, preview, and actor-analysis loops use atomic MongoDB
  `findOneAndUpdate` claims on torrent documents, so duplicate worker processes
  can only claim distinct eligible torrents.

## Environment Variables

The VM worker reads database, torrent, storage, and preview model settings. It
does not require Auth.js or Entra variables.

| Variable | Purpose |
| --- | --- |
| `MONGODB_URI` | MongoDB connection for job polling and metadata writes. |
| `MMV_MONGODB_DB_NAME` | Worker database name. |
| `MMV_MONGODB_SERVER_SELECTION_TIMEOUT_MS` | Mongo driver server-selection timeout. |
| `MMV_METADATA_WORKER_ENABLED` | Enables the metadata pipeline. |
| `MMV_METADATA_WORKER_MAX_CONCURRENCY` | Maximum concurrent metadata tasks. Defaults to `10`. |
| `MMV_PREVIEW_WORKER_ENABLED` | Enables the preview pipeline. |
| `MMV_ACTOR_ANALYSIS_WORKER_ENABLED` | Enables sequential actor identification. Defaults to `true`. |
| `MMV_ACTOR_ANALYSIS_MODELS_DIR` | Directory containing checksum-verified YuNet and SFace ONNX files. Defaults to `.local/models`. |
| `MMV_ACTOR_ANALYSIS_POLL_INTERVAL_SECONDS` | Idle actor-analysis polling interval. Defaults to `5`. |
| `MMV_ACTOR_ANALYSIS_LEASE_SECONDS` | Actor-analysis processing lease. Defaults to `1800`. |
| `MMV_ACTOR_ANALYSIS_MAX_ATTEMPTS` | Immediate actor-analysis attempt limit. Defaults to `3`. |
| `MMV_TORRENT_PROVIDER` | `http` for resolver/DHT processing, or `fake` for deterministic local metadata. |
| `MMV_TORRENT_RESOLVER_URLS` | HTTP resolver URL templates. |
| `MMV_TORRENT_FETCH_TIMEOUT_SECONDS` | HTTP torrent fetch timeout. |
| `MMV_TORRENT_METADATA_RETRY_DELAYS_SECONDS` | JSON list of transient metadata retry delays. |
| `MMV_TORRENT_DHT_FALLBACK_ENABLED` | Enables libtorrent DHT metadata fallback. |
| `MMV_TORRENT_DHT_TIMEOUT_SECONDS` | DHT fallback timeout. Defaults to `600`. |
| `R2_ENDPOINT` | Cloudflare R2 S3-compatible endpoint. |
| `R2_ACCESS_KEY_ID` | Cloudflare R2 access key ID. |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 secret access key. |
| `R2_BUCKET_NAME` | Cloudflare R2 bucket name. |
| `OPENAI_API_KEY` | Required by the preview ranking path. |
| `MMV_PREVIEW_WORKER_MAX_CONCURRENCY` | Maximum concurrent preview tasks. |
| `MMV_PREVIEW_WORKER_POLL_INTERVAL_SECONDS` | Idle preview polling interval. |
| `MMV_PREVIEW_REPAIR_STALE_PROCESSING_MINUTES` | Stale preview processing threshold. |
| `MMV_PREVIEW_TARGET_FRAMES` | Target preview frame count. |
| `MMV_PREVIEW_ANCHOR_RETRY_RANGE_MB` | JSON list of widened MiB-sized anchor retry ranges for sparse preview downloads. Defaults to `[64,128,256,384,512,768]`. |
| `MMV_PREVIEW_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS` | Seconds to wait for useful preview download progress before demoting a stalled sparse swarm or decoding available data. Defaults to `120`. |
| `MMV_PREVIEW_WARM_SWARM_MAX_HANDLES` | Maximum stalled sparse-swarm handles retained for low-rate background downloads. Defaults to `40`; set `0` to disable warming. |
| `MMV_PREVIEW_WARM_SWARM_IDLE_SECONDS` | Seconds without useful warm-swarm progress before eviction. Defaults to `7200`. |
| `MMV_PREVIEW_WARM_SWARM_DOWNLOAD_LIMIT_BYTES_PER_SECOND` | Per-torrent warm-swarm download-rate limit. Defaults to `65536`. |
| `MMV_PREVIEW_RETRY_DELAYS` | JSON list of retry delays using positive integer `m`, `h`, or `d` durations. Total attempts equal one initial attempt plus the number of delays. Defaults to `["15m","1h","2h","4h","8h","12h","1d","1d","1d"]`. |
| `MMV_VM_WORKER_DEBUG_LOG_PATH` | Rotated JSON Lines debug log path. Defaults to `.local/logs/vm-worker-debug.log` for native runs; the Docker image sets `/var/log/mymediavault/vm-worker/debug.log`. |
| `MMV_VM_WORKER_DEBUG_LOG_ROTATION` | Debug log rotation size. Defaults to `100 MB`. |
| `MMV_VM_WORKER_DEBUG_LOG_RETENTION` | Debug log retention period. Defaults to `7 days`. |

Use the same database, torrent, and optional R2 environment variables as the web
app when running the VM worker locally.

## Preview Pipeline

`apps/vm-worker` uses Beanie document models that mirror the Mongoose torrent
preview fields, then supplies a MongoDB job source to the internal preview
worker harness. The app-owned source continuously polls the
`torrents` collection for torrents whose metadata has succeeded and whose raw
torrent blob is available. It claims eligible torrents atomically by setting
`previewStatus = "processing"`, increments `previewAttempts`, runs the internal
preview engine, uploads the generated contact sheet and frames to R2,
and writes status, artifact keys, dimensions, warnings, status reason, and
diagnostics back to the torrent document. While previews are running, the
harness replenishes unused concurrency slots on its polling interval so newly
eligible torrents do not wait for an earlier batch to drain.

The internal preview engine uses bounded in-attempt anchor retry to
fill missing LLM-visible timeline anchors before ranking. The VM worker defaults
the retry ladder to `64`, `128`, `256`, `384`, `512`, and `768` MiB windows because real sparse
MP4 torrents can map timestamps later than proportional byte planning. Retry
diagnostics are stored in the existing preview diagnostics details payload.
`MMV_PREVIEW_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS` controls the per-attempt stall
timer. When a sparse download stalls, the engine releases its active preview
slot but retains the libtorrent handle in a bounded low-rate warm pool. Useful
background byte or piece progress promotes the delayed retry immediately.
Warm-pool membership is process-local and is evicted after prolonged inactivity
or capacity pressure. Rotated DEBUG logs record retention, progress, promotion,
and eviction events with peer, seed, byte, piece, and pool-size diagnostics.

The worker prioritizes torrents with no generated preview (`pending` or missing
preview status). It automatically retries `failed` and `partial` previews using
`MMV_PREVIEW_RETRY_DELAYS`, defaulting to 15 minutes, 1 hour, 2 hours, 4 hours,
8 hours, 12 hours, then three daily retries. Total attempts equal one initial
attempt plus the number of configured delays, so zero-peer torrents sample
availability over time without occupying worker capacity continuously. An empty
list disables automatic retries. It also regenerates `succeeded`, `partial`, and
`failed` previews when the recorded preview artifact contract version
or fingerprint is missing or stale for the current worker, resetting the attempt
count for that new artifact recipe. If a regeneration run produces no
replacement frame or sheet artifacts, the worker keeps any existing preview
artifact keys. Admins can reset preview attempts from torrent management.

## Actor Analysis Pipeline

The worker consumes persisted preview frames only; contact sheets are excluded.
It uses checksum-pinned OpenCV YuNet and SFace ONNX models baked into the Docker
image. Analysis runs sequentially so UUID actor creation and exact
application-side cosine matching remain simple and deterministic.

Eligible torrents have a successful preview with at least one durable frame, or
a partial preview with at least two durable frames. The worker clusters faces
within a torrent, keeps only frequent high-quality main-actor clusters, and
matches those clusters against active-model actor centroids and capped
exemplars. Ambiguous clusters remain unassigned. A successful run with no
qualifying main actor writes an empty `systemActorIds` list.

Actor records retain up to 12 exemplars, with at most two from one torrent.
Centroids are recomputed whenever retained evidence changes. Actor names are set
only when a UUID identity is first created. Profile selection is a separate
deterministic display concern: the worker shortlists up to five accepted-cluster
observations, creates `512x512` crops with the face occupying about 60 percent
of the height and blurred edge extension, and scores detector confidence,
resolution, sharpness, lighting, YuNet landmark pose and roll estimates,
clipping, extension padding, and additional faces. Complete sufficiently large
front-facing single-face crops rank ahead of angled or multi-face fallbacks.
System-managed profiles improve opportunistically when a same-version candidate
exceeds the persisted score by at least `0.10`. When a generated crop version is
outdated, the worker lazily selects the best usable candidate across the actor's
assigned torrents before replacing it once; unavailable preview frames are
skipped. Admin-uploaded profiles remain authoritative and leave the generated
version unset. Reliable closed-eye scoring is deferred until a portable Linux
ARM64-compatible landmark model is selected. Torrent deletion does not delete
actor-owned biometric evidence.

Actor-analysis state lives on each torrent. Claims use a processing lease,
expired leases return to `pending`, and unexpected failures retry immediately
up to `MMV_ACTOR_ANALYSIS_MAX_ATTEMPTS`. Replacing preview artifacts queues
downstream analysis while preserving visible detected assignments until a new
run succeeds. Completion writes are conditional on the claimed preview
generation and processing state, so stale in-flight work cannot overwrite a
newer preview or admin reset. Admins can queue one selected torrent from torrent
management.

The deployed VM runs the VM worker with Docker and systemd. The container image
includes Python 3.13, `libtorrent`, `ffmpeg`, and `ffprobe`, runs the
application as a non-root user, and is published by the dev workflow with the
`-vm-worker:<commit-sha>` suffix for `linux/amd64` and `linux/arm64`. The VM
service stores the full image reference in `/etc/mymediavault/vm-worker.env`.
Publish TCP and UDP port `6881` from the worker container, and allow both
protocols through the VM host firewall and cloud network security rules so
libtorrent can accept peer connections and DHT traffic.
Docker stdout/stderr remains at `INFO` for routine service logs. The worker also
writes redacted `DEBUG` logs as JSON Lines. Native local runs write to
`.local/logs/vm-worker-debug.log` by default; the Docker image sets
`MMV_VM_WORKER_DEBUG_LOG_PATH` to
`/var/log/mymediavault/vm-worker/debug.log`. Debug logs rotate at `100 MB` and
retain plain rotated files for `7 days`. The systemd service should create and
bind mount that host directory with UID/GID `10001:10001` because the container
runs as the non-root `mymediavault-vm` user.
