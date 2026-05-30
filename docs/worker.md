# Worker

## Target VM Worker

MyMediaVault uses a single long-running VM worker process for dev metadata and
preview processing. The worker runs on the manually managed Oracle Cloud VM that
supports UDP/DHT BitTorrent access. The VM worker replaces the former Azure
Container Apps metadata job.

The combined worker lives in `apps/vm-worker`. It keeps metadata and preview as
separate internal pipelines because they have different readiness rules,
failure modes, retry behavior, and resource costs.

Metadata processing uses the `torrents` collection as its queue. Torrent
documents carry metadata status, retry timing, lease timing, and diagnostics
directly, so there is no separate metadata job collection.
Metadata resolution attempts configured HTTP `.torrent` resolvers first for a
fast path, trying all configured resolvers in each attempt. Transient failures
are retried with explicit delays of 1, 2, 4, 8, 16, and 32 minutes. Permanent
failures remain failed until an admin or maintenance action manually requeues
metadata. DHT/qBittorrent-like metadata fetching is the fallback path after HTTP
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
| `MMV_PREVIEW_WORKER_ENABLED` | Enables the preview pipeline. |
| `MMV_TORRENT_PROVIDER` | `http` for resolver/DHT processing, or `fake` for deterministic local metadata. |
| `MMV_TORRENT_RESOLVER_URLS` | JSON list of HTTP resolver URL templates. |
| `MMV_TORRENT_FETCH_TIMEOUT_SECONDS` | Per-resolver HTTP timeout. |
| `MMV_TORRENT_METADATA_RETRY_DELAYS_SECONDS` | JSON list of transient retry delays. |
| `MMV_TORRENT_DHT_FALLBACK_ENABLED` | Enables libtorrent DHT metadata fallback. |
| `MMV_TORRENT_DHT_TIMEOUT_SECONDS` | DHT metadata fallback timeout. |
| `MMV_PREVIEW_WORKER_MAX_CONCURRENCY` | Maximum concurrent preview tasks. |
| `MMV_PREVIEW_WORKER_POLL_INTERVAL_SECONDS` | Idle preview polling interval. |
| `MMV_PREVIEW_REPAIR_STALE_PROCESSING_MINUTES` | Stale preview processing threshold. |
| `MMV_PREVIEW_TARGET_FRAMES` | Target preview frame count. |
| `MMV_PREVIEW_ANCHOR_RETRY_RANGE_MB` | JSON list of widened MiB-sized anchor retry ranges for sparse preview downloads. Defaults to `[64,128,256,384,512,768]`. |
| `MMV_PREVIEW_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS` | Seconds to wait for useful preview download progress before decoding available data or failing zero-byte downloads. Defaults to `600`. |
| `MMV_PREVIEW_RETRY_DELAYS` | JSON list of retry delays using positive integer `m`, `h`, or `d` durations. Total attempts equal one initial attempt plus the number of delays. Defaults to `["15m","1h","2h","4h","8h","12h","1d","1d","1d"]`. |
| `MMV_VM_WORKER_DEBUG_LOG_PATH` | Rotated JSON Lines debug log path. Defaults to `.local/logs/vm-worker-debug.log` for native runs; the Docker image sets `/var/log/mymediavault/vm-worker/debug.log`. |
| `MMV_VM_WORKER_DEBUG_LOG_ROTATION` | Debug log rotation size. Defaults to `100 MB`. |
| `MMV_VM_WORKER_DEBUG_LOG_RETENTION` | Debug log retention period. Defaults to `7 days`. |

## Responsibilities

- Poll torrent documents that need metadata or preview work.
- Fetch the raw `.torrent` payload through the configured provider.
- Store the raw torrent in Cloudflare R2.
- Write parsed torrent metadata and file lists back to the database.
- Repair stale metadata and preview processing leases.
- Generate preview artifacts after metadata succeeds.

## Triggers

