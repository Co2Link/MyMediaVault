# Python Package Guidelines

- Use uv to manage the Python environment and package metadata.
- Maintain a `CHANGELOG.md` for user-visible changes.
- Before handing off a change, classify whether it is release-impacting. If it changes public APIs, result semantics, artifact compatibility, default runtime behavior, or client integration contracts, update `CHANGELOG.md` and bump the package version with `uv version` in the same change unless the user explicitly asks to defer release metadata.
- Use `uv version` to inspect and update the package version. Do not edit the version in `pyproject.toml` directly.
