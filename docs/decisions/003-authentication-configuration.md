# Decision: Authentication Configuration

Production authentication uses Entra ID through the backend authentication
dependency. Protected API access requires a standard bearer token flow, and the
OpenAPI documentation is configured for PKCE against the separate OpenAPI app
registration.

Automated backend tests override the current-user dependency in-process instead
of using alternate transport headers. Local CI does not perform interactive
browser authentication against Entra.
