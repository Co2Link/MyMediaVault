# Quickstart: Video Vault Management

## Prerequisites

- Open the repository in the devcontainer.
- Confirm the devcontainer provides Python 3.14, Node.js, Terraform CLI, Azure
  CLI, uv, and the Playwright CLI skill/tooling.
- Authenticate to Azure only when provisioning or deploying infrastructure.

## Repository Areas

```text
apps/backend      FastAPI backend
apps/frontend     React SPA
apps/e2e          Playwright end-to-end tests
infra/terraform   Azure infrastructure
specs/001-video-vault-management   Feature design artifacts
```

## Backend Setup

```bash
cd apps/backend
uv sync --all-groups
```

When adding or updating backend dependencies, use `uv add` rather than editing
`pyproject.toml` directly so the lockfile and dependency metadata stay in sync.

## Backend Validation

```bash
cd apps/backend
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```

## Frontend Setup

```bash
cd apps/frontend
npm ci
```

## Frontend Validation

```bash
cd apps/frontend
npm run build
npm run test
```

## Playwright Assets

```bash
cd apps/e2e
npm ci
npx playwright install --with-deps
```

For local authenticated runs, create `apps/e2e/.env.local` from
`apps/e2e/.env.local.example` and set:

- `E2E_ENTRA_USERNAME`
- `E2E_ENTRA_PASSWORD`
- optional `E2E_BASE_URL`

## Playwright Validation Status

`npm run test:local` starts the backend and frontend automatically using
`apps/backend/.env`, `apps/frontend/.env`, and `apps/e2e/.env.local`, then runs
Playwright against the local stack.

```bash
cd apps/e2e
npm run test:local
```

Core scenarios:

- Standard user adds a video by info hash and sees a processing status.
- Metadata completion fixture updates the video detail view.
- User searches by title, tag, rating, torrent name, and info hash.
- Second user cannot see the first user's video.
- Admin creates, renames, and deletes tags.
- Non-admin cannot access tag management actions.

Current status:

- The repository intentionally does not provide a standalone runtime auth-bypass
  mode for browser end-to-end execution.
- Browser Playwright execution is available locally through `npm run test:local`
  and is also part of the tracked pre-commit hook.
- Backend tests use in-process dependency overrides; frontend tests mock MSAL at
  the component-test layer.

## Infrastructure Bootstrap

Create the remote Terraform state storage before applying the environment.

```bash
cd infra/terraform/bootstrap
terraform init
terraform plan
terraform apply
```

Then initialize the development environment with the Azure Blob backend.

```bash
cd ../envs/dev
terraform init
terraform plan
```

Use `terraform apply` only when ready to provision or update Azure resources.

## CI Expectations

To run CI-equivalent checks before committing, enable the tracked pre-commit
hook once per clone:

```bash
git config core.hooksPath .githooks
```

CI currently runs:

- ruff format check
- ruff lint
- ty type check
- pytest unit and integration tests

- frontend build
- frontend tests
- local authenticated Playwright browser tests
- terraform fmt and validate

## Test Mode Requirements

- Local browser validation requires a real Entra test user configured through
  `apps/e2e/.env.local`.
