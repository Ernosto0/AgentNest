# Session 10: E2E completion report

Date: 2026-10-22. Scope: P6-09 only. Session 11 has not started.

## Continuation

The previous attempt had already committed P6-09a–g through `9ed79b6`. This continuation preserves those commits and the separate, uncommitted landing-page work. Nothing is pushed.

Additional changes:

- Both mobile projects now run at exactly 390×844; desktop remains a separate project. The navigation spec asserts the exact mobile viewport, since the iPhone 13 preset's physical screen is 390×844 but its default viewport is 390×664.
- Scenarios A–D/F use the shared horizontal-scroll assertion after each test. The accessibility and language specs check every main screen; E/G also check their report, drill-down and failure screens.
- The language spec checks all eleven main screens in Turkish, English and Turkish again, including raw-key and interpolation checks on each pass.
- Scenario E checks every nonzero metric on both today's and yesterday's reports, including the snapshot metrics outside the nine H16 seed counts. A duration median opens its answered-burst rows rather than being treated as a count. Pagination waits for rows instead of sleeping.
- Scenario G advances the scheduled-post deadline using the existing injected `FrozenClock` job hook. Reconnect must add exactly one outbound reply to the seeded conversation, clear the revoked-token rule and leave held content held. The degraded path uses real simulator failures and the dev health-check route; no component-only fallback is used.
- The default scenario timeout allows 60 seconds for reseeding, browser setup and actions. F and immediate publication have 90-second budgets so their outcome assertions can finish; E has three minutes for opening every metric in mobile WebKit, and uses the screen's return link instead of repeated full reloads. G1's former five-minute budget is reduced to two minutes. Assertion conditions are unchanged or stronger.
- Vitest uses at most four workers. An unrestricted concurrent run exhausted its short rendering waits on this Windows machine; the worker cap controls resource use without changing assertions or retrying failures.
- The acceptance map, testing strategy and local-development instructions match this coverage. The walkthrough correctly says that reconnect clears `auth_revoked` rules only.

## Accessibility fixes and exclusions

The previous session-10 commits made two product fixes:

1. Home attention links derive their accessible names from their visible text, instead of an overriding `aria-label` that omitted visible words (`54b9bc7`).
2. The notification bell's accessible name includes its visible `9+` badge when there are ten or more unread notifications (`55f325f`).

No axe rules are disabled and no elements are excluded. Serious and critical violations fail the spec. The screen inventory includes Home, Inbox, a conversation, Content and its detail, Approvals and its sheet, Knowledge, Reports and a drill-down, Activity, Notifications, Members, Connections, System health, login and invite acceptance. Additional screens include More, Settings, pricing, automation and the dev panel.

## Verification

- `npm run lint`: passed.
- `npm run typecheck`: passed.
- `npm test`: 31 files, 474 tests passed with the four-worker cap.
- `npm run i18n:check`: passed; 1,154 keys and 735 literal translation calls checked.
- `git diff --check`: passed.

The full production-build run passed **171/171** in **42.9 minutes**, with zero skipped, unexpected or flaky tests. It ran with `CI=true`, `E2E_API_PORT=8100`, `E2E_WEB_PORT=5273`, and `npm run e2e -- --retries=0 --reporter=list,html,json` so the default development servers were left alone.

After correcting the WebKit viewport, `npm run e2e -- --project=mobile-webkit --retries=0 --reporter=list,html,json` passed **57/57** in **10.1 minutes**, again with zero skipped, unexpected or flaky tests. The Chromium configuration was unchanged from the full run.

| Project | Final verified viewport | Specs passed | Project time |
|---|---|---|---|
| mobile-webkit | 390×844 | 57/57 | 9m 36s |
| mobile-chromium | 390×844 | 57/57 | 12m 39s |
| desktop-chromium | Desktop Chrome preset | 57/57 | 11m 38s |

Project time is the interval from its first test's start to its last test's finish in the JSON report, excluding shared stack startup/global setup. WebKit's time is from its corrected-viewport rerun; the other two are from the full run.

The new exact-viewport assertion passed on both mobile projects: `npm run e2e -- --project=mobile-webkit --project=mobile-chromium --grep "navigation adapts" --retries=0 --reporter=list,html,json` (**2/2**, 34.4 seconds).

Local evidence is kept in the ignored `frontend/playwright-report/` directory: the full HTML report, `webkit-390x844/`, `viewport-guards/`, and `session-10-evidence/` (JSON results and logs).

## Commit

`P6-09h: complete session 10 E2E coverage and verification` is the local continuation commit. Nothing is pushed. The remaining uncommitted landing-page files and documentation belong to the separate work present at the start of this session.

## Deviations and questions

- The dev run-due endpoint runs only jobs due at real time. For G1's future deadline, the E2E helper invokes the existing `jobs.testing.run_due_jobs(FrozenClock(...))` in a subprocess. The API and worker retain their real clocks; no API contract, database scheduling record or production clock implementation changes.
- The prior run's 30-second test deadline could interrupt a 60-second publish assertion. Budgets now include fixture setup and the full assertion period; no retries are used for the final verification run.
- The full run used the iPhone preset's default 390×664 viewport; its physical screen had been mistaken for the viewport. WebKit is explicitly overridden to 390×844 and all its specs are rerun after that correction. Mobile Chromium was already explicitly 390×844 in the full run.
- No new blocking architecture questions. Earlier phase questions remain for session 11's review.
- Windows/real-phone walkthroughs, the full phase DoD and the phase summary belong to session 11. This report does not claim those checks or a remote CI run.
