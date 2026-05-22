# MyMediaVault

MyMediaVault is a monorepo for a video collection manager. The active
application is a full-stack Next.js app that authenticates with Entra ID, lets
users add videos by torrent info hash, and stores canonical torrent metadata
once per info hash while preserving private per-user notes like title,
description, and rating.

## Repository Layout

```text
apps/web          Next.js full-stack app
apps/worker       Container Apps worker job
apps/e2e          Playwright tests
packages/core     Shared Mongoose/domain/storage/torrent logic
docs              Project docs
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

The hook runs core, web, worker, e2e, and Terraform checks selectively based
on staged paths. The local authenticated Playwright browser suite uses
`apps/e2e/.env.local`, so Entra test-user credentials must be available there.
Use `apps/e2e/.env.example` as the template for the e2e env files.

## Web

```bash
cd apps/web
npm install
npm run build
npm run test
```

Run locally:

```bash
npm run dev
cd ../worker
npm ci
npm run manual-worker
```

## End-to-End Tests

```bash
cd apps/e2e
npm install
npm run test:local
```

`npm run test:local` expects a reachable MongoDB database, starts the Next.js
app and local queue worker automatically when needed, loads env from
`apps/web/.env.local` and `apps/e2e/.env.local`, cleans documents owned by the
Playwright test users, performs real Entra login, and runs the browser suite
against the local stack. To verify the deployed dev environment after GitHub
`CI` and `Dev` pass for the pushed commit, run `npm run test:smoke:dev` from
`apps/e2e`. A dev smoke run before commit, push, and deployment only validates
the previous deployed revision, not local working-tree changes.

## Infrastructure

Terraform state is stored in Cloudflare R2, while the dev application resources
run on Azure. See [docs/local-development.md](docs/local-development.md) for
the current bootstrap and `terraform init` commands. The dev environment
provisions Azure Container Apps, Azure Cosmos DB for MongoDB, and related app
infrastructure.
