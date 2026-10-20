# Session 2: Reporting service, job, API, drill-down and report commands

**Plan:** `plan.md` §2 **H1–H6**, §3 **P6-01** (second half) and **P6-02**. **Depends on:** session 1. **Commits:** `P6-01c: …` (service, job, scheduler), `P6-01d: …` (API, summary, drill-down), `P6-02a: …` (`query.activity_summary` via reporting), `P6-02b: …` (`explain_failure` with operations, `GET /operations/{id}`).

## Read first
- `workflows.md` §F (steps 1–5), §B.1 and §G, and `api-design.md` §2.8.
- `background-jobs.md` §4 and §6. Use the existing periodic examples (`approvals/jobs.py`, `operations/jobs.py`) as the pattern for `register_periodic`.
- `notifications/service.py` (`notify_permission_holders`) and `audit/service.py`.
- `core/i18n` and the backend `t()` helper, including how it handles plurals.
- `identity/permissions.py` (`reports.view`, `reports.view_inbox_metrics`).
- `commands/executors/query_activity_summary.py` and `query_explain_failure.py`, `commands/results.py`, the resolver (`latest_failure`) and the interpreter's fake grammar.
- `operations/models.py`, and `errors.py` (`ERROR_CATALOG`, `OUTCOME_UNCONFIRMED`).
- `frontend/src/features/commands/{CommandResultCard.tsx, messages.ts}`.

## Build: report service, job and API (P6-01c, P6-01d)
- `reporting/service.py`:
  - `get_report(ctx, local_date, now)` (H3: today is live; a past date is stored or computed and stored).
  - `generate_daily_report(ctx, local_date, *, scheduled)`: upsert, audit `report.generated`, and `report.daily_ready` (info, `reports.view` holders, dedup `report:{local_date}`) only when `scheduled`.
- Job `generate_daily_report` (3 attempts) in `reporting/jobs.py`, plus a periodic function:
  - every tick, for each active workspace whose local time is at or past `settings.daily_report_hour`, enqueue `daily_report:{ws}:{local_date}`;
  - register it in `app/handlers.py`.
- `reporting/links.py`. Each metric gets:
  - `link`: the API path and the frontend route of its drill-down;
  - `screen_link`, only where an exact filter exists (H1).
- `reporting/summary.py`: the templated, localised summary (H4). Zero sections are omitted, and there is an empty-day text. Keys go in `core/i18n/{tr,en}.json`.
- `reporting/router.py`:
  - `GET /…/reports/daily?date=` → `{local_date, timezone, period_start, period_end, generated_at, is_partial, definitions_version, has_simulated_data, metrics: [{key, value, section, link, screen_link}], summary}`;
  - `POST /…/reports/daily/generate {date}`;
  - `GET /…/reports/daily/{date}/metrics/{key}` → `{key, value, items: [{kind, id, label, occurred_at, link}], next_cursor}`, from the same row set.
  - Staff get the inbox keys only, and a non-inbox drill-down returns 403 (H2).
  - An invalid date or unknown key returns 422 or 404.

## Build: report commands (P6-02a, P6-02b)
- `query.activity_summary` (H5):
  - periods `today`, `yesterday` and `last_7_days` through `reporting.compute_metrics`;
  - result type `command.activity_summary` with the metrics named in H5 and a report link. Remove `command.activity_basic` and its frontend text.
  - The fake interpreter covers "Bugün kaç DM geldi?", "Dün ne oldu?" and "Son 7 gün" (tr/en).
- `query.explain_failure` (H6):
  - `latest_failure` picks the newest content problem **or** reply operation `failed` / `OUTCOME_UNCONFIRMED` within 7 days;
  - the answer gives what, when (in the local time and UI locale) and the next step, plus a link to the subject.
- `GET /…/operations/{id}` (owner/manager): the H6 shape, with no provider payloads.
- Frontend: `CommandResultCard` renders both new result shapes, with links and the SİMÜLASYON badge. Add Vitest tests.

## Build: shared
- Regenerate the OpenAPI files.
- Docs:
  - `api-design.md` §2.8: the exact shapes, including `operations/{id}`;
  - `workflows.md` §F (H3, H4) and §B.1 (command table);
  - `background-jobs.md`: the periodic job and the job catalog entry;
  - `observability.md` §5: confirm `report.generated`;
  - `agent-runtime.md` if the interpreter examples change.

## Done when
- Report tests pass for each of these:
  - the drill-down item count equals the metric value for **every** key, over the session 1 fixture;
  - the staff filter and its 403;
  - today is live and not stored; a past date is stored once and re-read; `generate` overwrites;
  - the scheduler enqueues exactly one job per workspace per local day, and none before the hour, including a workspace in Europe/Lisbon;
  - `report.daily_ready` is created only for scheduled runs, and dedup holds;
  - summary sections with zeros are omitted, and tr/en texts exist;
  - INV-08: the report path makes no LLM call (the fake provider's call count is unchanged).
- Command tests pass:
  - **AC-E4:** `tests/integration/commands/test_activity_query.py` asserts the answer equals the report's `inbound_messages` at the same frozen instant;
  - yesterday and 7-day sums;
  - explaining a failed reply (`OUTCOME_UNCONFIRMED`) and a failed post;
  - "no failure" when there is none.
- Isolation: a foreign workspace returns 404 on the three report routes and on `operations/{id}`, and the tests are added to `tests/isolation/`.
- Evals `interpret_command` still pass `--strict` with the fake provider. Add cases if the grammar changed.
- Full backend and frontend checks and the OpenAPI drift check are green.
