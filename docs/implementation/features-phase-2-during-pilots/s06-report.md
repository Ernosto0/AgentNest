# Feature Phase 2, Session 06: Missed-customer report in lira (D-03)

**Status:** Implemented, uncommitted, in worktree `C:\Users\ernos\pivoris-p2\s06`. Nothing was run against a real Instagram account or provider; all figures come from test data.
**Baseline commit:** 20a0551 (detached). **Migration:** none (the report is computed live; no table was added).
**Earlier work:** a Codex run left only `backend/app/reporting/weekly_sources.py` (kept after review, fixed: it required `last_verified_at`, which the app's own usability rule does not; its hours-to-instant code was rewritten; the registry was added). The D-01 line in `backend/pyproject.toml` was kept.

## What was built
- **Weekly report** for the workspace-local Monday to Sunday week (current week partial, ends now). Owner and manager only (`reports.view`). Real records only: simulated messages, simulated conversations and drafts, deleted messages and `mock` accounts are excluded, even when a row carries a false flag.
- **Metrics** (`weekly_sources.py`, same 7-column row-set convention as `definitions.py`): `after_hours_dms`, `first_reply_median_minutes`, `unanswered_conversations`, `answered_questions` (assistant-sent price or booking replies), `after_hours_price_answers`. Each has a `previous_value` for the previous full week. After-hours is decided against the verified, usable `hours.weekly` fact in the workspace timezone (open at the opening minute, closed at the closing minute; closed exception days are all after-hours). With no verified hours the two after-hours numbers are `null`, never 0.
- **Estimate:** `after_hours_price_answers x CONVERSION_RATE (0.05) x median verified TRY price`. `CONVERSION_RATE` is a named constant in `reporting/missed_customers.py`, returned by the API and shown in the UI next to the amount, with the formula and every price input. Prices are usable (verified, in-window, uncontested) `pricing` money facts in TRY. Without verified hours (`hours_missing`) or without a verified TRY price (`no_verified_price`) the amount is `null` and only counts are shown.
- **Drill-downs** per number reuse the drill-down paging and description code (`drilldown.rows_page`, extracted from `metric_items`; behaviour of the daily drill-down unchanged). Items count equals the value; customers appear by handle only.
- **Weekly job** `generate_missed_customer_report`, from Monday 09:00 workspace-local for the week just ended (catches up until the next Monday), one per workspace and week via dedup key. Sends `report.missed_customers_ready` only when some number is above zero, counts only (no lira in the notification).
- **UI** in its own components: `MissedCustomersReport.tsx` (week stepper, estimate card with formula and inputs, counts-only states with a link to add hours or prices, numbers with previous week and drill-down links), `MissedCustomerItems.tsx`, `missedHooks.ts`, `weeks.ts`. A link from the daily report (owner and manager) opens it. `ItemRow` moved out of `MetricItems.tsx` into `ItemRow.tsx` so both drill-downs share it.

## Files
Backend, new: `app/reporting/weekly_sources.py`, `missed_customers.py`, `missed_router.py`; `tests/integration/reporting/test_missed_customers.py`.
Backend, changed: `app/reporting/jobs.py`, `drilldown.py` (extraction, `decode_cursor` made public), `links.py`, `schemas.py`; `app/api/router.py`; `app/notifications/catalog.py`, `delivery_policy.py`; `pyproject.toml` (import-linter: two new modules in the no-API-layer list, `missed_router -> app.api.deps` ignored in two contracts).
Frontend, new: `features/reports/MissedCustomersReport.tsx`, `MissedCustomerItems.tsx`, `ItemRow.tsx`, `missedHooks.ts`, `weeks.ts`, `missed.test.tsx`.
Frontend, changed: `app/router.tsx`, `api/types.ts`, `api/schema.d.ts` (regenerated), `openapi.json` (only the two new paths and four schemas added), `features/reports/DailyReport.tsx` (link), `MetricItems.tsx` (ItemRow moved), `features/notifications/{catalog.json,describe.ts,target.ts}`, `i18n/locales/{en,tr}/{reports,ai}.json`.
Docs: `docs/architecture/{api-design,background-jobs,observability,workflows}.md` (workflows section F.2).

## Contracts
- **API:** `GET /api/v1/workspaces/{id}/reports/missed-customers?week_start=` and `GET .../reports/missed-customers/{week_start}/metrics/{key}?cursor=&limit=` (`reports.view`; staff 403; foreign workspace 404; future week 422 `in_future`; unknown key or after-hours key without verified hours 404). Schemas `MissedCustomerReportOut`, `WeeklyMetricOut`, `EstimateOut`, `PriceInputOut`. `estimate.price_count` is the number of verified prices the median is over; `estimate.price_inputs` lists at most 20 of them (cheapest first), and the UI says "median over N verified prices" and "showing 20 of N" when the list is cut.
- **Job:** `generate_missed_customer_report` `{workspace_id, week_start}`, 3 attempts, dedup `missed_customer_report:{workspace}:{week_start}`.
- **Notification type:** `report.missed_customers_ready` (info, `reports.view`, dedup `missed-customers:{week_start}`, params `week_start`, `after_hours_dms`, `unanswered_conversations`; quiet-hours class, not pushed). Frontend catalog, `describe.ts`, `target.ts` and tr/en strings added.
- **Constant:** `CONVERSION_RATE = Decimal("0.05")` (not an env setting, so no `.env.example` or environment-variables doc change).
- No new table, setting, audit action or reason code.

## Tests and results
All backend runs used `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN= OPENAI_API_KEY= PYTHONUTF8=1` and a per-shard `TEST_DATABASE_URL`.
- `pytest tests/integration/reporting tests/isolation/test_reports_isolation.py` (after the `price_count` fix): 173 passed. `test_missed_customers.py` alone has 22 tests (21 plus one with 25 prices: median over all 25, `price_count` 25, 20 inputs listed) (hours boundaries 06:59/07:00/23:00 and Saturday/Sunday, Istanbul vs Lisbon for one instant, closed exception day, missing and unverified hours, missing prices, unverified and non-TRY prices, empty week, partial and future week, simulated/mock/deleted exclusion, drill-down count equals value for every metric, staff 403, foreign workspace 404, workspace isolation, job timing and dedup, notification once and silent for an empty week).
- `pytest tests/unit tests/isolation tests/security tests/contract` (shard `_a`): 1997 passed, 13 skipped, 3 failed (`test_phase6_isolation::test_the_dev_job_listing_of_a_never_shows_the_jobs_of_b`, `test_publishing_isolation::test_the_simulator_listing_of_a_never_shows_what_b_published`, `test_invite_secrets::test_the_invite_token_is_never_logged_audited_notified_or_queued`). All three pass when rerun with `DEMO_TOOLS_ENABLED=true`; they depend on that environment setting, not on this change.
- `pytest tests/integration/reporting tests/integration/notifications tests/integration/activity tests/integration/test_simulation_flag.py` (shard `_b`): 303 passed, 1 failed (`test_ac_x2_the_api_exposes_the_flag_on_every_content_response`, 404 without demo tools; passes with `DEMO_TOOLS_ENABLED=true`).
- `uv run ruff check .`, `ruff format --check .`, `mypy app` (363 files), `lint-imports` (23 kept): clean.
- Frontend (PowerShell): `npm.cmd run lint`, `typecheck`, `i18n:check` (2478 keys) clean; `npm.cmd test` 53 files, 798 tests expected (11 earlier plus 2 new in `missed.test.tsx`; the reports, notifications and navigation files were rerun after the fix: 82 passed; the full suite was not rerun); `npm.cmd run build` OK.
- Not run: the other integration directories and the full suite.

## Invariant notes
INV-01 every row set filters by workspace (isolation test). INV-08 no model involved. INV-09 simulated and mock data excluded and the response says `has_simulated_data: false`. INV-02 the lira figure uses only verified, usable price facts and shows its inputs. INV-19 weeks and hours use the workspace timezone. No external calls; time from `Clock`.

## Deviations from the brief
1. The weekly metrics live in their own registry (`weekly_sources.py`), not in `definitions.py`/`metrics.py`, so the stored daily report and its `definitions_version` are untouched. They reuse `Definition` and `compute_metric`.
2. The report is computed live and not stored (no snapshot table), so a past week reflects retention deletions after the fact. The job's output is the notification only.
3. Comparison is with the previous full week, not "four weeks before activation".
4. No new audit entry for the weekly generation (the notification is the trace).
5. The brief's "daily or weekly notification summary" is a separate weekly notification with counts only.
6. `answered_questions` counts assistant replies (ai or approved answer) with the stored `intent` of pricing or booking; owner-written replies are not counted.

## Limitations and open questions
- Live-provider behaviour is unverified: the stored `intent` comes from the drafting pipeline and was only tested with seeded rows.
- The 5% rate is a placeholder planning figure; the owner of the product should confirm it. Median prices mix units (month, package, ...); units are listed but not normalised.
- "Unanswered" counts every conversation whose last customer message got no reply, including ones needing none (such as a thank-you).
- The new notification is not added to Web Push or Telegram-specific templates.
- Session 05 also adds a notification type and weekly job; expect a merge touch in `catalog.py`, `catalog.json`, `describe.ts`, `target.ts`, `ai.json`, `delivery_policy.py` and the docs tables.
