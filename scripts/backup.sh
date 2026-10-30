#!/usr/bin/env bash
# Nightly Encrypted PostgreSQL Backup Entrypoint (P8-02; ADR-025 §4.3).
#
# Performs:
#   1. Custom-format pg_dump (-Fc --no-owner --no-privileges)
#   2. Authenticated AES-256-GCM encryption (AGNBKP01 envelope with header AAD)
#   3. Off-site S3 upload and/or local backup directory write + verification
#   4. 35-day retention pruning (BACKUP_RETENTION_DAYS=35) after verified upload
#   5. Durable .backup-status.json heartbeat update (non-zero exit on failure)
#
# Usage:
#   ./scripts/backup.sh [--output-dir /var/backups/agentnest] [--s3-bucket ...]
#   ./scripts/backup.sh decrypt --input <archive.dump.enc> --output <archive.dump>
#
# Recommended cron / systemd schedule (02:00 UTC nightly):
#   0 2 * * * cd /opt/agentnest && docker compose -f compose.prod.yml --profile backup run --rm backup

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "error: python3 is required to run scripts/backup.py" >&2
  exit 1
fi

exec "${PYTHON_BIN}" "${SCRIPT_DIR}/backup.py" "$@"
