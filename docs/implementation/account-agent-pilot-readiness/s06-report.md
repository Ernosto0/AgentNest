# Session 06 Report — Close Booking and Lead-List Coverage Gaps

- **Date:** 2026-11-19 (Europe/Istanbul)
- **Plan:** [Account Agent Pilot Readiness](../../../answeres2.md) — Session 06
- **Local Git Baseline:** branch `main`, commit `e1c9f1367f63ed4afcd7e78b075c48a61c408fd8` (`e1c9f13`) + Sessions 01 through 05 work
- **Alembic Migration Head:** `0101` (`20261119_0101_channel_preferences.py`, parent `0100`)

---

## 1. Changes Made and Why

1. **Booking Trace Audit & Appointment Field Propagation (`backend/app/agent/calendar.py`, `backend/app/operations/calendar.py`):**
   - Audited the full Account Agent booking trace:
     `booking enquiry → availability → proposed booking → approval → verified calendar result → customer confirmation`.
   - In `backend/app/agent/calendar.py`:
     - Ensures customer identity is resolved and bound when booking from direct messages: if `thread.customer_identity_id` is missing, `resolve_identity(db, clock, thread)` safely creates/loads the deterministic participant identity without inventing arbitrary client references.
     - Enriches `content_intent` with `conversation_id`, `customer_identity_id`, `timezone`, `message_id`, and `intent="booking"`.
     - In `modify()`, ensures reschedule intents record `conversation_id`, `customer_identity_id`, `timezone`, and `intent="booking"`.
   - In `backend/app/operations/calendar.py` (`_prepare`):
     - When constructing `CalendarAppointment`, extracts `conversation_id` and `customer_identity_id` from `intent_payload`, with fallback to the active `AgentThread` (`thr.dm_conversation_id`, `thr.customer_identity_id`).
     - Stores `timezone`, `workspace_id`, `status="scheduled"`, and `version=1`.
     - Reuses existing appointment if `action.payload_ref` exists, preventing duplicate DB appointment rows across retries.

2. **Booking Call Idempotency and Provider Fencing (INV-05, INV-06):**
   - Replayed broker calls to `calendar.book`:
     - `admit_action` checks semantic slot and content intent. If already admitted, returns existing action result immediately without creating duplicate actions or appointments.
   - Replayed worker executions in `operations/calendar.py`:
     - Checks `Operation.idempotency_key == f"calendar_create_event:{action.id}"`.
     - If operation already exists and is terminal (`succeeded`, `failed`, `cancelled`), updates `action.status = op.status` and returns `None`.
     - If operation is `in_progress` or `outcome_unknown`, transitions interrupted runs and enqueues reconciliation.
     - Provider calls receive `operation_key = op.idempotency_key`, ensuring remote calendar providers (Google and Mock) deduplicate creations idempotently.

3. **Closed Lead-List Coverage Gap for Account Agent Conversations (`backend/app/reporting/leads.py`, `backend/app/agent/dm.py`):**
   - **Problem:**
     - Previously, `lead_rows` only qualified conversations via:
       `or_(ReplyDraft.intent.in_(LEAD_INTENTS), (ReplyDraft.origin == "agent") & agent_price)`.
     - On the Account Agent path, `ReplyDraft.intent` was `None`, leaving booking-only enquiries that quote no prices (or check availability, or server-rendered calendar replies) uncaptured.
     - Furthermore, abandoned or failed booking attempts where no `ReplyDraft` was created never appeared on the call-back lead list.
   - **Solution:**
     - In `backend/app/agent/dm.py`:
       - Implemented `determine_draft_intent(db, proposal, newest)`.
       - When `proposal.calendar_evidence` is present (booked, rescheduled, cancelled, pending_approval, available_slot), sets `draft.intent = "booking"`.
       - When pricing facts or price policy templates are used, sets `draft.intent = "pricing"`.
       - Evaluates inbound customer text across supported languages using `detect_inbound_topics(newest.text)`: detects `Topic.BOOKING_MUTATION` (`"booking"`) and `Topic.PRICING` (`"pricing"`).
       - Persists `draft.intent` directly on `ReplyDraft`, enabling all draft-covered Agent enquiries to qualify immediately.
     - In `backend/app/reporting/leads.py`:
       - Added `action_pairs` CTE to `lead_rows`.
       - Selects real inbound messages associated with booking `AgentAction`s (`action_type.in_(("calendar.book", "calendar.reschedule"))`) on the conversation, linked either through `AgentEvent` (`source_kind == "message"`, `message_transcript`, `message_image_description`) or by conversation timeline.
       - Combines draft-covered and action-evidenced qualifying questions via `draft_pairs.union(action_pairs).cte("qualifying_questions")`.
       - Booking-only enquiries now appear before conversion.
       - Abandoned or failed booking proposals with persisted action evidence appear on the call-back lead list.
       - When both pricing and booking intents are present, `"booking"` is prioritized for display per `workflows.md` §F.3.

