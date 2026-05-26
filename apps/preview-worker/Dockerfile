# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app/apps/preview-worker

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY apps/preview-worker/pyproject.toml apps/preview-worker/uv.lock apps/preview-worker/README.md ./
COPY apps/preview-worker/src ./src

RUN --mount=type=secret,id=uv_index_lingxt_password \
    UV_INDEX_LINGXT_USERNAME=az \
    UV_INDEX_LINGXT_PASSWORD="$(cat /run/secrets/uv_index_lingxt_password)" \
    uv sync --locked --no-dev

FROM python:3.13-slim-bookworm AS runner

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 mymediavault-preview \
    && useradd --uid 10001 --gid mymediavault-preview --home-dir /app --create-home --shell /usr/sbin/nologin mymediavault-preview

WORKDIR /app/apps/preview-worker

ENV PATH="/app/apps/preview-worker/.venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

COPY --from=builder --chown=mymediavault-preview:mymediavault-preview /app/apps/preview-worker/.venv ./.venv
COPY --from=builder --chown=mymediavault-preview:mymediavault-preview /app/apps/preview-worker/src ./src
COPY --from=builder --chown=mymediavault-preview:mymediavault-preview /app/apps/preview-worker/pyproject.toml ./pyproject.toml

USER mymediavault-preview

CMD ["mymediavault-preview-worker"]
