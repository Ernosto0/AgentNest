# Phase 8 — Session 04 Report: Backups, Media Protection and Restore Drill

- **Session:** `S04` (`docs/implementation/phase-8-sessions/phase-08-sessions.md` §Session 04)
- **Date:** 2026-10-30
- **Status:** `offline complete` (`scripts/backup.py`, `scripts/backup.sh`, `scripts/restore.py`, `scripts/restore.sh`, `backend/app/operations/backup_restore.py`, `backend/app/operations/system_health.py`, `compose.prod.yml` `backup` service, `app.cli` commands, `docs/operations/backup-restore.md`, unit/integration tests, and disposable container restore drill complete; live off-site production S3 bucket restore rehearsal remains externally pending Session 16 / `AC-2`)
- **Branch / Commit Baseline:** `main` at `d82431b` (`Complete Phase 8 Session 03 deployment workflow, migration gate, and rollback`)
- **Alembic Migration Head:** `20261029_0030_agent_content_intents.py` (revision `0030`, 30 migrations total)
- **Unrelated Work Preserved:** Modified/untracked files (`Dockerfile`, `frontend/*`, `design-preview/`, `docs/README.md`, `docs/implementation/roadmap.md`, `docs/implementation/task-breakdown.md`, `docs/product/user-journeys.md`, `docs/product/ui-redesign-specification.md`, `docs/implementation/phase-8.5-sessions/`, `docs/implementation/phases/phase-8.5-ui-redesign.md`) left untouched.

---

## 1. Summary of Implemented Artifacts & Contracts

