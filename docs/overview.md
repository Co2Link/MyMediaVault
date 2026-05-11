# Overview

MyMediaVault is an authenticated video collection manager. Users sign in with
Microsoft Entra ID, add videos by torrent info hash, and keep private
title/description/rating data while shared torrent metadata is reused once per
normalized info hash.

## Runtime Shape

- `apps/web`: Next.js app that owns the UI, Auth.js, server actions, and most
  write paths.
- `packages/core`: shared models, validation, storage, torrent provider, and
  torrent metadata processing logic.
- `apps/functions`: scheduled worker code for torrent metadata polling and
  processing.
- `apps/e2e`: Playwright coverage for local-stack and deployed-dev verification.
- `infra/terraform`: dev environment and Azure resource definitions.

## Request Flow

1. The user signs in through Auth.js and Entra.
2. The user adds a video by torrent info hash.
3. The web app writes user-owned video rows and creates a torrent metadata job.
4. The timer worker claims queued jobs from MongoDB, resolves the torrent,
   stores the raw payload in Cloudflare R2, and writes parsed metadata back to
   Cosmos DB.
5. The UI shows metadata-ready state once processing completes.
