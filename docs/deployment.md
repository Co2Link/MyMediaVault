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
2. It runs `terraform init -reconfigure`, `terraform plan`, and `terraform apply`
   in `infra/terraform/envs/dev`.
3. It smoke-checks `GET /api/health` on the deployed web app and verifies that
   the worker container app has a current revision.

The dev Terraform stack uses Azure Blob remote state with Azure AD auth:

- resource group: `rg-tfstate`
- storage account: `stlingxttfstate`
- container: `tfstate`
- app state key: `mymediavault-dev.tfstate`
- shared infra contract key: `shared-infra.tfstate`

## Azure Resources

Dev infrastructure is still defined in `infra/terraform/envs/dev` and modules
under `infra/terraform/modules`.

- Resource group: `rg-${prefix}`.
- Web: target shape is a public Azure Container Apps Node runtime for the Next.js
  server.
- Worker: target shape is a private worker process using the same build artifact.
- Database: shared Azure SQL server and database read from the shared-infra
  remote state contract.
- Storage: Standard LRS storage account with private `torrent-raw` container.

## Required Secrets and Variables

GitHub Actions expects Docker Hub credentials, Azure credentials, the shared SQL
admin password, `AUTH_SECRET`, Entra client credentials, and optional admin
object/group IDs. Keep all secrets in GitHub or local `.env` files; never
commit them.
