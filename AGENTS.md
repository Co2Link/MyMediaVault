# Repository Guidelines

- az cli and github cli are available, ask user to run `az login` or `gh auth login` when needed.
- Prefer the best practice when deciding on infrastructure, architecture, code structure, and implementation, even if it requires more effort, unless the user specifies otherwise. If you are unsure about the best practice, ask the user for clarification or suggest a few options with pros and cons.
- Run e2e tests at the end of the change to verify the overall behavior, ask user to setup the required environment if needed.
- Local testing and development use the local MongoDB service defined in `.devcontainer/docker-compose.yml`.
- Production uses Azure Cosmos DB for MongoDB vCore.
- You are in a devcontainer environment, ask user to rebuild the container if you update devcontainer configuration or Dockerfile.
- Do not hardcode any secrets, ID, or credentials in the codebase.
- When you update any AGENTS.md, it should be general guidelines and not specific to this repo.

<!-- BEGIN:nextjs-agent-rules -->
 
# Next.js: ALWAYS read docs before coding
 
Before any Next.js work, find and read the relevant doc in `node_modules/next/dist/docs/`. Your training data is outdated — the docs are the source of truth.
 
<!-- END:nextjs-agent-rules -->

## Project Structure & Module Organization

MyMediaVault is a video collection manager monorepo. Main code lives under `apps/`: `apps/web` is the Next.js full-stack application, `apps/vm-worker` is the long-running metadata and preview worker, and `apps/e2e` contains Playwright tests. Shared domain, database, storage, and torrent logic lives in `packages/core`. Infrastructure lives in `infra/terraform`; architecture and decisions live in `docs`.

## Build, Test, and Development Commands

Web:

```bash
cd apps/web
npm ci
npm run dev
npm run build
npm run test
```

End-to-end and infrastructure:

```bash
cd apps/e2e && npm ci && npm run test:local
cd infra/terraform/envs/dev && terraform fmt -check -recursive ../.. && terraform init -backend=false && terraform validate
```

Enable the tracked pre-commit hook in `.githooks` with `git config core.hooksPath .githooks` to run checks matching CI before commits.

## Coding Style & Naming Conventions

The active application uses TypeScript in Next.js with PascalCase component files and colocated route or domain helpers under `apps/web/src`. Keep Terraform formatted with `terraform fmt`.

## Testing Guidelines

Web tests use Vitest and Testing Library with `*.test.tsx` or `*.test.ts` naming. E2E tests use Playwright specs in `apps/e2e/tests`; local authenticated runs require env files for `apps/web` and `apps/e2e/.env.local`.

## Commit & Pull Request Guidelines

- Commit messages should be concise and use a bulleted list.
- Branch from `develop` and merge back by pull request.
- PRs should summarize behavior changes, list checks run, link related issues or docs, and include screenshots for visible UI changes.

## Security & Configuration Tips

Do not commit `.env` files, Entra credentials, database passwords, Terraform secrets, or Playwright test-user credentials. Prefer env names already documented in CI and README.

## Documentation Maintenance

Coding agents own `docs/`. Treat docs/index.md as the documentation entry point and read the relevant linked documents before changing code. When behavior changes, update the matching Markdown file in the same change. Create a focused `.md` when no existing doc fits, and link it from `docs/index.md`.

## Python guidelines
- Use uv to manage python environment, do not edit pyproject.toml directly.
- Tool preferences
  - loguru for logging.
  - ty for type checking.
  - ruff for linting and formatting.
