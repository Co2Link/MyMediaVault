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

`packages/core` owns shared domain logic, Mongoose access, queue enqueue/repair,
and torrent metadata processing. `apps/functions` owns Azure Functions trigger
wiring for the queue, poison queue, and timer repair paths.

`apps/e2e/scripts/run-local.sh` starts the Next.js app and local queue worker
on top of the local MongoDB/Cosmos and Azurite stack. `npm run test:smoke:local`
runs a focused smoke that verifies the full web -> Cosmos DB -> Azure Storage
Queue -> worker path.

## End-to-End

```bash
cd apps/e2e
npm run test:local
```

Playwright tests cover the authenticated header/account menu, add-video,
collection search, admin tag flows, and the queue/worker smoke path against the
Next.js app plus local queue worker. Separate setup projects log in through
Entra for the normal user and admin user and store browser state in
`apps/e2e/.auth/user.json` and `apps/e2e/.auth/admin.json`. Local runs require
real test-user credentials in `apps/e2e/.env.local`. Before each local run, the
harness deletes documents for both e2e users and cleans up any orphaned torrent
records and raw blobs so repeated runs do not fail on duplicate data.

## Infrastructure Checks

```bash
cd infra/terraform/envs/dev
terraform fmt -check -recursive ../..
terraform init -backend=false
terraform validate
```

These checks validate Terraform syntax without requiring remote state.
