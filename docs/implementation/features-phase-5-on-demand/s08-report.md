# Feature Phase 5, Session 08: one customer follow-up inside the 24-hour window (F-10)

**Status:** Done offline (backend, frontend, docs). Live Instagram behaviour is **pending** (nothing was sent to a real account).
**Baseline:** `1a58d41`. **Migration head of this track:** `0090` (`down_revision = "0061"`). Nothing committed.
**Trigger:** moved out of Deferred in `mvp-scope.md` on 2026-11-18 at the owner's request (all Feature Phase 5 sessions were requested). Pilot evidence for late replies is **not yet recorded**.

## What was delivered

- **Rule** (`backend/app/inbox/follow_up.py`, no model call): when a customer asked about a price or booking, the assistant's answer was **sent**, and the customer then stayed quiet for X hours, one follow-up reply draft is created. Computed from persisted records only:
  - Arming happens in `operations/resolution.record_delivered` (every path that records a sent reply, including repair and reconciliation). It requires: setting on; `origin = legacy`, `source in (ai, approved_answer)`, `intent in (pricing, booking)`; the answer covered the customer's newest inbound message; conversation on automatic handling; account controller in legacy mode. `due_at = sent_at + hours`.
  - A delayed job `follow_up_check` runs at `due_at` and re-checks everything under the conversation lock (stale or foreign jobs are no-ops).
- **Setting** (off by default): `workspaces.settings` gains `follow_up_enabled` (false), `follow_up_hours` (1 to 20, default 6) and `follow_up_text {tr, en}` (400 characters, empty = built-in neutral text, no numbers or links). They are **not** in the generic workspace PATCH. Dedicated endpoints `GET/PUT /api/v1/workspaces/{id}/follow-up-settings` (GET: `reply.write`; PUT: `workspace.manage`, owner only) validate custom text with the approved-answer template checker (no literal prices, times, contacts or links) and refuse a `{{fact:key}}` that names no fact. Audit `follow_up.settings_changed` (key names only).
- **Text**: the owner's per-language text or the built-in default, rendered by `render()` from usable facts and checked by `validate_claims` and the 1000-byte limit. A placeholder naming a fact that is not usable skips with `FACT_NOT_USABLE`; a claim issue skips with `GROUNDING_FAILED`. Nothing unvalidated is ever stored as sendable.
- **Draft**: `ReplyDraft` with `source = approved_answer`, `intent = follow_up`, `decision = approval_required`, reason `FOLLOW_UP_REQUIRES_APPROVAL`, an `authorization` approval bound to the exact text (`reply.send`, window-bound expiry), fact references (a changed fact supersedes/cancels it through the existing impact path). **Approval is always required in this session**; automatic sending is excluded.
- **One per conversation, DB-enforced**: table `conversation_follow_ups` with `UNIQUE (workspace_id, conversation_id)`, a unique partial index on `reply_draft_id`, and `CHECK` constraints (`drafted` iff `reply_draft_id`, reason required for `cancelled`/`skipped`, `due_at >= answered_at`). The row moves `scheduled -> drafted` through a conditional UPDATE inside a savepoint, so concurrent checks cannot both draft. Rows that never produced a draft (`scheduled`, `cancelled`, `skipped`) are re-armed by a later answered exchange (upsert with a status guard); a `drafted` row is final even if its draft is later rejected, cancelled or superseded.
- **A new customer message cancels** (`processing._on_customer_message`, same transaction, conversation lock held): a `scheduled` row becomes `cancelled/CUSTOMER_REPLIED`; a pending follow-up draft is superseded by the existing `close_open_drafts`; a queued (owner-approved) follow-up draft is cancelled and its approval withdrawn.
- **24-hour window, twice, rejected not skipped**: at draft time the boundary is the policy rule R2 boundary (`now >= last_inbound_at + 24h - 5 min` is closed; the row becomes `skipped/MESSAGING_WINDOW_CLOSED`, and arming with a `due_at` beyond the boundary stores a skipped row with no job). At send time `operations/send._prepare` keeps its generic check (`now >= window_end - 60 s` expires the draft with `MESSAGING_WINDOW_CLOSED`, no operation row, nothing sent), and for follow-up drafts (found through `conversation_follow_ups.reply_draft_id`, never by intent text) adds rejections `CUSTOMER_REPLIED`, `FOLLOW_UP_OFF`, `HUMAN_TAKEOVER`. The controller-changed check now runs after the window check so the window rejection has priority.
- **Report**: two weekly metrics in the missed-customer report: `follow_ups_sent` and `follow_up_replies` (the customer wrote again within 24 hours after a sent follow-up; each follow-up counted once). Persisted records only, simulated/mock excluded, drill-down runs the same SELECT as the number, local-week boundaries.
- **Frontend**: `FollowUpSettings` panel in Settings > Workspace (owner edits; others read-only): on/off, hours select 1 to 20, optional TR and EN text with the built-in default as placeholder, server validation errors per field; TR and EN strings. Draft card and approval view label a follow-up draft; reason chip `FOLLOW_UP_REQUIRES_APPROVAL` has TR/EN text; the report shows both new metrics with TR/EN labels.
- **Housekeeping**: Category C table list and the RLS count test (63 to 64), backup, workspace purge order and the customer/conversation data export include the new table; import-linter source lists; `frontend/openapi.json` and `schema.d.ts` patched in place.
- **Docs**: `mvp-scope.md` (new Track C section), `workflows.md` (follow-up subsection and metric definitions), `state-machines.md`, `background-jobs.md` (`follow_up_check`), `data-model.md`, `api-design.md`, `observability.md` (audit actions `follow_up.settings_changed`, `follow_up.drafted`, `follow_up.skipped`, `follow_up.cancelled`).

