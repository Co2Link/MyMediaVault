# Backend Validation

Date: 2026-04-27

Commands run from `apps/backend`:

```bash
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
```

Results:

- `ruff format`: passed, formatted backend files.
- `ruff check`: passed.
- `ty check`: passed.
- `pytest`: passed, 24 tests.

Residual risk:

- Cloud SQL, blob storage, and production Entra ID paths still require
  environment-backed validation.
