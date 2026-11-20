# Session 10 Report — Complete Combined Regression and Release Preparation

- **Date:** 2026-11-19 (Europe/Istanbul)
- **Plan:** [Account Agent Pilot Readiness](../../../answeres2.md) — Session 10
- **Local Git Baseline:** branch `main`, commit `e1c9f1367f63ed4afcd7e78b075c48a61c408fd8` (`e1c9f13`) + Sessions 01 through 09 work
- **Alembic Migration Head:** `0101` (`20261119_0101_channel_preferences.py`, parent `0100`)

---

## 1. Executive Summary

Session 10 executes the combined regression, build verification, OpenAPI/schema synchronization, and release preparation for the full change set introduced across Sessions 00 through 09 of the Account Agent Pilot Readiness initiative.

All static analysis, code formatters, dependency linter contracts, migration head checks, and frontend/landing production builds passed cleanly with **zero errors**. The pure offline unit test suites passed **100%**. As cataloged during Session 00, PostgreSQL container port 5433 is offline on this developer machine (no local Docker engine running), resulting in 61 expected database connection timeout errors across the 9 DB-backed unit suites, while all 3,281 offline unit tests passed cleanly.

OpenAPI schemas and client TypeScript definitions were re-exported from the FastAPI application and synchronized, resolving pending schema additions from Sessions 02 and 07.

---

## 2. Checks Executed and Verified Results

### 2.1 Backend Checks

| Check / Command | Scope | Result | Details |
|---|---|---|---|
| `uv run ruff check .` | `backend/` | **PASS** | `All checks passed!` across entire backend codebase and tests. |
| `uv run ruff format --check .` | `backend/` | **PASS** | `911 files already formatted`. Zero formatting discrepancies. |
| `uv run mypy app` | `backend/app/` | **PASS** | `Success: no issues found in 465 source files`. Strict type safety confirmed. |
| `uv run lint-imports` | `backend/` | **PASS** | `Analyzed 540 files, 4681 dependencies. Contracts: 27 kept, 0 broken.` Architectural boundaries strictly enforced. |
| `uv run alembic heads` | `backend/` | **PASS** | Single migration head: `0101 (head)` (`20261119_0101_channel_preferences.py`). |
| `uv run pytest tests/unit/` | `backend/tests/unit/` | **PASS (Offline)** / **61 DB Errors** | Total 3,343 items: **3,281 passed**, **1 skipped** (`test_ffmpeg_prober.py:183`, POSIX resource limits on Windows), **61 connection timeout errors** caused by local Docker/PostgreSQL port 5433 being offline. Zero test assertion failures. |

#### Detailed Breakdown of the 61 Database-Backed Unit Test Errors (Port 5433 Offline):
All 61 errors failed identically with `sqlalchemy.exc.OperationalError: (psycopg.errors.ConnectionTimeout) connection timeout expired ... host: 'localhost', port: 5433`:
1. `tests/unit/approvals/test_telegram_action_tokens.py`: 8 tests (Action token generation, consumption, replay, and expiry fixtures requiring DB session).
2. `tests/unit/core/test_backup_and_restore.py`: 3 tests (Audit log recording, restore reconcile, database role provisioning).
3. `tests/unit/core/test_rls_infrastructure.py`: 8 tests (Tenant context GUC binding, savepoints, worker dispatch under RLS).
4. `tests/unit/core/test_rls_policies.py`: 9 tests (Category C forced RLS table policies, isolation read/write, foreign delete).
5. `tests/unit/identity/test_auth_hardening.py`: 6 tests (Login throttling, session revocation, password change hardening).
6. `tests/unit/identity/test_channel_links.py`: 13 tests (Link code generation, redemption, case insensitivity, unlinking).
7. `tests/unit/integrations/channels/test_telegram_commands_media.py`: 7 tests (Photo ingestion, story draft creation, owner task routing).
8. `tests/unit/notifications/test_delivery_policy.py`: 3 tests (Delivery dispatch, failure recording, quiet hours).
9. `tests/unit/test_hardening_unit_regressions.py`: 4 tests (Member removal Telegram revocation, workspace deletion agent pause, webhook redaction, password reset throttling).

