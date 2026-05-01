# Local Development

Use the dev container when available. The repository expects Python managed by
`uv`, Node.js 24 for frontend/e2e packages, and Terraform for infrastructure
validation.

## Backend

```bash
cd apps/backend
uv sync --all-groups
uv run fastapi dev app/main.py
```

Backend settings load from `apps/backend/.env` with the `MMV_` prefix. Local
defaults use SQLite at `sqlite:///./mymediavault.db` and filesystem blob storage
under `.local/blob-storage` unless Azure storage variables are set. For live
`.torrent` resolution, set `MMV_TORRENT_PROVIDER=http` and provide
`MMV_TORRENT_RESOLVER_URLS` as a JSON array of resolver URL templates such as
`["https://itorrents.org/torrent/{info_hash}.torrent"]`.

## Frontend

```bash
cd apps/frontend
npm ci
npm run dev
```

Required frontend variables are `VITE_API_BASE_URL`, `VITE_ENTRA_TENANT_ID`,
`VITE_ENTRA_CLIENT_ID`, and `VITE_API_SCOPE`.

## End-to-End Local Stack

```bash
cd apps/e2e
npm ci
npm run test:local
```

`test:local` sources `apps/backend/.env`, `apps/frontend/.env`, and
`apps/e2e/.env.local`, starts backend and frontend if they are not already
running, waits for readiness, then runs Playwright. `apps/e2e/.env.local` must
define `E2E_ENTRA_USERNAME` and `E2E_ENTRA_PASSWORD`; use
`apps/e2e/.env.local.example` as the template.

## Git Hooks

Enable the tracked hook once per clone:

```bash
git config core.hooksPath .githooks
```

The hook runs backend lint/type/tests, frontend build/tests, authenticated local
e2e tests, and Terraform formatting/validation.
