#!/usr/bin/env bash
# Production & Optional Staging Application Rollback Entrypoint (P8-01, P8-12; deployment.md §2).
#
# Rolls back application containers (api, worker, caddy) to the previous recorded IMAGE_TAG
# (or --to-tag <tag>) ONLY when the current database Alembic revision matches the target
# rollback image's migration head. Blocks image-only rollback with exit code 3 if a forward
# or incompatible schema migration was already applied (requiring Session 04 DB restore or
# a forward-fix deployment).
#
# Usage:
#   ./scripts/rollback.sh [--to-tag v0.7.9] [--env-file .env] [--project-name agentnest]

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

exec "${PYTHON_BIN}" "${SCRIPT_DIR}/deploy.py" rollback "$@"