| Artifact / File | Status | Implementation Summary |
|---|---|---|
| `scripts/backup.py`, `scripts/backup.sh` | **Created** | Cross-platform Python 3.12 + POSIX shell backup orchestrator (`run`, `decrypt`, `prune`, `status`). Runs `pg_dump --format=custom --no-owner --no-privileges` (supporting local `pg_dump` or `--postgres-container`), verifies `PGDMP` magic header, encrypts dumps with authenticated `AES-256-GCM` (`AGNBKP01` binary envelope binding `backup_id`, `created_at`, `key_id`, `alembic_revision`, `plaintext_sha256`, and `plaintext_size_bytes` as GCM Additional Authenticated Data), uploads `.dump.enc` + `.manifest.json` to off-site S3 (`BACKUP_S3_BUCKET`, `BACKUP_S3_PREFIX`) and/or `--output-dir`, verifies uploaded sizes/checksums, prunes expired archives beyond the canonical **35-day retention window** (`BACKUP_RETENTION_DAYS=35`) only after a verified upload, and atomically writes `.backup-status.json` (exiting non-zero on failure). |
| `scripts/restore.py`, `scripts/restore.sh` | **Created** | Cross-platform Python 3.12 + POSIX shell restore orchestrator. Refuses to overwrite a non-empty database unless `--allow-overwrite-disposable` is explicitly passed; supports `--create-target-db`; verifies ciphertext SHA-256 against `.manifest.json` and decrypts `AGNBKP01` AES-256-GCM archives; runs `pg_restore --no-owner --no-privileges --role=agentnest_migrator --exit-on-error`; verifies restored Alembic revision against `migration_head()` (`0030`) and public table counts; provisions and verifies separated `agentnest_migrator` vs `agentnest_app` / `agentnest_worker` roles (`NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS` and `REVOKE UPDATE, DELETE` on `audit_logs` and `fact_versions`); and executes `post_restore_reconcile` (with optional `--tombstone-manifest`) before any worker starts. |
| `backend/app/operations/backup_restore.py` | **Created** | Implements `provision_database_roles()`, `verify_database_roles()`, `TombstoneManifest` (`CustomerTombstone`, `ConversationTombstone`, `AccountTombstone`, `load_tombstone_manifest()`), and `post_restore_reconcile()`. Before workers start after a restore (`ADR-025` §3.3, `INV-05`, `INV-18`), `post_restore_reconcile()` pauses all `account_agents` (`state = 'paused'`, incrementing `controller_epoch` and `config_version`), revokes active `agent_delegations` (`revoked_at = now`), transitions `in_progress` `operations` to `outcome_unknown` (`last_error_code = 'RESTORED_FROM_BACKUP_OUTCOME_UNKNOWN'`) and `sending` `reply_drafts` to `outcome_unknown` (enqueuing `reconcile_send` / `reconcile_publish`), holds `publishing`/overdue `content_items` (`status = 'on_hold'`), cancels active `agent_sessions` and `agent_threads`, abandons in-flight `agent_steps`, cancels queued outbound jobs, releases stale `running` job leases, and re-applies customer/conversation/account/workspace erasures from `--tombstone-manifest` (and `deletion_tombstones` if present). |
| `backend/app/operations/system_health.py` | **Updated** | Added `BACKUP_STALE_THRESHOLD = timedelta(hours=26)`, `BackupHealth`, `backup_health()`, `resolve_backup_status_path()`, and `record_backup_audit()` (`system.backup_succeeded` / `system.backup_failed`) per `ADR-025` §4.3 while preserving `SystemHealthOut` top-level keys for existing API/frontend callers. |
| `backend/app/core/config.py`, `backend/app/cli.py`, `backend/pyproject.toml` | **Updated** | Added `BACKUP_*` settings (`backup_encryption_key`, `backup_encryption_active_key_id`, `backup_s3_bucket`, `backup_s3_endpoint_url`, `backup_s3_region`, `backup_s3_prefix`, `backup_s3_access_key_id`, `backup_s3_secret_access_key`, `backup_local_dir`, `backup_retention_days=35`, `backup_status_file`), secret redaction, and production keyring validation in `config.py`. Extended `python -m app.cli generate-key --kind backup-encryption` and added `post-restore-reconcile [--tombstone-manifest <path>]` and `verify-db-roles [--provision]` to `app.cli`. Updated import-linter module lists in `pyproject.toml`. |
| `compose.prod.yml`, `.env.example`, `.gitignore`, `.dockerignore` | **Updated** | Added `backup` service (`profiles: ["backup", "ops"]`) and `backups_data` volume in `compose.prod.yml`, documented all `BACKUP_*` variables in `.env.example` and `docs/operations/environment-variables.md`, and ignored `.backup-status*`, `*.dump`, `*.dump.enc`, `*.manifest.json` in `.gitignore` and `.dockerignore`. |
| `docs/operations/backup-restore.md`, `docs/architecture/deployment.md` | **Created / Updated** | Documented nightly encrypted backup schedule (`02:00 UTC`), off-host key custody (`BACKUP_ENCRYPTION_KEY` and `TOKEN_ENCRYPTION_KEYS`), least-privilege S3 IAM policy + Object Lock/versioning, media bucket versioning & cross-store consistency limits, step-by-step restore runbook, post-restore operator checklist, and executed restore drill metrics. |
| `backend/tests/unit/core/test_backup_and_restore.py` | **Created** | Added 7 unit/integration tests covering Compose/script contracts, `generate-key --kind backup-encryption`, AES-256-GCM roundtrip + key rotation + ciphertext/AAD tamper rejection, 35-day retention pruning + failed-upload visibility + `backup_health()` `> 26h` staleness threshold, backup audit logging, `post_restore_reconcile()` worker fencing & tombstone re-application, and `provision_database_roles()` / `verify_database_roles()` append-only enforcement. |

---

## 2. Verification Results

### 2.1 Static Analysis, Typecheck, Import Boundaries & Test Suites

| Check | Command | Exit Code | Result Summary |
|---|---|---|---|
| Backend + Scripts Lint | `backend/.venv/Scripts/ruff.exe check . ../scripts/deploy.py ../scripts/backup.py ../scripts/restore.py` | `0` | `All checks passed!` |
| Backend + Scripts Format | `backend/.venv/Scripts/ruff.exe format --check . ../scripts/deploy.py ../scripts/backup.py ../scripts/restore.py` | `0` | `570 files already formatted` |
| Backend + Scripts Typecheck | `backend/.venv/Scripts/mypy.exe app evals ../scripts/deploy.py ../scripts/backup.py ../scripts/restore.py` | `0` | `Success: no issues found in 302 source files` |
| Backend Import Contracts | `backend/.venv/Scripts/lint-imports.exe` | `0` | `Analyzed 351 files, 2883 dependencies. Contracts: 19 kept, 0 broken.` |
| Backend Unit Tests | `backend/.venv/Scripts/pytest.exe tests/unit -q` | `0` | `1514 passed in 14.80s` |
| Frontend Lint | `npm.cmd run lint` | `0` | `eslint .` passed cleanly |
| Frontend Typecheck | `npm.cmd run typecheck` | `0` | `tsc -b --noEmit` passed cleanly |
| Frontend i18n Parity | `npm.cmd run i18n:check` | `0` | `i18n check passed` |

