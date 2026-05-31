#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
E2E_DIR="$ROOT_DIR/apps/e2e"
WEB_DIR="$ROOT_DIR/apps/web"
LOG_DIR="$E2E_DIR/.logs"

mkdir -p "$LOG_DIR"

log() {
  printf '[run-dev-smoke] %s\n' "$*"
}

source_optional_file() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    return
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    export "$line"
  done <"$file"
}

require_successful_workflow() {
  local workflow="$1"
  local sha="$2"
  local run

  run="$(
    gh run list \
      --workflow "$workflow" \
      --branch develop \
      --commit "$sha" \
      --json conclusion,status,url \
      --limit 1
  )"

  if [[ "$(jq 'length' <<<"$run")" -eq 0 ]]; then
    echo "No $workflow workflow run found for commit $sha on develop." >&2
    exit 1
  fi

  local status conclusion url
  status="$(jq -r '.[0].status' <<<"$run")"
  conclusion="$(jq -r '.[0].conclusion' <<<"$run")"
  url="$(jq -r '.[0].url' <<<"$run")"

  if [[ "$status" != "completed" || "$conclusion" != "success" ]]; then
    echo "$workflow workflow has not succeeded for $sha: status=$status conclusion=$conclusion url=$url" >&2
    exit 1
  fi

  log "$workflow workflow succeeded for $sha."
}

cleanup() {
  local exit_code=$?
  log "run-dev-smoke.sh exiting with code $exit_code."
  exit "$exit_code"
}

trap cleanup EXIT INT TERM

source_optional_file "$WEB_DIR/.env.dev"
source_optional_file "$E2E_DIR/.env.dev"

export MMV_PREVIEW_TARGET_FRAMES="${MMV_PREVIEW_TARGET_FRAMES:-3}"

: "${E2E_BASE_URL:?Set E2E_BASE_URL to the deployed dev web URL.}"
: "${E2E_USER_USERNAME:?Missing E2E_USER_USERNAME in apps/e2e/.env.dev.}"
: "${E2E_USER_PASSWORD:?Missing E2E_USER_PASSWORD in apps/e2e/.env.dev.}"
: "${E2E_ADMIN_USERNAME:?Missing E2E_ADMIN_USERNAME in apps/e2e/.env.dev.}"
: "${E2E_ADMIN_PASSWORD:?Missing E2E_ADMIN_PASSWORD in apps/e2e/.env.dev.}"
: "${MONGODB_URI:?Missing MONGODB_URI for dev Cosmos DB verification.}"
: "${R2_ENDPOINT:?Missing R2_ENDPOINT for R2 verification.}"
: "${R2_ACCESS_KEY_ID:?Missing R2_ACCESS_KEY_ID for R2 verification.}"
: "${R2_SECRET_ACCESS_KEY:?Missing R2_SECRET_ACCESS_KEY for R2 verification.}"

if [[ "$E2E_BASE_URL" == http://localhost:* || "$E2E_BASE_URL" == http://127.0.0.1:* ]]; then
  echo "E2E_BASE_URL must point to the deployed dev environment, not localhost." >&2
  exit 1
fi

HEAD_SHA="${DEV_SMOKE_COMMIT_SHA:-$(git -C "$ROOT_DIR" rev-parse HEAD)}"

require_successful_workflow "CI" "$HEAD_SHA"
require_successful_workflow "Dev" "$HEAD_SHA"

log "Clearing prior Playwright auth state."
rm -rf "$E2E_DIR/.auth"

log "Running deployed dev smoke against $E2E_BASE_URL."
cd "$E2E_DIR"
npx playwright test tests/smoke-dev.spec.ts --project=smoke-dev-chromium
