# Testing Strategy

Testing is split by application layer and mirrored by `.github/workflows/ci.yml`
where practical.

The tracked pre-commit hook runs these check groups selectively based on staged
paths, so web checks run for `apps/web`, e2e runs for `apps/web` or `apps/e2e`, and
Terraform checks run only for `infra/terraform`.

## Web App

```bash
cd apps/web
npm run build
npm run test
```

The web app uses Vitest and Testing Library. Keep tests colocated with route,
component, or domain modules as `*.test.tsx` or `*.test.ts`. Favor direct tests
of validation and domain helpers for server actions and route handlers.

## Core and Functions

```bash
cd packages/core
npm run build
npm run test

cd apps/functions
npm run build
npm run test
```

`packages/core` owns shared domain logic, Mongoose access, job scheduling, and
torrent metadata processing. `apps/functions` owns the worker entrypoints for
metadata polling and repair paths.

`apps/e2e/scripts/run-local.sh` starts the Next.js app and local worker on top
of the local MongoDB/Cosmos stack.

## End-to-End

```bash
cd apps/e2e
npm run test:local
```

Playwright tests cover the authenticated header/account menu, add-video with
tag selection, detail-page tag editing, collection search, and admin tag flows
against the Next.js app plus local worker. Separate setup projects log in
through Entra for the normal user and admin user and store browser state in
`apps/e2e/.auth/user.json` and `apps/e2e/.auth/admin.json`. Local runs require
real test-user credentials in `apps/e2e/.env.local`. Before each local run, the
harness deletes documents for both e2e users and cleans up any orphaned torrent
records and raw blobs so repeated runs do not fail on duplicate data.

## Dev Smoke

```bash
cd apps/e2e
npm run test:smoke:dev
```

Run the dev smoke locally after the GitHub `CI` and `Dev` workflows pass for
the current commit on `develop`. The script checks those workflow results with
GitHub CLI before running Playwright against the deployed dev URL. It verifies
the full user add-video path through the web app, Cosmos DB, the worker job,
Cloudflare R2, and the UI metadata-ready state.

`apps/e2e/.env.local` must set the Entra test-user credentials and `E2E_BASE_URL`
to the deployed dev web URL. Source values in `apps/web/.env.local` must point
to the dev Cosmos DB and Cloudflare R2 so the smoke can verify database records
and raw torrent blobs.

## Environment Variables

The local and deployed-dev test harnesses source `apps/web/.env.local` and
`apps/e2e/.env.local`. The tables below list the test-specific variables; the
web and worker variables documented in their own docs are also required when the
harness talks to the live app or worker.

| Variable | Purpose |
| --- | --- |
| `E2E_USER_USERNAME` | Normal test user username. |
| `E2E_USER_PASSWORD` | Normal test user password. |
| `E2E_ADMIN_USERNAME` | Admin test user username. |
| `E2E_ADMIN_PASSWORD` | Admin test user password. |
| `E2E_BASE_URL` | App under test base URL. Defaults to `http://localhost:3000` locally. |
| `E2E_DEV_SMOKE` | Enables the deployed-dev smoke spec. |
| `E2E_DEV_SMOKE_INFO_HASH` | Overrides the dev smoke torrent hash. |
| `E2E_INCLUDE_MANUAL_TORRENT_TESTS` | Keeps the `@manual-torrent` cases in local runs. |
| `E2E_FORCE_STACK_RESTART` | Restarts the local stack and clears auth state. |
| `E2E_REQUIRE_HTTP_TORRENT_PROVIDER` | Forces `MMV_TORRENT_PROVIDER=http` locally. |
| `DEV_SMOKE_COMMIT_SHA` | Commit SHA checked by the dev smoke script. |
| `MONGODB_URI` | Database connection for local and dev-smoke runs. |
| `MMV_MONGODB_DB_NAME` | Local-stack database name. |
| `MMV_TORRENT_PROVIDER` | Local torrent provider mode. |
| `MMV_TORRENT_RESOLVER_URLS` | Local HTTP resolver URLs. |
| `MMV_TORRENT_FETCH_TIMEOUT_SECONDS` | Local HTTP fetch timeout. |
| `R2_ENDPOINT` | Local R2 endpoint when you want remote blob storage. |
| `R2_ACCESS_KEY_ID` | Local R2 access key ID. |
| `R2_SECRET_ACCESS_KEY` | Local R2 secret access key. |
| `R2_BUCKET_NAME` | Local R2 bucket name. |
| `HEALTH_URL` | Optional local health-check URL. |

## Infrastructure Checks

```bash
cd infra/terraform/envs/dev
terraform fmt -check -recursive ../..
terraform init -backend=false
terraform validate
```

These checks validate Terraform syntax without requiring remote state.