- Long-running VM worker process. Metadata and preview loops use atomic MongoDB
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
| `MMV_PREVIEW_WORKER_ENABLED` | Enables the preview pipeline. |
| `MMV_TORRENT_PROVIDER` | `http` for resolver/DHT processing, or `fake` for deterministic local metadata. |
| `MMV_TORRENT_RESOLVER_URLS` | HTTP resolver URL templates. |
| `MMV_TORRENT_FETCH_TIMEOUT_SECONDS` | HTTP torrent fetch timeout. |
| `MMV_TORRENT_METADATA_RETRY_DELAYS_SECONDS` | JSON list of transient metadata retry delays. |
| `MMV_TORRENT_DHT_FALLBACK_ENABLED` | Enables libtorrent DHT metadata fallback. |
| `MMV_TORRENT_DHT_TIMEOUT_SECONDS` | DHT fallback timeout. |
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
| `MMV_PREVIEW_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS` | Seconds to wait for useful preview download progress before decoding available data or failing zero-byte downloads. Defaults to `600`. |
| `MMV_PREVIEW_RETRY_DELAYS` | JSON list of retry delays using positive integer `m`, `h`, or `d` durations. Total attempts equal one initial attempt plus the number of delays. Defaults to `["15m","1h","2h","4h","8h","12h","1d","1d","1d"]`. |
| `MMV_VM_WORKER_DEBUG_LOG_PATH` | Rotated JSON Lines debug log path. Defaults to `.local/logs/vm-worker-debug.log` for native runs; the Docker image sets `/var/log/mymediavault/vm-worker/debug.log`. |
| `MMV_VM_WORKER_DEBUG_LOG_ROTATION` | Debug log rotation size. Defaults to `100 MB`. |
| `MMV_VM_WORKER_DEBUG_LOG_RETENTION` | Debug log retention period. Defaults to `7 days`. |

Use the same database, torrent, and optional R2 environment variables as the web
app when running the VM worker locally.

## Preview Pipeline

`apps/vm-worker` uses Beanie document models that mirror the Mongoose torrent
preview fields, then supplies a MongoDB job source to the
`torrent-preview` worker harness. The app-owned source continuously polls the
`torrents` collection for torrents whose metadata has succeeded and whose raw
torrent blob is available. It claims eligible torrents atomically by setting
`previewStatus = "processing"`, increments `previewAttempts`, runs the pinned
`torrent-preview` version, uploads the generated contact sheet and frames to R2,
and writes status, artifact keys, dimensions, warnings, status reason, and
diagnostics back to the torrent document.

The pinned `torrent-preview` engine uses bounded in-attempt anchor retry to
fill missing LLM-visible timeline anchors before ranking. The VM worker defaults
the retry ladder to `64`, `128`, `256`, `384`, `512`, and `768` MiB windows because real sparse
MP4 torrents can map timestamps later than proportional byte planning. Retry
diagnostics are stored in the existing preview diagnostics details payload.
`MMV_PREVIEW_DOWNLOAD_PROGRESS_TIMEOUT_SECONDS` controls the per-attempt stall
timer. Keep the default short enough for zero-peer torrents to release worker
capacity; use a larger value only when tracker diagnostics show peers appear
slowly in the target environment.

The worker prioritizes torrents with no generated preview (`pending` or missing
preview status). It automatically retries `failed` and `partial` previews using
`MMV_PREVIEW_RETRY_DELAYS`, defaulting to 15 minutes, 1 hour, 2 hours, 4 hours,
8 hours, 12 hours, then three daily retries. Total attempts equal one initial
attempt plus the number of configured delays, so zero-peer torrents sample
availability over time without occupying worker capacity continuously. An empty
list disables automatic retries. It also regenerates `succeeded`, `partial`, and
`failed` previews when the recorded `torrent-preview` artifact contract version
or fingerprint is missing or stale for the current worker, resetting the attempt
count for that new artifact recipe. If a regeneration run produces no
replacement frame or sheet artifacts, the worker keeps any existing preview
artifact keys. Admins can reset preview attempts from torrent management.

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
