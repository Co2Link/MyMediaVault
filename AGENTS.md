# Repository Guidelines

## Project Structure & Module Organization

MyMediaVault is a video collection manager monorepo. Main code lives under `apps/`: `apps/backend` is FastAPI, `apps/frontend` is the Vite/React SPA, and `apps/e2e` contains Playwright tests. Backend source is in `apps/backend/app`, migrations in `apps/backend/alembic`, and tests in `apps/backend/tests/{unit,integration,contract}`. Frontend source is in `apps/frontend/src`. Infrastructure lives in `infra/terraform`; architecture and decisions live in `docs`.

## Build, Test, and Development Commands

Backend:

```bash
cd apps/backend
uv sync --all-groups
uv run fastapi dev app/main.py
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```

Frontend:

```bash
cd apps/frontend
npm ci
npm run dev
npm run build
npm run test
```

End-to-end and infrastructure:

```bash
cd apps/e2e && npm ci && npm run test:local
cd infra/terraform/envs/dev && terraform fmt -check -recursive ../.. && terraform init -backend=false && terraform validate
```

Enable the tracked pre-commit hook in `.githooks` with `git config core.hooksPath .githooks` to run checks matching CI before commits.

## Coding Style & Naming Conventions

Python uses Ruff with a 120-character line length and type checking through `ty`. Use 4-space indentation, snake_case modules/functions, and PascalCase Pydantic/SQLModel schemas. React uses TypeScript modules with PascalCase component files such as `CollectionPage.tsx`; colocate feature helpers and tests in `features/*`. Keep Terraform formatted with `terraform fmt`.

## Testing Guidelines

Backend tests use `pytest`; name files `test_*.py` and place them in the appropriate `unit`, `integration`, or `contract` directory. Frontend tests use Vitest and Testing Library with `*.test.tsx` naming. E2E tests use Playwright specs in `apps/e2e/tests`; local authenticated runs require env files for backend, frontend, and `apps/e2e/.env.local`.

## Commit & Pull Request Guidelines

Recent commits use short imperative subjects, for example `Fix CI checks and gate dev deploys` or `Add local authenticated e2e flow`. Branch from `develop` and merge back by pull request. PRs should summarize behavior changes, list checks run, link related issues or docs, and include screenshots for visible frontend changes.

## Security & Configuration Tips

Do not commit `.env` files, Entra credentials, database passwords, Terraform secrets, or Playwright test-user credentials. Prefer env names already documented in CI and README.

## Documentation Maintenance

Coding agents own `docs/`. Treat [docs/index.md](/workspaces/MyMediaVault/docs/index.md) as the documentation entry point and read the relevant linked documents before changing code that affects architecture, APIs, data models, tests, deployment, or workflows. When behavior changes, update the matching Markdown file in the same change. Create a focused `.md` when no existing doc fits, and link it from `docs/index.md`.
