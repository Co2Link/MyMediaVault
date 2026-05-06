# Testing Strategy

Testing is split by application layer and mirrored by `.github/workflows/ci.yml`
where practical.

The tracked pre-commit hook runs these check groups selectively based on staged
paths, so web checks run for `apps/web`, e2e runs for `apps/web` or `apps/e2e`, and
Terraform checks run only for `infra/terraform`.

## Web App

```bash
cd apps/web
npx prisma generate
npm run build
npm run test
```

The web app uses Vitest and Testing Library. Keep tests colocated with route,
component, or domain modules as `*.test.tsx` or `*.test.ts`. Favor direct tests
of validation and domain helpers for server actions, route handlers, and worker
logic.

## End-to-End

```bash
cd apps/e2e
npm run test:local
```

Playwright tests cover the authenticated header/account menu, add-video,
collection search, and admin tag flows against the Next.js app. Separate setup
projects log in through Entra for the normal user and admin user and store
browser state in
`apps/e2e/.auth/user.json` and `apps/e2e/.auth/admin.json`. Local runs require
real test-user credentials in `apps/e2e/.env.local`. Before each local run, the
harness deletes rows for both e2e users and cleans up any orphaned torrent
records and raw blobs so repeated runs do not fail on duplicate data.

## Infrastructure Checks

```bash
cd infra/terraform/envs/dev
terraform fmt -check -recursive ../..
terraform init -backend=false
terraform validate
```

These checks validate Terraform syntax without requiring remote state.
