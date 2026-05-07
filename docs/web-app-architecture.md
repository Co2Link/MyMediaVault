# Web App Architecture

The active codebase is a single Next.js App Router application in `apps/web`.
It owns the UI, Auth.js session handling, route handlers, and server actions.
Shared database/domain/storage logic lives in `packages/core`, and torrent
metadata processing runs in `apps/functions`.

## Application Structure

- `src/app`: collection, add-video, detail, admin tags, sign-in, and route
  handler segments.
- `src/components`: shared UI for the header, avatar, user menu, search form,
  video cards, and metadata status.
- `src/auth.ts`: Auth.js configuration for Microsoft Entra ID, database
  sessions, and admin resolution.
- `src/lib`: compatibility exports and auth/session guards. Most shared domain
  logic is implemented in `packages/core`.
- `Dockerfile`: web image for the Container Apps deployment.
- `../functions`: Azure Functions queue worker for torrent metadata jobs.

## Routing and Rendering

- `src/app/layout.tsx` loads the shared shell, background, fonts, and header.
- Pages are Server Components by default. Client Components are used only for
  interactive pieces such as the user menu and form state.
- Active route handlers include `/api/auth/[...nextauth]`, `/api/health`, and
  `/api/me/photo`.
- The public UI routes are `/`, `/add`, `/videos/[id]`, `/admin/tags`, and
  `/auth/sign-in`.

## Authentication

- Users sign in through Microsoft Entra ID via Auth.js.
- Sessions are database-backed, and the sign-in event upserts the local
  `users` document with the Entra object ID, admin flag, name, email, and
  profile image.
- Admin access is resolved from configured Entra object IDs, Entra group
  claims, or a Microsoft Graph `checkMemberGroups` fallback when group IDs are
  configured.
- The avatar uses the session image when available and falls back to
  `/api/me/photo`, which fetches the signed-in user's photo from Microsoft
  Graph.

## Data Flow

- `/` renders the user's collection and supports query-string search across
  title, description, torrent name, and info hash.
- `/add` normalizes the info hash, reuses or creates the canonical torrent
  document, creates the user-owned video, and enqueues a Storage Queue-backed
  metadata job. Adding the same torrent twice for the same user returns a
  conflict instead of creating a duplicate document.
- `/videos/[id]` shows and edits private video fields and renders torrent
  metadata status plus resolved file entries.
- `/admin/tags` is admin-only and uses server actions to create, rename, and
  delete tags.
- Each mutation revalidates the affected routes so server-rendered views stay
  current.

## Torrent Processing

- Torrent metadata is abstracted behind a provider interface so tests can use
  deterministic fixtures and production can use HTTP resolver URLs.
- The Azure Functions worker consumes `torrent-metadata-jobs`, fetches the raw
  `.torrent` payload, stores it in blob storage, and writes parsed metadata
  plus file lists back to the database.
- Invalid queue messages retry and can move to `torrent-metadata-jobs-poison`;
  the poison handler marks recoverable jobs `dead_lettered`.
- A timer trigger periodically re-enqueues stale `queued` and `processing`
  metadata jobs.
- Canonical torrent rows are keyed by normalized info hash, so multiple users
  can point at the same torrent without sharing private video fields.
