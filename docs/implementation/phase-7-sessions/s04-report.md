# Phase 7 Session 4: Connections UI, manual probes and offline close-out

**Date:** 2026-10-23 (Europe/Istanbul). **Scope:** P7-02b, P7-09b harness and P7-10; P7-00 live research remains pending. **Status:** offline implementation/verification complete; operator accepted after independent code/docs, component/JUnit and mobile screenshot review. Started from clean local `main` at `c59ea26`, after the operator accepted Sessions 1-3. No subagents, pushes, live calls, public tunnel, deployment, App Review, credentials collection or development-data reset/migration were performed. Gates 1/2 and all live acceptance remain pending.

## Changes

- Public `/api/v1/meta` now exposes deterministic typed `instagram_providers` and `mock_requires_demo_workspace`, with no secrets. Backend policy tests cover development/tools-off and production demo-only behavior; existing eligibility cases run with tools disabled. Callback OpenAPI declares the actual bodyless 303 redirect. Exported OpenAPI and regenerated TypeScript include the Session 3 OAuth/disconnect request schemas and Session 4 public policy; repeat generation hashes match.
- Connections uses backend provider policy and `workspace.is_demo`, owner-only connect/reconnect, real `window.location.assign` navigation, provider-enabled controls and shared pending locks. A Meta `needs_reauth` account starts reconnect with purpose/account ID; actual real accounts show no simulated badge. Safe catalog-only success/error callback banners dismiss without losing unrelated URL parameters; unknown query values never reach product text. Added tr/en OAuth errors and connection copy.
- Disconnect resets the optional history checkbox to false on open/cancel, submits the explicit boolean, handles failures visibly inside the still-actionable sheet, and prevents duplicate pending actions. Erasure removes workspace history caches; all affected account/inbox/approval/content/health/notification/activity/report views refresh. Copy explains send-verification delay and held-post reapproval, without implying immediate erasure or unrestricted reconnect. The global demo notice now scopes simulation claims to labelled actions while explaining that real connections affect real accounts.
- Manual `meta_live` harness skips without both explicit live inputs; optional recipient/image inputs separately opt into one real DM/post. It performs profile/quota reads, exact-ID outbound lookup and bounded media polling/permalink reads. No automatic side-effect retry, live object/URL/exception output or recorder. Offline unit tests prove both-input gating and exception-context suppression. Future direct adapter probes intentionally bypass persistence; product sends/publishes retain the ledger.
- Same-origin frontend5173 HTTPS tunnel instructions, exact Vite host allow-list, public-origin sign-in, token-ring command, provisional Meta dashboard checklist, S3/R2/MinIO signing/fetch setup and troubleshooting. Architecture/API/data/workflow/security/observability/environment/research/phase/roadmap/task contracts and [Phase 7 summary](../phase-summaries/phase-07-summary.md) map AC1-7 to offline evidence versus pending manual/live checks.

## Verification

| Check | Result |
|---|---|
| Focused backend public-policy/account/manual gating suite | 43 passed, 4 intentionally skipped in 10.66 seconds |
| Offline manual-harness safety tests | 4 passed in 0.04 seconds |
| Final backend Ruff check/format, mypy app evals, import contracts | Passed; 476 formatted files, 251 typed sources, 19 kept / 0 broken |
| Full backend pytest with log/JUnit | 2,904 passed, 4 intentional manual-live skips in 720.83 seconds (12m00s); both required live inputs explicitly blank |
| Frontend lint/typecheck | Passed |
| Full frontend Vitest | 497 passed, 31 files, 40.81 seconds; JUnit zero failures/errors |
| Operator independent Connections test run | 28 passed in 8.48 seconds |
| Final locale-only Connections/i18n/build verification | 28 passed in 6.57 seconds; i18n 1,170 keys / 743 literal calls checked; build passed (508 ms) |
| Strict fake evals (`--all --provider fake --strict`) | 166/166 passed, zero hard failures (67 command / 12 extraction / 61 reply / 26 content) |
| Local route-stub Chromium smoke, 390×844 | 10 checks passed; screenshots visually reviewed; all external requests intercepted; no backend/database/live proof |
| Repeat OpenAPI/type generation | SHA256 matches on consecutive exports/generation; postcommit zero-drift check recorded below |
| `git diff --check` | Passed; scoped staged checks passed before each commit |

