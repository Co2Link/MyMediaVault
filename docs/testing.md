# Testing Strategy

Testing is split by application layer and mirrored by `.github/workflows/ci.yml`
where practical.

The tracked hooks run these check groups selectively. Pre-commit keeps the
fast package and Terraform checks close to the commit. Pre-push runs the
expensive gates for pushed changes, including authenticated local e2e tests and
the web/VM worker Docker builds.

## Web App

```bash
cd apps/web
npm run build
npm run test
```

The web app uses Vitest and Testing Library. Keep tests colocated with route,
component, or domain modules as `*.test.tsx` or `*.test.ts`. Favor direct tests
of validation and domain helpers for server actions and route handlers. Actor
selection and preview lightbox behavior are covered with component tests.

## Core and VM Worker

```bash
cd packages/core
npm run build
npm run test

cd apps/vm-worker
uv sync --locked
uv run pytest
```

`packages/core` owns shared domain logic and Mongoose access. `apps/vm-worker`
owns long-running metadata polling, resolver/DHT fallback, retry scheduling, and
preview generation.

`apps/e2e/scripts/run-local.sh` starts the Next.js app on top of the local
MongoDB/Cosmos stack. Worker integration is covered separately by deployed dev
smoke verification.

## End-to-End

```bash
cd apps/e2e
npm run test:local
```

Playwright tests cover the authenticated header/account menu, add-video with
actor and tag selection, detail-page actor/tag editing, collection search, and
admin actor/tag flows against the Next.js app. Separate setup projects log in
through Entra for the normal user and admin user and store browser state in
`apps/e2e/.auth/user.json` and `apps/e2e/.auth/admin.json`. Local runs require
real test-user credentials in `apps/e2e/.env.local`. Copy
`apps/e2e/.env.example` to `apps/e2e/.env.local` for local runs or
`apps/e2e/.env.dev` for deployed-dev smoke. Before each local run, the harness
deletes documents for both e2e users and cleans up any orphaned torrent
records and raw blobs so repeated runs do not fail on duplicate data.

## Dev Smoke

```bash
cd apps/e2e
npm run test:smoke:dev
```

Run the dev smoke locally after the GitHub `CI` and `Dev` workflows pass for
the exact commit being validated has been pushed to `develop` and deployed.
Local working-tree changes are not part of the deployed dev app, so a dev smoke
run before commit, push, and deployment only validates the previous deployed
revision. Do not report dev smoke as validation for a local UI or app change
until the matching commit is visible in the `Dev` workflow and the workflow has
completed successfully.

The normal sequence for deployed-dev validation is:

1. Run local package and e2e checks against the local stack.
2. Commit the change and push it through the normal `develop` flow.
3. Wait for GitHub `CI` and the triggered `Dev` deployment to pass for that
   commit.
4. Run `npm run test:smoke:dev` without overriding `DEV_SMOKE_COMMIT_SHA`.
5. For visible UI changes, use Playwright against the deployed dev URL after
   deployment, not only against a local dev server.

The script checks workflow results with GitHub CLI before running Playwright
against the deployed dev URL. `DEV_SMOKE_COMMIT_SHA` is a diagnostic override
for investigating a specific deployed commit; it should not be used to claim
that unpushed local changes passed dev smoke. The smoke verifies the full user
add-video path through the web app, Cosmos DB, the VM worker, Cloudflare R2,
preview generation, preview UI behavior, and the UI metadata-ready state.
Preview UI assertions cover collection carousel navigation and full-size
preview navigation, accepting both complete and degraded preview artifacts when
the VM worker returns a usable result. The smoke expects the Oracle VM worker to
be running separately against the dev MongoDB/R2 environment. The smoke deletes
the created video, torrent, raw blob, and preview artifacts after the assertions
finish.

`apps/e2e/.env.dev` must set the Entra test-user credentials, `E2E_BASE_URL`,
dev Cosmos DB connection, and Cloudflare R2 settings so the smoke can verify
database records, raw torrent blobs, and preview artifacts. The script runs the
dedicated `smoke-dev-chromium` Playwright project so deployed-dev checks stay
out of normal local runs.

## Environment Variables

The local test harness sources `apps/web/.env.local` and `apps/e2e/.env.local`.
The deployed-dev smoke harness sources `apps/web/.env.local` and
`apps/e2e/.env.dev`. Use
`apps/e2e/.env.example` as the template for e2e variables. The tables below
list the test-specific variables. The web and VM worker variables documented in
their own docs are also required for deployed worker verification.

| Variable | Purpose |
| --- | --- |
| `E2E_USER_USERNAME` | Normal test user username. |
| `E2E_USER_PASSWORD` | Normal test user password. |
| `E2E_ADMIN_USERNAME` | Admin test user username. |
| `E2E_ADMIN_PASSWORD` | Admin test user password. |
| `E2E_BASE_URL` | App under test base URL. Defaults to `http://localhost:3000` locally. |
| `E2E_DEV_SMOKE_INFO_HASH` | Overrides the dev smoke torrent hash. |
| `E2E_DEV_SMOKE_PREVIEW_TIMEOUT_MS` | Optional preview-generation timeout for deployed-dev smoke. Defaults to `600000`. |
| `E2E_FORCE_STACK_RESTART` | Restarts the local stack and clears auth state. |
| `DEV_SMOKE_COMMIT_SHA` | Commit SHA checked by the dev smoke script. |
| `MONGODB_URI` | Database connection for local and dev-smoke runs. |
| `MMV_MONGODB_DB_NAME` | Local-stack database name. |
| `R2_ENDPOINT` | Local R2 endpoint when you want remote blob storage. |
| `R2_ACCESS_KEY_ID` | Local R2 access key ID. |
| `R2_SECRET_ACCESS_KEY` | Local R2 secret access key. |
| `R2_BUCKET_NAME` | Local R2 bucket name. |
| `OPENAI_API_KEY` | Required by deployed preview processing. |
| `HEALTH_URL` | Optional local health-check URL. |

## Infrastructure Checks

```bash
cd infra/terraform/envs/dev
terraform fmt -check -recursive ../..
terraform init -backend=false
terraform validate
```

These checks validate Terraform syntax without requiring remote state.
