# Session 07 Report — Make Practice Chat Truthful for the Selected Controller

- **Date:** 2026-11-19 (Europe/Istanbul)
- **Plan:** [Account Agent Pilot Readiness](../../../answeres2.md) — Session 07
- **Local Git Baseline:** branch `main`, commit `e1c9f1367f63ed4afcd7e78b075c48a61c408fd8` (`e1c9f13`) + Sessions 01 through 06 work
- **Alembic Migration Head:** `0101` (`20261119_0101_channel_preferences.py`, parent `0100`)

---

## 1. Changes Made and Why

1. **Controller Detection & Dual-Mode Practice Chat (`backend/app/inbox/sandbox.py`, `backend/app/inbox/sandbox_router.py`):**
   - Implemented `get_controller_mode(session, workspace_id)` in `backend/app/inbox/sandbox.py`.
   - Inspects the workspace's primary connected account and its `AccountAgent`:
     - If `controller_mode == "agent"` and `state == "active"`, practice chat runs in **Agent dry-run mode**.
     - If no account is connected, or `state != "active"` (e.g. paused/inactive), or `controller_mode == "legacy"`, practice chat runs in **Legacy drafting mode**.
   - Exposed `controller_mode` (`"agent"` | `"legacy"`) in API responses:
     - On `AssistantChatOut` (workspace-level controller state).
     - On `AssistantChatTurnOut` (turn-level controller provenance).

2. **Reuse Production Agent Logic in Dry-Run Sandbox (`backend/app/inbox/sandbox.py`):**
   - Implemented `evaluate_agent_dry_run(session, context, plan, customer_text)`.
   - Reuses production Agent components rather than maintaining a separate imitation:
     - **Language Selection:** Reuses 5-language detection from Session 04 (`choose_reply_language` supporting `tr`, `en`, `ru`, `de`, `ar`). Fails closed to `"ask"` with `reason="LANGUAGE_UNSUPPORTED"` if an unsupported language or ambiguous text is encountered.
     - **Grounding & Claim Safety (INV-02):** Reuses claim validation and usable fact constraints. Ungrounded claims or missing facts result in safe refusal / ask (`"GROUNDING_FAILED"`, `"FACT_NOT_USABLE"`), never fabricating prices or hours.
     - **Semi-Automation Policy Matrix:** Reuses `classify_request` and `evaluate_action_policy` from Session 03's `app/agent/policy.py`.
     - **Truthful Decision Resolution:**
       - Basic verified question (greeting, hours, address, services, standard verified price with price sharing) AND `dm.send` delegation rule is `automatic` -> `decision: "automatic"`, `reason: "basic_verified_topic"`.
       - Basic question BUT `dm.send` delegation rule is `ask` -> `decision: "ask"`, `reason: "delegation_ask"`.
       - Complex question (complaints, discounts/negotiations, booking enquiries, mixed topics) -> `decision: "ask"`, `reason: <reason_code>` (e.g. `complex_topic_complaint`, `booking_enquiry_requires_approval`, `complex_discount_or_negotiation`, `mixed_topics`).
       - Prohibited input (prompt injections, abusive language) -> `decision: "blocked"`, `reason: "injection_suspected"` or `"escalation_abusive"`.
     - **Draft Text Generation:** Produced using the same verified facts and approved answers as production.

3. **Strict Sandbox Effect Boundary (INV-01, INV-05, INV-15):**
   - Guaranteed that dry-run turns write strictly to `assistant_test_turns`.
   - Zero writes to:
     - `conversations`
     - `messages`
     - `reply_drafts`
     - `approvals`
     - `operations`
     - `notifications` / `notification_deliveries`
     - `customer_memories`
     - `calendar_appointments`
     - `external_events` / social account operations
   - Test chat does NOT contaminate reporting metrics or lead lists (INV-08).
   - In-memory simulation of booking and content tools prevents remote provider mutations.

4. **Schema & Models Synchronization (`backend/app/inbox/schemas.py`, `backend/app/inbox/models.py`, `frontend/src/api/schema.d.ts`):**
   - Synchronized `schemas.py` and `sandbox_router.py` models for test chat:
     - `AssistantChatMessageIn`, `FactUsedOut`, `AssistantChatDraftOut`, `AssistantChatTurnOut`, `AssistantChatOut`, `AssistantChatResetOut`.
     - Added `decision: Literal["auto", "approval_required", "human_required", "blocked", "automatic", "ask"]`.
     - Added `controller_mode: Literal["legacy", "agent"]` to `AssistantChatOut` and `AssistantChatTurnOut`.
   - Updated `DRAFT_DECISIONS` in `backend/app/inbox/models.py` to support `"automatic"` and `"ask"`.

