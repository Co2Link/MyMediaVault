# Decision: Authentication Configuration

Production authentication uses Entra ID through the backend authentication
dependency. Test mode is explicit through `MMV_TEST_MODE=true` or
`MMV_ENVIRONMENT=test` and accepts deterministic test headers.

Test mode must never be enabled in production configuration. CI and local
Playwright runs may use it to avoid depending on a live identity provider.
