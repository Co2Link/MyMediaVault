# Worker

The worker lives in `apps/worker` and is deployed as an event-driven Azure
Container Apps job. Locally, the same package can run as a long-lived Node.js
process for the e2e harness.

The torrent preview worker lives separately in `apps/preview-worker`. It is a
Python process packaged as a Docker image for a manually managed VM, not
infrastructure managed by this repo.

## Responsibilities

- Drain queued torrent metadata jobs when the Container Apps job starts.
- Fetch the raw `.torrent` payload through the configured provider.
- Store the raw torrent in Cloudflare R2.
- Write parsed torrent metadata and file lists back to the database.
- Repair stale processing jobs at the start of each worker run.

## Triggers

- Event-driven Container Apps job using the KEDA MongoDB scaler. The scaler
  polls the `torrentmetadatajobs` collection for `{ "status": "queued" }` and
  starts at most one job execution per polling interval.

KEDA is only the wake-up mechanism. The worker uses an atomic MongoDB
`findOneAndUpdate` claim on `status = "queued"` before processing, so duplicate
or stale scaler observations can only create no-op worker executions.

## Environment Variables

The worker reads only the database, torrent, storage, and app metadata slices
from `packages/core/src/env.ts`. It does not require Auth.js or Entra variables.

| Variable | Purpose |
| --- | --- |
| `MONGODB_URI` | MongoDB connection for job polling and metadata writes. |
| `MMV_MONGODB_DB_NAME` | Worker database name. |
| `MMV_MONGODB_SERVER_SELECTION_TIMEOUT_MS` | Mongo driver server-selection timeout. |
| `MMV_COMMIT_SHA` | Commit label for logs and diagnostics. |
| `MMV_TORRENT_PROVIDER` | Torrent provider mode. |
| `MMV_TORRENT_RESOLVER_URLS` | HTTP resolver URL templates. |
| `MMV_TORRENT_FETCH_TIMEOUT_SECONDS` | HTTP torrent fetch timeout. |
| `MMV_TORRENT_REPAIR_STALE_PROCESSING_MINUTES` | Stale processing-job threshold. |
| `R2_ENDPOINT` | Cloudflare R2 S3-compatible endpoint. |
| `R2_ACCESS_KEY_ID` | Cloudflare R2 access key ID. |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 secret access key. |
| `R2_BUCKET_NAME` | Cloudflare R2 bucket name. |

Use the same database, torrent, and optional R2 environment variables as the web
app when running the worker locally. The e2e harness sources the web app env
file before starting the manual worker.

## Local Notes

For local e2e runs, `apps/e2e/scripts/run-local.sh` starts
`npm run manual-worker`. That keeps the web -> database -> worker path
reliable in local test runs.

## Preview Worker

`apps/preview-worker` uses Beanie document models that mirror the Mongoose
torrent preview fields, then supplies a MongoDB job source to the
`torrent-preview` worker harness. The app-owned source continuously polls the
`torrents` collection for torrents whose metadata has succeeded and whose raw
torrent blob is available. It claims eligible torrents atomically by setting
`previewStatus = "processing"`, increments `previewAttempts`, runs the pinned
`torrent-preview` version, uploads the generated contact sheet and frames to R2,
and writes status, artifact keys, dimensions, warnings, status reason, and
diagnostics back to the torrent document.

The pinned `torrent-preview` engine uses bounded in-attempt anchor retry to
fill missing LLM-visible timeline anchors before ranking. Retry diagnostics are
stored in the existing preview diagnostics details payload.

The worker prioritizes torrents with no generated preview (`pending` or missing
preview status). It automatically retries `failed` and `partial` previews until
the configured maximum attempt count is reached, defaulting to three total
attempts. It also regenerates `succeeded`, `partial`, and `failed` previews when
the recorded `torrent-preview` artifact contract version or fingerprint is
missing or stale for the current worker, resetting the attempt count for that new
artifact recipe. If a regeneration run produces no replacement frame or sheet
artifacts, the worker keeps any existing preview artifact keys. Admins can reset
preview attempts from torrent management.

Run locally:

```bash
cd apps/preview-worker
cp .env.example .env
uv run mymediavault-preview-worker
```

Preview worker environment:

| Variable | Purpose |
| --- | --- |
| `MONGODB_URI` | MongoDB connection for polling torrents. |
| `MMV_MONGODB_DB_NAME` | Database name. |
| `MMV_MONGODB_SERVER_SELECTION_TIMEOUT_MS` | Mongo driver server-selection timeout. |
| `R2_ENDPOINT` | Cloudflare R2 S3-compatible endpoint. |
| `R2_ACCESS_KEY_ID` | Cloudflare R2 access key ID. |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 secret access key. |
| `R2_BUCKET_NAME` | Cloudflare R2 bucket name. |
| `OPENAI_API_KEY` | Required by the Pydantic AI preview ranker. |
| `MMV_PREVIEW_WORKER_MAX_CONCURRENCY` | Maximum concurrent preview tasks. Defaults to `20`. |
| `MMV_PREVIEW_WORKER_POLL_INTERVAL_SECONDS` | Idle polling interval. Defaults to `5`. |
| `MMV_PREVIEW_REPAIR_STALE_PROCESSING_MINUTES` | Stale processing threshold. Defaults to `120`. |
| `MMV_PREVIEW_MAX_ATTEMPTS` | Maximum total automatic attempts for pending, failed, and partial previews. Defaults to `3`. |
| `MMV_PREVIEW_TARGET_FRAMES` | Target preview frame count. Defaults to `9`; supported values are `3`, `9`, and `16`. |

The deployed VM runs the preview worker with Docker and systemd. The container
image includes Python 3.13, `libtorrent`, `ffmpeg`, and `ffprobe`, runs the
application as a non-root user, and is published by the dev workflow with the
`-preview-worker:<commit-sha>` suffix for `linux/amd64` and `linux/arm64`.
The VM service stores the full image reference in
`/etc/mymediavault/preview-worker.env`.
