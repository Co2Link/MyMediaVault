# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app/apps/vm-worker

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY apps/vm-worker/pyproject.toml apps/vm-worker/uv.lock apps/vm-worker/README.md ./
COPY apps/vm-worker/src ./src
COPY apps/vm-worker/models ./models
COPY apps/vm-worker/scripts/download_face_models.py ./scripts/download_face_models.py

RUN uv sync --locked --no-dev
RUN python scripts/download_face_models.py --output .local/models

FROM python:3.13-slim-bookworm AS runner

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 mymediavault-vm \
    && useradd --uid 10001 --gid mymediavault-vm --home-dir /app --create-home --shell /usr/sbin/nologin mymediavault-vm \
    && install -d -m 750 -o mymediavault-vm -g mymediavault-vm /var/log/mymediavault/vm-worker

WORKDIR /app/apps/vm-worker

ENV PATH="/app/apps/vm-worker/.venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
ENV MMV_VM_WORKER_DEBUG_LOG_PATH="/var/log/mymediavault/vm-worker/debug.log"

COPY --from=builder --chown=mymediavault-vm:mymediavault-vm /app/apps/vm-worker/.venv ./.venv
COPY --from=builder --chown=mymediavault-vm:mymediavault-vm /app/apps/vm-worker/src ./src
COPY --from=builder --chown=mymediavault-vm:mymediavault-vm /app/apps/vm-worker/pyproject.toml ./pyproject.toml
COPY --from=builder --chown=mymediavault-vm:mymediavault-vm /app/apps/vm-worker/models ./models
COPY --from=builder --chown=mymediavault-vm:mymediavault-vm /app/apps/vm-worker/.local/models ./.local/models

USER mymediavault-vm

CMD ["mymediavault-vm-worker"]
