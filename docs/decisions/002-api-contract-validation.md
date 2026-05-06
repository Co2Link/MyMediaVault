# Decision: API Contract Validation

Status: superseded.

This repository previously treated the FastAPI-generated OpenAPI document as the
contract source of truth.

That decision no longer applies because the FastAPI application and its contract
tests were removed when the Next.js full-stack rewrite became the only active
application.

Current rule:

- Do not resurrect or maintain the deleted FastAPI/OpenAPI contract artifacts
  unless a new explicit API surface is introduced and documented for the current
  application.
