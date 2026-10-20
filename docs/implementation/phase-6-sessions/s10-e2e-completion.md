# Session 10: E2E completion (scenarios A–G, i18n, accessibility, layout)

**Plan:** `plan.md` §3 **P6-09**. **Depends on:** session 9. **Commits:** `P6-09a: …` (scenario E), `P6-09b: …` (scenario G), `P6-09c: …` (A–D, F updates), `P6-09d: …` (i18n spec), `P6-09e: …` (axe and scroll checks), `P6-09f: …` (fixes they found).

This is a long session. Land the scenarios (a–c) green on all 3 projects **before** starting the i18n and accessibility work (d–f). If the context is running low after `P6-09c`, stop there and report: the operator will start a new session for the rest.

## Read first
- `testing-strategy.md` (E2E section; accessibility: no serious or critical axe violations).
- `acceptance-criteria.md` scenarios E and G, AC-X3 and AC-X4.
- `frontend/e2e/{playwright.config.ts, global-setup.ts, helpers.ts}` and the existing scenario specs (the patterns for the dev API, run-due-jobs and badges).
- `ac-test-map.md` (the GAPs left for E2E) and `local-development.md` §6 E and G.
- `user-journeys.md` §1 (colour plus icon, never colour alone) and §3.
- `frontend/scripts/check-i18n.mjs` and `src/i18n/*`, and how the UI language is switched (`PATCH /auth/me` and the language setting).

## Build: scenarios (a–c)
- `scenario-e.spec.ts`:
  - "Bugün kaç DM geldi?" → the number equals the report's message number;
  - the report: for **every** nonzero number, open its list and assert that number of rows (AC-E3);
  - the SİMÜLASYON label on the report (AC-E5);
  - the activity feed shows the matching events;
  - yesterday's seeded report has the H16 numbers.
- `scenario-g.spec.ts`:
  - `send → auth_revoked` → the red Home banner and the critical notification (AC-G1);
  - a post due during the reauth reads *Beklemede*;
  - reconnect on the connections screen → the banner is gone and the reply is *Gönderildi*;
  - the degraded path per plan §3 P6-09 (driven by the dev API; if it is too slow, use the documented fallback and say so in the report);
  - system health shows the account status.
- Update scenarios A–D and F for the Home dashboard, the moved reconnect button and the seeded history, changing assertions only.
- Use helpers instead of copy-paste, and do not wait for real minutes: use the dev run-due API and the health-check route.

## Build: i18n, accessibility and layout (d–f)
- Add `@axe-core/playwright` as a dev dependency.
- `e2e/a11y.spec.ts`: run axe on these screens at 390×844 and on desktop:
  - Home, Inbox, a conversation, Content and a content detail, Approvals and an approval sheet;
  - Knowledge, Reports and a drill-down, Activity, Notifications, Members, Connections, System health;
  - the login and invite accept pages.

  Fail on serious or critical violations. **Fix the code**, not the rules. Any exclusion is narrow, commented and listed in the report.
- `e2e/i18n.spec.ts`: switch tr → en → tr and assert known visible strings on each main screen. Fail on a visible raw i18n key (a heuristic over the visible text for `namespace.key` patterns).
- Add `expectNoHorizontalScroll(page)` to `helpers.ts` (`scrollWidth <= innerWidth`), called on every main screen in the a11y spec and the scenario specs at 390×844 (AC-X4).
- Fix what these checks find: labels, contrast, focus order, missing `aria-*`, overflow. Re-run the Vitest suite after the fixes.

## Done when
- `npm run e2e` passes **all** specs on all 3 projects, including the new ones. Report the run time per project.
- Every GAP from `ac-test-map.md` assigned to E2E is closed, and the map is updated (AC-E3, E5, G1, X3, X4 at least).
- `npm run lint ; npm run typecheck ; npm test ; npm run i18n:check` is green.
- The report lists every a11y fix and any justified exclusion.
