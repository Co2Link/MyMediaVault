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
uv init --package
uv add "fastapi[standard]" fastapi-azure-auth sqlmodel alembic azure-storage-blob bencode2
uv add --dev pytest pytest-asyncio httpx ruff ty
```

Do not edit `pyproject.toml` directly to add dependencies. Use `uv add` so the
lockfile and dependency metadata stay in sync.

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
npm create vite@latest . -- --template react-ts
npm install
npm install -D vitest @testing-library/react @testing-library/user-event @testing-library/jest-dom jsdom
```

## Frontend Validation

```bash
cd apps/frontend
npm run build
npm run test
```

## End-to-End Setup

```bash
cd apps/e2e
npm init -y
npm install -D @playwright/test typescript
npx playwright install --with-deps
```

## End-to-End Validation

Run the backend and frontend in test mode, with authentication bypass enabled
only for local and CI test environments.

```bash
cd apps/e2e
npx playwright test
```

Core scenarios:

- Standard user adds a video by info hash and sees a processing status.
- Metadata completion fixture updates the video detail view.
- User searches by title, tag, rating, torrent name, and info hash.
- Second user cannot see the first user's video.
- Two users adding the same info hash reuse one canonical torrent.
- Admin creates, renames, and deletes tags.
- Non-admin cannot access tag management actions.

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

Backend CI must run:

- ruff format check
- ruff lint
- ty type check
- pytest unit and integration tests

Frontend CI must run:

- frontend build
- frontend tests

End-to-end CI must run Playwright tests against a test-mode deployment or local
services with deterministic torrent metadata fixtures.

## Test Mode Requirements

- Authentication bypass must be explicit and unavailable in production
  configuration.
- Test users must include one standard user, one second standard user, and one
  administrator.
- Torrent metadata provider must support deterministic fixtures for success,
  failure, delayed processing, large file list, and duplicate info hash cases.
