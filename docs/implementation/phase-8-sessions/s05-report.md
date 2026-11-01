# Phase 8 — Session 05 Report: RLS Roles and Transaction Infrastructure

- **Session:** `S05` (`docs/implementation/phase-8-sessions/phase-08-sessions.md` §Session 05, `docs/implementation/phases/phase-08-hardening.md` `P8-03`)
- **Date:** 2026-11-01
- **Status:** `complete`
- **Branch / Commit Baseline:** `main` at `d82431b`
- **Alembic Migration Head:** `20261101_0031_rls_bootstrap_functions.py` (revision `0031`, 31 migrations total)

---

## 1. Summary of Implemented Artifacts & Contracts

| Artifact / File | Status | Implementation Summary |
|---|---|---|
| `backend/migrations/versions/20261101_0031_rls_bootstrap_functions.py` | **Created** | Alembic migration `0031` adding 8 narrow `SECURITY DEFINER` bootstrap and periodic discovery functions in `public` schema (`SET search_path = public, pg_temp`): `resolve_social_account_by_external(provider_kind, external_account_id)`, `resolve_invite_by_token_hash(token_hash)`, `resolve_oauth_state_by_hash(state_hash)`, `discover_expired_approval_ids(now, limit)`, `discover_expired_reply_draft_ids(cutoff, limit)`, `discover_expired_command_ids(now, limit)`, `discover_stuck_operations(cutoff, limit)`, and `discover_stuck_agent_sessions(cutoff, limit)`. Granted `EXECUTE` on functions to `PUBLIC`. Clean forward (`upgrade head`) and rollback (`downgrade -1`) verified. |
| `backend/app/core/db.py` | **Updated** | Implemented transaction-local tenant context binding: `set_tenant_context(session, workspace_id)` issuing `SELECT set_config('app.workspace_id', :ws_id, true)`, validating non-empty UUID string; `clear_tenant_context(session)`; `get_current_tenant_guc(session)`; `@event.listens_for(Session, "after_begin")` listener that transparently re-applies `set_config` on new transactions within multi-transaction sessions; context manager `tenant_session(workspace_id, session_factory)`; and `make_tenant_session_factory(base_factory, workspace_id)`. |
| `backend/app/api/deps.py` | **Updated** | Integrated tenant context binding in `require_membership`: immediately after verifying active workspace membership, calls `set_tenant_context(db, workspace.id)` ensuring all subsequent request ORM queries and statements execute within the verified tenant context. |
| `backend/app/jobs/worker.py` | **Updated** | Integrated tenant context binding in background worker execution (`execute_job`): when `job.workspace_id` is present on a claimed job, wraps `ctx.session_factory` with `make_tenant_session_factory`, binding the tenant context on every session opened by the handler. |
| `backend/app/integrations/instagram/queries.py` | **Updated** | Updated `resolve_by_external()` to call bootstrap function `resolve_social_account_by_external` and bind tenant context `set_tenant_context(session, row.workspace_id)` before loading and returning the tenant-scoped `SocialAccount`. |
| `backend/app/identity/invites.py` | **Updated** | Updated `accept_invite()` to query `resolve_invite_by_token_hash` before tenant context exists, then set tenant context `set_tenant_context(session, invite_row.workspace_id)` for the remainder of the transaction. |
| `backend/app/operations/oauth_service.py` | **Updated** | Updated `complete_connect_meta()` to query `resolve_oauth_state_by_hash` prior to setting tenant context, binding `set_tenant_context(session, state_row.workspace_id)` before completing OAuth token exchange. |
| `backend/app/approvals/repository.py`, `backend/app/approvals/jobs.py` | **Updated** | Updated cross-workspace expiry discovery to use `discover_expired_approval_ids`, and updated `expire_approvals` worker job to bind tenant context per expired item during status transitions. |
| `backend/app/inbox/expiry.py` | **Updated** | Updated `sweep_expired_drafts` to discover candidate drafts across workspaces via `discover_expired_reply_draft_ids`, binding tenant context for each draft resolution. |
| `backend/app/commands/repository.py` | **Updated** | Updated `due_clarifications()` cross-workspace query to use `discover_expired_command_ids`. |
| `backend/app/operations/jobs.py` | **Updated** | Updated `reconcile_stuck_operations` to query `discover_stuck_operations`, binding tenant context per stuck operation during unsticking / reconciliation. |
| `backend/app/operations/backup_restore.py` | **Updated** | Updated `provision_database_roles()` to grant `EXECUTE ON ALL FUNCTIONS IN SCHEMA public` and set default function execution privileges for runtime roles (`agentnest_app`, `agentnest_worker`). |
| `backend/tests/unit/core/test_rls_infrastructure.py` | **Created** | 8 comprehensive tests verifying: tenant GUC binding and fail-closed state when unset; invalid UUID rejection; context reset across sessions and connection pool reuse; nested savepoints; `tenant_session` context manager; worker job dispatch with workspace context; all 8 `SECURITY DEFINER` bootstrap functions; and least-privilege non-bypass roles with `REVOKE UPDATE, DELETE` on append-only tables (`audit_logs`, `fact_versions`). |
| `backend/tests/unit/core/test_deployment_workflow_and_rollback.py` | **Updated** | Updated expected migration head revision to `0031`. |