### 2.2 Executed Disposable PostgreSQL Restore Drill (`agentnest-s04-drill`)

An end-to-end backup and restore drill (`C:\Users\ernos\.gemini\antigravity\brain\86de9a0e-1b9a-44e7-8338-c394fe1a1b25\scratch\rehearse_s04_drill.py`) was executed against a disposable PostgreSQL 16 container (`agentnest-s04-drill`, host port `15434 -> 5432`) and torn down cleanly after verification:

| Metric / Assertion | Observed Outcome |
|---|---|
| **Backup Archive ID** | `agentnest-20261030T212245Z-s04-drill` |
| **Alembic Schema Revision & Public Tables** | `0030` (`59` public tables) |
| **Plaintext `pg_dump -Fc` Size & SHA-256** | `279,616` bytes (`273.1 KiB`), SHA-256 `50eeedd18e1e3e91e0644a43731b1201cb44b81b51b16ec5910506550f310c92` |
| **Encrypted `.dump.enc` Size & SHA-256** | `279,976` bytes (`273.4 KiB`), SHA-256 `e7b6eded1ef04da3c24c23d5c033ee871388ecebc3281b578e39bb9a3b35b99e` |
| **Backup Duration** | `0.250s` |
| **Measured Snapshot Age (Drill RPO)** | `2.364s` (`2026-10-30T21:22:45.077Z` -> `2026-10-30T21:22:47.441Z`; production nightly schedule RPO ceiling `< 24h`, alert threshold `> 26h`) |
| **Measured Restore + Reconcile Duration (Drill RTO)** | `1.406s` (decrypt + `pg_restore` + role provisioning/verification + `post-restore-reconcile`) |
| **Direct `pg_restore` on `.dump.enc` Rejected** | Exit non-zero: `pg_restore: error: input file does not appear to be a valid archive` |
| **Tampered Ciphertext / AAD Rejected** | Raised `BackupTamperedError` (`AES-256-GCM authentication tag verification failed`) |
| **Non-Empty Target DB Overwrite Refused** | Refused restore into populated `agentnest_drill_src` when `--allow-overwrite-disposable` was omitted (`Target database 'agentnest_drill_src' is not empty (59 tables found)`) |
| **Restored Workspace, Facts, Conversation & Media Refs** | Verified in `agentnest_restored_drill`: workspace `golkent-pilates-drill`, verified fact `pricing.monthly_reformer` (`4500 TRY`) + `fact_versions`, kept conversation `ayse_wellness`, and `media_assets` key `workspaces/<ws_id>/media/reformer-schedule-2026.jpg` |
| **Post-Restore Worker Fencing (`post-restore-reconcile`)** | `in_progress` `send_reply` operation -> `outcome_unknown` (`last_error_code = 'RESTORED_FROM_BACKUP_OUTCOME_UNKNOWN'`, `enqueued_reconcile_jobs = 1`); `sending` `ReplyDraft` -> `outcome_unknown`; `AccountAgent` -> `paused` (`paused_account_agents = 1`); `AgentDelegation` -> revoked (`revoked_agent_delegations = 1`); `AgentSession` -> `cancelled`; `AgentStep` -> `abandoned`; queued `send_reply` job -> `cancelled` |
| **Post-Snapshot Tombstone Re-Application** | Customer `cust-erased-202` in `tombstones.json` (`reapplied_customer_tombstones = 1`) purged from `conversations`, `messages`, and `customer_memories`; `inbound_events.payload` nulled; `customer_identities.generation` incremented |
| **Runtime Role Privilege Verification (`agentnest_app`)** | `verified: true` (`non_owned_tables: []`, `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`); live connection as `agentnest_app` confirmed `DELETE FROM audit_logs` and `UPDATE fact_versions` fail with `psycopg.errors.InsufficientPrivilege` |

---

## 3. Reproducible Backup, Decrypt & Restore Drill Commands

```powershell
# 1. Generate a 32-byte URL-safe base64 backup encryption key ring entry
python -m app.cli generate-key --kind backup-encryption --key-id b1

# 2. Run encrypted pg_dump -Fc backup, upload/write manifest, prune >35d archives, and write .backup-status.json
python scripts/backup.py run `
  --database-url "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/agentnest" `
  --output-dir ./var/backups `
  --retention-days 35 `
  --status-file ./.backup-status.json `
  --postgres-container agentnest-postgres-1
# (On Linux VPS: ./scripts/backup.sh --output-dir /var/backups/agentnest --s3-bucket agentnest-backups)

