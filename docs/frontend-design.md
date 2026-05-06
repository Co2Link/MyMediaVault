# Frontend Design

The active application is the Next.js App Router app in `apps/web`. It combines
UI routes, Auth.js session handling, server-side data access, and the internal
health/photo/auth route handlers in one package.

## Application Structure

- `src/app`: route tree for collection, add-video, detail, admin tags, sign-in,
  and route handlers.
- `src/components`: reusable UI such as header, avatar dropdown, status badges,
  and collection cards.
- `src/auth.ts`: Auth.js configuration for Microsoft Entra ID plus Prisma
  adapter callbacks.
- `src/lib`: Prisma access, validation, blob storage adapters, and torrent/job
  domain logic shared by pages and the worker.
- `src/worker`: long-running polling worker for torrent metadata processing.
- `Dockerfile`: production image definition used by the dev deployment workflow
  for both the public web server and the private worker process.

## Authentication Flow

The app requires `AUTH_SECRET`, Entra client credentials, issuer, and
`DATABASE_URL`. Auth.js performs the sign-in redirect, requests account
selection, stores server-side sessions, and records the Entra object ID and
admin status on the shared `User` row.

The header avatar uses the signed-in user profile information from Auth.js and
attempts to fetch the Entra photo through Microsoft Graph at `/api/me/photo`,
falling back to initials when no photo is available.

## User Experience

The active routes are `/`, `/add`, `/videos/[id]`, `/admin/tags`, and
`/auth/sign-in`. Collection search is query-string based and rendered from a
server component. Add and edit flows use server actions. Admin tag management is
guarded both in the page and in the server actions.

Tests use Vitest and Testing Library in `apps/web/src`.
