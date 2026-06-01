# Documentation Index

This directory is the project documentation source of truth. Coding agents must
update these documents when implementation, architecture, deployment, data model,
testing, or workflow behavior changes.

## Project Map

- [Overview](overview.md): product summary, runtime shape, and request flow.
- [Web App](web-app.md): Next.js routes, auth, and UI responsibilities.
- [Worker](worker.md): VM worker processing and runtime config.
- [Data Model](data-model.md): persisted entities, relationships, constraints,
  and metadata states.

## Workflows

- [Local Development](local-development.md): environment setup and local run
  commands.
- [Testing Strategy](testing.md): web, core, e2e, dev smoke, and CI checks.
- [Deployment](deployment.md): dev deployment flow and Azure resources.
- [Branching Strategy](branching-strategy.md): branch rules and release
  boundaries.

## Feature Design

- [Actor Identification Plan](actor-identification-plan.md): staged
  implementation record and verification plan for asynchronous main-actor
  identification.

## Architecture Decisions

- [ADR 001: Asynchronous Actor Identification](decisions/001-asynchronous-actor-identification.md):
  accepted design for durable global actor identities, biometric evidence, and
  the downstream VM-worker pipeline.
