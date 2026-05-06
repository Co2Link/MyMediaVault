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

The repository no longer includes the retired FastAPI backend or Vite frontend.
The previous `dev.yml` deployment workflow targeted those legacy apps and has
been removed. Dev deployment automation for the current Next.js web server and
worker will need a new workflow when that path is requested.

## Azure Resources

Dev infrastructure is still defined in `infra/terraform/envs/dev` and modules
under `infra/terraform/modules`.

- Resource group: `rg-${prefix}`.
- Web: target shape is a public Azure Container Apps Node runtime for the Next.js
  server.
- Worker: target shape is a private worker process using the same build artifact.
- Database: Azure SQL free database using `AutoPause`.
- Storage: Standard LRS storage account with private `torrent-raw` container.

## Required Secrets and Variables

GitHub Actions expects Docker Hub credentials, Azure credentials, Terraform
state variables, `DATABASE_URL`, Auth.js Entra credentials, database admin
password, and optional admin object IDs. Keep all secrets in GitHub or local
`.env` files; never commit them.