## Contracts

| Item | Value |
|---|---|
| Job type | `follow_up_check`, payload `{follow_up_id, answer_draft_id}`, `max_attempts=3`, dedup key `follow_up_check:{follow_up_id}:{answer_draft_id}`, `run_at = due_at`; a raised hours setting reschedules |
| Table | `conversation_follow_ups` (RLS forced, tenant policy, composite FKs, cascade) |
| Reason codes | `CUSTOMER_REPLIED`, `FOLLOW_UP_OFF`, `SOMEONE_ELSE_REPLIED`, `HUMAN_TAKEOVER`, `CONTROLLER_CHANGED`, `ACCOUNT_NOT_CONNECTED`, `OPEN_DRAFT_EXISTS`, `MESSAGING_WINDOW_CLOSED`, `FACT_NOT_USABLE`, `GROUNDING_FAILED` |
| Env vars | none added |

## Tests and checks

## Check results

- Backend: `ruff check`, `ruff format --check`, `mypy app` (434 files) and `lint-imports` (24 contracts kept) all clean. `alembic heads` = `0090`.
- Backend tests (not the full suite): `tests/unit` and `tests/contract` passed; `tests/security`, `tests/isolation`, `tests/integration/inbox`, `reporting`, `identity` and `operations` ran 966 tests. The first pass had 43 failures: one real (the exact-settings expectation in `test_workspaces.py`, fixed: the three new keys are now in the expected defaults) and 42 that passed on re-run (all of `test_simulator.py`, `test_simulator_published.py`, `test_members_and_invites.py`; a `tests/security/test_invite_secrets.py` failure in an earlier pass also passed on re-run). Those looked like interference from other test runs sharing the track's test DB at the same time; re-run alone: 140 passed (identity + both simulator files), security 2 passed. The new Follow-up tests (68 tests across unit, integration, reporting, isolation, migration and `test_rls_policies`) passed together in one run.
- Frontend (PowerShell): `lint`, `typecheck`, `i18n:check` (2778 keys), `build` clean; `vitest` 65 files / 918 tests passed (one earlier full run had a single failure under heavy machine load; the re-run was fully green, and settings/reports/approvals/inbox ran 219/219).
- Not run: the full backend suite (over an hour), `tests/e2e` and `tests/browser`.


New tests: `tests/unit/inbox/test_follow_up.py`, `tests/integration/inbox/test_follow_up.py` (off creates nothing; happy path for pricing and booking with duplicate-job idempotency; non-eligible answers do not arm; draft-time window boundary just inside and at/after the boundary; arming too late; send-time window boundary just inside and at/after; expired approval cannot send; DB uniqueness and conversation deletion; customer reply cancelling at each stage; send-time rejections; due-time refusals; hours raised reschedules; re-arm after a cancel; custom fact text and the price-change hold; foreign and stale jobs are no-ops), `test_follow_up_settings.py` (defaults, owner-only write, template validation, hours bounds, generic PATCH cannot set the keys, foreign workspace 404), `test_follow_up_migration.py` (up/down/up), `tests/integration/reporting/test_follow_up_metrics.py` (exact counts, drill-down equals the count, simulated excluded, non-UTC week), `tests/isolation/test_follow_ups_isolation.py` (forced RLS, runtime-role isolation, composite FKs, foreign settings 404), frontend `followUp.test.tsx`.

## Deviations and decisions

- **No automatic follow-ups.** The brief says approval "by default". It is always required here: an unsolicited automatic nudge is riskier, and an auto mode needs a new policy action class (policy CHECK, API and UI). Recorded as excluded in `mvp-scope.md`; the coordinator approved it.
- **Agent-controlled accounts are excluded** (Phase 7.5 agent drafts carry no intent; delegation and grounding rules differ). Documented limitation.
- **Only assistant-written answers arm a follow-up.** A person's own typed reply or a native app reply (no intent) does not.
- **Custom text lives in workspace settings**, not in approved answers, to avoid widening the approved-answer intent CHECK and its UI. The dedicated endpoint, not the generic PATCH, writes it, because `identity` may not import `knowledge`.
- **Existing send check reordered**: the `CONTROLLER_CHANGED` cancel in `send._prepare` now runs after the window check (window first). No existing test depends on the old order.
- `follow_up` is a new `ReplyDraft.intent` value. Readers checked: the approval-ladder suggestions only use the fixed `SUGGESTIBLE` intents; the weekly `answered_questions` filters on `pricing`/`booking`; save-as-answer falls back to `faq` for an unknown intent; the draft card and approval view label it.

## Limitations

- Live behaviour with real Instagram accounts is **pending**; the window and send path were exercised only against the simulator.
- A skipped row (for example `FACT_NOT_USABLE`) is silent to the owner; it is visible only in the audit log. The report counts sent follow-ups, not skipped ones.
- Changing the hours setting after arming affects the next check (a raise reschedules; a lowering does not pull an already scheduled job earlier).
- The report metrics exist only in the weekly report, not the daily report.
- No ADR was written (none needed for this session).

## Questions

1. Is an automatic (no-approval) follow-up wanted later? It would need a new `reply.follow_up` policy class.
2. Pilot evidence for the trigger is still to be recorded in `mvp-scope.md` by the owner.
