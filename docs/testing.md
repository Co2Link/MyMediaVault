# Testing Strategy

Testing is split by application layer and mirrored by `.github/workflows/ci.yml`
where practical.

The tracked pre-commit hook runs these check groups selectively based on staged
paths, so backend checks run only for `apps/backend` changes, frontend checks
only for `apps/frontend`, e2e for `apps/backend`, `apps/frontend`, or
`apps/e2e`, and Terraform checks only for `infra/terraform`.

## Backend

```bash
cd apps/backend
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```

Backend tests use `pytest` with an in-memory SQLite database and dependency
overrides from `apps/backend/tests/conftest.py`. Unit tests cover validation,
authorization, torrent upsert, provider behavior, and search statement building.
Integration tests cover add-video behavior, duplicate conflicts, authentication,
admin tags, canonical torrent reuse, search, and user isolation. Contract tests
verify route behavior and OpenAPI auth schema expectations.

## Frontend

```bash
cd apps/frontend
npm run build
npm run test
```

Frontend tests use Vitest and Testing Library. Keep tests colocated with feature
components as `*.test.tsx` and mock `fetch` or auth boundaries where needed.

## End-to-End

```bash
cd apps/e2e
npm run test:local
```

Playwright tests cover authenticated add-video, collection search, and admin tag
flows. The setup project logs in through Entra and stores browser state in
`apps/e2e/.auth/user.json`. Local runs require real test-user credentials in
`apps/e2e/.env.local`.

## Infrastructure Checks

```bash
cd infra/terraform/envs/dev
terraform fmt -check -recursive ../..
terraform init -backend=false
terraform validate
```

These checks validate Terraform syntax without requiring remote state.
