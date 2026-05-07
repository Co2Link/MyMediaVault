# Deployment

The only deployed environment is dev. Production infrastructure and production
release workflows are intentionally out of scope until requested.

## CI

`.github/workflows/ci.yml` runs on pull requests and pushes to `develop` or
`main`. It uses path filters so the web and Functions jobs only run when the
shared app/core code changes, and the Terraform job only runs when infrastructure
changes.

- Web job: Node 24, `npm ci`, `npm run build`, and `npm run test`.
- Functions job: Node 22, `npm ci`, `npm run build`, and `npm run test`.
- Terraform job: `terraform fmt -check -recursive ../..`,
  `terraform init -backend=false`, and `terraform validate`.

## Dev Workflow

`.github/workflows/dev.yml` runs after `CI` succeeds on `develop`.

1. It builds and pushes the web Docker image from `apps/web/Dockerfile`.
2. It resolves the repo-owned Azure Blob backend key with Azure CLI, then runs
   `terraform init -reconfigure`, `terraform plan`, and `terraform apply` in
   `infra/terraform/envs/dev`.
3. It builds and zip-deploys `apps/functions` to the Function App.
4. It smoke-checks `GET /api/health` on the deployed web app and verifies that
   the Function App exists.

The dev Terraform stack uses repo-owned Azure Blob remote state:

- resource group: `rg-mymediavault-tfstate`
- storage account: `mymediavaulttfstate`
- container: `tfstate`
- app state key: `mymediavault-dev.tfstate`

## Azure Resources

Dev infrastructure is defined in `infra/terraform/envs/dev` and modules under
`infra/terraform/modules`.

- Resource group: `rg-${prefix}`.
- Web: public Azure Container Apps Node.js 24 runtime for the Next.js server.
- Functions: Azure Functions Flex Consumption Node.js 22 app with one maximum
  instance, queue trigger, poison queue handler, and timer repair trigger.
- Database: Azure Cosmos DB for MongoDB account created by this repository.
- Storage: Standard LRS storage account with private `torrent-raw` and
  `function-packages` containers plus the `torrent-metadata-jobs` queue.
- Observability: Log Analytics workspace with 30-day retention and
  workspace-based Application Insights for the Function App.

## Function KQL

Useful starter queries in the Log Analytics workspace:

```kusto
traces
| where message has "Torrent metadata"
| order by timestamp desc
```

```kusto
exceptions
| order by timestamp desc
```

```kusto
traces
| where message has "dead_lettered" or message has "poison"
| order by timestamp desc
```

```kusto
traces
| where customDimensions.jobId != ""
| order by timestamp desc
```

## Required Secrets and Variables

GitHub Actions expects Docker Hub credentials, Azure credentials, `AUTH_SECRET`,
Entra client credentials, and optional admin object/group IDs. Keep all secrets
in GitHub or local `.env` files; never commit them.
