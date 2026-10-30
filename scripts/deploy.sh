#!/usr/bin/env bash
# Production & Optional Staging Deployment Entrypoint (P8-01, P8-12; deployment.md §2).
#
# Performs:
#   1. Non-blocking host lockfile acquisition (.deploy.lock via flock / fcntl)
#   2. Preflight validation (.env 0600 permissions, docker compose config, validate_production_settings)
#   3. Pre-deploy state recording (.deploy-state: active_image_tag, previous_db_revision)
#   4. One-off database migration gate (docker compose --profile migrate run --rm migrate)
#   5. Rolling service update (api, worker with 35s lease drain, caddy)
#   6. /readyz readiness verification and structured diagnostics on failure
#
# Usage:
#   ./scripts/deploy.sh --image-tag v0.8.0 --env-file .env --project-name agentnest

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "error: python3 is required to run scripts/deploy.py" >&2
  exit 1
fi

exec "${PYTHON_BIN}" "${SCRIPT_DIR}/deploy.py" deploy "$@"
