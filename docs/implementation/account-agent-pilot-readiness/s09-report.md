# Session 09 Report — Align Assisted Onboarding, Pilot Terms and Measurement

- **Date:** 2026-11-19 (Europe/Istanbul)
- **Plan:** [Account Agent Pilot Readiness](../../../answeres2.md) — Session 09
- **Local Git Baseline:** branch `main`, commit `e1c9f1367f63ed4afcd7e78b075c48a61c408fd8` (`e1c9f13`) + Sessions 01 through 08 work
- **Alembic Migration Head:** `0101` (`20261119_0101_channel_preferences.py`, parent `0100`)

---

## 1. Changes Made and Why

1. **Updated Assisted Onboarding Runbook (`docs/operations/pilot-onboarding-checklist.md`):**
   - **Target Alignment:** Re-aligned the runbook for the owner's target of onboarding **10–15 local businesses within a week** (Pilates studios, gyms, beauty salons, wellness clinics).
   - **Account Agent Activation:** Upgraded from legacy topic-based automation policies to explicit **Account Agent activation**:
     - Activating Account Agent mode (`POST /api/v1/workspaces/{ws}/accounts/{account_id}/agent/activate` with `mode="agent"`).
     - UI workflow: Owner navigates to **Daha fazla -> Asistan**, taps **Hesap asistanını etkinleştir**, and confirms the controller cutover dialog.
   - **Semi-Automation Delegation Configuration:**
     - Owner configures action delegation (`dm.send`, `comment.reply`, `comment.private_reply`) to `automatic` or `ask` under **Daha fazla -> Asistan -> Yetkilendirme**.
     - Documented the deterministic semi-automation policy matrix: basic verified FAQ questions (standard greetings, business hours, studio/clinic location, services, standard verified prices when disclosure is allowed) auto-send with a policy grant. Complex questions (custom quotes, discounts, complaints, appointments, voice notes) strictly require human approval (`ask`). Prompt injections and legal/medical claims fail closed (`blocked`).
     - Clarified invariant INV-04: Topic policy rules can only restrict an action grant; they can never broaden it.
   - **Explicit Channel Choice (Session 02):**
     - Prioritized **Telegram** as the primary day-one channel for instant alerts and interactive `act:<token>` approval buttons on owner mobile devices.
     - Documented **WhatsApp** and **App-Only** as explicit first-class alternatives without forcing Telegram.
     - Documented **Web Push** as a device-level browser opt-in.
   - **Multilingual Customer Reply Setup:**
     - Documented support for **5 customer reply languages** (`tr`, `en`, `ru`, `de`, `ar`), including automatic language detection, localized fact placeholders, localized calendar confirmations, and Arabic RTL formatting within 1000-byte platform limits.
     - Clarified that the **app UI remains strictly bilingual in Turkish and English (`tr` and `en`)**.
   - **Structured Credentials-Free Onboarding Record Template (§8):**
     - Authored a clean, repeatable markdown template capturing: Workspace ID, business name, category, location, public contact phone, Instagram handle.
     - Verified facts inventory checklist (hours, services, pricing, cancellation policy, booking instructions).
     - Customer reply languages enabled (`tr`, `en`, `ru`, `de`, `ar`).
     - Selected notification channels (Telegram chat ID / WhatsApp number / App-only, plus Web Push opt-in).
     - Agreed trial period: captures either 7 days or 30 days as agreed with the owner.
     - Agreed post-trial package: Kurucu İşletme Paketi (Founder Package) at **990 TRY/month + KDV** (locked for 12 months).
     - Manual billing agreement (bank transfer / EFT invoice via E-Arşiv / Paraşüt; static payment link; explicitly confirming no credit card required and no automated charges at trial end).
     - Assigned operator and dated acceptance sign-off.
   - **Persisted Metric Measurements for Pilot Success (§9):**
     - Formulated exact SQL reporting queries against persisted database records (INV-08):
       - **First-response time:** `messages.provider_timestamp` of inbound message to first outbound reply `messages.provider_timestamp` or `operations.created_at`.
       - **Reply & Approval Workload:** `agent_actions` auto-sent count (`policy_grant IS NOT NULL AND approval_id IS NULL`) vs approval-requested count (`approval_id IS NOT NULL`), and `approvals` status breakdown (`approved`, `rejected`, `expired`).
       - **Linked Appointments & Conversions:** `calendar_appointments` with `conversation_id IS NOT NULL` and `status != 'cancelled'`.
       - **Failures & Unknown Outcomes:** `operations` and `notification_deliveries` with `status IN ('failed', 'outcome_unknown', 'undeliverable')`.
     - Explicitly separated computed system metrics from owner-reported qualitative feedback (e.g. owner-reported time saved, subjective stress reduction).
     - Clarified that the 5% missed-customer revenue estimate is explicitly illustrative modeling, never counted as actual earned revenue.
     - Documented that numeric success targets and review periods are tracked collaboratively with each business owner before formal evaluation.

