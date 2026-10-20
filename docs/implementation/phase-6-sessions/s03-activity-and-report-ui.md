# Session 3: Activity feed and the daily report UI

**Plan:** `plan.md` §2 **H1–H4, H7**, §3 **P6-03** and **P6-01** (UI part). **Depends on:** session 2. **Commits:** `P6-03a: …` (activity API, templates, labels), `P6-03b: …` (activity UI), `P6-01e: …` (report UI).

Build the backend first (the feed), then the two screens. They share list and badge patterns.

## Read first
- `observability.md` §5 (the audit catalog, the account audit names and the Activity view rule).
- User journey J5 ("Activity" and the daily report) and the status vocabulary in `user-journeys.md` §1.
- `audit/models.py` and `audit/service.py`, including the metadata restrictions, and `core/pagination.py`.
- The models that labels resolve from: conversations (customer alias), content items (title), facts (label), users (display name), approvals and commands.
- The report API from session 2 (`api-design.md` §2.8).
- `frontend/src/api/schema.d.ts`, `features/content/ContentPage.tsx` (tabs and list patterns), `SimulatedBadge`, and `mockApi` in the Vitest setup.

## Build: activity feed backend (P6-03a)
- `audit/feed.py`:
  - query newest first with an opaque cursor over `(occurred_at, id)`;
  - the `type` group map (H7) and an optional `date` (local day, using the workspace timezone);
  - the `workspace_id` filter on every query.
- `audit/labels.py`:
  - actor labels;
  - resource labels resolved at read time, batch-loaded with no N+1 queries, and always workspace-scoped (a resource that no longer exists gets a neutral label);
  - links per resource type.
- `audit/router.py`: `GET /…/activity?type=&date=&cursor=`, with `activity.view`.
- Templates `activity.<action>` in tr/en for **every** action in the observability §5 catalog, plus every action found in the code with grep. Add any action missing from the catalog to the doc.

## Build: activity UI (P6-03b)
- `features/activity/ActivityFeed.tsx`: group chips, a "load more" list, actor and resource links, and the SİMÜLASYON badge.
- Route `more/activity` and its More menu entry. `activity.json` in tr/en.

## Build: report UI (P6-01e)
- `features/reports/DailyReport.tsx`:
  - a date stepper (today, previous and next day; nothing after today);
  - the summary text;
  - the sections, where **every number is a link** to its drill-down;
  - "HH:MM itibarıyla" when `is_partial`;
  - the SİMÜLASYON badge when `has_simulated_data`;
  - the empty-day state;
  - for owners and managers, a "Yeniden oluştur" button that calls `POST generate`.
- `features/reports/MetricItems.tsx`: the drill-down list with the count in the header, each row linking to its screen, and the `screen_link` shortcut where present.
- Routes `more/reports` and `more/reports/:date/:key`, and the More menu entry. The command result "Raporu aç" link from session 2 opens the report.
- Staff see only the inbox sections, with no broken links.
- `reports.json` in tr/en.

## Build: shared
- Regenerate the OpenAPI files.
- Docs: `api-design.md` §2.8 (activity shape and groups) and `observability.md` §5 (groups, label rule, any added actions).

## Done when
- Backend tests pass for each of these:
  - every group filter;
  - the date filter across local midnight (Istanbul);
  - the cursor stays stable when several entries have the same timestamp;
  - a removed member's entries read "Eski üye";
  - template coverage: every catalog action has tr and en text;
  - no message text in the output;
  - isolation and the staff 403.
- Vitest tests pass:
  - the activity feed: rendering, a filter change and the badge;
  - the report: every number renders as a link with the right href, zero sections are hidden, the partial label, the badge (AC-E5, component level), the staff view, and the drill-down count matches the number of items.
- Full backend and frontend checks and the OpenAPI drift check are green.
