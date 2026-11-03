# Phase 8 — Session 12 Report: Retention, Key Rotation and Dependency Auditing

- **Session:** `S12` (`docs/implementation/phase-8-sessions/phase-08-sessions.md` §Session 12, `docs/implementation/phases/phase-08-hardening.md` `P8-06`, `docs/architecture/decisions/ADR-025-phase-8-hardening-contracts.md` §4, `docs/architecture/decisions/ADR-026-audit-log-retention-and-purge-boundary.md`)
- **Date:** 2026-11-03
- **Status:** `complete` (Retention extensions, key rotation CLI/worker job, CI dependency auditing, ADR-026, and operational runbooks implemented and verified; provisional legal periods tracked under `OQ-12` keeping Gate 3 open)
- **Branch / Commit Baseline:** `main` at `716935b`
- **Alembic Migration Head:** `20261103_0036_data_deletion_requests.py` (revision `0036`)

---

## 1. Summary of Implemented Artifacts & Contracts

| Artifact / File | Status | Implementation Summary |
|---|---|---|
| `docs/architecture/decisions/ADR-026-audit-log-retention-and-purge-boundary.md` | **Created** | Setteled audit log retention and purge boundary: 1. Runtime roles (`agentnest_app`, `agentnest_worker`) have `REVOKE UPDATE, DELETE ON audit_logs` strictly enforced (`INV-06`, `INV-12`, `ADR-022`, `ADR-025`); 2. Application runtime purge is forbidden and automated 730-day purge is deferred pending counsel review (`OQ-12`), keeping Gate 3 open; 3. Purging (if approved) must run as an out-of-band administrative script under `agentnest_migrator` with an immutable `audit.purged` log entry; 4. Reconciles 35-day backup retention (`backup_retention_days = 35`) with erasure obligations via post-restore `deletion_tombstones` re-application; 5. Defines key custody deprecation policy: retired encryption keys must be retained in `TOKEN_ENCRYPTION_KEYS` for ≥ 35 days until backups taken under that key have expired. |
| `backend/app/retention/cleanup.py` | **Updated** | Extended daily retention sweep to Phase 7.5 tables and multi-tenant RLS context: 1. Sweeps Category C tables per workspace using `set_tenant_context(session, ws_id)` across active/deleting workspaces; 2. Redacts `OwnerQuestion` (`body=None`, `source_message_id=None`, `source_hash=""`) and `OwnerAnswer` (`body=None`) at `retention_message_text_days` (default 180d provisional); 3. Redacts `OwnerTask` (`request_text="[REDACTED]"`, `clarification=None`, `answers=[]`) at `retention_message_text_days`; 4. Scrubs raw prompts/checkpoints in `AgentStep` (`read_checkpoint=None`, `input_ref=None`, `output_ref=None`) and `AgentAction` (`content_intent=None`, `policy_grant=None` for non-active states) at `retention_agent_input_days` (default 30d provisional); 5. Preserves state ledger (statuses, version numbers, token usage counters, audit references) in full compliance with `INV-17` and `ADR-022`; 6. Returns expanded `RetentionCounts` fields. |
| `backend/app/operations/key_rotation.py` | **Created** | Implemented token re-encryption service and background worker job (`rotate_token_keys`): 1. Validates `TokenKeyRing` with `TOKEN_ENCRYPTION_KEYS` and `TOKEN_ENCRYPTION_ACTIVE_KEY_ID`; 2. Scans `social_accounts` where `token_key_id != active_key_id` in bounded batches with row-level locking (`with_for_update()`); 3. Re-encrypts tokens in-place preserving AAD (`<workspace_id>:<account_id>`); 4. Handles concurrency safely by skipping disconnected or already-rotated accounts; 5. Emits `security.token_key_rotated` without leaking secrets (`INV-08`); 6. Resiliently handles corrupted ciphertexts/unreadable keys by logging `security.token_key_rotation_failed`, setting `last_error_code = "KEY_ROTATION_FAILED"`, and continuing batch execution. |
| `backend/app/handlers.py` | **Updated** | Registered `app.operations.key_rotation` in `load_handlers()`. |
| `backend/app/activity/groups.py` | **Updated** | Registered `"security.token_key_rotated"` and `"security.token_key_rotation_failed"` in the `"system"` activity group. |
| `backend/app/core/i18n/` | **Updated** | Added bilingual localized templates in `en.json` and `tr.json` for security key rotation audit events. |
| `scripts/rotate_token_keys.py` | **Created** | Cross-platform administrative CLI script to trigger token key rotation manually with configurable `--batch-size`. |
| `docs/operations/token-key-rotation-runbook.md` | **Created** | Operational runbook for generating AES-256 keys, updating server `.env`, restarting services, executing re-encryption, and safely deprecating retired keys after the 35-day backup retention window. |
| `docs/operations/dependency-auditing-runbook.md` | **Created** | Operational runbook for dependency vulnerability scanning (`pip-audit` & `npm audit`), SLAs by vulnerability severity (Critical/High/Moderate), and governance for time-bounded 30-day exceptions. |
| `.github/workflows/ci.yml` | **Updated** | Added automated dependency auditing steps: `uv run pip-audit` in `backend` job and `npm audit --audit-level=moderate` in `frontend` job. |
| `backend/pyproject.toml` | **Updated** | Added `pip-audit>=2.7.3` to dev dependency group and upgraded `certifi` to `>=2026.10.18` (remediating PYSEC-2026-4320). |
| `backend/tests/unit/operations/test_key_rotation.py` | **Created** | Unit test suite (5 tests) verifying successful re-encryption with AAD preservation, active key decryptability, skipping already-rotated/disconnected accounts, resilient error handling for corrupt ciphertexts, and job handler invocation. |
| `backend/tests/unit/retention/test_retention_phase8.py` | **Created** | Unit test suite (2 tests) verifying Phase 7.5 questions/answers redaction, owner tasks redaction, agent steps/actions payload scrubbing, ledger preservation, and multi-workspace tenant RLS context handling. |

