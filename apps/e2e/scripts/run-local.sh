#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
E2E_DIR="$ROOT_DIR/apps/e2e"
WEB_DIR="$ROOT_DIR/apps/web"
FUNCTIONS_DIR="$ROOT_DIR/apps/functions"
LOG_DIR="$E2E_DIR/.logs"

mkdir -p "$LOG_DIR"

log() {
  printf '[run-local] %s\n' "$*"
}

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

stop_existing_local_stack() {
  log "Stopping any existing local Next.js dev server and Functions worker processes."
  pkill -f "/workspaces/MyMediaVault/apps/web/node_modules/.bin/next dev" >/dev/null 2>&1 || true
  pkill -f "next dev --hostname localhost --port 3000" >/dev/null 2>&1 || true
  pkill -f "[f]unc start" >/dev/null 2>&1 || true
  pkill -9 -f "[m]anual-worker.js" >/dev/null 2>&1 || true
}

stop_managed_process() {
  local pid="$1"
  local name="$2"

  if ! kill -0 "$pid" >/dev/null 2>&1; then
    log "$name process group $pid is already stopped."
    return
  fi

  log "Stopping $name process group $pid."
  kill -- "-$pid" >/dev/null 2>&1 || kill "$pid" >/dev/null 2>&1 || true

  for _ in {1..20}; do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      return
    fi
    sleep 0.25
  done

  log "$name process group $pid did not exit after SIGTERM. Sending SIGKILL."
  kill -9 -- "-$pid" >/dev/null 2>&1 || kill -9 "$pid" >/dev/null 2>&1 || true
}

cleanup() {
  local exit_code=$?
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    log "Stopping Next.js dev server started by this run (process group $FRONTEND_PID)."
    stop_managed_process "$FRONTEND_PID" "Next.js dev server"
    wait "$FRONTEND_PID" >/dev/null 2>&1 || true
  else
    log "Leaving existing Next.js dev server running because this run did not start it."
  fi
  if [[ -n "${WORKER_PID:-}" ]]; then
    log "Stopping Functions worker started by this run (process group $WORKER_PID)."
    stop_managed_process "$WORKER_PID" "Functions worker"
    wait "$WORKER_PID" >/dev/null 2>&1 || true
    pkill -9 -f "[m]anual-worker.js" >/dev/null 2>&1 || true
  else
    log "Leaving existing Functions worker running because this run did not start it."
  fi
  log "run-local.sh exiting with code $exit_code."
  exit "$exit_code"
}

trap cleanup EXIT INT TERM

source_required_file "$WEB_DIR/.env.local"
source_required_file "$E2E_DIR/.env.local"

: "${E2E_USER_USERNAME:?Missing E2E_USER_USERNAME in apps/e2e/.env.local}"
: "${E2E_USER_PASSWORD:?Missing E2E_USER_PASSWORD in apps/e2e/.env.local}"
: "${E2E_ADMIN_USERNAME:?Missing E2E_ADMIN_USERNAME in apps/e2e/.env.local}"
: "${E2E_ADMIN_PASSWORD:?Missing E2E_ADMIN_PASSWORD in apps/e2e/.env.local}"

export MONGODB_URI="${MONGODB_URI:-mongodb://127.0.0.1:27017/mymediavault}"
export MMV_MONGODB_DB_NAME="${MMV_MONGODB_DB_NAME:-mymediavault}"
export AzureWebJobsStorage="${AzureWebJobsStorage:-UseDevelopmentStorage=true}"
export MMV_AZURE_STORAGE_CONNECTION_STRING="${MMV_AZURE_STORAGE_CONNECTION_STRING:-$AzureWebJobsStorage}"
export E2E_BASE_URL="${E2E_BASE_URL:-http://localhost:3000}"
HEALTH_URL="${HEALTH_URL:-http://localhost:3000/api/health}"
PLAYWRIGHT_ARGS=("$@")
RUN_ID="${RUN_ID:-$(date +%s)-$$}"
GENERATED_TORRENT_METADATA_QUEUE=0
if [[ -z "${MMV_TORRENT_METADATA_QUEUE:-}" ]]; then
  export MMV_TORRENT_METADATA_QUEUE="torrent-metadata-jobs-${RUN_ID}"
  GENERATED_TORRENT_METADATA_QUEUE=1
fi

if [[ "${E2E_INCLUDE_MANUAL_TORRENT_TESTS:-}" != "1" ]]; then
  PLAYWRIGHT_ARGS+=(--grep-invert "@manual-torrent")
fi

if [[ "${E2E_REQUIRE_HTTP_TORRENT_PROVIDER:-}" == "1" ]]; then
  log "Manual torrent mode requested. Forcing MMV_TORRENT_PROVIDER=http."
  export MMV_TORRENT_PROVIDER="http"
else
  export MMV_TORRENT_PROVIDER="fake"
fi

if [[ "${E2E_FORCE_STACK_RESTART:-}" == "1" ]]; then
  log "Forced stack restart requested. Existing auth state and local processes will be cleared."
  stop_existing_local_stack
  rm -rf "$E2E_DIR/.auth"
fi

if [[ "$GENERATED_TORRENT_METADATA_QUEUE" == "1" ]]; then
  log "Using isolated queue $MMV_TORRENT_METADATA_QUEUE. Existing local worker processes will be restarted."
  pkill -9 -f "[m]anual-worker.js" >/dev/null 2>&1 || true
fi

log "Resetting Playwright user data and orphaned torrent state. Logs: $LOG_DIR/reset.log"
(
  cd "$WEB_DIR"
  npx tsx ./scripts/reset-e2e-state.ts
) >"$LOG_DIR/reset.log" 2>&1

if [[ "${E2E_FORCE_STACK_RESTART:-}" == "1" ]] || ! curl -fsS "$E2E_BASE_URL" >/dev/null 2>&1; then
  log "Starting Next.js dev server. Logs: $LOG_DIR/frontend.log"
  (
    cd "$WEB_DIR"
    exec setsid npm run dev -- --hostname localhost --port 3000
  ) >"$LOG_DIR/frontend.log" 2>&1 &
  FRONTEND_PID=$!
  log "Started Next.js dev server with pid $FRONTEND_PID."
else
  log "Reusing existing Next.js dev server at $E2E_BASE_URL."
fi

if [[ "${E2E_FORCE_STACK_RESTART:-}" == "1" ]] || [[ "$GENERATED_TORRENT_METADATA_QUEUE" == "1" ]] || ! pgrep -f "manual-worker.js" >/dev/null 2>&1; then
  log "Starting Functions worker. Logs: $LOG_DIR/worker.log"
  (
    cd "$FUNCTIONS_DIR"
    npm run build
    exec setsid npm run manual-worker
  ) >"$LOG_DIR/worker.log" 2>&1 &
  WORKER_PID=$!
  log "Started Functions worker with pid $WORKER_PID."
else
  log "Reusing existing Functions worker process."
fi

log "Waiting for frontend at $E2E_BASE_URL."
wait_for_http "$E2E_BASE_URL" "Frontend"
log "Waiting for health endpoint at $HEALTH_URL."
wait_for_http "$HEALTH_URL" "Health endpoint"

log "Running Playwright with args: ${PLAYWRIGHT_ARGS[*]:-(none)}"
cd "$E2E_DIR"
npx playwright test "${PLAYWRIGHT_ARGS[@]}"
