# Deployment

The only deployed environment is dev. Production infrastructure and production
release workflows are intentionally out of scope until requested.

## CI

`.github/workflows/ci.yml` runs on pull requests and pushes to `develop` or
`main`.

- Web job: Node 24, `npm ci`, `npx prisma generate`, `npm run build`, and
  `npm run test`.
- Terraform job: `terraform fmt -check -recursive ../..`,
  `terraform init -backend=false`, and `terraform validate`.

## Dev Workflow

`.github/workflows/dev.yml` runs after `CI` succeeds on `develop`.

1. It builds and pushes one Docker image from `apps/web/Dockerfile`.
2. It resolves the repo-owned Azure Blob backend key with Azure CLI, then runs
   `terraform init -reconfigure`, `terraform plan`, and `terraform apply` in
   `infra/terraform/envs/dev`.
3. It smoke-checks `GET /api/health` on the deployed web app and verifies that
   the worker container app has a current revision.

The dev Terraform stack uses repo-owned Azure Blob remote state:

- resource group: `rg-mymediavault-tfstate`
- storage account: `mymediavaulttfstate`
- container: `tfstate`
- app state key: `mymediavault-dev.tfstate`

## Azure Resources

Dev infrastructure is defined in `infra/terraform/envs/dev` and modules under
`infra/terraform/modules`.

- Resource group: `rg-${prefix}`.
- Web: target shape is a public Azure Container Apps Node runtime for the Next.js
  server.
- Worker: target shape is a private worker process using the same build artifact.
- Database: Azure SQL server and database created by this repository.
- Storage: Standard LRS storage account with private `torrent-raw` container.

## Required Secrets and Variables

GitHub Actions expects Docker Hub credentials, Azure credentials, the database
admin password, `AUTH_SECRET`, Entra client credentials, and optional admin
object/group IDs. Keep all secrets in GitHub or local `.env` files; never
commit them.
