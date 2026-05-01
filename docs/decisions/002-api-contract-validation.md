# Decision: API Contract Validation

Status: accepted.

FastAPI already generates the runtime OpenAPI document at `/openapi.json`, and
that generated schema should be treated as the implementation source of truth.

Contract tests in `apps/backend/tests/contract/` verify route behavior and key
response shapes. Tests in `apps/backend/tests/contract/test_openapi_auth_contract.py`
also assert important properties of the generated OpenAPI schema.

Maintenance rule:

- Do not maintain a separate hand-edited OpenAPI artifact for this feature.
- When API behavior changes, update the backend behavior, the contract tests,
  generated-OpenAPI assertions, and [Backend Design](../backend-design.md)
  together.
