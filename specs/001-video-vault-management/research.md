# Research: Video Vault Management

## Decision: Use a domain-first FastAPI backend structure with APIRouter modules

**Rationale**: The backend needs separate ownership boundaries for videos,
torrents, tags, users, auth, and storage. FastAPI's documented larger-application
pattern uses `APIRouter` modules that are included in the main app, which maps
well to this domain structure. The requested FastAPI best-practices reference
also emphasizes production conventions and includes an AGENTS.md variant for AI
agent work.

**Alternatives considered**:

- Single-file FastAPI app: rejected because it will create immediate coupling
  between auth, torrent processing, and video workflows.
- Layer-only folders (`models`, `services`, `routers`): rejected because domain
  ownership is less clear as the app grows.

**Sources**:

- https://fastapi.tiangolo.com/tutorial/bigger-applications/
- https://github.com/zhanymkanov/fastapi-best-practices

## Decision: Use SQLModel with Alembic for metadata persistence

**Rationale**: SQLModel is designed to combine table models with Pydantic-style
data models and is documented with FastAPI. It fits the requested stack and keeps
entity definitions close to validation while Alembic owns migrations.

**Alternatives considered**:

- Raw SQLAlchemy models plus separate Pydantic schemas: more explicit but more
  boilerplate for the first slice.
- Direct SQL statements: rejected because relationship modeling, migrations, and
  test fixtures would be harder to maintain.

**Sources**:

- https://sqlmodel.tiangolo.com/tutorial/fastapi/

## Decision: Store canonical metadata in Azure SQL Database and raw torrent files in Azure Blob Storage LRS

**Rationale**: The spec requires relational ownership and many-to-many tag
relationships plus preserved raw torrent files. Azure SQL Database free offer
supports small always-free databases within documented monthly limits, while
Blob Storage LRS is the requested low-cost object store for raw torrent files.

**Alternatives considered**:

- Store raw torrent bytes in the relational database: rejected because it makes
  database backups and row access heavier while object storage better fits
  binary blobs.
- Store all data in blob storage: rejected because collection search, uniqueness,
  user isolation, and tag relationships need relational constraints.

**Sources**:

- https://learn.microsoft.com/en-us/azure/azure-sql/database/free-offer
- https://learn.microsoft.com/en-us/azure/storage/common/storage-redundancy-zrs

## Decision: Use Azure Container Apps consumption plan for backend hosting

**Rationale**: Azure Container Apps supports containerized backend hosting with
free monthly grants for consumption usage and requests. It aligns with Docker
Hub as the external image registry and allows scale-to-zero behavior for a
cost-conscious MVP.

**Alternatives considered**:

- Azure App Service: viable, but less aligned with the requested container app
  target.
- Azure Functions: rejected for the initial backend because the app needs a
  conventional API service, migrations, auth integration, and background work.

**Sources**:

- https://azure.microsoft.com/en-us/pricing/details/container-apps/

## Decision: Use Azure Static Web Apps Free plan for frontend hosting

**Rationale**: Static Web Apps provides a Free plan, GitHub integration, globally
distributed static content, and SSL support. It fits the requested SPA hosting
target and keeps frontend deployment separate from the backend container.

**Alternatives considered**:

- Serve frontend from FastAPI: rejected because it couples frontend deployment
  to backend container releases.
- Azure Blob static website hosting: viable, but Static Web Apps has a better
  app-oriented deployment flow for this SPA.

**Sources**:

- https://learn.microsoft.com/en-us/azure/static-web-apps/plans

## Decision: Use Azure Blob Storage remote backend for Terraform state

**Rationale**: Microsoft documents Azure Storage as a remote Terraform state
store, including the backend fields needed for storage account, container, key,
and access key. The infrastructure workspace will include a bootstrap step for
creating the remote state account/container before normal environment applies.

**Alternatives considered**:

- Local state: rejected because state can include sensitive information and is
  unsuitable for collaboration.
- Terraform Cloud: viable, but the user requested Azure Blob Storage for state.

**Sources**:

- https://learn.microsoft.com/en-us/azure/developer/terraform/store-state-in-azure-storage
- https://developer.hashicorp.com/terraform/language/settings/backends/azurerm

## Decision: Isolate torrent retrieval behind `TorrentMetadataProvider`

**Rationale**: A torrent info hash alone does not contain file metadata; metadata
must be resolved from a torrent source, magnet/DHT retrieval, or a configured
provider. The first implementation will define a provider interface, a
deterministic fake provider for tests, and a real provider adapter that can be
implemented with an existing library or service. The domain stores canonical
metadata only after provider output is validated.

**Alternatives considered**:

- Build BitTorrent/DHT retrieval from scratch: rejected by project guidance to
  search for existing tools and avoid reinventing protocol implementations.
- Make live network retrieval mandatory in tests: rejected because tests must be
  deterministic and independent from peer availability.

**Sources**:

- https://libtorrent.org/tutorial.html
- https://pypi.org/project/bencode2/

## Decision: Use bencode2 for parsing `.torrent` payloads

**Rationale**: Torrent files are bencoded. `bencode2` is a current Python package
that validates inputs and intentionally preserves bencode strings as bytes,
which matters because torrent names and file paths may not be valid UTF-8.
Parsing is kept inside the torrent provider adapter and normalized before data
enters the domain model.

**Alternatives considered**:

- Custom bencode parser: rejected because a maintained package exists.
- Decode all torrent strings to text immediately: rejected because invalid
  encodings are valid in real torrent metadata and must be handled explicitly.

**Sources**:

- https://pypi.org/project/bencode2/

## Decision: Use React + TypeScript with Vite, Vitest, Testing Library, and Playwright

**Rationale**: React officially supports TypeScript in production-grade
frameworks and type definitions. Vitest provides React examples and aligns well
with Vite-based frontend development. Playwright covers cross-application
end-to-end tests and can run repeatable flows for add-video, search, and admin
tag management.

**Alternatives considered**:

- Plain JavaScript: rejected because TypeScript is requested and improves
  maintainability.
- Jest for unit tests: viable, but Vitest is a better fit for Vite projects and
  modern TypeScript workflows.

**Sources**:

- https://react.dev/learn/typescript
- https://v2.vitest.dev/guide/
- https://playwright.dev/docs/test-typescript

## Decision: Use ruff, ty, pytest, and GitHub Actions for backend quality gates

**Rationale**: The constitution requires testable behavior and documented
validation. Ruff covers linting and formatting, ty covers type checking via
`ty check`, pytest covers backend automated tests, and GitHub Actions provides
Python CI workflow support.

**Alternatives considered**:

- Manual validation only: rejected by the testing principle.
- Multiple overlapping Python linters: rejected until there is a proven gap
  because ruff covers formatting and linting in one tool.

**Sources**:

- https://docs.astral.sh/ruff/linter/
- https://docs.astral.sh/ruff/formatter/
- https://docs.astral.sh/ty/type-checking/
- https://docs.github.com/en/actions/tutorials/build-and-test-code/python