---

## 2. Verification Results

### 2.1 Static Analysis, Typecheck & Import Boundaries

| Check | Command | Exit Code | Result Summary |
|---|---|---|---|
| Backend Lint | `backend/.venv/Scripts/ruff.exe check .` | `0` | `All checks passed!` (0 errors) |
| Backend Format | `backend/.venv/Scripts/ruff.exe format --check .` | `0` | `568 files already formatted` |
| Backend Typecheck | `backend/.venv/Scripts/mypy.exe app` | `0` | `Success: no issues found in 293 source files` |
| Import Boundaries | `backend/.venv/Scripts/lint-imports.exe` | `0` | `Contracts: 19 kept, 0 broken` |
| Frontend Lint | `npm.cmd run lint` (frontend) | `0` | `eslint .` passed cleanly |
| Frontend Typecheck | `npm.cmd run typecheck` (frontend) | `0` | `tsc -b --noEmit` passed cleanly |
| Frontend i18n | `npm.cmd run i18n:check` (frontend) | `0` | `i18n check passed: en, tr \| 1496 keys \| 963 literal t() calls verified` |

### 2.2 Test Suite Execution

| Test Suite | Command | Exit Code | Result Summary |
|---|---|---|---|
| RLS Infrastructure Tests | `pytest tests/unit/core/test_rls_infrastructure.py -q` | `0` | `8 passed in 5.20s` |
| Full Backend Unit Tests | `pytest tests/unit -q` | `0` | `1522 passed in 12.06s` |

---

## 3. Key Architectural Decisions (`ADR-025` §1 Alignment)

1. **Transaction-Local GUC Binding (`SET LOCAL app.workspace_id`):**
   - Implemented via `SELECT set_config('app.workspace_id', :ws_id, true)` where `is_local = true`.
   - Automatically expires on transaction boundary (`COMMIT` or `ROLLBACK`).
   - Re-applied across multi-transaction sessions using SQLAlchemy `@event.listens_for(Session, "after_begin")` reading `session.info["tenant_workspace_id"]`.
   - Rejects non-UUID strings to prevent injection or malformed settings.
2. **Connection Pooling Safety:**
   - Because `set_config(..., true)` is local to the active transaction, returning connections to the pool leaves no persistent GUC state on subsequent transactions.
   - Fail-closed semantics: when `app.workspace_id` is empty or unset, `nullif(current_setting('app.workspace_id', true), '')` returns `NULL`.
3. **Narrow `SECURITY DEFINER` Functions:**
   - Only narrow lookup paths that must execute prior to tenant context establishment (e.g. webhook account resolution, invite token hashing, OAuth state callback, periodic sweeper discovery) are allowed to bypass RLS.
   - All functions set `search_path = public, pg_temp` to prevent schema search-path hijacking attacks.
4. **Least-Privilege Database Roles:**
   - `agentnest_app` and `agentnest_worker` roles are configured with `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`.
   - Explicit `REVOKE UPDATE, DELETE ON public.audit_logs, public.fact_versions` enforces append-only immutability.

---

## 4. Handoff to Next Session (Session 06)

- **Next Objective:** Phase 8 Session 06 — RLS Policies for Category C (Workspace-Scoped) Tables (`P8-03`).
- **Prerequisites Satisfied:**
  - Database roles (`agentnest_migrator`, `agentnest_app`, `agentnest_worker`) provisioned and verified.
  - Transaction-local GUC binding and session factory infrastructure in place across HTTP API dependencies and job worker.
  - Narrow bootstrap discovery functions deployed via migration `0031`.
  - All unit tests (1522 passing), linters, formatters, and type checkers passing cleanly.
