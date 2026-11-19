# Session 08 Report — Verify All Requested Features Together on Account Agent Accounts

- **Date:** 2026-11-19 (Europe/Istanbul)
- **Plan:** [Account Agent Pilot Readiness](../../../answeres2.md) — Session 08
- **Local Git Baseline:** branch `main`, commit `e1c9f1367f63ed4afcd7e78b075c48a61c408fd8` (`e1c9f13`) + Sessions 01 through 07 work
- **Alembic Migration Head:** `0101` (`20261119_0101_channel_preferences.py`, parent `0100`)

---

## 1. Changes Made and Why

1. **Dedicated Combined Offline Acceptance Suite (`backend/tests/unit/agent/test_account_agent_pilot_acceptance_unit.py`):**
   - Authoring a comprehensive, offline acceptance test suite exercising all 6 required pilot feature areas together on Account Agent accounts using real broker, policy, executor, grounding, claim validation, and operations ledger paths without relying on an external PostgreSQL service (INV-01 through INV-20).
   - Designed 35 focused acceptance tests across 9 feature areas:
     - **Feature Area 1 — DMs & Semi-Automation Policy Matrix (INV-02, INV-04, INV-16):**
       - Basic verified FAQ (greetings, business hours, location/contact, services, standard verified pricing with price disclosure allowed) auto-sends under owner automatic grant (`decision="automatic"`).
       - Basic FAQ without automatic grant stays `ask` (never auto-sends without explicit owner grant).
       - Complex / mixed questions (hours + pricing), discounts/negotiations, custom quotes require human approval (`decision="ask"`).
       - Escalations (complaints, refund requests) and prompt injections fail closed (`decision="blocked"`).
       - Single customer effect via write-ahead operation ledger and idempotency key (INV-05, INV-06).
     - **Feature Area 2 — Comments & Comment-to-DM (INV-03, INV-04, INV-11):**
       - Public comment replies respect price disclosure (`price_disclosure_forbidden_in_public` blocks public price quotes).
       - Comment-to-DM one-shot private reply works safely; subsequent private reply attempts are refused (`PRIVATE_REPLY_COMMENT_ALREADY_USED`).
     - **Feature Area 3 — Voice Notes & Image Descriptions (INV-02, INV-03, INV-04):**
       - Inbound voice note transcript wakes the Agent via `message.transcript_ready` and enforces the transcript approval floor (`require_human=True` / `decision="ask"`, reason `"voice_transcript_requires_approval"`).
       - Image descriptions provide untrusted customer context without hallucinating business facts; prompt injections in image descriptions are blocked (`is_blocked=True`).
       - Completed image descriptions wake the Agent via `message.image_described`.
     - **Feature Area 4 — Bookings & Calendar Operations (INV-04, INV-05, INV-16):**
       - Availability check validation (`CalendarAvailabilityArgs`).
       - Booking, rescheduling, and cancellation follow configured delegation authority and pilot safety rules (`"pilot_mutation_requires_approval"`).
       - `CalendarAppointment` records verified provider outcomes (`confirmed`, `rescheduled`, `cancelled`); replayed booking calls are idempotent.
     - **Feature Area 5 — Leads & Lead List Qualifying / Conversion (INV-08, INV-17):**
       - Agent pricing and booking-only enquiries are classified as qualifying leads (`intent="pricing"` or `"booking"`).
       - Conversion requires an eligible confirmed linked appointment (`status="scheduled"` or `"completed"` created after first enquiry); pending approval, uncertain outcomes, and cancelled appointments do NOT convert.
       - CSV export sanitizes formula injection characters (`=`, `+`, `-`, `@`, `\t`, `\r`) and enforces 300-character length caps.
     - **Feature Area 6 — Publishing Pipeline & Idempotency (INV-05, INV-06, INV-11, INV-15, INV-16):**
       - Verified broker registration of content tools (`content.read`, `content.prepare`, `content.schedule`, `content.publish`, `content.cancel`, `task.clarify`).
       - Domain support for Feed image, Story image, feed carousel, and Reel content types.
       - Approvals bound to subject version and payload hash (INV-16); changing payload invalidates unexecuted approvals.
     - **Feature Area 7 — Knowledge Import, Verification & Fact-Change Invalidation (INV-02, INV-16):**
       - Instagram/website fact import produces candidates (`status="pending"`, `relation="new"`).
       - Candidates remain unusable until owner acceptance verifies the fact.
       - Fact price changes invalidate unexecuted reply drafts (`ReplyDraftReferrers`) and place affected scheduled content on hold (`ContentItemReferrers`, `on_hold`, `FACT_CHANGED`).
     - **Feature Area 8 — Multilingual, Arabic Layouts, UI Languages & Role Permissions:**
       - Full support for 5 customer reply languages (`tr`, `en`, `ru`, `de`, `ar`); unsupported languages fail closed to human approval.
       - Arabic RTL text handling respects the 1000-byte constraint and preserves characters.
       - Strict role permission boundaries: Owner has full delegation and approval authority; Manager approves content and replies but cannot manage agent delegation; Staff can draft and edit but cannot approve or publish.
     - **Feature Area 9 — Operational Resilience & Edge Cases (INV-05, INV-06, INV-07, INV-13, INV-16):**
       - Native Instagram app outbound echoes trigger human takeover (`takeover_thread`, `handling_mode="human"`).
       - Duplicate webhooks deduplicated via `inbound_events.dedup_key`.
       - Expired approvals cannot be decided or executed.
       - Quota exhaustion pauses the agent (`quota_paused`).
       - Follow-ups are confirmed disabled by default on pilot accounts (`follow_up_enabled == False`) with strict approval floor (`FOLLOW_UP_REQUIRES_APPROVAL`).
       - Human Agent tag replies remain human-written within permitted windows (24h standard, up to 7 days for Human Agent tag).

