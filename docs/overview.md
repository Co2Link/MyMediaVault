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
3. The web app writes user-owned video rows and queues the canonical torrent.
4. The VM worker claims FIFO torrent sessions atomically, resolves metadata,
   stores the raw payload in Cloudflare R2, downloads useful ranges, and
   generates preview artifacts.
5. The worker analyzes durable preview frames sequentially, reuses or creates
   global actor identities, and writes system-managed torrent actor assignments.
6. The UI shows processing state, detected actors, and separately editable
   manual actor assignments once processing completes.
