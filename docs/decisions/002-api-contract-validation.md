# Decision: API Contract Validation

The source API contract for this feature is
`specs/001-video-vault-management/contracts/openapi.yaml`.

Contract tests in `apps/backend/tests/contract/` verify that implemented routes
match the expected status codes and response shapes. A future dedicated OpenAPI
validator can be added to CI once the project standardizes on a validator
package.
