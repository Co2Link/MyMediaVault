---
name: refresh-file-dependencies
description: Diagnose and refresh stale file-based package dependencies in monorepos when a shared package changes but consumer apps, workers, or tests still read old builds from copied local installs. Use when a package is linked with a local path or `file:` dependency and reinstalling alone does not clear stale types or runtime code.
---

# Refresh File Dependencies

## Overview

Use this skill when a shared package has been rebuilt, but a consuming app still sees outdated declarations, code, or tests. The usual fix is to refresh the consumer copy of the package, not to keep reinstalling the source package itself.

## Workflow

1. Rebuild the source package first.
1. Check which consumers depend on it via a local path or `file:` reference.
1. If a consumer still sees stale output, remove the copied package from that consumer's `node_modules`.
1. Reinstall that consumer's dependencies.
1. Rebuild or retest the consumer.
1. Repeat for each affected consumer package.

## Decision Points

- Prefer refreshing the consumer install over changing source code when the error points at old declaration output.
- Avoid repeated reinstall cycles in the source package unless its build output is actually wrong.
- If multiple apps consume the package, refresh each consumer separately.
- Keep unrelated workspace edits out of the fix.

## Reference

Load [references/stale-file-dependencies.md](references/stale-file-dependencies.md) for the full stale-copy checklist and command pattern.
