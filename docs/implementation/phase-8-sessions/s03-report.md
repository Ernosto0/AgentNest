# Phase 8 — Session 03 Report: Deployment, Migrations and Rollback

- **Session:** `S03` (`docs/implementation/phase-8-sessions/phase-08-sessions.md` §Session 03)
- **Date:** 2026-10-30
- **Status:** `offline complete` (`.github/workflows/deploy.yml`, `scripts/deploy.py`, `scripts/deploy.sh`, `scripts/rollback.sh`, `app.cli` preflight & migration-status commands, runtime/migration credential separation in `compose.prod.yml`, `docs/operations/deployment-runbook.md`, unit/contract tests, and disposable 8-step Docker Compose rehearsal complete; live GitHub Actions -> GHCR publish and hosted VPS SSH deployment remain externally pending Session 16 / `AC-1`)
- **Branch / Commit Baseline:** `main` at `641b1f5` (`Complete Phase 8 Session 02 production packaging, Compose, and Caddy`; preceded by `6cf4a30` and `e74a2b5`)
- **Alembic Migration Head:** `20261029_0030_agent_content_intents.py` (revision `0030`, 30 migrations total)
- **Unrelated Work Preserved:** Untracked `design-preview/` and `docs/implementation/phases/phase-8.5-ui-redesign.md` left untouched.

---

## 1. Summary of Implemented Artifacts & Contracts

