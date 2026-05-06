# Branching Strategy

The default integration branch is `develop`. All feature work should branch from
`develop` and merge back through a pull request unless the user explicitly asks
for a direct commit.

## Branches

- `develop`: active development branch. A push to `develop` runs CI.
- `main`: reserved for future production releases. Do not target `main` for dev
  deployment changes.
- Feature branches: keep them focused on one feature or infrastructure change.

## Agent Rules

- Read this document before changing CI/CD, deployment, or release behavior.
- Keep `docs/` current with implementation and workflow changes; update
  [Documentation Index](index.md) when adding, removing, or renaming docs.
- Keep local work on the current feature branch unless the user asks to switch.
- Push feature work to the matching feature branch first.
- Push to `develop` only when the user asks for integration on `develop`.
- Do not push deployment workflow changes to `main` unless the user explicitly
  requests a production release path.
- If a change affects deployment, document whether it is CI-only, dev deploy, or
  future production work.

## Current Environments

- Dev is the only deployed environment.
- Production infrastructure and production deployment workflows are intentionally
  out of scope until requested.
- Dev deployment is intentionally cost constrained and should stay aligned with
  Azure free-tier or always-free resources where possible.
