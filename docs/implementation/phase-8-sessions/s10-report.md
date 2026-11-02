# Phase 8 — Session 10 Report: Conversation, Customer, and Workspace Deletion Lifecycle

- **Session:** `S10` (`docs/implementation/phase-8-sessions/phase-08-sessions.md` §Session 10, `docs/implementation/phases/phase-08-hardening.md` `P8-05 erasure`, `docs/architecture/decisions/ADR-025-phase-8-hardening-contracts.md` §3.2, §3.3)
- **Date:** 2026-11-03
- **Status:** `complete`
- **Branch / Commit Baseline:** `main` at `0249199`
- **Alembic Migration Head:** `20261103_0035_workspace_deletion_and_tombstones.py` (revision `0035`)

---

## 1. Summary of Implemented Artifacts & Contracts

| Artifact / File | Status | Implementation Summary |
|---|---|---|
| `backend/migrations/versions/20261103_0035_workspace_deletion_and_tombstones.py` | **Created** | Migration 0035 adding `deletion_requested_at`, `deletion_scheduled_at`, `deletion_requested_by` (FK to `users.id`) to `workspaces`, creating `deletion_tombstones` table with indices (`ix_deletion_tombstones_entity`, `ix_deletion_tombstones_workspace`), and runtime grants for `agentnest_app` and `agentnest_worker`. |
| `backend/app/identity/models.py` | **Updated** | Added `deletion_requested_at`, `deletion_scheduled_at`, and `deletion_requested_by` columns to the `Workspace` model. |
| `backend/app/operations/models.py` | **Updated** | Added `DeletionTombstone` model matching the manifest schema used by backup & restore safeguards. |
| `backend/app/operations/data_rights.py` | **Updated** | Implemented `erase_conversation` and `erase_customer` adhering to `ADR-025 §3.2`: 1. Reconciliation & ledger preservation guard (`INV-05`, `ADR-022`) preventing hard row deletion while operations or drafts are in-flight (`in_progress`, `outcome_unknown`, `sending`); 2. Immediate redaction of personal text (`messages.text=None`, `attachments=[]`, `reply_drafts.text=None`) with fence advancement and `{"status": "redacted_reconciliation_pending"}`; 3. Complete hard purge when settled: erases messages, drafts, approvals, agent threads, customer memories (`memory_service.erase_customer`), redacts owner questions/answers (`owner_requests_service.redact`), redacts public comments (`comments_privacy.redact_receipts`), and scrubs raw webhook payloads (`InboundEvent`); 4. Durable tombstone generation in `deletion_tombstones` to prevent backup-restore resurrection; 5. Audit emission of `data_rights.conversation_erased` and `data_rights.customer_erased`. |
| `backend/app/operations/workspace_lifecycle.py` | **Created** | Implemented 7-day grace period workspace deletion lifecycle (`ADR-025 §3.3`): 1. `request_workspace_deletion()` sets `workspaces.status = 'deleting'`, `deletion_scheduled_at = now + 7 days`, pauses outbound agent automation (`AccountAgent.operating_mode = 'paused'`), cancels pending drafts/approvals/content, disconnects social accounts, emits `workspace.deletion_requested`, and sends confirmation email with cancellation link to workspace owners; 2. `cancel_workspace_deletion()` restores active status before scheduled date and emits `workspace.deletion_cancelled`; 3. `get_workspace_deletion_status()` returns status, scheduled date, days remaining, and `can_cancel`; 4. `purge_workspace()` hard-purges all workspace data rows, records workspace tombstone in `deletion_tombstones`, verifies no in-progress operations remain (`INV-05`), and deletes workspace row. |
| `backend/app/core/email.py` | **Updated** | Added `send_workspace_deletion_email()` with localized TR and EN plain text and HTML templates explaining the 7-day grace period, scheduled permanent purge date, and immediate cancellation URL. |
| `backend/app/operations/data_rights_router.py` | **Updated** | Mounted workspace and customer erasure endpoints: `DELETE .../conversations/{conversation_id}` (`data.delete`), `DELETE .../customers/{customer_identity_id}` (`data.delete`), `POST .../delete-request` (`workspace.manage`), `POST .../cancel-deletion` (`workspace.manage`), and `GET .../deletion-status` (`workspace.manage`). |
| `backend/app/activity/groups.py` | **Updated** | Registered activity actions: `"data_rights.conversation_erased"`, `"data_rights.customer_erased"`, `"workspace.deletion_requested"`, `"workspace.deletion_cancelled"`, `"workspace.purged"`. |
| `backend/app/core/i18n/` | **Updated** | Added localized TR and EN templates for the 5 activity actions in `en.json` and `tr.json`. |
| `backend/tests/unit/operations/test_workspace_lifecycle_and_erasure.py` | **Created** | Comprehensive unit test suite (10 tests) verifying conversation erasure, reconciliation guard with redaction, customer erasure, permission enforcement, deletion request, 7-day calculation, cancellation, cancellation refusal after expiry, and hard purge with tombstones. |
| `frontend/openapi.json` & `frontend/src/api/schema.d.ts` | **Regenerated** | Synchronized frontend OpenAPI client schema with erasure and workspace deletion lifecycle endpoints. |
| `frontend/src/features/inbox/hooks.ts` | **Updated** | Added typed React Query mutation hook `useEraseConversation(ws, conversationId)`. |
| `frontend/src/features/inbox/ConversationPage.tsx` | **Updated** | Added "Erase data" (`convo.erase`) button with confirmation prompt, invalidating queries and navigating back to inbox on completion. |
| `frontend/src/features/settings/hooks.ts` | **Updated** | Added `WorkspaceDeletionStatus`, `useWorkspaceDeletionStatus`, `useRequestWorkspaceDeletion`, and `useCancelWorkspaceDeletion`. |
| `frontend/src/features/settings/WorkspaceDangerZone.tsx` | **Created** | Danger Zone UI component rendering active 7-day grace period banner with days remaining and "Cancel Deletion" action, or "Delete Workspace" trigger with modal confirmation. |
| `frontend/src/features/settings/SettingsPage.tsx` | **Updated** | Embedded `WorkspaceDangerZone` for workspace owners. |
| `frontend/src/i18n/locales/` | **Updated** | Added localized TR and EN strings across `inbox.json` and `common.json`. |
| `frontend/src/features/inbox/inbox.test.tsx` | **Updated** | Added test verifying conversation erase action. |
| `frontend/src/features/settings/settings.test.tsx` | **Updated** | Added test verifying workspace deletion request action. |