# 3. Inspect durable backup heartbeat status
python scripts/backup.py status --status-file ./.backup-status.json

# 4. Standalone verification & decryption of an encrypted .dump.enc archive
python scripts/backup.py decrypt `
  --input ./var/backups/agentnest-20261030T212245Z-s04-drill.dump.enc `
  --manifest ./var/backups/agentnest-20261030T212245Z-s04-drill.manifest.json `
  --output ./var/backups/decrypted.dump

# 5. Restore encrypted archive into a fresh isolated database with role verification & worker fencing
python scripts/restore.py `
  --archive ./var/backups/agentnest-20261030T212245Z-s04-drill.dump.enc `
  --manifest ./var/backups/agentnest-20261030T212245Z-s04-drill.manifest.json `
  --target-database-url "postgresql://postgres:postgres@127.0.0.1:5433/agentnest_restored_drill" `
  --create-target-db `
  --postgres-container agentnest-postgres-1 `
  --migrator-role agentnest_migrator `
  --runtime-roles agentnest_app,agentnest_worker `
  --tombstone-manifest ./var/backups/tombstones.json
# (On Linux VPS: ./scripts/restore.sh --archive ... --target-database-url ... --create-target-db)

# 6. Standalone CLI role verification and post-restore worker fencing / tombstone reconciliation
python -m app.cli verify-db-roles --migrator-role agentnest_migrator --runtime-roles agentnest_app,agentnest_worker --provision
python -m app.cli post-restore-reconcile --tombstone-manifest ./var/backups/tombstones.json
```

---

## 4. Canonical Task Coverage, External Dependencies & Handoff to Session 05

- **Canonical Phase 8 Task Coverage:**
  - `P8-02` (Nightly encrypted `pg_dump` backups, 35-day retention, media bucket protection, restore procedure, post-restore worker fencing, and restore drill): `scripts/backup.py`, `scripts/backup.sh`, `scripts/restore.py`, `scripts/restore.sh`, `backend/app/operations/backup_restore.py`, `backend/app/operations/system_health.py`, `docs/operations/backup-restore.md`, unit/integration tests, and the disposable container restore drill (`agentnest-s04-drill`) are **offline complete**.
  - `P8-12` (optional staging): `compose.prod.yml` `backup` service and `scripts/backup.py` / `scripts/restore.py` are fully parameterized via environment variables (`BACKUP_S3_PREFIX`, `BACKUP_LOCAL_DIR`, `BACKUP_STATUS_FILE`, `--target-database-url`) so staging and production backups remain strictly isolated.
- **Externally Pending Evidence & Re-Drill Requirements (`AC-2`):**
  - This Session 04 restore drill proves encrypted archive creation, tamper detection, isolated restoration, least-privilege role grants (`agentnest_migrator` vs `agentnest_app` / `agentnest_worker`), append-only table enforcement (`audit_logs` and `fact_versions`), post-restore worker fencing (`in_progress` -> `outcome_unknown`, `account_agents` paused, `agent_delegations` revoked), and post-snapshot tombstone re-application on the **pre-RLS schema (`0030`)** against a disposable PostgreSQL 16 container.
  - Per `phase-08-sessions.md` (`Session 04` §3 & §6), **an early local drill alone does not close `AC-2`**: the restore drill **must be revisited after PostgreSQL RLS policies and role changes land in Sessions 05–06** (to confirm `pg_restore --no-owner --no-privileges --role=agentnest_migrator` and `verify_database_roles()` preserve `ENABLE`/`FORCE ROW LEVEL SECURITY` and RLS policies) and **executed against live off-site S3-compatible object storage in Session 16** (`AC-2`).
- **Handoff to Session 05 (`RLS roles and transaction infrastructure`):**
  - `backend/app/operations/backup_restore.py` provides `provision_database_roles()` and `verify_database_roles()` (also exposed via `python -m app.cli verify-db-roles [--provision]`), establishing the canonical role separation contract (`agentnest_migrator` owning schema objects vs `agentnest_app` and `agentnest_worker` running with `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS` and `REVOKE UPDATE, DELETE, TRUNCATE` on `audit_logs` and `fact_versions`).
  - Session 05 can build directly on these role definitions and `ADR-025` §1 to wire `SET LOCAL app.current_workspace_id` / `app.rls_bypass` transaction helpers in `backend/app/core/db.py`, `api/deps.py`, and `jobs/worker.py`.