5. **Frontend Test Chat UI & Localization (`frontend/src/features/test-chat/`):**
   - Created `ControllerBadge`:
     - Displays `Account Agent` (`testChat.controller.agent`) or `Standard Assistant` (`testChat.controller.legacy`) beside the `SimulatedBadge` in reply cards and intro banner.
   - Created `DecisionBadge`:
     - Displays `Auto-Send` (`testChat.badge.autoSend`), `Needs Approval` (`testChat.badge.needsApproval`), or `Blocked` (`testChat.badge.blocked`).
   - Integrated `DecisionBadge` into `DecisionNote`, showing plain-language reason sentences for every policy reason code.
   - Preserved `FactsUsed` displaying verified facts and source lines.
   - Added Turkish and English localization in `testChat.json` with 0 missing translations.

---

## 2. Files and Migrations Changed

### Files Created:
- `backend/tests/unit/inbox/test_sandbox_agent_unit.py` (20 offline unit tests)
- `docs/implementation/account-agent-pilot-readiness/s07-report.md`

### Files Modified:
- `backend/app/agent/policy.py`
- `backend/app/inbox/models.py`
- `backend/app/inbox/sandbox.py`
- `backend/app/inbox/sandbox_router.py`
- `backend/app/inbox/schemas.py`
- `frontend/src/api/schema.d.ts`
- `frontend/src/features/test-chat/TestChat.tsx`
- `frontend/src/features/test-chat/testChat.test.tsx`
- `frontend/src/i18n/locales/en/testChat.json`
- `frontend/src/i18n/locales/tr/testChat.json`

### Migration Revision:
- None required (operates within existing `assistant_test_turns` table schema).

---

## 3. Checks Actually Executed and Their Results

### Backend Checks:
1. **Linter & Formatting:**
   - `backend\.venv\Scripts\ruff.exe check backend/app backend/tests` -> **PASS** (All checks passed!)
   - `backend\.venv\Scripts\ruff.exe format --check backend/app backend/tests` -> **PASS** (902 files already formatted)
2. **Type Checking:**
   - `cd backend; .venv\Scripts\mypy.exe app` -> **PASS** (Success: no issues found in 465 source files)
3. **Architecture Import Linter:**
   - `cd backend; .venv\Scripts\lint-imports.exe` -> **PASS** (Contracts: 27 kept, 0 broken)
4. **Offline Unit Test Suite:**
   - `backend\.venv\Scripts\pytest.exe backend/tests/unit/inbox/test_sandbox_agent_unit.py -v` -> **PASS** (20 passed in 0.24s)
     - Covers controller mode detection (agent active vs legacy/paused/inactive/disconnected).
     - Covers truthful agent decisions (basic auto-send vs ask delegation).
     - Covers complex enquiries (complaints, discounts, booking, mixed).
     - Covers prohibited inputs (injections, abuse).
     - Covers 5 languages (TR, EN, RU, DE, AR) and unsupported fail-closed.
     - Covers grounding failure fail-closed.
     - Covers sandbox effect boundary (0 rows in production tables).
     - Covers rate limits and reset isolation.

### Frontend Checks:
1. **Type Checking:**
   - `cd frontend; npm.cmd run typecheck` -> **PASS** (0 errors)
2. **Linter:**
   - `cd frontend; npm.cmd run lint` -> **PASS** (0 errors)
3. **i18n Coverage Check:**
   - `cd frontend; npm.cmd run i18n:check` -> **PASS** (en, tr | 3023 keys | 2136 literal t() calls verified)
4. **Vitest Suite:**
   - `cd frontend; npm.cmd test -- --run src/features/test-chat/testChat.test.tsx` -> **PASS** (18 passed in 10.64s)
     - Covers controller badge rendering (Account Agent vs Standard Assistant).
     - Covers decision badge rendering (Auto-Send, Needs Approval, Blocked).
     - Covers Turkish and English localization.

---

## 4. Acceptance Criteria Satisfied

1. **Controller Detection:** The practice chat detects the workspace's active AccountAgent and selects Agent dry-run mode or Legacy mode truthfully.
2. **Reuse of Production Logic:** Agent dry-run mode reuses production language selection (5 languages), grounding checks, and semi-automation reply policy matrix.
3. **Truthful Decisions:** Resolves `automatic` for basic verified queries under automatic delegation, `ask` for complex/mixed/discount/booking topics, and `blocked` for prohibited inputs.
4. **Sandbox Boundary:** Proven 0 side-effecting operations or writes to `conversations`, `messages`, `reply_drafts`, `approvals`, `operations`, `notifications`, `customer_memories`, `calendar_appointments`.
5. **No Metric Contamination:** Test chat runs do not contaminate reporting metrics or lead lists.
6. **UI & Badging:** Frontend displays controller mode badge, decision badge, verified facts, and plain-language explanation reasons in Turkish and English with 0 missing translations.

---

## 5. Remaining Failures, External Dependencies, and Unresolved Decisions

1. **External Database Dependency in Full Regression:**
   - As documented in prior session reports (`s00` through `s06`), integration tests that target local PostgreSQL on port 5433 require a running database container; all unit and isolation test suites execute offline and pass cleanly.
2. **Next Steps (Session 08):**
   - Conduct combined end-to-end acceptance across all six pilot feature areas (DMs, publishing, comments, voice notes, bookings, lead lists) under the Account Agent controller mode with fake LLM and mock Instagram providers.
