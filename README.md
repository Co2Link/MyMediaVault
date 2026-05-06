# MyMediaVault

MyMediaVault is a monorepo for a video collection manager. The active
application is a full-stack Next.js app that authenticates with Entra ID, lets
users add videos by torrent info hash, and stores canonical torrent metadata
once per info hash while preserving private per-user notes like title,
description, and rating.

## Repository Layout

```text
apps/web          Next.js full-stack app
apps/e2e          Playwright tests
docs              Project decisions and workflow guidance
infra/terraform   Azure infrastructure
```

## Branching and Deployment

The default integration branch is `develop`. Feature work should branch from
`develop` and merge back through pull requests. A push to `develop` runs CI, and
the `Dev` workflow deploys after `CI` succeeds on `develop`. See
[docs/branching-strategy.md](docs/branching-strategy.md) for the current
workflow rules.

## Git Hooks

Enable the tracked pre-commit hook once per clone:

```bash
git config core.hooksPath .githooks
```

The hook runs the web and Terraform checks that mirror CI.
It also runs the local authenticated Playwright browser suite through
`apps/e2e/.env.local`, so Entra test-user credentials must be available there.

## Web

```bash
cd apps/web
npm install
npx prisma generate
npm run build
npm run test
```

Run locally:

```bash
npm run dev
npm run worker
```

## End-to-End Tests

```bash
cd apps/e2e
npm install
npm run test:local
```

`npm run test:local` expects a reachable SQL Server database, starts the
Next.js app and torrent worker automatically when needed, loads env from
`apps/web/.env.local` and `apps/e2e/.env.local`, cleans rows owned by the
Playwright test users, performs real Entra login, and runs the browser suite
against the local stack.

## Infrastructure

```bash
cd infra/terraform/bootstrap
terraform init
terraform plan
```

After the repo-owned backend storage exists:

```bash
cd ../envs/dev
backend_key="$(
  az storage account keys list \
    --resource-group rg-mymediavault-tfstate \
    --account-name mymediavaulttfstate \
    --query '[0].value' -o tsv
)"
terraform init -reconfigure -backend-config="access_key=${backend_key}"
terraform plan
```

The dev Terraform backend lives in the Azure Blob storage account managed by
this repository. The dev environment also provisions its own Azure SQL
database.
