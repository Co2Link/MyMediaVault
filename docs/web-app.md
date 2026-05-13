# Web App

The active product surface lives in `apps/web`, a Next.js App Router
application.

## Responsibilities

- Own the UI routes and server actions.
- Handle Auth.js sign-in with Microsoft Entra ID.
- Read and write the shared Mongoose models in `packages/core`.
- Serve the auth callback and health-check route handlers.

## Structure

- `src/app`: collection, add-video, detail, admin-tags, admin-torrents, sign-in, and route
  handler segments.
- `src/components`: shared UI for the header, avatar, user menu, search form,
  video cards, and metadata status.
- `src/auth.ts`: Auth.js configuration for Entra sign-in, database sessions,
  and admin resolution.
- `src/lib`: compatibility exports and auth/session guards around shared core
  logic.

## Routes

- `/`: the signed-in user collection with search.
- `/add`: add a video by torrent info hash and assign existing tags.
- `/videos/[id]`: view, edit, tag, and delete private video details.
- `/admin/tags`: admin-only tag management.
- `/admin/torrents`: admin-only torrent management and deletion.
- `/auth/sign-in`: explicit sign-in page.
- `/api/auth/[...nextauth]`: Auth.js handler.
- `/api/health`: deployment health check.
- `/api/me/photo`: Microsoft Graph avatar lookup.

## Data Flow

- Sign-in upserts the local `users` document with the Entra object ID, admin
  flag, name, email, and image.
- Adding a video normalizes the info hash, reuses or creates the canonical
  torrent, creates the user-owned video, attaches any selected tags, and
  creates a MongoDB-backed metadata job.
- Updating a video detail view can change the private fields and replace the
  video's existing tag links with the selected catalog tags.
- Deleting a video removes its private tags and, when it was the last video
  referencing the canonical torrent, deletes the torrent metadata and raw blob.
- Admin torrent deletion removes the torrent, its dependent videos and video
  tags, the metadata job records, and the stored raw blob.
- Detail and admin changes revalidate the affected routes so the server-rendered
  views stay current.

## Worker Boundary

The web app creates metadata jobs for `apps/worker`, but it does not process
torrent metadata itself. Shared domain logic for both apps stays in
`packages/core`.

## Environment Variables

The web app reads the shared loader in `packages/core/src/env.ts` and the
Auth.js config in `apps/web/src/auth.ts`.

| Variable | Purpose |
| --- | --- |
| `AUTH_URL` | Auth.js callback base URL for the deployed web app. |
| `AUTH_SECRET` | Auth.js session secret. |
| `AUTH_MICROSOFT_ENTRA_ID_ID` | Microsoft Entra client ID. |
| `AUTH_MICROSOFT_ENTRA_ID_SECRET` | Microsoft Entra client secret. |
| `AUTH_MICROSOFT_ENTRA_ID_ISSUER` | Entra issuer URL. |
| `MONGODB_URI` | Mongoose connection string. |
| `MMV_MONGODB_DB_NAME` | Database name. |
| `MMV_MONGODB_SERVER_SELECTION_TIMEOUT_MS` | Mongo driver server-selection timeout. |
| `MMV_COMMIT_SHA` | Commit label for health/debug output. |
| `MMV_ADMIN_OBJECT_IDS` | Entra object IDs with admin access. |
| `MMV_ADMIN_GROUP_OBJECT_IDS` | Entra group IDs with admin access. |
| `MMV_TORRENT_PROVIDER` | Torrent provider mode. |
| `MMV_TORRENT_RESOLVER_URLS` | HTTP resolver URL templates. |
| `MMV_TORRENT_FETCH_TIMEOUT_SECONDS` | HTTP torrent fetch timeout. |
| `MMV_TORRENT_REPAIR_STALE_PROCESSING_MINUTES` | Stale processing-job threshold. |
| `R2_ENDPOINT` | Cloudflare R2 S3-compatible endpoint. |
| `R2_ACCESS_KEY_ID` | Cloudflare R2 access key ID. |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 secret access key. |
| `R2_BUCKET_NAME` | Cloudflare R2 bucket name. |
