# Local Development

Use the dev container when available. The repository expects Node.js 24 for the
web app, worker, and e2e packages, access to MongoDB or Azure Cosmos DB for
MongoDB, Cloudflare R2 credentials when you want to
exercise remote blob storage, and Terraform for infrastructure validation.

## Web App

```bash
cd apps/web
npm ci
npm run dev
```

Copy `apps/web/.env.local.example` to `apps/web/.env.local` and fill in the
Entra credentials, `AUTH_SECRET`, and any optional `MMV_*` overrides. Set
`MONGODB_URI` and `MMV_MONGODB_DB_NAME` to the local MongoDB or Cosmos values
you want to use. Set `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
and `R2_BUCKET_NAME` when you want blob reads and writes to go through
Cloudflare R2 instead of the local filesystem fallback.

The worker uses the fake torrent metadata provider by default. Set
`MMV_TORRENT_PROVIDER=http` and provide `MMV_TORRENT_RESOLVER_URLS` as a JSON
array of base URLs or `{info_hash}` templates only when you want to exercise a
real resolver during local development.

Run the worker in a second terminal after exporting the same shared
auth/database settings plus optional R2 variables used by the web app.

```bash
cd apps/worker
npm ci
npm run manual-worker
```

For local e2e runs, the harness builds `apps/worker` and runs
`npm run manual-worker`. That process polls MongoDB directly, which keeps the
web -> database -> worker smoke reliable even when the Container Apps job
runtime is not part of the local test loop.

## End-to-End Local Stack

```bash
cd apps/e2e
npm ci
npm run test:local
```

`test:local` sources `apps/web/.env.local` and `apps/e2e/.env.local`, deletes
the Playwright test users' existing documents plus any now-orphaned torrent
metadata, starts the Next.js app and local worker, then executes Playwright.
The database must already be reachable via `MONGODB_URI`.
`apps/e2e/.env.local` must define `E2E_USER_USERNAME`, `E2E_USER_PASSWORD`,
`E2E_ADMIN_USERNAME`, and `E2E_ADMIN_PASSWORD`; use
`apps/e2e/.env.local.example` as the template.

Deployed dev verification lives in [Testing Strategy](testing.md); use
`npm run test:smoke:dev` there after GitHub `CI` and `Dev` pass.

## Dev Terraform

Bootstrap the R2-backed Terraform state locally, then initialize the dev stack
against the same bucket. After `az login` and with the R2 env vars available:

```bash
cd infra/terraform/bootstrap
terraform init
terraform apply \
  -var="r2_endpoint=${R2_ENDPOINT}" \
  -var="r2_access_key_id=${R2_ACCESS_KEY_ID}" \
  -var="r2_secret_access_key=${R2_SECRET_ACCESS_KEY}"

cd ../envs/dev
terraform init -reconfigure \
  -backend-config="bucket=mymediavault-tfstate" \
  -backend-config="key=envs/dev/terraform.tfstate" \
  -backend-config="region=auto" \
  -backend-config="endpoint=${R2_ENDPOINT}" \
  -backend-config="access_key=${R2_ACCESS_KEY_ID}" \
  -backend-config="secret_key=${R2_SECRET_ACCESS_KEY}" \
  -backend-config="skip_credentials_validation=true" \
  -backend-config="skip_metadata_api_check=true" \
  -backend-config="skip_region_validation=true" \
  -backend-config="force_path_style=true"
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