2. **Reconciled Pricing Claims & Unit Economics (`docs/product/pricing-and-unit-economics.md`):**
   - **Header Callout & Status:** Updated the document header to reflect code status following Feature Phases 1–5 and Pilot Readiness Sessions 01–08.
   - **Assisted Pilot Terms (§3.1):** Recorded the agreed terms for the 10–15 pilot businesses:
     - 7-day or 30-day free trial (0 TRY, no credit card required, no automated charges at trial end).
     - Followed by Founder Package at **990 TRY/month + KDV** locked for 12 months.
     - Manual billing via bank transfer / EFT (*E-Arşiv Fatura* via GİB portal or Paraşüt) or static link.
     - Clarified that plan period extension (`plan-extend`) via CLI is operational quota and period management, not payment enforcement or automated subscription renewal.
   - **Reconciled Feature Matrix (§3.2 & §4):**
     - Comment automation: Private replies via Comment-to-DM marked delivered on real accounts with `instagram_business_manage_comments` permission.
     - Owner control channels: Mobile Web + Telegram (primary) + WhatsApp (delivered, optional).
     - Reply languages: 5 customer reply languages (`tr`, `en`, `ru`, `de`, `ar`) marked delivered; UI strictly `tr` and `en`.
     - Autonomous Account Agent: Delivered with semi-automation policy.
     - Scheduled Posts & Stories + Template images + Carousels & Reels: Marked delivered.
     - Lead list: Marked delivered.
   - **Reconciled P-19 Feature Status Check (§8):**
     - Updated the P-19 table across all 12 feature lines, recording code evidence and delivered status for WhatsApp owner channel, 5 reply languages, Comment-to-DM, template images, lead list, carousels & reels, voice notes & image descriptions, and test chat Account Agent parity.
     - Reconciled commercial boundaries: billing is strictly manual; CLI `plan-extend` is not payment enforcement; WhatsApp is not compulsory.

3. **Roadmap Status Sync (`docs/implementation/roadmap.md`):**
   - Added an entry under Feature Phases for the Account Agent Pilot Readiness track, reflecting completion of Sessions 00 through 09 and migration head `0101`.

---

## 2. Files and Migrations Changed

### Files Created:
- `docs/implementation/account-agent-pilot-readiness/s09-report.md`

### Files Modified:
- `docs/operations/pilot-onboarding-checklist.md` (Comprehensively updated for 10-15 pilot target, Account Agent activation, semi-automation delegation, channel choice, 5 languages, onboarding record template, and SQL-persisted metric measurements)
- `docs/product/pricing-and-unit-economics.md` (Reconciled pilot terms: 7/30 days trial, 990 TRY founder package, manual billing, and updated P-19 feature inventory with delivered capabilities)
- `docs/implementation/roadmap.md` (Added Account Agent Pilot Readiness progress entry)

### Migration Revision:
- None required (documentation and operational runbook alignment).

---

## 3. Checks Actually Executed and Their Results

### Backend Checks:
1. **Linter & Formatting:**
   - `backend\.venv\Scripts\ruff.exe check backend/app backend/tests` -> **PASS** (All checks passed!)
   - `backend\.venv\Scripts\ruff.exe format --check backend/app backend/tests` -> **PASS** (903 files already formatted)
2. **Acceptance Test Suite Regression:**
   - `backend\.venv\Scripts\pytest.exe backend/tests/unit/agent/test_account_agent_pilot_acceptance_unit.py -v` -> **PASS** (35 passed in 0.26s)

---

## 4. Acceptance Criteria Satisfied

- [x] **10–15 Local Business Target:** Runbook is tailored specifically for the assisted onboarding of 10–15 local businesses within a week.
- [x] **Account Agent Mode & Semi-Automation Delegation:** Runbook replaces legacy topic policies with explicit `POST /agent/activate` (`mode="agent"`) and delegation configuration (`dm.send`, `comment.reply`, `comment.private_reply`). Semi-automation policy matrix explains basic auto-sends vs complex approval requirements.
- [x] **Channel Choice:** Prioritizes Telegram delivery for day-one alerts and `act:<token>` buttons on owner phones; provides WhatsApp and App-Only as explicit first-class alternatives without forcing Telegram; explains Web Push device opt-in.
- [x] **Multilingual Setup:** Explains customer-facing support for 5 languages (`tr`, `en`, `ru`, `de`, `ar`) while keeping the app UI strictly in Turkish and English (`tr` and `en`).
- [x] **Structured Credentials-Free Onboarding Record Template:** Authored template in §8 covering business info, verified facts checklist, enabled languages, selected channels, agreed trial (7 or 30 days), post-trial Founder Package (990 TRY + KDV, locked for 12 months, manual billing, no automated charge), operator and owner sign-off.
- [x] **Reconciled Pricing Claims & Unit Economics:** Section 3.1 records agreed trial options and founder package; Section 8 reconciles all delivered functionality from Feature Phases 1–5 and Sessions 01–08 (WhatsApp, 5 languages, comment-to-DM, template images, lead list, carousels/reels, voice notes & image descriptions, test chat parity).
- [x] **Commercial Boundaries:** Kept billing manual; documented that CLI `plan-extend` is operational quota tracking, not automated payment enforcement; clarified WhatsApp is not compulsory.
- [x] **Persisted Metric Measurements for Pilot Success:** Provided exact SQL queries from persisted database tables for first-response time, reply/approval workload, linked appointments/conversions, and failures/unknown outcomes (INV-08).
- [x] **Qualitative vs Quantitative Separation:** Separated computed SQL system metrics from owner-reported feedback (time saved); stated that the 5% revenue estimate is illustrative only; documented that numeric success targets and review periods are tracked with the owner.
- [x] **No Unverified Claims or Invented Billing:** Ensured all commands, schemas, and operational instructions match real code and invariants.

---

## 5. Remaining Failures, External Dependencies and Unresolved Decisions

1. **Owner-Specific Trial Duration Choice:** The onboarding record supports both 7-day and 30-day options; the operator selects and records the specific choice agreed with each business owner during their onboarding session.
2. **Numeric Success Thresholds:** The SQL measurement framework is delivered; exact numeric targets (e.g. median first-response time under 2 minutes, > 80% coverage) and review periods are tracked with each owner before formal pilot evaluation.
3. **Live Environment Prerequisites (for Session 11):**
   - Meta App Review for general public access (pilots use Instagram Tester invitations until review is complete).
   - Live Meta WhatsApp Cloud API phone registration and approved templates for owners choosing WhatsApp.
   - Telegram Bot token configured in the production environment.
