# Session 1: Reporting metrics core

**Plan:** `plan.md` §1 (reporting layout, import contract), §2 **H1, H2, H4** (the registry shape only), §3 **P6-01** (first half). **Depends on:** Phase 5 + the plan commit. **Commits:** `P6-01a: …` (table + periods + registry), `P6-01b: …` (all metric queries + AC tests). The session may split them further.

## Read first
- `workflows.md` §F and §F.1, which give every metric definition exactly.
- `data-model.md` §3.8 (`daily_reports`), plus the columns the metrics read: `messages`, `conversations`, `reply_drafts`, `approvals`, `content_items`, `operations`, `inbound_events`, `social_accounts`, `audit_logs`.
- `state-machines.md` §4–§7.
- `commands/executors/query_activity_summary.py`, whose `period_bounds` moves into `reporting/periods.py`.
- `tests/factories.py` and the Phase 5 integration test conftests, for how fixtures are built.

## Build
- Migration `0012` `daily_reports`, with `unique (workspace_id, local_date)` and a composite FK to the workspace, plus the `reporting/models.py` model.
- `reporting/periods.py`:
  - `day_bounds(local_date, tz)` and `period_bounds(period, now, tz)`, using `zoneinfo`. A DST day is 23 or 25 hours long.
  - Make the `query.activity_summary` executor import `period_bounds` from here. Its behaviour stays unchanged until session 2.
- `reporting/definitions.py`: the v1 registry. For each of the 20 keys, record:
  - `kind` (period or snapshot);
  - `section` (H4);
  - `inbox` flag (H2);
  - `value` (count or median);
  - `rows(session, ctx, start, end, now) -> Select` (the row set, H1).

  `DEFINITIONS_VERSION = "1"`.
- `reporting/metrics.py`: `compute_metrics(session, ctx, start, end, now) -> Metrics`.
  - Use one read-only transaction, and filter every query by `workspace_id`.
  - Each metric gives `{key, value}`. Links are added in session 2.
  - `has_simulated_data` is true if any contributing row is simulated.
  - `median_first_response_minutes`: use the burst rule of §F.1, and return `null` when there is no answered burst.
- Add the import contract for `app.reporting` to `pyproject.toml`.
- Docs:
  - `data-model.md` §3.8, only if a column differs.
  - `workflows.md` §F.1: the row-set rule (H1) and the inbox keys (H2).

## Done when
- `tests/integration/reporting/test_daily_report.py` passes:
  - **AC-E1:** one fixture with known, different non-zero counts for **every** metric, all asserted exactly;
  - **AC-E2:** records at 23:59:59 and 00:00:00 local, in Europe/Istanbul **and** Europe/Lisbon, including the Lisbon DST change day.
- For every metric, the row count of `rows()` equals `value` (for the median metric, the rows are the answered bursts).
- A record in another workspace changes no metric.
- Unit tests for `periods.py` pass.
- Full backend checks are green.