4. **Strict Reporting Invariants & Conversion Rules (INV-08, INV-09, INV-19):**
   - Enforced that enquiry classification is reporting evidence, never proof of a sale or appointment.
   - Conversion is counted **ONLY** from an eligible linked appointment:
     - `CalendarAppointment.workspace_id == ctx.workspace_id`
     - `CalendarAppointment.conversation_id == first.c.conversation_id`
     - `CalendarAppointment.status != "cancelled"`
     - `CalendarAppointment.created_at >= first.c.first_at`
     - Unconfirmed operations check:
       `~exists(Operation with operation_type == 'calendar_create_event' and status != 'succeeded')`.
     - Unconfirmed agent booking check:
       `~exists(AgentAction with action_type == 'calendar.book' and status != 'succeeded')`.
   - Results:
     - Pending approval (`waiting_approval`) does **NOT** convert the lead.
     - Failed calendar operation (`failed`) does **NOT** convert the lead.
     - Uncertain provider outcome (`outcome_unknown`) does **NOT** convert the lead before reconciliation confirms creation.
     - Confirmed linked appointment (`succeeded` / `scheduled`) **DOES** convert and removes the lead from the call-back list (`~converted`).
     - Appointment cancellation sets `status = "cancelled"` and un-converts the lead, returning it to the call-back list.
   - Preserved CSV formula protection (`=`, `+`, `-`, `@`, `\t`, `\r`), export auditing (`leads.exported`), row cap (5000 / 500 rows), and workspace timezone conversions.

5. **Multilingual Regex Enhancements (`backend/app/agent/policy.py`):**
   - In `Topic.PRICING`: expanded Russian pattern to `сколько сто[ия]т\w*` to match both singular ("сколько стоит") and plural ("сколько стоят").
   - In `Topic.BOOKING_MUTATION`: added English `schedule\w*` and Russian `забронир\w*` / `бронир\w*` to match "schedule a session" and "забронировать время".

---

## 2. Files and Migrations Changed

### Files Created:
- `backend/tests/unit/reporting/test_leads_agent_unit.py` (32 comprehensive offline unit tests)
- `docs/implementation/account-agent-pilot-readiness/s06-report.md`

### Files Modified:
- `backend/app/agent/calendar.py`
- `backend/app/agent/dm.py`
- `backend/app/agent/policy.py`
- `backend/app/operations/calendar.py`
- `backend/app/reporting/leads.py`

### Migration Revision:
- None required (existing tables `calendar_appointments`, `agent_actions`, `agent_events`, `agent_threads`, `reply_drafts`, and `operations` already contain all necessary columns, indexes, and foreign keys).

---

## 3. Checks Actually Executed and Their Results

1. **Dedicated Offline Unit Test Suite:**
   ```bash
   cd backend; .venv\Scripts\pytest.exe tests/unit/reporting/test_leads_agent_unit.py -q
   ```
   - **Result:** `32 passed in 0.37s`
   - Tests:
     - Account Agent booking enquiry appears as `booking` lead.
     - Account Agent pricing enquiry without pricing facts appears as `pricing` lead.
     - Booking-only enquiry that quotes no prices appears as a lead.
     - Confirmed linked appointment removes the lead from call-back list.
     - Pending approval does NOT remove the lead.
     - Failed calendar operation does NOT remove the lead.
     - Uncertain provider outcome (`outcome_unknown`) does NOT remove the lead.
     - Cancelled appointment leaves the lead on the list.
     - Abandoned booking proposals appear on the call-back list.
     - Replayed booking calls are idempotent.
     - CSV export formula escaping, length caps, and row caps.
     - Multilingual intent extraction across TR, EN, RU, DE, AR.

