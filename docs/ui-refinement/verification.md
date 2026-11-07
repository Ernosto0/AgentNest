# Verification record

Final source verification on 2026-11-07:

| Check | Outcome |
| --- | --- |
| `npm.cmd run build` | Passed; existing large JavaScript chunk warning remains (971.84 kB / 270.28 kB gzip) |
| `npm.cmd run typecheck` | Passed |
| `npm.cmd run lint` | Passed |
| `npm.cmd run i18n:check` | Passed: English and Turkish, 1600 keys |
| `node node_modules/vitest/vitest.mjs run --pool=threads --maxWorkers=2 --reporter=verbose` | Passed: 45 files, 595 tests |
| Focused regression reruns after late refinements | Passed: 50 app/knowledge/report tests and 18 health/command tests |
| Palette comparison against HEAD | Passed: all 28 hex color tokens unchanged |
| `git diff --check` | Passed |
| Production fixture browser journeys | Passed: 22 suites / 180 scenarios, Chromium and WebKit |
| Public legal, password reset and not-found pages | Passed: 40 checks, Chromium and WebKit |
| Recorded uncaught browser runtime errors | None |

All 220 browser scenarios passed. Consolidated counts and production bundle names are in `checks/summary.json`; per-suite outcomes are in `checks/results.json`. Screenshots were reviewed across desktop and phone layouts, including intermediate report, connection, timeline and diagnostics pages.

Browser verification uses the production build with isolated API fixtures. It does not contact live Instagram, send messages, publish content, or run the real backend E2E stack. Representative widths are 390, 768, 1024, and 1440px; shell checks additionally cover 1920px. Chromium and WebKit are exercised. Journeys include dialogs, focus restoration, navigation, permissions, form interaction, accessibility scans, page errors and overflow checks, with details varying by suite.

Earlier attempts encountered Windows memory pressure and a full disk. They are not counted as clean final verification. Disk space was restored before the successful final build and full test run.

The fixture adapter corrects legacy data mistakes: a missing authentication error code, mismatched approval/metric identifiers, an incorrect rendered-fact span, unsupported readiness codes, and missing workspace/session/deletion/channel metadata. The login journey explicitly waits for the email field before its accessibility scan. Old contrast-rule exclusions are removed. Intermediate report, activity, connection, health and developer screens are captured individually rather than saving only the last screen in a journey. Workspace not-found recovery is also scanned.

The existing dashboard changes and matching updates in `frontend/e2e/scenario-g.spec.ts`, `frontend/scripts/ui-today.mjs`, and `frontend/src/features/home/home.test.tsx` are included with the refinement so the committed interface and tests remain consistent. The unrelated `.railwayignore` is excluded. No push was made.
