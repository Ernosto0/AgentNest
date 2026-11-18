# Feature Phase 5, Session 12: light lead list and CSV export (Track E, F-12)

**Status:** Done offline (backend, frontend, docs); track close-out included. Nothing is verified with a pilot owner or on a real phone.
**Baseline:** `1a58d41` (`main`). **Migration head:** `0061` unchanged; no migration was needed (IDs `0110` to `0119` stay unused). Nothing committed.
**Trigger:** "Owners ask for a call-back list" is treated as confirmed by the product owner's request (2026-11-17/18) to implement every Feature Phase 5 session. Trigger evidence from pilot owners is **not recorded**; `mvp-scope.md` says so.

## What was delivered

- **Backend** (`backend/app/reporting/`):
  - `leads.py`: the query and period rules. One SQL decides inclusion, so `total` equals the number of rows by construction.
  - `leads_csv.py`: the in-memory CSV writer with formula escaping.
  - `leads_router.py`: the two routes, registered in `api/router.py`.
  - A one-line import-linter exemption per layer in `pyproject.toml` (`leads_router -> api.deps`), exactly as for the missed-customer router. Nothing else in the contracts changed.
- **API**
  - `GET /workspaces/{id}/leads?from=&to=&limit=&offset=` returns the list.
  - `POST /workspaces/{id}/leads/export` with body `{from, to}` returns the CSV.
  - Both need `reports.view` (owner and manager). Staff get 403, a foreign workspace id gets 404.
  - The export is a POST because it writes an audit row, so it is CSRF-protected and never cached.
- **CSV**
  - Header `customer_handle,last_question,date,conversation_link` and exactly those four columns.
  - UTF-8 with a BOM, all fields quoted, CRLF line ends, at most 5,000 rows.
  - Headers: `Content-Disposition: attachment`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `X-Row-Count`, `X-Truncated`.
  - The file is built in memory and never stored.
  - The date is the workspace-local date of the last question. The link is `{frontend_origin or app_base_url}/w/{ws}/inbox/{conversation}`.
- **Formula injection**: no CSV exporter existed, so the escaping is new. A text cell whose first character is `=`, `+`, `-`, `@`, tab or CR gets a leading `'`. It is detected on the raw text before control characters are replaced, so a leading tab or CR is still caught. Newlines are collapsed to spaces.
- **Audit**: `leads.exported` (resource type `lead_export`, no resource id), metadata only `{period_from, period_to, row_count, truncated, columns: 4}`. It is written and committed before the response is returned; if the audit write fails, no file is returned. It appears in the Activity feed group `system`. The list view is not audited.
- **Frontend**
  - `more/reports/leads` (`LeadsList.tsx`, `leadsHooks.ts`), linked from the daily report for owners and managers.
  - A segmented period filter (7, 30 or 90 days, default 30, in the workspace timezone).
  - A card list that works at phone width, with a "Load more" button.
  - A "Download CSV" button: full width on phones, in the header on wide screens, disabled with no rows or while working.
  - The "Exported N rows" confirmation appears only after the blob has arrived (INV-18); the row count comes from `X-Row-Count`, falling back to the list total.
  - Staff get the not-found page.
  - Always-visible notes (TR and EN): a view, not a CRM; the file holds personal data (KVKK); only assistant-classified conversations are listed; simulated data is never shown.
- **Docs**: `mvp-scope.md` (Track E section, "a view, not a CRM"), `api-design.md` (both endpoints and the definition), `observability.md` §5 (`leads.exported`), `security-and-privacy.md` (one row), `roadmap.md` (Track E entry), `frontend/openapi.json` (the new paths and schemas patched in) and `schema.d.ts` (regenerated, additions only), and the leads phase summary.

## The "did not convert" definition (from real data)

A **lead** is a real conversation in the workspace-local inclusive range `[from, to]`, converted to UTC `[start, end)`.

1. **Question.** An inbound message qualifies when it is real and a non-simulated reply draft covers it (`covers_through_message_id`) with `reply_drafts.intent` in (`pricing`, `booking`). Draft status does not matter, because the intent describes the customer's message.
   - "Real" means the existing `weekly_sources.real_message` rule: not simulated, not deleted, a real conversation, a non-mock account.
