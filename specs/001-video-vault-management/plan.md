# Implementation Plan: Video Vault Management

**Branch**: `001-video-vault-management` | **Date**: 2026-04-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-video-vault-management/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Build the first usable slice of MyMediaVault as a monorepo with backend,
frontend, infra, and end-to-end test workspaces. The slice lets signed-in users
add videos by torrent info hash, stores canonical torrent metadata once per info
hash, links user-specific video records to that canonical torrent, supports
personal collection search, supports administrator tag management, and establishes
repeatable local and CI validation.

The technical approach is a FastAPI backend with domain-first modules, SQLModel
entities backed by Azure SQL Database, Azure Blob Storage for raw torrent files,
React + TypeScript SPA frontend, Terraform-managed Azure infrastructure, and
backend/frontend automated validation with retained Playwright scaffolding for
future authenticated browser coverage. Torrent metadata retrieval is isolated
behind a provider interface so the MVP can use deterministic fixtures in tests
and a real metadata provider without spreading protocol-specific details through
the domain.

## Technical Context

**Language/Version**: Python 3.14 for backend; TypeScript on Node.js for frontend; Terraform HCL for infrastructure  
**Primary Dependencies**: FastAPI with `fastapi[standard]`, fastapi-azure-auth, SQLModel, Alembic, Azure SDK packages, bencode2 for torrent parsing, React, Vite, Vitest, Testing Library, Playwright CLI  
**Storage**: Azure SQL Database for metadata; Azure Blob Storage LRS for raw torrent files and Terraform state; local development storage emulators or filesystem-backed test doubles where practical  
**Testing**: pytest for backend unit/integration and contract tests; ty for backend type checking; ruff for backend linting/formatting; Vitest + Testing Library for frontend tests; Playwright CLI scaffolding for future authenticated browser coverage  
**Target Platform**: Web SPA hosted on Azure Static Web Apps; backend container hosted on Azure Container Apps; infrastructure provisioned with Terraform against Azure  
**Project Type**: Monorepo with `apps/backend`, `apps/frontend`, `infra/terraform`, shared docs, GitHub Actions CI/CD, and Playwright scaffolding for future browser coverage  
**Performance Goals**: Video submission acknowledged within 2 seconds; collection search returns visible results or empty state within 2 seconds for 10,000 videos; duplicate torrent submissions do not create duplicate canonical records  
**Constraints**: Use `uv add` instead of editing backend `pyproject.toml` manually; keep first delivery minimal; avoid a dedicated runtime auth-bypass mode; prefer established libraries over custom implementations; use Azure always-free or consumption-tier services where possible  
**Scale/Scope**: Initial MVP supports one web app, one backend API, one Azure environment, 10,000 videos per user for search validation, canonical torrent reuse, admin tag management, and test infrastructure

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Code quality**: Backend modules are organized by domain boundary
  (`videos`, `torrents`, `tags`, `users`, `auth`, `storage`) with API routers
  separated from services and persistence. Frontend code is organized by
  features and shared UI primitives. Torrent retrieval is isolated behind a
  provider interface to avoid coupling domain logic to protocol tooling.
- **Testing**: Required layers are backend unit tests, backend integration tests
  with test database/storage doubles, backend behavioral contract tests plus
  generated OpenAPI checks, frontend component tests, and regression tests for
  duplicate info hash handling and user isolation. Playwright assets are kept as
  scaffolding until a stable authenticated browser environment is defined.
- **UX consistency**: The first UI establishes the product patterns for
  collection list, detail view, add-video form, metadata status, search empty
  state, error state, and admin-only tag management. Accessibility requirements
  include keyboard navigation, visible focus, labels, and status messaging.
- **Performance**: The plan defines 2-second budgets for video submission
  acknowledgement and collection search at 10,000 videos. Search uses indexed
  fields and pagination rather than full-library scans. Duplicate torrent writes
  rely on a database uniqueness constraint and transaction-safe upsert behavior.
- **Maintainable delivery**: Local setup, validation, migration, and deployment
  commands are documented in quickstart.md. CI includes backend lint, type check,
  and tests. Complexity is tracked below because the monorepo spans backend,
  frontend, infra, and end-to-end concerns in the first feature.

**Post-design re-check**: PASS. research.md resolves technology choices and
risks; data-model.md defines constraints and state transitions; backend contract
tests and generated OpenAPI define API behavior; quickstart.md documents
commands; no unresolved clarification markers remain.

## Project Structure

### Documentation (this feature)

```text
specs/001-video-vault-management/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── tasks.md
```

### Source Code (repository root)

```text
apps/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   └── routers/
│   │   ├── core/
│   │   ├── auth/
│   │   ├── users/
│   │   ├── torrents/
│   │   ├── videos/
│   │   ├── tags/
│   │   ├── storage/
│   │   └── testsupport/
│   ├── alembic/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── contract/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── features/
│   │   │   ├── videos/
│   │   │   ├── tags/
│   │   │   └── auth/
│   │   ├── shared/
│   │   └── test/
│   ├── tests/
│   ├── package.json
│   └── vite.config.ts
└── e2e/
    ├── tests/
    ├── fixtures/
    └── playwright.config.ts

infra/
└── terraform/
    ├── bootstrap/
    ├── envs/
    │   └── dev/
    └── modules/

.github/
└── workflows/
    ├── ci.yml
    └── dev.yml

docs/
└── decisions/
```

**Structure Decision**: Use a workspace monorepo with independent backend,
frontend, e2e, and Terraform areas. Backend and frontend remain deployable
separately, while `apps/e2e` retains Playwright scaffolding for future
authenticated browser scenarios.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| First feature spans backend, frontend, infra, CI, and e2e | The repository is empty and the spec requires a working app foundation, deployment target, and repeatable validation before feature iteration | A backend-only slice would not satisfy the user's monorepo, frontend, infra, or Playwright foundation requirements |
| Torrent metadata provider abstraction | Info-hash-only metadata retrieval depends on external network/protocol behavior and library support; tests need deterministic behavior without live peers | Directly embedding one library call in video submission would make tests flaky and couple domain logic to retrieval mechanics |
