# Local Development

Use the dev container when available. The repository expects Node.js 24 for the
web app and e2e packages, Node.js 22/Azure Functions Core Tools for
`apps/functions`, access to MongoDB or Azure Cosmos DB for MongoDB, Azurite for
local queues/blobs, and Terraform for infrastructure validation.

## Web App

```bash
cd apps/web
npm ci
npm run dev
```

Copy `apps/web/.env.local.example` to `apps/web/.env.local` and fill in the
Entra credentials, `AUTH_SECRET`, and any optional `MMV_*` overrides. Set
`MONGODB_URI` and `MMV_MONGODB_DB_NAME` to the local MongoDB or Cosmos values
you want to use. For local queue enqueueing, set
`MMV_AZURE_STORAGE_CONNECTION_STRING=UseDevelopmentStorage=true` or
`AzureWebJobsStorage=UseDevelopmentStorage=true` while Azurite is running.

The Functions worker uses the fake torrent metadata provider by default. Set
`MMV_TORRENT_PROVIDER=http` and provide `MMV_TORRENT_RESOLVER_URLS` as a JSON
array of base URLs or `{info_hash}` templates only when you want to exercise a
real resolver during local development.

Run the Functions worker in a second terminal. Copy
`apps/functions/local.settings.json.example` to `apps/functions/local.settings.json`
or export equivalent values; the example uses `AzureWebJobsStorage=UseDevelopmentStorage=true`
for Azurite.

```bash
cd apps/functions
npm ci
npm run start
```

For local e2e runs, the harness builds `apps/functions` and runs
`npm run manual-worker`. That process polls the configured Azure Storage Queue
directly, which keeps the web -> database -> queue -> worker smoke reliable even
when Azure Functions Core Tools is not part of the local test loop.

## End-to-End Local Stack

```bash
cd apps/e2e
npm ci
npm run test:local
```

`test:local` sources `apps/web/.env.local` and `apps/e2e/.env.local`, deletes
the Playwright test users' existing documents plus any now-orphaned torrent
metadata, starts the Next.js app and local queue worker, then executes
Playwright. The database must already be reachable via `MONGODB_URI`.
`apps/e2e/.env.local` must define `E2E_USER_USERNAME`, `E2E_USER_PASSWORD`,
`E2E_ADMIN_USERNAME`, and `E2E_ADMIN_PASSWORD`; use
`apps/e2e/.env.local.example` as the template.
`npm run test:smoke:local` runs a focused smoke that verifies the web app,
Cosmos DB, queue, and worker path end to end.

## Dev Terraform

The dev stack uses a repo-owned Azure Blob backend and its own Azure Cosmos DB
for MongoDB account. After `az login`:

```bash
cd infra/terraform/envs/dev
backend_key="$(
  az storage account keys list \
    --resource-group rg-mymediavault-tfstate \
    --account-name mymediavaulttfstate \
    --query '[0].value' -o tsv
)"
terraform init -reconfigure -backend-config="access_key=${backend_key}"
terraform plan
```

Provide the required `TF_VAR_*` values for the app image, Auth.js secret, and
Entra client credentials before planning or applying.

## Git Hooks

Enable the tracked hook once per clone:

```bash
git config core.hooksPath .githooks
```

The hook runs `apps/web` build/tests, authenticated local e2e tests, and
Terraform formatting/validation.