2. **Agent path** (added because `agent/dm.py` stores `intent = NULL`). An agent-origin draft also qualifies, as `pricing`, when its persisted `fact_references` (referrer `reply_draft`, same workspace) point at a business fact of category `pricing`. That is the category the missed-customer report already uses (`PRICE_CATEGORY`, imported from `missed_customers`; that module is unchanged). It is stored evidence that a price was used in the reply, not a new classifier and no model call.
3. **Not converted.** The conversation is dropped when an appointment of the same workspace and conversation exists with `status <> 'cancelled'` and `created_at >=` the **first** qualifying question of the period. It is evaluated as of now, not capped at the period end. A cancelled appointment, an earlier booking and another conversation's booking do not convert it.
4. **Display.** The last qualifying question (latest timestamp, then higher message id) is shown; if several drafts cover it, `booking` wins over `pricing`. A human reply does not count as conversion.
5. **No done marker.** There is no resolved or done marker on conversations and customer memory holds no conversion signal, so neither is used, and none was added.

**Still not covered:** manual conversations; booking-only conversations on the agent path (the stored agent proposal carries no price or booking intent field, and session goal keys identify responses, not intent); and appointments the owner created without linking them to the conversation (`calendar_appointments.conversation_id` null), so such a customer stays on the list. Text is nullable (voice notes, retention and erasure), and shown as "No text".

## Tests and checks (real results)

| Check | Result |
|---|---|
| `uv run ruff check .`, `uv run ruff format --check .` | pass (823 files formatted) |
| `uv run mypy app` | pass (435 files) |
| `uv run lint-imports` | 24 contracts kept, 0 broken |
| `uv run pytest tests/integration/reporting tests/isolation/test_leads_isolation.py tests/isolation/test_reports_isolation.py tests/integration/activity tests/unit/reporting` | 258 passed |
| Re-run of `test_leads.py` and `test_leads_isolation.py` after replacing a deprecated `distinct(...)` with `distinct_on` (the first run showed 36 deprecation warnings, now none) | 30 passed |
| `uv run pytest tests/unit` (without `test_backup_and_restore.py`, 7 tests deselected: it fails in this sandbox on a temp-directory permission error, unrelated to this change) | 2186 passed |
| `uv run pytest tests/security tests/contract` | 166 passed, 18 skipped (live probes without credentials) |
| `npm.cmd run lint`, `typecheck`, `i18n:check` | pass (i18n: 2785 keys) |
| `npm.cmd test` (PowerShell) | 65 files, 925 tests passed (11 of them new) |
| `npm.cmd run build` | pass |

New backend tests (30 cases in `tests/integration/reporting/test_leads.py` and `tests/isolation/test_leads_isolation.py`, plus `tests/unit/reporting/test_leads_csv.py`):
- Inclusion and exclusion: other intents, null intent, a simulated message, conversation, draft or mock account, a deleted message.
- Period boundaries at the first and last local instant, in Europe/Istanbul.
- Last question and ties; pagination and `total`.
- Conversion cases: first-question rule, cancelled, earlier and other-conversation bookings, and an unclassified agent draft.
- The agent price-fact path and its tenant scope.
- Roles (owner and manager 200; staff 403; anonymous 401) and validation codes with no audit row.
- Default period, export cap and `truncated`, and "audit failure returns no file".
- CSV: header, four columns, BOM, headers, local date, link, newline collapse, escaping of every leading character, quote and comma round trip.
- Audit metadata: exact keys, and no handle, text or link in it.
- Foreign workspace: 404, no leakage, nothing written.
- The weekly and daily report registries are unchanged.

Eleven Vitest cases in `leads.test.tsx`: render, periods, empty state, nullable fields, paging, export success and failure, header fallback, list error, staff not-found, link visibility.

## Deviations

- The prompt asked for a lead list from `reply_drafts.intent` only; the orchestrator's addendum added the agent pricing-fact signal (point 2 above). Booking-only agent conversations remain uncovered.
- `reports.view` is reused instead of a new permission, so the permission matrix and its docs are unchanged.
- The CSV header is a fixed English machine-readable header (the UI is localized, the file is not).

## Limitations and pending

- **Pending, not verified:** the screen on a real phone, and opening the CSV in Excel with Turkish characters (the BOM is there for that).
- No pilot-owner evidence for the trigger yet.
- The CSV is personal data once it leaves the app. The UI says so, but retention of the file is the owner's duty; the export itself stores nothing.
- Only the latest question per conversation is shown, and a person who followed up by phone cannot cross the customer off (no done marker, by decision).

## Questions

1. **KVKK purpose wording.** The aydinlatma template (`docs/legal/kvkk-aydinlatma-metni-template.md`, section 3) does not name "listing price or booking enquiries that did not result in an appointment, so the business can contact the customer again" as a purpose. Counsel should decide whether to add it; the template was not edited because it is `PENDING_COUNSEL_REVIEW`.
2. Should the agent path persist a draft intent (including booking) in a later change, so booking-only agent conversations are listed? A "done" marker is the other likely owner request once the list is used; both are deliberately not built.
