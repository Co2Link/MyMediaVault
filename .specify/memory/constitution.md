<!--
Sync Impact Report
Version change: template -> 1.0.0
Modified principles:
- Template principle 1 -> I. Code Quality Is Non-Negotiable
- Template principle 2 -> II. Tests Define Acceptable Behavior
- Template principle 3 -> III. User Experience Consistency
- Template principle 4 -> IV. Performance Budgets Are Requirements
- Template principle 5 -> V. Maintainable Delivery
Added sections:
- Engineering Standards
- Delivery Workflow
Removed sections:
- None
Templates requiring updates:
- Updated: .specify/templates/plan-template.md
- Updated: .specify/templates/spec-template.md
- Updated: .specify/templates/tasks-template.md
- Reviewed, no change required: .specify/extensions/git/commands/*.md
Follow-up TODOs: None
-->

# MyMediaVault Constitution

## Core Principles

### I. Code Quality Is Non-Negotiable

All production code MUST be simple, cohesive, and locally understandable. Each
module MUST have one clear responsibility, explicit data boundaries, and names
that describe domain intent. Duplication MUST be removed when it obscures
behavior or creates competing sources of truth. New abstractions MUST be backed
by current use, not speculative reuse. Dead code, unexplained global state, and
silent error handling are not acceptable in merged work.

Rationale: MyMediaVault will grow around user media workflows where data loss,
confusing behavior, and hidden coupling are expensive to diagnose.

### II. Tests Define Acceptable Behavior

Every behavior change MUST include automated tests at the lowest useful level,
plus integration or contract tests when a user journey, persistence boundary,
external service, or shared interface is affected. Bug fixes MUST include a
regression test that fails without the fix. Tests MUST be deterministic,
isolated from developer-specific state, and runnable through documented commands.
Uncovered changes require an explicit plan entry explaining why automation is
not practical and how the behavior will be verified.

Rationale: Tests are the executable agreement that future changes did not break
existing media organization, retrieval, or playback behavior.

### III. User Experience Consistency

User-facing work MUST follow existing interaction patterns, terminology,
navigation structure, accessibility conventions, and visual density unless a
feature plan explicitly approves a change. Primary user journeys MUST be
specified with acceptance scenarios and independently demonstrable outcomes.
Interfaces MUST provide clear loading, empty, error, and success states for the
states they can enter. Copy MUST use domain language consistently and avoid
surprising users with implementation details.

Rationale: A media vault depends on user trust; consistent workflows make stored
content feel predictable and recoverable.

### IV. Performance Budgets Are Requirements

Each feature plan MUST define measurable performance expectations for the
affected path, including latency, throughput, memory, storage, startup, or
rendering targets where applicable. Implementations MUST avoid avoidable
full-library scans, blocking user interactions, unbounded memory growth, and
unmeasured background work. Performance-sensitive changes MUST include a
repeatable measurement method and document results before release.

Rationale: Media libraries can become large quickly, so acceptable behavior at
small scale is not evidence that the product remains usable at real scale.

### V. Maintainable Delivery

Work MUST be delivered in small, reviewable increments that map back to a
feature specification, plan, and task list. Each increment MUST preserve the
ability to build, test, and run the project from documented commands. Cross-cutting
changes MUST include migration notes or compatibility guidance when they affect
data, configuration, APIs, or user-visible behavior. Complexity that violates a
constitution gate MUST be documented with a simpler alternative and a concrete
reason for rejection.

Rationale: Traceable delivery keeps project decisions auditable and keeps future
maintenance from depending on personal memory.

## Engineering Standards

Feature plans MUST identify the language, framework, storage, testing tools,
target platform, performance goals, and constraints before implementation
begins. Specifications MUST include measurable success criteria, UX expectations,
and non-functional requirements when they affect users or operations.

Code review MUST verify the following before merge:

- The implementation matches the specification and preserves existing behavior.
- Automated tests cover new behavior and relevant regressions.
- UX states, terminology, and accessibility expectations are consistent.
- Performance budgets are defined, measured, or explicitly marked not applicable.
- Any accepted complexity is recorded in the plan's Complexity Tracking table.

## Delivery Workflow

Development MUST follow the Spec Kit flow: specification, implementation plan,
task generation, implementation, and validation. Constitution Check gates in
plans MUST pass before Phase 0 research and be re-evaluated after Phase 1 design.
Tasks MUST be grouped by independently testable user stories and include quality,
test, UX, and performance work required by the plan.

Before marking work complete, the implementer MUST run the relevant automated
tests and any documented validation commands. If a command cannot be run, the
reason and remaining risk MUST be recorded with the delivery summary.

## Governance

This constitution supersedes conflicting project practices, templates, and
informal guidance. Amendments require a documented change to this file, a Sync
Impact Report, updates to affected templates or runtime guidance, and a version
change following semantic versioning.

Versioning policy:

- MAJOR: Removes or redefines a core principle or governance requirement in a
  backward-incompatible way.
- MINOR: Adds a principle or materially expands required governance, workflow,
  quality, testing, UX, or performance obligations.
- PATCH: Clarifies wording, fixes errors, or makes non-semantic refinements.

Compliance review is required for every feature plan and code review. Plans MUST
explain any constitution gate violation in Complexity Tracking before work
continues. Reviewers MUST block changes that omit required tests, ignore UX
consistency, leave performance budgets undefined for performance-sensitive work,
or introduce unjustified complexity.

**Version**: 1.0.0 | **Ratified**: 2026-04-27 | **Last Amended**: 2026-04-27
