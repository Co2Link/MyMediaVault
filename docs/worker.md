# Worker

The worker lives in `apps/worker` and is deployed as an event-driven Azure
Container Apps job. Locally, the same package can run as a long-lived Node.js
process for the e2e harness.

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
