# Worker

## VM Worker 1.0

`apps/vm-worker` is a single long-running process for torrent processing and
actor identification. Torrent metadata resolution and preview generation share
one FIFO lifecycle because both are stages of obtaining enough torrent data to
produce useful preview frames. Actor analysis remains a separate sequential
downstream pipeline.

The `torrents` collection is the durable queue. There is no separate job
collection and no durable preview retry ladder. Each active torrent owns one of
`MMV_PREVIEW_WORKER_MAX_CONCURRENCY` slots. An active session resolves metadata
when needed, downloads useful ranges, asks the OpenAI-backed ranker to select
frames, and continues downloading when the result is not yet good enough.
If the selected media file is fully downloaded but the ranker still accepts
fewer than the target number of frames, the session stores the usable artifact
as `complete` with the `completed_best_effort` outcome. More download passes
cannot improve that file.

With no queue pressure, a sparse swarm may retain its slot indefinitely. Repeated
no-progress checkpoints wait quietly before retrying preview generation and are
throttled in the debug log, while the retained libtorrent handle can continue
downloading. Under queue pressure, an incomplete session that made no useful
byte or piece progress yields at the next engine checkpoint, stores libtorrent
resume data, releases its handle, and rejoins the FIFO tail. HTTP, DHT, or
external service failures use one fixed cooldown timestamp to avoid hot loops.
Bounded metadata, permanent media, or bounded external service failures become
`exhausted`.

## Torrent States

| State | Meaning |
| --- | --- |
| `queued` | Waiting in FIFO order. |
| `running` | Owns a worker slot. `processingPhase` identifies the current stage. |
| `partial` | Has usable frames and remains queued for improvement. |
| `complete` | Has the current preview artifact, including a best-effort artifact when the selected file is fully downloaded. |
| `exhausted` | Needs admin attention after a permanent or bounded external failure. |
| `cancelled` | Removed from scheduling by an admin. |

Admins can `Queue again` or `Cancel` torrent processing. Queueing again clears
the failure counter and cooldown while preserving existing artifacts.

## Persistent Cache

MongoDB remains authoritative. Downloaded torrent bytes and libtorrent resume
data live in a bounded rebuildable cache at `MMV_PREVIEW_CACHE_DIR`. Deployments
must bind mount this path so container replacement does not discard sparse-swarm
progress. The cache uses an LRU budget controlled by `MMV_PREVIEW_CACHE_MAX_MB`.

## Actor Analysis

Actor analysis consumes durable preview frames and runs sequentially. Complete
torrents with at least one frame and partial torrents with at least two frames
are eligible. Replacing preview artifacts queues actor analysis again while
preserving visible assignments until the replacement run completes.

## Configuration

Run locally:

```bash
cd apps/vm-worker
cp .env.example .env
uv run mymediavault-vm-worker
```

Important variables:

| Variable | Purpose |
| --- | --- |
| `MONGODB_URI` | MongoDB connection. |
| `OPENAI_API_KEY` | Required by OpenAI-backed frame selection. |
| `MMV_PREVIEW_WORKER_ENABLED` | Enables unified torrent processing. |
| `MMV_PREVIEW_WORKER_MAX_CONCURRENCY` | Maximum active torrent sessions. Defaults to `20`. |
| `MMV_PREVIEW_WORKER_POLL_INTERVAL_SECONDS` | Idle FIFO poll interval. Defaults to `5`. |
| `MMV_PREVIEW_REPAIR_STALE_PROCESSING_MINUTES` | Crash-recovery lease threshold. Defaults to `120`. |
| `MMV_PREVIEW_SESSION_FAIRNESS_SECONDS` | Queue-pressure fairness lifetime. Defaults to `7200`. |
| `MMV_PREVIEW_FAILURE_LIMIT` | Metadata and external processing failure limit. Defaults to `3`. |
| `MMV_PREVIEW_EXTERNAL_FAILURE_COOLDOWN_SECONDS` | Fixed resolver/service cooldown. Defaults to `300`. |
| `MMV_PREVIEW_CACHE_DIR` | Persistent libtorrent cache path. |
| `MMV_PREVIEW_CACHE_MAX_MB` | Bounded cache budget. Defaults to `32768`. |
| `MMV_PREVIEW_TARGET_FRAMES` | Required accepted frame count. Defaults to `9`. |
| `MMV_PREVIEW_ANCHOR_RETRY_RANGE_MB` | In-session widened anchor ranges. |
| `MMV_PREVIEW_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS` | Stall checkpoint interval. Defaults to `120`. |
| `MMV_TORRENT_PROVIDER` | `http` or deterministic local `fake`. |
| `MMV_TORRENT_RESOLVER_URLS` | HTTP `.torrent` resolver templates. |
| `MMV_TORRENT_DHT_FALLBACK_ENABLED` | Enables libtorrent DHT metadata fallback. |
| `MMV_TORRENT_DHT_TIMEOUT_SECONDS` | DHT metadata timeout. Defaults to `600`. |
| `MMV_ACTOR_ANALYSIS_WORKER_ENABLED` | Enables sequential actor analysis. |

See `apps/vm-worker/.env.example` for the complete list.

## Diagnostics

Console logs stay at `INFO`. Rotated redacted JSON Lines `DEBUG` logs include
queue claims, phases, byte and piece progress, peer counts, yields, cooldowns,
resume persistence, and releases. MongoDB stores the current state, phase,
queue timestamp, lease, cooldown, failure count, last outcome, last error, and
preview diagnostics directly on each torrent.

## Migration

Worker `1.0.0` is a one-way replacement. Stop older workers before running:

```bash
cd apps/vm-worker
MONGODB_URI=... uv run python scripts/migrate_processing_queue_v1.py \
  --backup ../../tmp/torrents-before-worker-1.0.json
```

The migration preserves raw metadata and preview artifacts, maps usable
nine-frame artifacts to `complete`, usable partial artifacts to `partial`, and
other valid torrents to `queued`.
