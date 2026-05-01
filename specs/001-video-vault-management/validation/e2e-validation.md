# End-to-End Validation

Date: 2026-05-01

Commands run from `apps/e2e`:

```bash
npx playwright install chromium
npx playwright install-deps chromium
```

Results:

- Playwright dependencies can be installed locally.
- Browser Playwright execution is not considered a supported validation path in
  the current repository because the application intentionally has no runtime
  auth-bypass mode and no documented shared authenticated browser environment.
- `apps/e2e/tests/canonical-torrent.spec.ts` is currently closer to an API test
  scaffold than a browser e2e flow and sends headers the backend runtime does
  not consume.
- `apps/e2e/tests/test-mode-fixtures.spec.ts` validates local fixture objects,
  not end-to-end application behavior.

Conclusion:

- Keep the Playwright files as scaffolding for future authenticated-environment
  coverage.
- Do not treat `apps/e2e` as part of the default validation bar until a real
  browser-authenticated execution path is defined and documented.
