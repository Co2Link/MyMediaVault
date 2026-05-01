#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
E2E_DIR="$ROOT_DIR/apps/e2e"
BACKEND_DIR="$ROOT_DIR/apps/backend"
FRONTEND_DIR="$ROOT_DIR/apps/frontend"
LOG_DIR="$E2E_DIR/.logs"

mkdir -p "$LOG_DIR"

source_required_file() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "Missing required env file: $file" >&2
    exit 1
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    export "$line"
  done <"$file"
}

wait_for_http() {
  local url="$1"
  local name="$2"
  local attempts="${3:-60}"
  local delay="${4:-1}"

  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay"
  done

  echo "$name did not become ready at $url" >&2
  exit 1
}

reset_backend_state() {
  if [[ "${MMV_DATABASE_URL:-}" == sqlite:///./* ]]; then
    local db_path="${MMV_DATABASE_URL#sqlite:///./}"
    rm -f "$BACKEND_DIR/$db_path"
  fi

  if [[ -n "${MMV_BLOB_STORAGE_ROOT:-}" ]]; then
    rm -rf "$BACKEND_DIR/$MMV_BLOB_STORAGE_ROOT"
  fi

  rm -rf "$E2E_DIR/.auth"
}

cleanup() {
  local exit_code=$?
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
    wait "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
    wait "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  exit "$exit_code"
}

trap cleanup EXIT INT TERM

source_required_file "$BACKEND_DIR/.env"
source_required_file "$FRONTEND_DIR/.env"
source_required_file "$E2E_DIR/.env.local"

: "${E2E_ENTRA_USERNAME:?Missing E2E_ENTRA_USERNAME in apps/e2e/.env.local}"
: "${E2E_ENTRA_PASSWORD:?Missing E2E_ENTRA_PASSWORD in apps/e2e/.env.local}"

export E2E_BASE_URL="${E2E_BASE_URL:-http://localhost:5173}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"

if ! curl -fsS "$BACKEND_URL/health" >/dev/null 2>&1; then
  reset_backend_state
  (
    cd "$BACKEND_DIR"
    uv run fastapi dev app/main.py --host 0.0.0.0 --port 8000
  ) >"$LOG_DIR/backend.log" 2>&1 &
  BACKEND_PID=$!
fi

if ! curl -fsS "$E2E_BASE_URL" >/dev/null 2>&1; then
  (
    cd "$FRONTEND_DIR"
    npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
  ) >"$LOG_DIR/frontend.log" 2>&1 &
  FRONTEND_PID=$!
fi

wait_for_http "$BACKEND_URL/health" "Backend"
wait_for_http "$E2E_BASE_URL" "Frontend"

cd "$E2E_DIR"
npx playwright test "$@"