---

## 2. Verification Outcomes

### 2.1 Static Analysis & Quality

| Check | Command | Exit Code | Result Summary |
|---|---|---|---|
| Backend Lint | `backend/.venv/Scripts/ruff.exe check .` | `0` | All checks passed (0 errors) |
| Backend Typecheck | `backend/.venv/Scripts/mypy.exe app` | `0` | Success: 0 issues in source files |
| Import Architecture | `backend/.venv/Scripts/lint-imports.exe` | `0` | 19 contracts kept, 0 broken |
| Frontend Lint | `npm.cmd run lint` | `0` | ESLint passed cleanly |
| Frontend Typecheck | `npm.cmd run typecheck` | `0` | `tsc -b --noEmit` passed cleanly |
| Frontend i18n Check | `npm.cmd run i18n:check` | `0` | Passed: en, tr \| 1548 keys \| 1025 literal t() calls verified |

### 2.2 Test Suite Execution

| Test Suite | Command | Exit Code | Result Summary |
|---|---|---|---|
| Workspace Lifecycle & Erasure Unit Suite | `pytest tests/unit/operations/test_workspace_lifecycle_and_erasure.py -q` | `0` | `10 passed in 0.23s` |
| Combined Backend Data Rights Suite | `pytest tests/unit/operations/test_workspace_lifecycle_and_erasure.py tests/unit/operations/test_data_rights_export.py -q` | `0` | `16 passed in 0.25s` |
| Frontend Inbox Vitest Suite | `vitest run src/features/inbox/inbox.test.tsx` | `0` | `19 passed in 2.63s` |
| Frontend Settings Vitest Suite | `vitest run src/features/settings/settings.test.tsx` | `0` | `5 passed in 0.96s` |

---

## 3. Canonical Task Coverage

- **P8-05 Erasure & ADR-025 §3.2 (Conversation & Customer Erasure):**
  - Durable tombstones in `deletion_tombstones` to prevent backup-restore resurrection.
  - Reconciliation guard (`INV-05`, `ADR-022`) safely deferring row purge and immediately blanking text content if operations/drafts are in-flight.
  - Hard purge removes messages, drafts, approvals, agent threads, customer memories, redacts owner questions/public comment receipts, and scrubs inbound webhooks.
  - Strictly Owner-only (`data.delete`).
- **ADR-025 §3.3 (Workspace Deletion Lifecycle):**
  - Owner-only initiation with 7-day grace period.
  - Pauses all outbound automation and social channels immediately.
  - Email notification with cancel link sent to workspace owners.
  - Cancellation capability during active grace period.
  - Complete workspace purge upon grace period expiration with durable tombstone recording.