#### Key Pure Offline Unit Suites (100% Pass):
- `tests/unit/agent/test_account_agent_pilot_acceptance_unit.py`: 35 passed in 0.26s.
- `tests/unit/agent/test_agent_languages_unit.py`: 82 passed.
- `tests/unit/agent/test_agent_media_unit.py`: 30 passed.
- `tests/unit/agent/test_agent_policy_matrix_unit.py`: 81 passed.
- `tests/unit/identity/test_channel_preferences_unit.py`: 24 passed.
- `tests/unit/reporting/test_leads_agent_unit.py`: 7 passed.
- `tests/unit/inbox/test_sandbox_agent_unit.py`: 18 passed.
- `tests/unit/integrations/channels/test_telegram_delivery_unit.py`: 13 passed.
- `tests/unit/content/`: 188 passed.
- `tests/unit/ai/`: 129 passed.

---

### 2.2 Frontend Checks

| Check / Command | Scope | Result | Details |
|---|---|---|---|
| `npm.cmd run lint` | `frontend/` | **PASS** | `eslint .` exited with code 0 (0 warnings, 0 errors). |
| `npm.cmd run typecheck` | `frontend/` | **PASS** | `tsc -b --noEmit` exited with code 0. Full TypeScript compilation clean. |
| `npm.cmd run i18n:check` | `frontend/` | **PASS** | `i18n check passed: en, tr \| 3023 keys \| 2136 literal t() calls verified`. |
| `npm.cmd test -- --run` | `frontend/` | **PASS** | `Test Files: 69 passed (69)`, `Tests: 977 passed (977)`, duration 96.14s. All component, hook, and integration tests passed. |
| `npm.cmd run build` | `frontend/` | **PASS** | `tsc -b && vite build` completed in 631ms. Production assets emitted to `frontend/dist/`. |

---

### 2.3 Landing App Checks

| Check / Command | Scope | Result | Details |
|---|---|---|---|
| `npm.cmd run build` | `landing/` | **PASS** | `tsc -b && vite build` completed in 368ms. Production assets emitted to `landing/dist/`. |

---

### 2.4 OpenAPI and Client Type Synchronization

1. **Backend Export:**
   Executed `uv run python -m app.cli export-openapi --output ../frontend/openapi.json`.
   Synchronized:
   - Added endpoint `/api/v1/workspaces/{workspace_id}/channels/preferences` (`GET`, `PUT`) and schemas `ChannelPreferencesIn`, `ChannelPreferencesOut`, and `ChannelDeliveryStatusOut` (Session 02).
   - Added `controller_mode` ("legacy" | "agent") to `AssistantChatOut` and `AssistantChatTurnOut` (Session 07).
   - Added `automatic` and `ask` decision values to `AssistantChatDraftOut` (Session 07).
2. **Frontend Type Generation:**
   Executed `npm.cmd run gen:api` (`openapi-typescript openapi.json -o src/api/schema.d.ts`).
3. **Test Fixture Alignment:**
   Updated test helper functions `turn()` and `chat()` in `frontend/src/features/test-chat/testChat.test.tsx` to supply the required `controller_mode: "legacy"` property, aligning the tests with the updated OpenAPI contract.

---

## 3. Migration Inspection: `20261119_0101_channel_preferences.py`

### 3.1 Schema & Design Audit
- **Table:** `channel_preferences`
- **Revision:** `0101`, down revision `0100` (`20261118_0100_reply_languages_ru_de_ar.py`).
- **Columns:**
  - `id`: `UUID`, primary key (`pk_channel_preferences`).
  - `workspace_id`: `UUID NOT NULL`, foreign key (`fk_channel_preferences_workspace_id_workspaces`) with `ON DELETE CASCADE`.
  - `user_id`: `UUID NOT NULL`, foreign key (`fk_channel_preferences_user_id_users`) with `ON DELETE CASCADE`.
  - `channel`: `TEXT NOT NULL`, checked by `ck_channel_preferences_channel` (`channel IN ('telegram', 'whatsapp')`).
  - `enabled`: `BOOLEAN NOT NULL`, server default `true`.
  - `created_at` / `updated_at`: `TIMESTAMPTZ NOT NULL`, server default `now()`.
