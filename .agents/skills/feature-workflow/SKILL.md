---
name: feature-workflow
description: "Use when a user asks to add a new feature, change existing behavior, or otherwise modify application code in this repo. Clarify requirements only when needed, then make the code change, add or update tests as needed, run relevant verification, and commit the result."
---

# Feature Workflow

## Workflow

1. Restate the requested behavior in one sentence.
2. If the request is ambiguous, ask the smallest clarifying question and stop.
3. Otherwise inspect the relevant code paths and implement the smallest correct change.
4. Add or update tests when behavior changes or regression risk is non-trivial.
5. Run the narrowest meaningful verification first, then broader checks only if needed.
6. Update repo docs when the behavior change affects documented user-facing behavior.
7. Commit the finished change with a concise message.

## Guardrails

- Prefer existing conventions and architecture.
- Keep the diff focused; avoid unrelated refactors.
- Fix failing tests or build errors before finishing.
- If the requested change touches multiple areas, handle the critical path first and defer side work only when safe.
