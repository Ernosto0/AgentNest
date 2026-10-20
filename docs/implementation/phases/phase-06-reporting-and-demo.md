# Phase 6: Reports, Activity, Failure UX and Demo Completion

## Objective
Complete the local MVP: deterministic daily reports and activity queries (F), the activity feed, Home dashboard and notification centre, integration-failure handling and UX with the mock (G: reauth, degraded circuit, health), member invitations, demo reset, retention jobs, and the full E2E suite. End with the **Local MVP Definition of Done**.

## Read first
[workflows.md §F, §G](../../architecture/workflows.md) · [observability.md](../../architecture/observability.md) · [acceptance-criteria.md](../../product/acceptance-criteria.md) · [user-journeys.md J5, J6](../../product/user-journeys.md) · [security-and-privacy.md §8](../../architecture/security-and-privacy.md) · [local-development.md §5–7](../../operations/local-development.md)

## Scope
**In:** `reporting` (metric definitions v1, compute, `daily_reports`, scheduled generation, API, templated summary, metric links); full `query.activity_summary` and `query.explain_failure`; activity feed API and UI; notification centre (all types, dedup, read-all); Home dashboard; account states `needs_reauth` and `degraded` with mock reconnect (Phase 5), circuit breaker and `account_health_check`, `resume_account` on recovery; system health panel; invites and member management; demo reset and demo history seed; `retention_cleanup` and `media_cleanup` with default periods; promotion expiry notices; full E2E for scenarios A–G; i18n and accessibility checks.
**Out:** real Meta, deployment, email delivery.

## Prerequisites
Phase 5 accepted.

## Files and modules expected to change
```
backend/app/reporting/{metrics.py, definitions.py, service.py, models.py, router.py, jobs.py, templates (i18n keys)}
backend/app/audit/feed.py, router.py
backend/app/notifications/* (types, read-all)
backend/app/operations/health.py (circuit), jobs (health check, resume)
backend/app/integrations/instagram/mock.py (mock reconnect clears auth_revoked)
backend/app/identity/invites.py (+ model, API)
backend/app/demo/{reset.py, history_seed.py}
backend/app/core/retention.py, jobs
frontend/src/features/{home/Dashboard, reports/DailyReport, activity/ActivityFeed, notifications/NotificationCenter, settings/{Members, Connections, SystemHealth}}.tsx
frontend/e2e/{scenario-a…g}.spec.ts, i18n.spec.ts
```

## Key interfaces and contracts
- `reporting.compute_metrics(ctx, period) -> Metrics` (definitions v1 in [workflows.md §F.1](../../architecture/workflows.md)); each metric `{key, value, link}`.
- `reporting.generate_daily_report(ctx, local_date)`; scheduler enqueues at `settings.daily_report_hour`.
- Account state transitions per [state-machines.md §7](../../architecture/state-machines.md).
- Config added: `CIRCUIT_FAILURE_THRESHOLD` (5), `CIRCUIT_WINDOW_MINUTES` (10), `CIRCUIT_COOLDOWN_MINUTES` (10), retention variables ([environment-variables.md](../../operations/environment-variables.md)).

## Tasks (in order)

| ID | Task | Details | Size |
|---|---|---|---|
| P6-01 | Reporting | Metric SQL per definition (timezone-correct boundaries); compute; the `daily_reports` table; generation job + scheduler entry; API; localised templated summary that omits zero sections; links to filtered lists (inbox filters, content tabs, activity filters) whose counts equal the metrics; simulated flag. | L |
| P6-02 | Command executors | `query.activity_summary` via reporting (today, yesterday, last 7 days); `query.explain_failure` via operation + error catalog. | S |
| P6-03 | Activity feed | API with type filters and cursor; i18n templates per audit action; actor labels; simulated badges. | M |
| P6-04 | Notifications and Home | All notification types with severity and dedup; centre with read and read-all; Home dashboard: status strip (connection, simulation, AI mode), attention cards, upcoming posts, recent failures, today's numbers (from reporting), command bar. | M |
| P6-05 | Integration failure UX | `needs_reauth` on auth errors with holds and banners; mock reconnect action (built in Phase 5 as `POST /social-accounts/{id}/reconnect` with `resume_account`; Phase 6 adds clearing the `auth_revoked` failure rule and resuming on health recovery); circuit breaker (`degraded`, cooldown, health check job, recovery); system health panel ([observability.md §6](../../architecture/observability.md)). | M |
| P6-06 | Members and invites | `invites` model; create link (shown as URL and QR); accept flow (new or existing user); role change; removal; last-owner protection; audit. | M |
| P6-07 | Demo reset and history | `seed --reset` and `POST /dev/workspaces/{ws}/reset` (demo only): delete workspace data and `sim_*` rows, re-seed facts, account and a small history (yesterday: 6 inbound, 4 replies, 1 escalation, 1 published post, 1 failed post) so that reports are meaningful; audit `demo.reset`. Ship sample media used by the demo script (`backend/app/demo/media/story-sample.png` 1080×1920, `feed-sample.jpg` 1080×1350; self-made, no third-party rights). | M |
| P6-08 | Retention and cleanup | `retention_cleanup` with defaults ([security-and-privacy.md §8](../../architecture/security-and-privacy.md)); `media_cleanup`; `promotion_expiry_notices`. Tests with the frozen clock. | S |
| P6-09 | E2E completion | Scenarios A–G on three Playwright projects; i18n spec (tr ↔ en main screens); axe checks; no horizontal scroll checks. | L |
| P6-10 | MVP DoD review | Run the full DoD checklist; manual walkthrough on Windows and on a real phone over the LAN; update docs for any drift; write the phase summary including limitations. | S |

## Tests to add
- **Integration:** AC-E1…E5 (fixtures with exact counts across local midnight in Europe/Istanbul and Europe/Lisbon), AC-G1…G3, activity filters, invites (expiry, reuse, role), last-owner protection, retention (text nulled after 365 days with the frozen clock), demo reset only for `is_demo`.
- **E2E:** all scenario specs, `i18n.spec.ts`, accessibility.

## Acceptance criteria
**The Local MVP Definition of Done** in [acceptance-criteria.md](../../product/acceptance-criteria.md) holds in full.

## Demo scenario
The complete walkthrough in [local-development.md §6](../../operations/local-development.md) (about 15 minutes), suitable for showing to pilot businesses on a laptop or phone.

## Known risks
- Metric definition disagreements discovered during pilots. Mitigation: `definitions_version`, and reports are recomputable from records.

## Explicitly excluded
Real integrations, deployment, email, Telegram.