2. **Frontend Wizard Test Adjustment (`frontend/src/features/workspaces/wizard.test.tsx`):**
   - Updated assertion in `wizard.test.tsx` from `screen.getByTestId("simulated-badge")` to `screen.getAllByTestId("simulated-badge")[0]` to accommodate the new controller simulation badge introduced on the test chat intro card in Session 07 without regressions.

---

## 2. Files and Migrations Changed

### Files Created:
- `backend/tests/unit/agent/test_account_agent_pilot_acceptance_unit.py` (35 combined acceptance tests)
- `docs/implementation/account-agent-pilot-readiness/s08-report.md`

### Files Modified:
- `frontend/src/features/workspaces/wizard.test.tsx`

### Migration Revision:
- None required (exercises existing schemas and models).

---

## 3. Checks Actually Executed and Their Results

### Backend Checks:
1. **Linter & Formatting:**
   - `backend\.venv\Scripts\ruff.exe check backend/app backend/tests` -> **PASS** (All checks passed!)
   - `backend\.venv\Scripts\ruff.exe format --check backend/app backend/tests` -> **PASS** (903 files already formatted)
2. **Type Checking:**
   - `cd backend; .venv\Scripts\mypy.exe app` -> **PASS** (Success: no issues found in 465 source files)
3. **Architecture Import Linter:**
   - `cd backend; .venv\Scripts\lint-imports.exe` -> **PASS** (Contracts: 27 kept, 0 broken)
4. **Acceptance Test Suite:**
   - `backend\.venv\Scripts\pytest.exe backend/tests/unit/agent/test_account_agent_pilot_acceptance_unit.py -v` -> **PASS** (35 passed in 0.30s)
5. **Full Agent Unit Test Suite:**
   - `backend\.venv\Scripts\pytest.exe backend/tests/unit/agent/ -v` -> **PASS** (228 passed in 0.75s)

### Frontend Checks:
1. **Linter:**
   - `cd frontend; npm.cmd run lint` -> **PASS** (0 errors)
2. **Type Checking:**
   - `cd frontend; npm.cmd run typecheck` -> **PASS** (0 errors)
3. **i18n Coverage Check:**
   - `cd frontend; npm.cmd run i18n:check` -> **PASS** (en, tr | 3023 keys | 2136 literal t() calls verified)
4. **Vitest Test Suite:**
   - `cd frontend; npm.cmd test -- --run` -> **PASS** (69 test files passed, 977 tests passed in 95.40s)

---

## 4. Acceptance Criteria Satisfied

1. **Combined Offline Acceptance:** Comprehensive acceptance suite `test_account_agent_pilot_acceptance_unit.py` authored and passing 100% offline with zero external database container dependencies.
2. **All 6 Pilot Features Covered on Account Agent:**
   - DMs (basic auto-send vs complex approval vs blocked escalations).
   - Comments & Comment-to-DM (price disclosure rules and one-shot private replies).
   - Voice Notes & Image Descriptions (transcript approval floor, untrusted media context, and injection blocking).
   - Bookings & Calendar Operations (availability checks, delegation authority, verified outcomes, idempotency).
   - Leads & Lead List (pricing and booking-only qualifying enquiries, evidenced appointment conversion, CSV sanitization).
   - Publishing (Feed, Story, Carousel, Reel, payload-hash binding, fact holds).
3. **Fact Import, Verification & Change Lifecycle:** Proved that imported facts start as unusable candidates, owner verification makes them usable, and price changes invalidate drafts and hold scheduled content.
4. **Multilingual & UI Integrity:** Proved 5-language customer replies, Arabic layout safety, TR/EN UI constraint, and owner/manager/staff RBAC permissions.
5. **Operational Resilience:** Proved native-app echo takeover, duplicate webhook deduplication, expired approval protection, quota pauses, and disabled-by-default follow-ups.

---

## 5. Remaining Failures, External Dependencies, and Unresolved Decisions

1. **External PostgreSQL Container Requirement for Live DB Integration Tests:**
   - As documented in prior session reports (`s00` through `s07`), integration tests that target local PostgreSQL on port 5433 require an active database container; all unit, acceptance, and isolation test suites execute offline and pass cleanly.
2. **Next Steps (Session 09):**
   - Align assisted onboarding runbook, pilot terms (trial duration, founder package terms), and persisted metric measurements with the owner answers and pricing strategy document.
