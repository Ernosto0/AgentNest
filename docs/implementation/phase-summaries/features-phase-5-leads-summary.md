# Feature Phase 5 Close-Out Summary: Track E, Light Lead List (F-12)

- **Track:** Feature Phase 5, Track E (F-12 lead list with CSV export). The other four tracks (A WhatsApp, B Carousels and Reels, C Follow-up, D Languages) have their own summaries and are not covered here.
- **Specification:** [features-phase-5-on-demand/sessions.md](../features-phase-5-on-demand/sessions.md), Session 12; source [pre-launch-feature-recommendations.md](../../review/pre-launch-feature-recommendations.md) §4 step 5, F-12.
- **Sessions executed:** 12. Report: [s12-report.md](../features-phase-5-on-demand/s12-report.md).
- **Baseline Git commit:** `1a58d41` (`main`). **Nothing is committed.**
- **Alembic migration head:** Track E adds no migration (block `0110` to `0119` was reserved and not used); merged migration head is `0100`.
- **Status:** **Implemented and verified offline. Stopped for review.** Not tried by a pilot owner or on a real phone.
- **Date:** 2026-11-18

> [!NOTE] Current Status (Date: 2026-11-19)
> The code for this feature phase was subsequently committed to `main` (`e1c9f13`). Its functionality has been integrated, verified offline, and extended to Account Agent pilot readiness in Sessions 00–10 of the `answeres2.md` plan (specifically Session 06). The original historical test records and offline verification below are preserved intact. Remaining live provider verifications (live lead export checks and conversion deduplication on production UI) are cataloged as pending live verification runbooks in Session 11 (`docs/implementation/account-agent-pilot-readiness/s11-report.md`).

---

## 1. Executive summary

An owner or manager can open a call-back list: the customers who asked about a price or a booking in the last 7, 30 or 90 days and have no appointment. They can download the same list as a four-column CSV. It is a **filtered view of conversations that already exist, not a CRM**: no stages, statuses, tags, notes, assignees or custom fields, and no marker to cross someone off.

The trigger ("owners ask for a call-back list") was treated as confirmed by the product owner's request to implement all Feature Phase 5 sessions; evidence from pilot owners is not yet recorded.

## 2. What changed

- **Backend** (no migration): `reporting/leads.py` (query, period rules), `leads_csv.py` (CSV, formula escaping), `leads_router.py`; routes `GET /workspaces/{id}/leads` and `POST /workspaces/{id}/leads/export`, both with `reports.view` (owner and manager; staff 403; foreign workspace 404).
- **Export and KVKK**:
  - Only four columns: customer handle, last question, local date, conversation link. No phone, e-mail, ids or intent.
  - Built in memory, never stored; `Cache-Control: no-store`; at most 5,000 rows, with a visible `truncated` flag.
  - Audited as `leads.exported` with the period dates, row count, truncated flag and column count only. No customer data is in the audit row. If the audit write fails, no file is returned.
  - Cells that start with `=`, `+`, `-`, `@`, tab or CR are escaped with a leading `'`. The check runs on the raw text.
  - The UI states that the file holds personal data and must be kept safely and deleted when no longer needed.
- **Frontend**: page `more/reports/leads` (period filter, phone-width card list, paging, "Download CSV", notes in TR and EN), linked from the daily report for owners and managers; staff get the not-found page. The "exported" confirmation appears only after the file has arrived.
- **Docs and contracts**: `mvp-scope.md` (view, not a CRM), `api-design.md`, `observability.md` §5, `security-and-privacy.md`, `roadmap.md`, `frontend/openapi.json` and `schema.d.ts`, plus this summary and the s12 report.

## 3. Definition of "did not convert" (the contract)

Computed live from stored records. No model is used, and nothing is inferred from customer text.

1. A real inbound message qualifies when a non-simulated reply draft covers it with `intent` in (`pricing`, `booking`), whatever the draft status. Simulated and deleted messages, simulated conversations and mock accounts never count (INV-09).
2. On the Phase 7.5 agent path the draft has no intent, so an agent draft qualifies as `pricing` when it rendered a verified fact of category `pricing` (the stored `fact_references`; the same category the missed-customer report uses).
3. The conversation is **not** a lead when a non-cancelled appointment linked to it was created at or after its first qualifying question in the period, evaluated as of now.
4. A person replying is not a conversion. There is no done marker and no use of customer memory.

**Not covered:** manual conversations; booking-only agent conversations (nothing stored says so); and appointments created without a link to the conversation (that customer stays on the list).

## 4. Verification

| Check | Result |
|---|---|
| ruff check, ruff format --check, mypy | pass |
| lint-imports | 24 kept, 0 broken |
| pytest: reporting, leads isolation, reports isolation, activity, unit/reporting | 258 passed; the two new backend files were re-run after a small query-API change: 30 passed |
| pytest: security, contract | 166 passed, 18 skipped (live probes) |
| eslint, tsc, i18n:check | pass |
| vitest (65 files), build | 925 passed; build passes |

Covered by tests: inclusion and exclusion rules, timezone boundaries, conversion rules, the agent price-fact path, roles, foreign-workspace isolation, CSV format and formula escaping, the audit row without PII, and the export cap.

## 5. Not verified, open

- A pilot owner using the list; the trigger evidence.
- The screen on a real phone, and the CSV opened in Excel with Turkish characters.
- **Question for counsel:** the KVKK clarification template does not name "listing enquiries that did not result in an appointment so the business can contact the customer again" as a purpose. The template was not edited (`PENDING_COUNSEL_REVIEW`).
- **Product follow-ups, deliberately not built:** persisting a draft intent on the agent path (so booking-only agent conversations are listed) and a "done" marker. Both would widen the feature toward a CRM and need an explicit decision.
