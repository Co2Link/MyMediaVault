# Stale File Dependencies

## Symptoms

- A shared package was rebuilt, but a consumer app still reports old types or behavior.
- `npm install` completes, but the consumer keeps reading an outdated copied package from `node_modules`.
- Errors reference a missing prop, old export, or stale declaration file that exists in the source package now.

## Refresh Pattern

1. Build the source package.
1. Identify every consumer using a local path or `file:` dependency.
1. Remove the copied package directory from each affected consumer's `node_modules`.
1. Reinstall dependencies in that consumer.
1. Rebuild the consumer and retest.

## Repo Example

- Source package: `packages/core`
- Consumers: `apps/web`, `apps/functions`
- Typical stale path: `apps/web/node_modules/@mymediavault/core`
- Typical refresh sequence:
  - `npm --prefix packages/core run build`
  - `rm -rf apps/web/node_modules/@mymediavault/core`
  - `npm install` in `apps/web`
  - Repeat for other consumers as needed

## Avoid

- Reinstalling the source package over and over when the stale copy lives in the consumer.
- Changing source code just to satisfy an old consumer install.
- Updating lockfiles unless the dependency graph actually changed.
