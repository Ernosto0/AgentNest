# Today production-readiness fixes

Reviewed and fixed on 2026-11-09 against the current working tree. Verification performed no deployment, real Instagram request, real message or real publication. Temporary databases, browser captures and raw logs remain local under the ignored `.tmp/` directory and are excluded from the source commit.

| Finding | Result |
|---|---|
| Insights commits inside the scheduler transaction | Scheduler callbacks now enqueue separate account jobs. Services flush and the worker owns commits. Daily, weekly and hourly story jobs use persistent period keys, including terminal jobs. The worker closes read transactions before collection and backfills missing days across both 28-day periods. Story collection uses the external Instagram media ID. |
| Failed requests appear healthy or empty | Assistant status distinguishes loading, inactive and unavailable. Failed account reads and pause/resume mutations display errors. Failed calendar/activity reads do not claim an empty feed or disconnected calendar. Failed schedule reads do not create story-gap warnings. |
| Capped and incorrect attention counts | A workspace-scoped `/home/attention` endpoint counts all drafts and visible unanswered comments in SQL. Received owner replies and positively verified reply operations remove a comment from attention; pending, failed and unknown operations do not. Disconnected/foreign accounts are excluded. Staff never receive the draft count. Missing counts remain unknown and prevent all-clear. |
| Incomplete insights presented as zero/full comparisons | Summary responses include current/previous coverage. A metric needs complete daily history before its period total or comparison is shown. Zero previous activity does not invent a 100% increase. Chart gaps stay missing, and the card labels incomplete history. Assistant command narration also preserves unavailable history. |
| Broken reconnect route | The permission warning links to `/more/settings/connections`. |
| Accessibility failures | Insight text contrast is corrected, range state and account selection are labelled, the reconnect link has no nested button, and daily-number trends use valid definition-list markup. Missing values use an accessible dash to fit narrow translated tiles. |

Migration `0044` is verified locally. Its three insights tables have forced row-level security, tenant policies, runtime grants and matching metadata registration. The runtime database-role verification inventory includes the new tables. The generated Today/insights OpenAPI schemas and routes match the runtime definitions.

| Final verification | Evidence |
|---|---|
| Frontend tests | 624 passed across 45 files; `.tmp/today-frontend-final.log` |
| Focused PostgreSQL checks | 18 passed; `.tmp/today-backend-final.log` |
| Production-bundle browser checks | 32 scenarios passed; `.tmp/today-fixed-browser/results.json` |
| Browser coverage | Chromium/WebKit; EN/TR; widths 360, 390, 768, 1024 and 1440; owner/staff, API errors, missing permission, partial history, inactive assistant and multiple accounts |
| Browser outcomes | Zero axe WCAG A/AA violations, horizontal page overflow, unexpected requests or runtime errors; partial-history phone screenshots visually inspected |
| Static checks | Frontend lint, typecheck, localization and production build passed. Scoped backend Ruff and mypy passed. `git diff --check` passed. |

The focused backend checks exercise exact counts beyond the former list limits, verified versus queued replies, workspace/role isolation, incomplete 7/28-day history, scheduler transaction ownership, durable interval deduplication, 56-day initial backfill, two-day refresh, actual worker execution, external story IDs, migration head and all 52 registered tenant-table policies. PostgreSQL runs used only the disposable `agentnest_today_test` database on port 55435.

Broader backend verification is **not green**. An attempted full offline suite and a broader reporting/jobs selection reported failures and were stopped. Isolated checks confirmed the following outside the six Today findings:

- `test_ac2_telegram_daily_summary_matches_web_report`: the response contains the correct count `6`, but the test expects different bold formatting.
- `test_the_report_is_stored_by_the_first_read_of_a_past_day`: the first and second responses serialize the same timestamp as `2026-03-10T21:00:00Z` and `2026-03-11T00:00:00+03:00`; the string-equality assertion fails.
- `test_ac4_core_architectural_isolation_import_linter`: `app/commands/service.py` imports the Telegram client directly, contrary to the architecture assertion.
- `test_dm_customer_checks_availability_and_books_appointment_automatically`: the scenario produces zero appointments where the test expects one.

Those workflows were left outside this fix scope. The isolated traces are in `.tmp/today-backend-investigation.log` and `.tmp/today-backend-broader-failures.log`. The 18 passing focused checks do not establish a passing full backend suite.

These changes address the six Today findings. Application-wide production sign-off still requires resolving broader backend acceptance failures, applying the migration with the release, and separately verifying live Meta permissions/data and actual-device behavior. Offline mocks and browser fixtures do not establish those external gates.