---

## 2. Verification Outcomes

### 2.1 Static Analysis & Quality

| Check | Command | Exit Code | Result Summary |
|---|---|---|---|
| Backend Lint | `uv run ruff check .` | `0` | All checks passed (0 errors) |
| Backend Formatting | `uv run ruff format --check .` | `0` | 584 files already formatted |
| Backend Typecheck | `uv run mypy app` | `0` | Success: no issues found in 301 source files |
| Import Architecture | `uv run lint-imports` | `0` | 19 contracts kept, 0 broken |
| Python Dependency Audit | `uv run pip-audit` | `0` | No known vulnerabilities found |
| Frontend Lint | `npm.cmd run lint` | `0` | ESLint passed cleanly |
| Frontend Typecheck | `npm.cmd run typecheck` | `0` | `tsc -b --noEmit` passed cleanly |
| Frontend i18n Check | `npm.cmd run i18n:check` | `0` | Passed: en, tr \| 1548 keys \| 1025 literal t() calls verified |

### 2.2 Test Suite Execution

| Test Suite | Command | Exit Code | Result Summary |
|---|---|---|---|
| Token Key Rotation Unit Suite | `uv run pytest tests/unit/operations/test_key_rotation.py -v` | `0` | `5 passed in 0.70s` |
| Retention Phase 8 Unit Suite | `uv run pytest tests/unit/retention/test_retention_phase8.py -v` | `0` | `2 passed in 0.46s` |
| Combined Backend Hardening Suite (S07–S12) | `uv run pytest tests/unit/operations/test_key_rotation.py tests/unit/retention/test_retention_phase8.py tests/unit/operations/test_meta_callbacks.py tests/unit/operations/test_workspace_lifecycle_and_erasure.py tests/unit/operations/test_data_rights_export.py tests/unit/identity/test_password_reset_and_email.py tests/unit/test_activity_templates.py tests/unit/test_import_rules.py -q` | `0` | `51 passed in 4.86s` |
| Frontend Vitest Suite | `npm.cmd test` | `0` | `43 test files passed, 589 tests passed in 156.87s` |

---

## 3. Canonical Task Coverage & Gate 3 Tracking

- **P8-06 Retention Inventory & Cleanup Extension:**
  - Fully covers all Phase 7.5 tables: `owner_questions`, `owner_answers`, `agent_owner_tasks`, `agent_steps`, `agent_actions`, customer memory (`memory.service.retention_batch`), and public comments (`comments.privacy.retention_batch`).
  - Strict preservation of outcome ledger and audit records (`INV-17`, `INV-12`, `ADR-022`).
  - Sweeps run under explicit tenant RLS context (`set_tenant_context(session, ws_id)`) across workspaces.
  - Periods remain configurable via environment variables (`RETENTION_*`) and tracked as **provisional** pending counsel review (`OQ-12`), keeping Gate 3 open.
- **P8-06 Audit Purge Decision Resolution:**
  - Resolved through `ADR-026`: runtime application and worker roles possess no audit purge capability. Automated purge is deferred to an out-of-band administrative procedure under `agentnest_migrator`.
- **P8-06 Token Encryption Key Rotation:**
  - Key rotation service (`rotate_social_account_tokens`), CLI script (`scripts/rotate_token_keys.py`), and background worker job handler (`rotate_token_keys`) implemented and tested.
  - In-place re-encryption preserving AAD, with audit events (`security.token_key_rotated`, `security.token_key_rotation_failed`) and no secret exposure (`INV-08`).
  - 35-day key custody deprecation policy documented in `docs/operations/token-key-rotation-runbook.md`.
- **P8-06 Dependency Auditing in CI:**
  - Automated `pip-audit` added to `backend` and `npm audit --audit-level=moderate` added to `frontend` in `.github/workflows/ci.yml`.
  - Upgraded `certifi` to `>=2026.10.18` (remediating PYSEC-2026-4320). Local `pip-audit` verified cleanly with 0 known vulnerabilities.
  - Exception policy and SLAs established in `docs/operations/dependency-auditing-runbook.md`.

---

## 4. Handoff to Session 13

- **Next Session:** `S13` — Operator Monitoring and Alerts (`docs/implementation/phase-8-sessions/phase-08-sessions.md` §Session 13, `P8-07`).
- **Prerequisites Satisfied:** Session 08 email delivery, Session 04 backup failure signals, and Session 11–12 agent/operation health states are available.
- **Scope for S13:**
  - External `/readyz` uptime check runbook and Sentry-compatible error reporting with privacy scrubbing.
  - Alert on dead jobs, stale backups (> 26h), webhook signature failure bursts, accounts in `needs_reauth` > 24h, dead agent wakes, stuck recovery, and budget exhaustion.
  - Durable deduplication table `operator_alert_states` with recovery notices (`firing -> resolved`).