Evidence is retained under ignored `backend/var/phase7-evidence/s04-*` (logs, JUnit, browser script/results and two mobile screenshots); eval report `backend/evals/reports/20261023T182828Z-fake.{md,json}`. Test database resolved explicitly to `localhost:5433/agentnest_test` immediately before pytest, with the existing `_test` guard unchanged. Only one DB pytest process runs at a time. Existing healthy Postgres service was reused; no development database/data was reset or migrated. Required live credentials were explicitly blanked in focused/full pytest so inherited process credentials could not cause a real request.

The operator independently confirmed backend JUnit: 2,908 total, 2,904 passes, four explicitly skipped manual probes, zero failures/errors, suite time 720.291 seconds. Frontend JUnit confirms 497 tests with zero failures/errors. The first stable full backend run passed; there was no failed/interrupted Session 4 full backend run. The build reports an existing large-chunk advisory; it exits successfully. Local Chromium route-stub verification passed before and after the locale-only accuracy correction; the operator visually reviewed both mobile screenshots.

The first full frontend run failed one existing assertion (496 passed / 1 failed): `findByTestId("preview-media")` matched a loading paragraph before the image's blob URL existed. `waitFor` now applies the same exact blob-src assertion in the two existing affected tests; runtime preview code and expectations are unchanged. The failed full log/XML are retained as `s04-frontend-pre-media-wait-failure.*`; the later full run passed all 497. The first focused UI authoring run had two test errors (Vitest empty-array parameter expansion and an ambiguous `role=status` query); the next had the remaining status-query ambiguity, retained as `s04-frontend-focused-failure.log`. The first authoring-run output was not archived; it is reported here, not claimed retained. These were fixed with an explicit object parameter table and scoped banner assertion. Initial Ruff generic/import/parametrize and test-only optional-array-access type errors were corrected before final checks. A PowerShell pipe replaced new Turkish literal characters during early authoring; those texts were rewritten through UTF-8 patches before passing tests/browser review.

## Adaptations and pending boundaries

The operator accepted the public policy flag, callback303 declaration, cached-history removal, modal-error visibility, accurate demo notice, bounded harness lookback/quota checks and async image test correction. Backend contracts from Sessions 1-3 remain intact: Meta/S3 requirement, actual grants, disconnect/credential/state fences, workspace mutex and send-safe deferred erasure. No fixtures are relabelled as recordings. Live research pages returned 429; public Vite/Cloudflare docs support only configuration instructions. Gates 1/2, V-01/V-02/V-03/V-05/V-08/V-09, P7-00 final re-plan, founder/tester/live/S3 acceptance, CI and Phase 8 stay pending. The browser smoke proves synthetic UI/layout behavior only; it is not an unassisted Windows/phone walkthrough or a backend/live integration test.

## Local commits and handoff

- `708dc27` — `P7-02b: frontend Connections OAuth connect, reconnect, callback banner and disconnect options` (UI/API/schema/tests and matching contracts).
- `cdcc882` — `P7-09b: live Meta contract test suite (-m meta_live)` (unrun manual harness, offline safety tests, empty environment examples and matching docs).
- The following `P7-10: tunnel and Meta setup docs, platform capabilities update and Phase 7 summary` commit contains the final setup/research/status/report docs; its exact SHA is supplied in the handoff rather than embedded into itself.

After the first two commits, OpenAPI was re-exported and `npm run gen:api` rerun. `git diff --exit-code -- openapi.json src/api/schema.d.ts` returned zero against committed generated files, not the old pre-session HEAD. The same check is repeated after the final documentation commit and saved in `s04-schema-postcommit.log`. Consecutive generation hashes were already equal before committing (`s04-schema-determinism.log`). Final working-tree/commit evidence is supplied in the handoff. Nothing is pushed, and this child stops at the accepted offline Session 4 boundary.
