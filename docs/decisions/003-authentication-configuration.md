# Decision: Authentication Configuration

Status: accepted.

Production authentication uses Entra ID through the backend authentication
dependency. Protected API access requires a standard bearer token flow, and the
OpenAPI documentation is configured for PKCE against the separate OpenAPI app
registration.

Automated backend tests override the current-user dependency in-process instead
of using alternate transport headers. Frontend code uses MSAL and requires
`VITE_ENTRA_TENANT_ID`, `VITE_ENTRA_CLIENT_ID`, and `VITE_API_SCOPE`.

Local Playwright e2e tests do perform a real Entra browser sign-in with
credentials from `apps/e2e/.env.local`. GitHub CI currently runs backend and
frontend tests, while the authenticated local e2e suite is run through the
tracked pre-commit hook and `npm run test:local`.
