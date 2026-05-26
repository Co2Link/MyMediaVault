# Deployment

The only deployed environment is dev. Production infrastructure and production
release workflows are intentionally out of scope until requested.

## CI

`.github/workflows/ci.yml` runs on pull requests and pushes to `develop` or
`main`. It uses path filters so the web and worker jobs only run when the
shared app/core code changes, and the Terraform job only runs when infrastructure
changes. Pushes to `develop` also publish the same path-filter results for the
dev deployment workflow.

- Web job: Node 24, `npm ci`, `npm run build`, and `npm run test`.
- Worker job: Node 24, `npm ci`, `npm run build`, and `npm run test`.
- Preview worker job: Python 3.13, `uv sync --locked`, and `uv run pytest`.
- Terraform job: `terraform fmt -check -recursive ../..`,
  `terraform init -backend=false`, and `terraform validate`.
- CI result job: verifies that every required or skipped validation job reached
  an acceptable result, giving PRs and pushes one explicit aggregate status.

## Dev Workflow

`.github/workflows/dev.yml` runs after `CI` succeeds on `develop`. It can also
be started manually to apply Terraform with the current deployed image, which is
useful after changing GitHub repository secrets or variables that Terraform
passes into Azure runtime configuration.

CI publishes its path-filter results as a short-lived artifact for successful
`develop` pushes, and the dev workflow uses those flags to avoid unnecessary
deployment work.

1. It builds and pushes the web Docker image from `apps/web/Dockerfile` only
   when the web app or shared core package changes. The public image uses
   Next.js standalone output so only traced production runtime files are copied
   into the final image.
1. It builds and pushes the worker Docker image from `apps/worker/Dockerfile`
   only when the worker app or shared core package changes. The public image
   copies compiled worker/core output and production dependencies only.
1. It builds and pushes the preview worker Docker image from
   `apps/preview-worker/Dockerfile` only when preview worker code or workflows
   change. The image is published to the same Docker Hub namespace as the web
   image, using the `-preview-worker:<commit-sha>` suffix. The tag supports
   `linux/amd64` and `linux/arm64` VMs. VM deployment remains manual.
2. It runs `terraform init -reconfigure`, `terraform plan`, and
   `terraform apply` in `infra/terraform/envs/dev` only when Terraform files or
   workflows change. Infra-only runs query the currently deployed web image and
   commit metadata, plus the currently deployed worker image, inside the
   Terraform job instead of publishing a new app revision.
3. It deploys the Container App only when a new web image was pushed. If
   Terraform also ran, Terraform applies the new image; otherwise Azure CLI
   updates the Container App image and commit environment variable.
4. It smoke-checks `GET /api/health` on the deployed web app and verifies that
   the event-driven worker job exists after successful CI and successful or
   skipped deploy prerequisites. The smoke check validates the new commit only
   when a web image was deployed.

The dev Terraform stack uses Cloudflare R2-backed remote state:

- bucket: `mymediavault-tfstate`
- state key: `envs/dev/terraform.tfstate`
- backend: Terraform S3-compatible backend configured with the R2 endpoint

Bootstrap state is written locally once under `infra/terraform/bootstrap`, which
creates the R2 bucket before the remote backends are initialized.

## Azure Resources

Dev infrastructure is defined in `infra/terraform/envs/dev` and modules under
`infra/terraform/modules`.

- Resource group: `rg-${prefix}`.
- Web: public Azure Container Apps Node.js 24 runtime for the Next.js server.
  Terraform sets `AUTH_URL` to the external Container App FQDN so Entra/Auth.js
  redirects return to the deployed app instead of an internal runtime address.
  The app can scale to zero and now uses a 300-second scale-in cooldown so it
  stops billing idle replicas sooner.
- Worker: event-driven Azure Container Apps job that uses the KEDA MongoDB
  scaler to start when queued torrent metadata jobs exist. It uses the same auth
  settings as the web app because the shared core environment loader is used by
  both HTTP and worker code paths.
- Preview worker: long-running Docker container on a manually managed Azure
  Linux VM. The VM runs a root-owned systemd service that pulls the exact Docker
  Hub image tag from `/etc/mymediavault/preview-worker.env` and starts the
  container in the foreground. The container image runs the Python worker as a
  non-root user and includes Python 3.13, `libtorrent`, `ffmpeg`, and
  `ffprobe`; preview artifacts are stored in R2 so the VM stays stateless.
- Database: Azure Cosmos DB for MongoDB vCore free-tier cluster created by this
  repository, configured for MongoDB 8.0 so the Node MongoDB driver can connect
  through Mongoose. The Mongo vCore firewall includes the Azure-services rule
  so Container Apps and KEDA can reach the cluster without maintaining
  per-revision outbound IP allowlists.
- Storage: raw torrent blobs live in Cloudflare R2, and Terraform state uses
  the R2 backend.
- Observability: Log Analytics workspace with 30-day retention for the worker
  job and web app.

## Worker KQL

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
| where message has "Torrent metadata jobs repaired"
| order by timestamp desc
```

```kusto
traces
| where customDimensions.jobId != ""
| order by timestamp desc
```

## Required Secrets and Variables

GitHub Actions expects Docker Hub credentials, Azure credentials, `AUTH_SECRET`,
Entra client credentials, optional admin object/group IDs, and
`uv_index_lingxt_password` for installing the `torrent-preview` package from the
Azure Artifacts `lingxt` feed. The Azure Artifacts username is the dummy value
`az`. The preview worker VM also needs its own root-owned environment file with
MongoDB, R2, OpenAI, and image reference settings. Keep all secrets in GitHub,
VM-local secret files, or local `.env` files; never commit them.

## GitHub Actions Configuration Policy

The dev workflows intentionally use a simple repo-level configuration model.
Application configuration that is not sensitive is stored as GitHub repository
variables, and sensitive application configuration is stored as GitHub
repository secrets. Azure CLI is used only for operational deployment lookups,
such as the current Container App image, worker job, and smoke-test resource
discovery.

Do not duplicate Terraform-owned resource values in GitHub variables. Values
created or owned by Terraform should flow through Terraform resources, data
sources, outputs, or module inputs. Azure CLI lookups should stay limited to
runtime deployment state that is outside Terraform's current graph.

OIDC-based Azure login and Azure Key Vault-backed app secrets are preferred
future hardening options, but they are not part of the current simple dev
workflow.