| Artifact / File | Status | Implementation Summary |
|---|---|---|
| `.github/workflows/deploy.yml` | **Created** | Tag-triggered (`v*`) and `workflow_dispatch` (`environment: production \| staging`, `image_tag`, `skip_build`) deployment workflow. Enforces least-privilege `permissions: contents: read, packages: write` and non-cancelling environment concurrency (`group: deploy-${{ inputs.environment \|\| 'production' }}`, `cancel-in-progress: false`). Builds and pushes `ghcr.io/<owner>/agentnest-backend:<tag>` (`target: backend`) and `ghcr.io/<owner>/agentnest-caddy:<tag>` (`target: caddy`) plus `:sha-<short_sha>` tags while rejecting mutable `latest`. Deploys over SSH using `StrictHostKeyChecking=yes` with verified `DEPLOY_SSH_KNOWN_HOSTS`, `--password-stdin` GHCR login, and pinned `--image-tag`. |
| `scripts/deploy.py`, `scripts/deploy.sh`, `scripts/rollback.sh` | **Created** | Cross-platform Python 3.12 deployment and rollback orchestrator (`scripts/deploy.py`) with POSIX shell wrappers (`scripts/deploy.sh`, `scripts/rollback.sh`). Enforces non-blocking host lockfile acquisition (`.deploy.lock` via `fcntl.flock` / `msvcrt.locking`, exit code `2` on overlap), `.env` `0600` permission checks on POSIX, separated migration/runtime credential checks, container config validation (`python -m app.cli check-config --production`), pre-deploy `.deploy-state` recording, one-off migration gate (`docker compose --profile migrate run --rm migrate`) before rolling `up -d --remove-orphans api worker caddy`, `/readyz` readiness polling, redacted failure diagnostics (`docker compose ps -a` + container log tails), and schema-checked application rollback (blocking image-only rollback with exit code `3` when DB `current_revision` has advanced past the rollback image's `head_revision`). |
| `compose.prod.yml` | **Updated** | Explicitly sets `MIGRATION_DATABASE_URL: ""` in the `api` and `worker` service environments so long-running runtime containers never hold the privileged `agentnest_migrator` credential from `.env`, while the one-off `migrate` service uses `MIGRATION_DATABASE_URL` (`ADR-025` §1.1). |
| `backend/app/core/config.py`, `backend/app/core/db.py`, `backend/app/cli.py` | **Updated** | Added `Settings.has_separated_migration_credentials`, URL validation for `MIGRATION_DATABASE_URL`, redacted `migration_database` and `migration_credentials_separated` fields in `public_dict()`, `migration_revisions()` in `app.core.db`, and two new CLI commands in `app.cli`: `check-config [--production] [--require-separated-migration-credentials]` and `migration-status [--head-only] [--require-ready]`. |
| `.gitignore`, `.dockerignore` | **Updated** | Excluded `.deploy-state*` and `.deploy*.lock` from git and Docker build contexts, and excluded `scripts/` from the Docker build context. |
| `docs/operations/deployment-runbook.md`, `docs/architecture/deployment.md`, `docs/operations/troubleshooting.md` | **Created / Updated** | Documented fresh Ubuntu 24.04 VPS bootstrap (`deploy` user, Docker, `ufw`, `.env` `chmod 600`, `DEPLOY_SSH_KNOWN_HOSTS`), separated `agentnest_migrator` vs `agentnest_app` credentials, backward-compatible migration rules (expand -> migrate -> contract), safe operator response to failed migrations, step-by-step deploy and rollback commands (distinguishing image rollback from Session 04 database backup restoration), worker lease drain (`stop_grace_period: 35s` > `SHUTDOWN_GRACE_SECONDS = 30.0`) and `in_progress` -> `outcome_unknown` reconciliation (`INV-05`, `INV-07`), and optional staging (`P8-12`) setup. |
| `backend/tests/unit/core/test_deployment_workflow_and_rollback.py` | **Created** | Added 7 unit and contract tests verifying `.github/workflows/deploy.yml`, `compose.prod.yml` credential blanking, `scripts/deploy.sh` & `scripts/rollback.sh` wrappers, `app.cli` `check-config` and `migration-status --head-only`, image tag & `.env` permission checks, host lockfile contention (`EXIT_LOCKED = 2`), migration gate ordering, failed readiness diagnostics with secret redaction, compatible rollback, and schema-incompatible rollback refusal (`EXIT_ROLLBACK_INCOMPATIBLE = 3`). |

---

## 2. Verification Results

### 2.1 Static Analysis, Typecheck, Import Boundaries & Test Suites

| Check | Command | Exit Code | Result Summary |
|---|---|---|---|
| Backend + Deploy Script Lint | `backend/.venv/Scripts/ruff.exe check . ../scripts/deploy.py` | `0` | `All checks passed!` |
| Backend + Deploy Script Format | `backend/.venv/Scripts/ruff.exe format --check . ../scripts/deploy.py` | `0` | `566 files already formatted` |
| Backend + Deploy Script Typecheck | `backend/.venv/Scripts/mypy.exe app evals ../scripts/deploy.py` | `0` | `Success: no issues found in 299 source files` |
| Backend Import Contracts | `backend/.venv/Scripts/lint-imports.exe` | `0` | `Analyzed 350 files, 2850 dependencies. Contracts: 19 kept, 0 broken.` |
| Backend Unit Tests | `backend/.venv/Scripts/pytest.exe tests/unit -q` | `0` | `1507 passed in 15.34s` |
| Frontend Lint | `npm.cmd run lint` | `0` | `eslint .` passed cleanly |
| Frontend Typecheck | `npm.cmd run typecheck` | `0` | `tsc -b --noEmit` passed cleanly |
| Frontend i18n Parity | `npm.cmd run i18n:check` | `0` | `i18n check passed: en, tr \| 1415 keys \| 888 literal t() calls verified` |

### 2.2 Live Disposable Docker Infrastructure Rehearsal (`rehearse_s03.py`)

A full 8-step container rehearsal (`C:\Users\ernos\.gemini\antigravity\brain\6d18dbef-9fe6-42b5-a860-59801a27f30a\scratch\rehearse_s03.py`) was executed against Docker Engine `29.4.3` and Docker Compose `v5.1.3` using a disposable project (`COMPOSE_PROJECT_NAME=agentnest-s03-rehearsal`, `HTTP_PORT=18083`, `HTTPS_PORT=18446`) and torn down with `down -v --remove-orphans`:

| Step | Scenario Rehearsed | Observed Outcome |
|---|---|---|
| **1** | Build production images (`backend`, `caddy`) & tag `v0.8.0-s03` and `v0.8.1-s03` | Exit `0`; both release tags created locally. |
| **2** | Provision separated PostgreSQL roles (`agentnest_migrator` vs `agentnest_app` with `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`) | Exit `0`; `agentnest_migrator` granted DDL ownership on `public`, `agentnest_app` granted DML only via default privileges. |
| **3** | Normal deploy (`python scripts/deploy.py deploy --image-tag v0.8.0-s03 --skip-pull --require-separated-migration-credentials ...`) | Exit `0`; preflight validated production config and separated roles, `migrate` applied all 30 Alembic migrations (`0001` -> `0030`) as `agentnest_migrator`, `api`/`worker`/`caddy` started, `/readyz` returned `200 {"status": "ok", "checks": {"database": true, "migrations": true}}`, and `.deploy-state.s03` recorded `status: "succeeded"`, `active_image_tag: "v0.8.0-s03"`, `current_db_revision: "0030"`. |
| **4** | Runtime container credential isolation check inside running `api` and `worker` | Exit `0`; both `api` and `worker` reported `os.environ.get('MIGRATION_DATABASE_URL') == ''` and `SELECT current_user == 'agentnest_app'`. |
| **5** | Host lockfile contention (`acquire_deployment_lock` held while invoking concurrent `deploy.py deploy`) | Concurrent deploy exited immediately with exit code `2` (`error: Another deployment or rollback is already in progress`). |
| **6** | Failed readiness detection (`v0.8.1-s03` with failing readiness probe) + redacted diagnostics + schema-compatible rollback to `v0.8.0-s03` | Failed readiness exited `1`, emitted `=== Deployment Failure Diagnostics ===` (`docker compose ps -a` + container logs with secrets redacted), and recorded `status: "readiness_failed"`. Subsequent rollback (`deploy.py rollback`) verified `current_revision == "0030" == target_head_revision`, restored `v0.8.0-s03`, verified `/readyz` `200`, and recorded `status: "rolled_back"`. |
| **7** | Schema-incompatible rollback refusal (simulated forward DB revision `0031_forward_incompatible` > image head `0030`) | `deploy.py rollback --to-tag v0.8.0-s03` exited with code `3` (`Refusing image-only rollback to 'v0.8.0-s03': database is at revision '0031_forward_incompatible', which is newer than target image head '0030'`) without restarting runtime containers. |
| **8** | Worker restart during leased job & stuck `in_progress` operation reconciliation (`INV-05`, `INV-07`) | Seeded a stuck `send_reply` operation (`status='in_progress'`, `started_at = now - 20m`) and `ReplyDraft` (`status='sending'`) plus a due `reconcile_stuck_operations` job, then restarted `worker` (`1.22s` graceful `SIGTERM` restart). Restarted worker claimed `reconcile_stuck_operations` (`status='succeeded'`), transitioned `Operation` and `ReplyDraft` to `outcome_unknown` (`last_error_code='OUTCOME_UNKNOWN'`), and enqueued `reconcile_send` without blind retry. |

---

## 3. Reproducible Deploy & Rollback Commands

```powershell
# 1. Validate production configuration and separated migration/runtime credentials
docker compose -f compose.prod.yml --env-file .env --profile ops run --rm --no-deps migrate `
  python -m app.cli check-config --production --require-separated-migration-credentials

# 2. Execute deployment (preflight -> migration gate -> rolling restart -> /readyz check)
python scripts/deploy.py deploy --image-tag v0.8.0 --env-file .env --project-name agentnest
# (On Linux VPS: ./scripts/deploy.sh --image-tag v0.8.0 --env-file .env --project-name agentnest)

# 3. Inspect recorded deployment state
python scripts/deploy.py status --env-file .env --project-name agentnest

# 4. Roll back application image when schema-compatible
python scripts/deploy.py rollback --env-file .env --project-name agentnest
# (On Linux VPS: ./scripts/rollback.sh --env-file .env --project-name agentnest)
```

---

## 4. Canonical Task Coverage, External Dependencies & Handoff to Session 04

- **Canonical Phase 8 Task Coverage:**
  - `P8-01` (delivery, migration gate, and rollback portion): `.github/workflows/deploy.yml`, `scripts/deploy.py`, `scripts/deploy.sh`, `scripts/rollback.sh`, separated migration/runtime credentials, and `docs/operations/deployment-runbook.md` are **offline complete**.
  - `P8-12` (optional staging): `.github/workflows/deploy.yml`, `scripts/deploy.sh`, and `scripts/rollback.sh` support `--project-name agentnest-staging` and `--env-file .env.staging` with zero file duplication.
- **Externally Pending Evidence:**
  - Live GitHub Actions tag push to GHCR and SSH deployment against a provisioned production/staging VPS with public DNS and Let's Encrypt TLS remain pending external infrastructure provisioning (`Session 16` / `AC-1`). Local container rehearsal and workflow YAML verification are recorded distinctly from live VPS execution.
- **Handoff to Session 04 (`Backups, media protection and restore drill`):**
  - Session 04 will build on `compose.prod.yml`, `scripts/deploy.py`, and the schema-incompatible rollback boundary (`EXIT_ROLLBACK_INCOMPATIBLE = 3`) to implement nightly encrypted `pg_dump -Fc` backups to S3-compatible off-site storage (35-day retention), media bucket protection, `scripts/restore*` into an isolated database with role/privilege verification and post-restore operation fencing (`in_progress` -> `outcome_unknown` + deletion tombstone re-application), and the executed local restore drill with measured RPO/RTO.
