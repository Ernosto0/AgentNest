#!/usr/bin/env bash
# Encrypted PostgreSQL Backup Restore & Post-Restore Fencing Entrypoint (P8-03; ADR-025 §3.3).
#
# Performs:
#   1. Target database isolation check (refuses non-empty DB without --allow-overwrite-disposable)
#   2. Archive & manifest SHA-256 verification and AES-256-GCM decryption
#   3. pg_restore (--no-owner --no-privileges --role=agentnest_migrator)
#   4. Alembic revision, table count, and least-privilege role verification
#   5. Post-restore worker fencing (in_progress -> outcome_unknown, account_agents -> paused,
#      agent_delegations -> revoked) and tombstone manifest re-application
#
# Usage:
#   ./scripts/restore.sh \
#     --archive /var/backups/agentnest/agentnest-20261030T020000Z.dump.enc \
#     --target-database-url postgresql://postgres:postgres@localhost:5432/agentnest_restored \
#     --create-target-db \
#     --tombstone-manifest /var/backups/agentnest/tombstones.json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "error: python3 is required to run scripts/restore.py" >&2
  exit 1
fi

exec "${PYTHON_BIN}" "${SCRIPT_DIR}/restore.py" "$@"