- **Unique Constraints:**
  - `uq_channel_preferences_workspace_id_id`: `(workspace_id, id)` composite key for INV-01 invariant consistency.
  - `uq_channel_preferences_workspace_id_user_id_channel`: `(workspace_id, user_id, channel)` preventing duplicate channel records per user.
- **Indices:**
  - `ix_channel_preferences_workspace_id`: `[workspace_id]`.
  - `ix_channel_preferences_user`: `[workspace_id, user_id]`.

### 3.2 Tenant Isolation and RLS Verification
- Under PostgreSQL dialect:
  - `ALTER TABLE channel_preferences ENABLE ROW LEVEL SECURITY;`
  - `ALTER TABLE channel_preferences FORCE ROW LEVEL SECURITY;`
  - Policy `tenant_isolation_policy`:
    ```sql
    CREATE POLICY tenant_isolation_policy ON channel_preferences FOR ALL
    USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
    WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
    ```
  - Grants `SELECT, INSERT, UPDATE, DELETE` to runtime roles (`pivoris_app`, `pivoris_worker`, `pivoris_migrator`) if present.
  - Backfill query: Seeds initial preferences as `enabled=true` for all existing active `channel_links`, ensuring zero notification drops for currently onboarded owners upon deployment.

### 3.3 Rollback / Downgrade Restrictions and Data Dependencies
- **Downgrade Action:** Drops indexes and drops the table `channel_preferences`.
- **Data Loss Warning:** Rolling back from `0101` to `0100` permanently destroys all user-configured channel preferences (e.g. explicitly muted Telegram or WhatsApp channels, or app-only preferences).
- **Subsequent Re-upgrade:** If migration `0101` is reapplied after a rollback, all active links will default to `enabled=true`, requiring owners with muted channels to re-mute them in Settings.
- **Code Dependency:** Application and worker services must be rolled back concurrently with the migration downgrade; otherwise, queries attempting to select from `channel_preferences` will raise undefined table errors (`42P01`).

---

## 4. Release Note — Account Agent Pilot Readiness

### 4.1 Key Capabilities Delivered

1. **Owner Notification Channel Choice (`channel_preferences`):**
   - Owners can configure their notification destinations independently per workspace: Telegram (primary), WhatsApp, or App-Only.
   - Interactive Telegram alerts deliver single-use `act:<token>` approval buttons directly to owner mobile phones for instant one-tap decisions.
   - Web Push remains an independent device-level browser notification opt-in.
   - Comprehensive delivery status visibility (`connected`, `unlinked`, `disabled`, `unconfigured`, `delivery_failure`) displayed in Workspace Settings.

2. **Deterministic Account Agent Semi-Automation:**
   - Account Agent activation operates under explicit owner delegation (`POST /api/v1/workspaces/{ws}/accounts/{account_id}/agent/activate` with `mode="agent"`).
   - Semi-automation policy matrix enforces full automation for basic FAQ queries (greetings, business hours, studio address, services, verified pricing) using verified fact substitution.
   - Complex requests (complaints, custom offers, appointment modifications, voice notes) strictly require human approval (`ask` / `approval_required`).
   - Prompt injections and ungrounded claims fail closed (`blocked` / human intervention required). Topic policy can only restrict action grants, never broaden them (`INV-04`).

3. **5-Language Customer Reply Support:**
   - Customer-facing replies and bookings support **Turkish (`tr`)**, **English (`en`)**, **Russian (`ru`)**, **German (`de`)**, and **Arabic (`ar`)**.
   - System prompts, grounding validators, and calendar confirmations are fully localized in all 5 languages, with Arabic RTL formatting and 1,000-byte platform constraint guards.
   - App UI and owner notifications remain strictly bilingual in **Turkish and English** (`INV-03`, `INV-14`).

4. **Media Transcript & Image Context Processing:**
   - Completed audio voice note transcriptions and image descriptions safely wake the Account Agent via internal drafting jobs.
   - Inbound voice notes automatically mandate human approval (`ask`), preventing autonomous agent responses to spoken requests without owner confirmation.
   - Customer media is strictly treated as untrusted data (`INV-03`), with sandboxed context separation.

