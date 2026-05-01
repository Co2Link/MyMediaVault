# Deployment

The only deployed environment is dev. Production infrastructure and production
release workflows are intentionally out of scope until requested.

## CI

`.github/workflows/ci.yml` runs on pull requests and pushes to `develop` or
`main`.

- Backend job: `uv sync --all-groups`, Ruff format check, Ruff lint, `ty check`,
  and `pytest`.
- Frontend job: Node 24, `npm ci`, `npm run build`, and `npm run test`.
- Terraform job: `terraform fmt -check -recursive ../..`,
  `terraform init -backend=false`, and `terraform validate`.

## Dev Workflow

`.github/workflows/dev.yml` runs after the `CI` workflow succeeds on `develop`.
It checks out the exact CI commit, builds and pushes the backend Docker image,
applies Terraform, builds the frontend with Terraform output values, deploys to
Azure Static Web Apps, and smoke-tests both frontend and backend.

Backend images are tagged both as the configured base image and as
`<image>-<commit_sha>`. Terraform passes the deployed commit into
`MMV_COMMIT_SHA`; the smoke test verifies `/health` returns that SHA.

## Azure Resources

Dev infrastructure is defined in `infra/terraform/envs/dev` and modules under
`infra/terraform/modules`.

- Resource group: `rg-${prefix}`.
- Backend: Azure Container Apps, external ingress on port 8000, zero minimum
  replicas, ten-minute cooldown.
- Frontend: Azure Static Web Apps Free tier.
- Database: Azure SQL free database using `AutoPause`.
- Storage: Standard LRS storage account with private `torrent-raw` container.

The backend deployment also injects torrent resolver settings into the Container
App. Dev defaults use the direct HTTP resolver provider with
`https://itorrents.org/torrent/{info_hash}.torrent`, a 20 second fetch timeout,
and the in-process torrent worker enabled.

## Required Secrets and Variables

GitHub Actions expects Docker Hub credentials, Azure credentials, Terraform state
variables, Entra IDs/scopes, backend image name, database admin password, and
optional admin object IDs. Keep all secrets in GitHub or local `.env` files;
never commit them.
