# Session 4: Notification catalog, notification centre and Home dashboard

**Plan:** `plan.md` §2 **H8, H9**, §3 **P6-04**. **Depends on:** session 3. **Commits:** `P6-04a: …` (catalog and new types), `P6-04b: …` (notification centre), `P6-04c: …` (Home dashboard).

## Read first
- `user-journeys.md` §1 (Home, global elements), J5 and J6.
- `observability.md` §4.3.
- Every `notify(` / `notify_permission_holders(` call: grep `backend/app`.
- `notifications/{service,router}.py`.
- `frontend/src/features/{notifications/*, home/*, commands/CommandBar.tsx}` and `api/types.ts`.
- `GET /api/v1/meta` (`llm_mode`).

## Build
- **Catalog (H8):**
  - `notifications/catalog.py`, the single source: `type → severity, recipients (permission), dedup pattern`;
  - `notify*` refuses an unknown type (test);
  - rename the account dedup key to `account:{id}:{status}`;
  - add the new types that already have a producer: `report.daily_ready` (session 2), and `account.permission_missing` at `handle_permission_error`. The circuit types are added in session 5, the promotion type in session 9 and `member.joined` in session 7; each of those sessions extends the catalog;
  - write observability §4.4 (the full table).
- **Notification centre:**
  - `features/notifications/NotificationCenter.tsx` at `more/notifications`: the unread/all toggle, mark read when opened, read-all, severity icon **and** text (never colour alone), a link to the subject, and the SİMÜLASYON badge;
  - the bell opens it;
  - `describe.ts` covers every catalog type.
- **Home (H9):**
  - `features/home/Dashboard.tsx` replaces the placeholder content of `HomePage` (keep the readiness card and the command bar);
  - the status strip (connection, simulation, AI mode);
  - the `needs_reauth` (red) and `degraded` (amber) banners, with the J6 texts and the action link to the connections screen (`more/automation` until session 6 adds `Connections`);
  - attention cards with counts from the live report;
  - the next 3 scheduled posts (add sorting to `GET content-items` only if needed, and document it);
  - the 3 most recent failures;
  - today's numbers, where staff see inbox numbers only.
- Regenerate the OpenAPI files if the API changed.
- Docs: observability §4.4, user-journeys §1 (only if the Home content changed), api-design §2.7 (if content list sorting was added).

## Done when
- Backend tests pass:
  - every type produced in code is in the catalog, and an unknown type raises;
  - dedup works per type;
  - read-all touches only the caller's notifications.
- Vitest tests pass:
  - catalog types are a subset of `describe.ts` (from a generated or shared list);
  - the centre (read and read-all);
  - each Home card, including its empty state;
  - both banners appear, driven by the account status;
  - staff Home.
- `e2e/scenario-a.spec.ts` (AC-A1) still passes (update its Home assertions if they changed; assertions only).
- Full backend and frontend checks are green.
