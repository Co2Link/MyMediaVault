# End-to-End Validation

Date: 2026-04-27

Commands run from `apps/e2e`:

```bash
npx playwright install chromium
npx playwright install-deps chromium
npx playwright test
```

Local services were started in test mode:

```bash
MMV_ENVIRONMENT=test MMV_TEST_MODE=true MMV_DATABASE_URL=sqlite:///./e2e.db uv run fastapi dev app/main.py --host 0.0.0.0 --port 8000
npm run dev -- --host 0.0.0.0
```

Results:

- First run failed because Chromium browser binaries were missing.
- Second run failed because OS browser libraries were missing.
- After installing Chromium and dependencies, `npx playwright test` passed:
  5 tests passed.
