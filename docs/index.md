# Documentation Index

This directory is the project documentation source of truth. Coding agents must
update these documents when implementation, architecture, deployment, data model,
testing, or workflow behavior changes.

## Core Design

- [Architecture](architecture.md): system components, request flow, and deployed topology.
- [Application Features](features.md): current user-facing and admin capabilities.
- [Backend Design](backend-design.md): FastAPI structure, API routes, domain services, authentication, and storage.
- [Frontend Design](frontend-design.md): React application structure, auth flow, and UI behavior.
- [Data Model](data-model.md): persisted entities, relationships, constraints, and metadata states.

## Operations

- [Local Development](local-development.md): environment setup and local run commands.
- [Testing Strategy](testing.md): backend, frontend, e2e, and CI checks.
- [Deployment](deployment.md): dev deployment flow and Azure resources.
- [Branching Strategy](branching-strategy.md): branch rules and release boundaries.

## Decisions

- [001: Canonical Torrent Reuse](decisions/001-canonical-torrent-reuse.md)
- [002: API Contract Validation](decisions/002-api-contract-validation.md)
- [003: Authentication Configuration](decisions/003-authentication-configuration.md)
- [004: Torrent Metadata Provider](decisions/004-torrent-metadata-provider.md)
