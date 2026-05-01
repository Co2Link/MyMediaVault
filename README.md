# MyMediaVault

MyMediaVault is a monorepo for a video collection manager. Users add videos by
torrent info hash, the backend stores canonical torrent metadata once per info
hash, and each user maintains private video details such as title, description,
rating, and tags.

## Repository Layout

```text
apps/backend      FastAPI backend
apps/frontend     React SPA
apps/e2e          Playwright tests
docs              Project decisions and workflow guidance
infra/terraform   Azure infrastructure
specs/001-video-vault-management   Spec Kit artifacts
```

## Branching and Deployment

The default integration branch is `develop`. Feature work should branch from
`develop` and merge back through pull requests. A push to `develop` runs CI; the
dev environment deploys only after the `CI` workflow succeeds on `develop`. See
[docs/branching-strategy.md](docs/branching-strategy.md) for the agent-facing
rules.

## Git Hooks

Enable the tracked pre-commit hook once per clone:

```bash
git config core.hooksPath .githooks
```

The hook runs the backend, frontend, and Terraform checks that mirror CI.
It also runs the local authenticated Playwright browser suite through
`apps/e2e/.env.local`, so Entra test-user credentials must be available there.

## Backend

```bash
cd apps/backend
uv sync --all-groups
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```

Run locally:

```bash
cd apps/backend
uv run fastapi dev app/main.py
```

## Frontend

```bash
cd apps/frontend
npm install
npm run build
npm run test
```

Run locally:

```bash
cd apps/frontend
npm run dev
```

## End-to-End Tests

```bash
cd apps/e2e
npm install
npm run test:local
```

`npm run test:local` starts backend and frontend automatically, loads env from
`apps/backend/.env`, `apps/frontend/.env`, and `apps/e2e/.env.local`, performs
real Entra login, and runs the browser suite against the local stack.

## Infrastructure

```bash
cd infra/terraform/bootstrap
terraform init
terraform plan
```

After remote state storage exists:

```bash
cd ../envs/dev
terraform init
terraform plan
```
