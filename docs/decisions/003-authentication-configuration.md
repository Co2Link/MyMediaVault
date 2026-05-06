# Decision: Authentication Configuration

Status: accepted.

Authentication uses Entra ID through Auth.js in the Next.js application. The
server stores database-backed sessions and persists Entra user metadata on the
shared `users` table.

The app uses the Entra OAuth flow directly from Auth.js and stores the account
access token so the server can fetch the signed-in user's profile photo from
Microsoft Graph.

Local Playwright e2e tests do perform a real Entra browser sign-in with
credentials from `apps/e2e/.env.local`. GitHub CI currently runs web tests and
Terraform validation, while the authenticated local e2e suite is run through
the tracked pre-commit hook and `npm run test:local`.
