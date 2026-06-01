# Web App

The active product surface lives in `apps/web`, a Next.js App Router
application.

## Responsibilities

- Own the UI routes and server actions.
- Handle Auth.js sign-in with Microsoft Entra ID.
- Read and write the shared Mongoose models in `packages/core`.
- Serve the auth callback and health-check route handlers.

## Structure

- `src/app`: collection, add-video, actor profile, detail, admin-actors,
  admin-tags, admin-torrents, sign-in, and route handler segments.
- `src/components`: shared UI for the header, avatar, user menu, search form,
  video cards, torrent previews, and metadata status.
- `src/auth.ts`: Auth.js configuration for Entra sign-in, database sessions,
  and admin resolution.
- `src/lib`: compatibility exports and auth/session guards around shared core
  logic.

## Routes

- `/`: the signed-in user collection with search.
- `/add`: add a video by torrent info hash and assign existing actors and tags.
- `/actors/[id]`: view the shared actor profile, description, profile image, and
  signed-in user's videos featuring the actor through detected or manual
  attribution.
- `/tags/[id]`: view the signed-in user's videos assigned a shared catalog tag.
- `/videos/[id]`: view detected actors, edit manual actors/tags, and delete
  private video details.
- `/admin/actors`: admin-only actor catalog management.
- `/admin/tags`: admin-only tag management.
- `/admin/torrents`: admin-only torrent management and deletion.
- `/auth/sign-in`: explicit sign-in page.
- `/api/auth/[...nextauth]`: Auth.js handler.
- `/api/health`: deployment health check.
- `/api/me/photo`: Microsoft Graph avatar lookup with an initial-based SVG
  fallback when Graph does not return a profile photo.
- `/api/actors/[id]/image`: authenticated actor profile-image proxy for
  private blob-store objects.
- `/api/videos/[id]/preview/[artifact]`: authenticated preview artifact proxy
  for torrent preview sheets and frames stored in R2.
- `/api/admin/torrents/[id]/preview/[artifact]`: admin-only preview artifact
  proxy by canonical torrent ID for torrent management.

## Data Flow

- Sign-in upserts the local `users` document with the Entra object ID, admin
  flag, name, email, and image.
- Adding a video normalizes the info hash, reuses or creates the canonical
  torrent, applies selected actors to the shared manual actor list, creates the
  user-owned video, attaches any selected tags, and marks metadata as pending.
- Updating a video detail view can change the private fields, replace the
  video's existing tag links with the selected catalog tags, and replace the
  canonical torrent's shared manual actor list. Detected actors remain
  read-only in this form.
- Deleting a video removes its private tags and, when it was the last video
  referencing the canonical torrent, deletes the torrent metadata and raw blob.
- Admin torrent deletion removes the torrent, its dependent videos and video
  tags, the stored raw blob, and preview artifacts.
- Admin torrent management can view stored preview sheets and frames by torrent
  ID and reset preview attempts, which returns preview status to `pending`
  without deleting existing artifacts.
- Admin torrent management shows actor-analysis status and can queue one
  selected torrent for reanalysis without clearing its current detected actors.
- Admin actor deletion removes the actor, pulls it from all torrent actor lists,
  and deletes the stored profile image.
- Detail and admin changes revalidate the affected routes so the server-rendered
  views stay current.
- Preview sheets and frames are served through authenticated route handlers so
  private R2 object keys are never exposed as public URLs.
- Collection, detail, and admin preview images use consistent full-size
  lightbox navigation with prominent side-aligned previous/next controls.
  Torrent previews render expanded by default on video detail pages and
  collapsed by default on the admin torrent management page.
  Detail torrent file folders render collapsed by default so long file lists do
  not dominate the page.
- Read-only tags on collection cards, actor and tag result cards, and video
  detail pages link to tag result pages. Actor and tag result pages list only
  the signed-in user's private collection in newest-first order.
- Collection cards paginate in newest-first order. Admin actor, tag, and
  torrent catalogs support URL-backed filtering and pagination so large
  catalogs remain navigable.
- Narrow layouts collapse primary navigation behind a menu button, keep
  preview thumbnails in a compact two-column grid, and stack failed metadata
  details below their status badge.

## Worker Boundary

The web app marks torrent metadata or actor reanalysis as pending, but it does
not process torrent metadata, preview images, or faces itself. Metadata, preview
generation, and actor identification are handled by the VM-hosted
`apps/vm-worker` process. Shared domain logic for the web app stays in
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
| `R2_ENDPOINT` | Cloudflare R2 S3-compatible endpoint. |
| `R2_ACCESS_KEY_ID` | Cloudflare R2 access key ID. |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 secret access key. |
| `R2_BUCKET_NAME` | Cloudflare R2 bucket name. |
