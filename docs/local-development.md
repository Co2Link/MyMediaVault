# Local Development

Use the dev container when available. The repository expects Node.js 24 for the
web app and e2e packages, access to a SQL Server database, and Terraform for
infrastructure validation.

## Web App

```bash
cd apps/web
npm ci
npx prisma generate
npm run dev
```

Copy `apps/web/.env.local.example` to `apps/web/.env.local` and fill in the
Entra credentials, `AUTH_SECRET`, and any optional `MMV_*` overrides. The local
default `DATABASE_URL` targets SQL Server on `localhost:1433`.

The worker uses the fake torrent metadata provider by default. Set
`MMV_TORRENT_PROVIDER=http` and provide `MMV_TORRENT_RESOLVER_URLS` as a JSON
array of base URLs or `{info_hash}` templates only when you want to exercise a
real resolver during local development.

Microsoft's current SQL Server Linux container images support only Intel/AMD
x86-64 hosts. On ARM64 devcontainer hosts, do not expect `.devcontainer` to
start a local SQL Server container. Point `DATABASE_URL` at an external SQL
Server or Azure SQL instance instead.

Run the worker in a second terminal:

```bash
cd apps/web
npm run worker
```

## End-to-End Local Stack

```bash
cd apps/e2e
npm ci
npm run test:local
```

`test:local` sources `apps/web/.env.local` and `apps/e2e/.env.local`, starts a
database migration with `prisma db push`, deletes the Playwright test users'
existing rows plus any now-orphaned torrent metadata, starts the Next.js app
and worker if they are not already running, then executes Playwright. The
database must already be reachable via `DATABASE_URL`.
`apps/e2e/.env.local` must define `E2E_USER_USERNAME`, `E2E_USER_PASSWORD`,
`E2E_ADMIN_USERNAME`, and `E2E_ADMIN_PASSWORD`; use
`apps/e2e/.env.local.example` as the template.

## Dev Terraform

The dev stack uses a repo-owned Azure Blob backend and its own Azure SQL
database. After `az login`:

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

Provide the required `TF_VAR_*` values for the app image, database admin
password, Auth.js secret, and Entra client credentials before planning or
applying.

## Git Hooks

Enable the tracked hook once per clone:

```bash
git config core.hooksPath .githooks
```

The hook runs `apps/web` build/tests, authenticated local e2e tests, and
Terraform formatting/validation.
