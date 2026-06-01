---
name: frontend-dev-ux-fix
description: Inspect a deployed development frontend with playwright-cli, authenticate with admin credentials from repository env files, identify UI/UX defects and improvements, obtain explicit user approval for the fix set, implement only approved changes, commit and push to deploy, then verify the deployed fixes. Use when Codex is asked to audit a dev frontend and carry approved UI/UX fixes through deployment verification.
---

# Frontend Dev UX Fix

## Overview

Run a browser-driven UI/UX audit against the deployed development environment and carry explicitly approved fixes through implementation, deployment, and verification. Use the `playwright-cli` skill for browser automation.

## Workflow

### 1. Read Repository Guidance

- Read the repository `AGENTS.md` files and relevant documentation before editing.
- Read the `playwright-cli` skill and use it for frontend inspection.
- Before changing a Next.js application, read the relevant installed Next.js documentation required by repository guidance.
- Inspect `git status` before making changes. Preserve unrelated user changes.

### 2. Discover Dev Configuration

- Read development environment files such as `apps/e2e/.env.dev` and `apps/web/.env.dev`.
- Use the configured deployed dev URL when available.
- Use admin credentials from env files. Never print, hardcode, commit, or include credential values in reports.
- If authentication requires interactive account access that cannot be completed from the available env files, ask the user for the minimum required action.

### 3. Audit With playwright-cli

- Open the deployed dev frontend and log in as the admin user.
- Inspect the main user workflows and admin workflows that are reachable from the application shell.
- Exercise responsive layouts at desktop and narrow mobile widths.
- Check snapshots, screenshots when useful, console errors, and failed network requests.
- Test empty, pending, error, and long-content states when reachable.
- Prefer read-only exploration. If a create, update, or delete operation is necessary, record the initial state first and restore it before reporting findings.
- Close the browser session after the audit.

### 4. Report Findings and Stop

- Report concrete findings ordered by severity.
- Include reproduction steps, affected viewport or workflow, observed behavior, expected behavior, and a concise recommended fix.
- Mention any failed request or console error that affects user experience.
- Confirm whether application data was mutated and restored.
- Ask the user which findings to fix.
- Stop and wait for explicit approval. Do not edit source files, commit, push, or deploy before approval.

### 5. Implement Approved Fixes

- Implement only the approved findings.
- Follow existing repository patterns and keep the patch scoped.
- Update documentation when behavior changes.
- Add or update focused automated tests for the affected behavior.
- Run relevant checks and the repository-required end-to-end tests. If environment setup blocks a required test, report the exact prerequisite.

### 6. Commit and Push

- Review `git diff` and `git status`. Exclude unrelated changes from the commit.
- Commit the approved fix with the repository's required commit-message format.
- Push the current branch to trigger the dev deployment.
- If GitHub authentication is missing, ask the user to run `gh auth login`.
- Determine deployment status using repository CI or deployment tooling. Wait for the dev deployment to complete successfully before browser verification.

### 7. Verify Deployed Dev

- Reopen the deployed dev frontend with `playwright-cli`.
- Authenticate as the admin user.
- Repeat each approved defect's reproduction steps against the deployed build.
- Check relevant desktop and mobile layouts, console errors, and failed network requests.
- Confirm that each approved defect is fixed and report any remaining issues.
- Restore any verification data mutations and close the browser session.