2. **Combined Offline Reporting, Agent, and Policy Test Suite:**
   ```bash
   cd backend; .venv\Scripts\pytest.exe tests/unit/reporting tests/unit/agent/test_agent_policy_matrix_unit.py tests/unit/agent/test_agent_media_unit.py tests/unit/policy -q
   ```
   - **Result:** `360 passed in 0.75s`.

3. **Ruff Linter & Formatter:**
   ```bash
   cd backend; .venv\Scripts\ruff.exe check app tests
   cd backend; .venv\Scripts\ruff.exe format --check app tests
   ```
   - **Result:** `All checks passed! 901 files already formatted`.

4. **MyPy Type Checker:**
   ```bash
   cd backend; .venv\Scripts\mypy.exe app
   ```
   - **Result:** `Success: no issues found in 465 source files`.

5. **Import Linter Architecture Enforcement:**
   ```bash
   cd backend; .venv\Scripts\lint-imports.exe
   ```
   - **Result:** `Contracts: 27 kept, 0 broken`.

6. **Frontend Verification (Linter, Typecheck, i18n):**
   ```bash
   cd frontend; npm.cmd run lint
   cd frontend; npm.cmd run typecheck
   cd frontend; npm.cmd run i18n:check
   ```
   - **Result:** All passed with 0 errors (`i18n check passed: en, tr | 2996 keys | 2134 literal t() calls verified`).

---

## 4. Acceptance Criteria Satisfied

- [x] **Booking trace audit:** Account Agent booking path in `agent/calendar.py` and `operations/calendar.py` correctly populates `conversation_id`, `customer_identity_id`, `timezone`, and `workspace_id`.
- [x] **Idempotency:** Replayed booking calls reuse existing `AgentAction` and `Operation`, preventing duplicate appointment rows or duplicate external provider calls.
- [x] **Lead-list coverage closed:**
  - Booking enquiries covered by Account Agent drafts qualify as `"booking"`.
  - Pricing enquiries covered by Account Agent drafts (with or without pricing facts) qualify as `"pricing"`.
  - Booking-only enquiries appear on the lead list before conversion.
  - Abandoned or failed booking proposals with persisted enquiry evidence (`calendar.book` action) appear on the call-back lead list.
- [x] **Conversion precision (INV-08, INV-19):**
  - Confirmed linked appointment (`status="scheduled"`, `Operation.status="succeeded"`, `created_at >= first_at`) removes the lead.
  - Pending approval or failed provider call does NOT remove the lead.
  - Uncertain provider outcome (`outcome_unknown`) does NOT remove the lead before reconciliation.
  - Cancelled appointment leaves the lead on the list / un-converts.
- [x] **Security & CSV protections:** In-memory CSV formula escaping (`=`, `+`, `-`, `@`, `\t`, `\r`), export auditing, row caps (5000 max), and timezone boundaries preserved.

---

## 5. Remaining Failures, External Dependencies, and Unresolved Decisions

- **Docker daemon dependency for integration suites:** Running integration test suites with `pytestmark = pytest.mark.commits` (such as `test_leads.py` and `test_calendar_agent.py`) requires a running local Docker engine hosting PostgreSQL 16 on port 5433. All offline unit test suites (`test_leads_agent_unit.py`, `test_leads_csv.py`, `test_periods.py`, `test_summary.py`, `test_agent_policy_matrix_unit.py`, `test_agent_media_unit.py`) run entirely offline and pass 100%.
- **Live Google Calendar API check:** Deferred to live pilot execution; offline mock calendar provider and fake LLM tests verify the complete ledger and broker contract.
