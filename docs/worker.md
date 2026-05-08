# Worker

The worker lives in `apps/functions` and runs as a Node.js 22 Azure Functions
Flex Consumption app.

## Responsibilities

- Consume `torrent-metadata-jobs` queue messages.
- Fetch the raw `.torrent` payload through the configured provider.
- Store the raw torrent in blob storage.
- Write parsed torrent metadata and file lists back to the database.
- Move invalid deliveries to the poison queue.
- Re-enqueue stale queued or processing jobs with the timer trigger.

## Triggers

- Queue trigger for normal torrent metadata processing.
- Poison queue handler for recoverable failures.
- Timer trigger for stale-job repair.

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
| `MONGODB_URI` | Queue, poison, and timer DB connection. |
| `MMV_MONGODB_DB_NAME` | Worker database name. |
| `MMV_MONGODB_SERVER_SELECTION_TIMEOUT_MS` | Mongo driver server-selection timeout. |
| `MMV_COMMIT_SHA` | Commit label for logs and diagnostics. |
| `MMV_ADMIN_OBJECT_IDS` | Shared admin object IDs. |
| `MMV_ADMIN_GROUP_OBJECT_IDS` | Shared admin group IDs. |
| `MMV_AZURE_STORAGE_CONNECTION_STRING` | Preferred storage connection string. |
| `AzureWebJobsStorage` | Functions host storage account. |
| `FUNCTIONS_WORKER_RUNTIME` | Node worker runtime. |
| `AzureWebJobsFeatureFlags` | Core Tools worker indexing flag. |
| `MMV_AZURE_BLOB_CONTAINER` | Raw torrent blob container. |
| `MMV_TORRENT_METADATA_QUEUE` | Queue consumed by the worker. |
| `MMV_TORRENT_PROVIDER` | Torrent provider mode. |
| `MMV_TORRENT_RESOLVER_URLS` | HTTP resolver URL templates. |
| `MMV_TORRENT_FETCH_TIMEOUT_SECONDS` | HTTP torrent fetch timeout. |
| `MMV_TORRENT_REPAIR_STALE_QUEUED_MINUTES` | Stale queued-job threshold. |
| `MMV_TORRENT_REPAIR_STALE_PROCESSING_MINUTES` | Stale processing-job threshold. |

`apps/functions/local.settings.json.example` covers the local host settings used
by Core Tools.

## Local Notes

For local e2e runs, `apps/e2e/scripts/run-local.sh` can start
`npm run manual-worker` instead of Azure Functions Core Tools. That keeps the
web -> database -> queue -> worker path reliable in local test runs.
