# Overview

MyMediaVault is an authenticated video collection manager. Users sign in with
Microsoft Entra ID, add videos by torrent info hash, and keep private
title/description/rating data while shared torrent metadata is reused once per
normalized info hash.

## Runtime Shape

- `apps/web`: Next.js app that owns the UI, Auth.js, server actions, and most
  write paths.
- `packages/core`: shared models, validation, storage, and domain logic.
- `apps/vm-worker`: long-running VM worker for torrent metadata, preview
  processing, and actor identification.
- `apps/e2e`: Playwright coverage for local-stack and deployed-dev verification.
- `infra/terraform`: dev environment and Azure resource definitions.

## Request Flow

1. The user signs in through Auth.js and Entra.
2. The user adds a video by torrent info hash.
3. The web app writes user-owned video rows and marks the canonical torrent as
   pending metadata.
4. The VM worker claims pending torrent documents atomically, resolves the
   torrent, stores the raw payload in Cloudflare R2, writes parsed metadata
   back to Cosmos DB, and then generates preview artifacts.
5. The worker analyzes durable preview frames sequentially, reuses or creates
   global actor identities, and writes system-managed torrent actor assignments.
6. The UI shows metadata-ready state, detected actors, and separately editable
   manual actor assignments once processing completes.
