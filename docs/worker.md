# Worker

The worker lives in `apps/functions` and is deployed as a scheduled Azure
Container Apps job. Locally, the same code can run as a long-lived Node.js
process for the e2e harness.

## Responsibilities

- Poll MongoDB for queued torrent metadata jobs on a timer.
- Fetch the raw `.torrent` payload through the configured provider.
- Store the raw torrent in Cloudflare R2.
- Write parsed torrent metadata and file lists back to the database.
- Repair stale processing jobs on each scheduled run.

## Triggers

- Scheduled Container Apps job for normal torrent metadata processing and
  stale-job repair.

## Environment Variables

The worker also reads the shared loader in `packages/core/src/env.ts`. It uses
the same auth variables as the web app because the shared core code requires
them, even though the Functions host itself does not run Auth.js.

| Variable | Purpose |
| --- | --- |
| `AUTH_SECRET` | Shared auth secret required by the core loader. |
| `AUTH_MICROSOFT_ENTRA_ID_ID` | Shared Entra client ID. |
| `AUTH_MICROSOFT_ENTRA_ID_SECRET` | Shared Entra client secret. |
| `AUTH_MICROSOFT_ENTRA_ID_ISSUER` | Shared Entra issuer URL. |
| `MONGODB_URI` | MongoDB connection for job polling and metadata writes. |
| `MMV_MONGODB_DB_NAME` | Worker database name. |
| `MMV_MONGODB_SERVER_SELECTION_TIMEOUT_MS` | Mongo driver server-selection timeout. |
| `MMV_COMMIT_SHA` | Commit label for logs and diagnostics. |
| `MMV_ADMIN_OBJECT_IDS` | Shared admin object IDs. |
| `MMV_ADMIN_GROUP_OBJECT_IDS` | Shared admin group IDs. |
| `MMV_TORRENT_PROVIDER` | Torrent provider mode. |
| `MMV_TORRENT_RESOLVER_URLS` | HTTP resolver URL templates. |
| `MMV_TORRENT_FETCH_TIMEOUT_SECONDS` | HTTP torrent fetch timeout. |
| `MMV_TORRENT_REPAIR_STALE_QUEUED_MINUTES` | Stale queued-job threshold. |
| `MMV_TORRENT_REPAIR_STALE_PROCESSING_MINUTES` | Stale processing-job threshold. |
| `R2_ENDPOINT` | Cloudflare R2 S3-compatible endpoint. |
| `R2_ACCESS_KEY_ID` | Cloudflare R2 access key ID. |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 secret access key. |
| `R2_BUCKET_NAME` | Cloudflare R2 bucket name. |

`apps/functions/local.settings.json.example` covers the local environment used
by the manual worker and local e2e harness.

## Local Notes

For local e2e runs, `apps/e2e/scripts/run-local.sh` starts
`npm run manual-worker`. That keeps the web -> database -> worker path
reliable in local test runs.