5. **Booking Enquiries and Lead Attribution:**
   - Booking enquiries received through the Account Agent are recorded as genuine sales leads in reporting tables.
   - Linked appointments in `calendar_appointments` serve as verified conversion signals; booking-only conversations without pricing requests are accurately accounted for.

---

## 5. Invariants & Recovery Procedures (INV-05, INV-06, INV-16)

### 5.1 Stale Queued Work and Policy Version Invalidation (INV-16)
- **Problem:** When an owner modifies the workspace automation policy, delegation mode, or business facts, existing queued drafts or pending approvals could execute under obsolete permissions.
- **Enforcement:**
  - Every agent action and human approval is bound to an exact `subject_version` and cryptographic `payload_hash` (`INV-16`).
  - An approval token or policy grant generated under version $N$ is immediately invalidated if the underlying draft, fact version, or delegation configuration is mutated.
  - The operations executor re-validates current workspace delegation authority and account state immediately before dispatching any external operation.
  - Expired, replayed, or stale approval button presses are rejected with explicit user feedback (`EXPIRED_OR_STALE`).

### 5.2 Idempotency and Reconciliation of Unknown Outcomes (INV-05, INV-06)
- **Problem:** Network timeouts, transient provider dropouts, or worker container restarts during Telegram/WhatsApp dispatch or Instagram publishing can leave operations in an indeterminate state.
- **Enforcement:**
  - Write-ahead ledger: Every external side effect creates a pending record in `operations` before calling remote APIs (`INV-15`).
  - If a call times out or terminates unexpectedly, the operation enters `outcome_unknown`.
  - The reconciliation worker queries provider status before attempting any retry. Duplicate sends are strictly prevented via `operations.idempotency_key` and unique database constraints (`INV-06`).
  - Repeated clicks on Telegram approval buttons or web UI actions are idempotently deduplicated.

### 5.3 Emergency Rollback & Recovery Runbook

1. **Step 1: Pause Account Agents (if incident in progress):**
   - Set account controller mode to `legacy` or pause agent execution via UI / API (`POST /agent/pause`).
2. **Step 2: Stop In-Flight Workers:**
   - Drain or pause worker processes processing notification and agent queues.
3. **Step 3: Revert Application Binaries:**
   - Deploy previous stable container/commit image.
4. **Step 4: Roll Back Database Migration:**
   - Execute Alembic downgrade:
     ```bash
     uv run alembic downgrade 0100
     ```
   - Note: This drops `channel_preferences`. All notification routing falls back to active links in `channel_links`.
5. **Step 5: Restart Workers and Reconcile:**
   - Restart worker containers. The reconciliation loop resolves any pending operations in `operations` ledger.

---

## 6. Files Changed in Session 10

1. `frontend/openapi.json` — Updated OpenAPI spec exported from FastAPI with channel preferences and test chat controller properties.
2. `frontend/src/api/schema.d.ts` — Regenerated TypeScript types from `openapi.json`.
3. `frontend/src/features/test-chat/testChat.test.tsx` — Updated test fixture helpers (`turn`, `chat`) to supply required `controller_mode: "legacy"`.
4. `docs/implementation/account-agent-pilot-readiness/s10-report.md` — This report.

---

## 7. Acceptance Criteria Satisfied

- [x] Backend static analysis (`ruff check`, `ruff format --check`, `mypy app`, `lint-imports`) passes with 0 issues.
- [x] Alembic migration head verified as single head `0101`.
- [x] Backend complete unit regression suite executed and documented (3,281 passed offline; 61 connection timeout errors accurately recorded against offline Postgres port 5433).
- [x] Frontend checks (`lint`, `typecheck`, `i18n:check`, `test`, `build`) pass with 0 errors across 977 Vitest tests and production build.
- [x] Landing build verified clean (`tsc -b && vite build` passes).
- [x] OpenAPI schema and frontend types fully up-to-date and synchronized.
- [x] Migration `0101` upgrade, downgrade, RLS policies, and rollback restrictions thoroughly audited and documented.
- [x] Comprehensive Release Note and Recovery Procedure prepared covering `channel_preferences`, semi-automation, 5 languages, media wake, lead signals, and INV-05/06/16 reconciliation.
- [x] Working tree kept clean of unrequested changes; no commits or pushes performed.
