# Frontend Design

The frontend is a Vite React application in `apps/frontend`. Source lives under
`apps/frontend/src` and is organized by app shell, shared API code, auth, tags,
and videos.

## Application Structure

- `src/main.tsx`: initializes MSAL, then renders the app inside `MsalProvider`
  and `AuthGate`.
- `src/app/App.tsx`: simple in-memory navigation between collection, add video,
  video detail, and admin tags.
- `src/features/auth`: Entra/MSAL configuration, sign-in gate, and admin-only UI
  guard.
- `src/shared/api/client.ts`: fetch wrapper that requires `VITE_API_BASE_URL`,
  acquires bearer tokens, and normalizes API errors.
- `src/features/videos`: collection search, add form, metadata status display,
  detail editing, and typed API helpers.
- `src/features/tags`: admin tag management UI and typed API helpers.

## Authentication Flow

The app requires `VITE_ENTRA_TENANT_ID`, `VITE_ENTRA_CLIENT_ID`, and
`VITE_API_SCOPE` at build/runtime. `AuthGate` redirects unauthenticated users
through MSAL. API calls use `acquireTokenSilent` first and fall back to popup
acquisition when interaction is required.

Admin tag management is hidden behind an `AdminOnly` component that checks token
roles for `Admin` or `MyMediaVault.Admin`. The backend still enforces admin
authorization, so this UI guard is only a convenience.

## User Experience

The app exposes four current screens: collection search, add video, video detail,
and admin tags. Collection search currently sends text queries to `/videos` and
displays torrent metadata status. Add video accepts info hash, optional title,
description, and rating. Add-video responses are asynchronous: the UI should
expect `202 Accepted` with `metadataStatus` still `pending` or `processing`, and
subsequent reads surface completion or failure. Detail view allows editing
private video fields and shows torrent files when metadata is available.

Tests use Vitest and Testing Library with colocated `*.test.tsx` files.
