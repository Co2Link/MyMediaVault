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
- `ty check`: passed with one deprecation warning for FastAPI `on_event`.
- `pytest`: passed, 22 tests.

Residual risk:

- The FastAPI startup hook uses `on_event`, which is deprecated. It is tracked
  as a future cleanup and does not block current behavior.
