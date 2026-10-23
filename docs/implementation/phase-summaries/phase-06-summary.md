# Phase 6 summary: Reports, activity, failure UX and demo completion

**Owner Q&A follow-up (2026-10-22):** Q1/Q2 historical snapshot and retention changes, plus Q8 reconnect wording, are implemented in the [Q&A implementation report](../phase-6-sessions/qa-implementation-report.md). The session-11 results below remain the original review record; use the follow-up for the current reporting contract and verification. This does not approve Gate 1.

**Status:** implementation and local review complete; **waiting for review**. **The Local MVP DoD and Gate 1 are not met.** The full E2E run has one unexplained WebKit navigation failure, AC-E3 has a reproduced historical snapshot mismatch, and invariant decisions, an unassisted Windows walkthrough, a real-phone walkthrough and GitHub CI remain open. Phase 7 has not started.

**Date:** 2026-10-22 (Europe/Istanbul). **Scope:** [Phase 6](../phases/phase-06-reporting-and-demo.md), [session plan](../phase-6-sessions/plan.md), sessions 1–11. Phase 5 was treated as accepted with its owner follow-ups already committed. **Branch:** `main`; local commits only, nothing pushed. Separate landing-page changes present before session 11 are preserved and excluded from its commits.

## 1. What changed

| Session | Local commits | Contents |
|---|---|---|
| Plan | `7a10cae` | P6-01–P6-10, H1–H18 and eleven sequential session briefs |
| 1 | `dc447c6`, `6638e51` (P6-01a/b) | Migration 0012, workspace-local day periods, SQL registry of 20 metrics, exact-count/timezone/isolation tests |
| 2 | `5f10869`, `a7e55d3`, `0ccb9b3`, `f94b25b` (P6-01c/d, P6-02a/b) | Live/stored reports, scheduled generation, templated summaries, metric drill-downs, activity-summary and reply/content failure commands, operation detail API |
| 3 | `8b524ab`, `077b138`, `69f8187` (P6-03a/b, P6-01e) | `app/activity/` feed and labels, activity UI, report/date/drill-down UI |
| 4 | `c7910db`, `7c3851d`, `1d7864d` (P6-04a/b/c) | Notification catalog and centre, Home dashboard/status/banners/attention/upcoming/failure cards; content status shortcuts |
| 5 | `80bf96a`, `3e2a3fc` (P6-05a/b) | Migration 0013, windowed circuit breaker, executor pause/half-open, health checks/recovery, reconnect clears revoked-token rules |
| 6 | `edb3e2c`, `be8bfa6` (P6-05c/d) | SQL system-health API, Connections/SystemHealth screens, health-check dev button; completed session 5's full-suite verification |
| 7 | `fd8cf7a`, `dc17647`, `118e378` (P6-06a/b/c) | Migration 0014, hashed single-use expiring invites, member roles/removal/last-owner guard, acceptance and QR/link UI, test formatting fix |
| 8 | `8086701`, `ec9f09c`, `7932b76`, `93ed81e` (P6-07a/b/c) | Yesterday's realistic history, isolated demo reset with new workspace id, transactional history construction/handler loading, E2E seeded-history assertions |
| 9 | `faf6858`, `7ef3917`, `2f54dbf` (P6-08a/b, P6-10a) | Retention, media cleanup and promotion expiry notices; full AC inventory, isolation/simulation/settings/invite tests and seven mutation checks |
| 10 | `dfc8ae7`, `9b3919d`, `e99affc`, `dff93a4`, `60c6957`, `54b9bc7`, `55f325f`, `9ed79b6`, `54a9ce3` (P6-09a–h) | Scenarios E/G, i18n round trip, axe, scroll checks, accessible Home/bell names, exact 390×844 mobile viewports, complete metric checks and bounded test resources. [Report](../phase-6-sessions/s10-report.md) |
| 11 | `a5ae5c7` P6-10b (docs close-out and live account refresh), P6-10c (this summary) | Contract audit and drift fixes, complete local verification, real-time automated Windows walkthrough, a regression-tested fix for stale Home account banners, acceptance/invariant review and owner checklists |

Intermediate operator-ledger commits (`dbddcab`, `0bf3fe2`, `6a25f64`, `68e728c`, `774bd8a`) preserve the questions now collected in §7. There were no session 7–9 narrative reports supplied beyond the ledger, commits and acceptance/mutation inventory; no missing operator decisions are assumed.

## 2. Verification

All commands run on Windows PowerShell 5.1. Backend tests use `agentnest_test`; E2E uses the ordinary `agentnest` demo database on ports **8100/5273**, `npm run dev`, one worker, all three projects, **zero retries**. The separate real-time walkthrough uses `agentnest_s11_walkthrough`, `MEDIA_LOCAL_ROOT=./var/session-11-media`, API **8200** and Vite **5373**, with the ordinary worker clock and default eight-second reply debounce. It uses no future-clock or run-due shortcut.

| Check | Session 11 result |
|---|---|
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed; 452 files already formatted |
| `uv run mypy app evals` | Passed; 243 source files |
| `uv run lint-imports` | Passed; 18 kept, 0 broken |
| `uv run pytest` | **2,531 passed**, 1,100.97 s (18m 20s); no failures or skips |
| `uv run python -m evals run --all --provider fake --strict` | **166/166 passed**, 0 hard failures: interpret 67, extract 12, reply 61, content 26 |
| `npm run lint` / `npm run typecheck` | Passed |
| `npm test` | Initial **31 files, 474 passed**, 82.48 s; final **31 files, 475 passed**, 34.09 s, including the new banner regression |
| `npm run i18n:check` | Passed; 1,154 keys and 735 literal translation calls |
| Existing-checkout setup and production build | Docker Compose, `uv python install 3.12`, `uv sync`, migration head/seed, `npm ci`, `npx playwright install chromium webkit` and `npm run build` passed. `npm ci`: 316 packages, 0 reported vulnerabilities; build emitted the existing large-chunk advisory |
| Export OpenAPI → `npm run gen:api` → `git diff --exit-code -- openapi.json src/api/schema.d.ts` | Passed; no drift |
| `npm run e2e -- --retries=0 --reporter=list,html,json` | **170 passed, 1 failed**, 28.0 min (1,677.10 s); 0 skipped, 0 retries, reporter flaky count 0. WebKit return-link failure detailed below |
| Isolated original WebKit failure, `--project=mobile-webkit --grep 'yesterday.s seeded report' --retries=0 --reporter=list,json` | **1/1 passed**, 32.4 s. Does not erase the full-run failure; root cause is unresolved |
| Scenario G, all three projects, after live account refresh fix | **6/6 passed**, 1.6 min, no retries; WebKit/Chromium mobile and desktop each passed G1 and G3 |
| H1–H18/new-contract documentation presence audit | **53/53 passed**, followed by source review; presence alone does not prove semantic agreement (AC-E3 below) |
| Real-time automated Windows UI walkthrough | A–G and reset completed across the logged checkpoints; **25m 29s wall time including runner corrections/pauses** (15:38:21–16:03:50 UTC). Supporting evidence, not DoD 2 human sign-off |
| Historical snapshot API reproduction | **AC-E3 mismatch confirmed**, exact output in §3; reproduction script succeeded in detecting it |
| `git diff --check` | Passed at documentation review; repeated before commits |
| GitHub CI / CI secret scan | **Not run**. Nothing is pushed; no remote CI result or no-egress guarantee is claimed |

Session 9's seven mutation spot-checks all killed their intended mutants and were reverted. Their named failing tests are in the [AC map](../phase-6-sessions/ac-test-map.md#mutation-spot-checks-session-9-all-reverted); they were not needlessly repeated for documentation changes. Session 10 separately verified the production-build E2E stack: 171/171, then the corrected WebKit viewport 57/57. Those historical results are not substituted for this session's run.

Local evidence is ignored: `backend/var/session-11-evidence/` (check/walkthrough logs, contract audit, read-only reproduction, E2E JSON, G/reset runner and PNGs), `frontend/playwright-report/` (full E2E HTML) and `frontend/test-results/session-11/` (failure trace/context). The HTML reporter cleared the original scratch A–F runner/screenshots stored under its output directory; the separate backend logs remain. Subsequent evidence is stored outside that directory. Raw logs/screenshots are local artifacts, not committed data. Reproduction instructions below are committed so review does not depend on ignored files.

| Full-run project | Result | Viewport |
|---|---|---|
| mobile-webkit | **56 passed, 1 failed** | 390×844 |
| mobile-chromium | **57 passed** | 390×844 |
| desktop-chromium | **57 passed** | Desktop Chrome preset |

**Full-run failure output** (`scenario-e.spec.ts:73`, yesterday's H16 drill-down loop):

```text
Error: expect(locator).toBeVisible() failed
Locator: getByRole('heading', { name: 'Günlük rapor', level: 1 })
Expected: visible
Timeout: 5000ms
Error: element(s) not found
1 failed, 170 passed (28.0m)
```

The trace shows `Rapora dön` was clicked after checking `integration_errors`, but the failure snapshot still shows the **Bağlantı hatası** drill-down. An initial pre-login `/auth/me` 401 is the only console error recorded; it does not establish the navigation cause. The isolated unchanged case passes (17.8 s test body). No timeout/assertion/retry was changed to make it pass; the intermittent failure remains an open AC-X4/DoD issue. The full 171-case suite ran before the small account-refresh fix; the final frontend suite and scenario G cover that subsequent change.

## 3. Acceptance criteria and Local MVP DoD

The complete AC-A1…G5 / AC-X1…X8 test inventory is [ac-test-map.md](../phase-6-sessions/ac-test-map.md). Earlier scenarios are exercised again by the full suites; the inventory is coverage, not proof of remote CI or manual acceptance.

| AC | Evidence and result |
|---|---|
| AC-E1 | `tests/integration/reporting/test_daily_report.py::test_ac_e1_every_metric_has_its_exact_known_value`, registry and cross-workspace tests; all 20 metrics derive from SQL |
| AC-E2 | `::test_ac_e2_records_on_the_local_day_boundaries` (Istanbul, Lisbon summer and both DST transitions); `tests/unit/reporting/test_periods.py` (23/25-hour days) |
| AC-E3 | Same-instant/unchanged-fixture row-set tests, report API tests and `scenario-e.spec.ts` pass their covered cases. **Not fully satisfied:** stored historical snapshot versus current drill-down mismatch reproduced below; a median's duration is not a row count |
| AC-E4 | `tests/integration/commands/test_activity_query.py::test_ac_e4_the_answer_equals_the_reports_number_at_the_same_instant`; scenario E compares command/report inbound counts |
| AC-E5 | `tests/integration/test_simulation_flag.py`, report API tests and scenario E show simulation flags/badges on today/yesterday |
| AC-G1 | `tests/integration/integrations/test_reauth.py`; scenario G1 covers banner, critical notification, held due post, exactly one resumed reply, cleared revoked rule and held post remaining held |
| AC-G2 | `tests/integration/integrations/test_rate_limit.py`: Retry-After and finite attempt budget, frozen clock |
| AC-G3 | `tests/integration/integrations/test_circuit.py`: five failures inside ten minutes, spread-out failures, zero calls while degraded, half-open/health recovery, queued replies and publications; scenario G3 exercises simulator failures and real health-check route |
| AC-X3 | Catalog parity/literal checks, plus `i18n.spec.ts` covering eleven main screens tr → en → tr with no raw keys/interpolation leftovers |
| AC-X4 | Mobile WebKit and Chromium are exactly 390×844; horizontal-scroll checks across main/scenario/failure screens; axe has no disabled rules or excluded elements. **Not fully satisfied in this run:** one WebKit report-return navigation failure, despite its isolated pass |
| AC-X8 | **Pending owner CI run**, despite locally executable pipeline checks |

**AC-E3 reproduction (no production credentials or test mutation).** Fresh `seed --reset`; open Gölkent as owner; run B's new price question/approval, complaint and injection. Read yesterday's report, then follow its snapshot links without regenerating. Session 11's read-only API inspection returned:

```text
date: 2026-10-21
attention_now:        stored_value=2, drilldown_value=4, row_count=4
unanswered_open_now:  stored_value=2, drilldown_value=4, row_count=4
pending_approvals_now: stored_value=1, drilldown_value=2, row_count=2
```

`reporting.service.get_report` returns the saved metrics; `reporting.drilldown.metric_items` calls `compute_metric(..., now)` and builds rows from current state. `api-design.md` already described this limitation, while workflows H1/AC-E3 claimed unconditional equality. Tests compare a report and list before changing their state. **Recommendation:** decide and document historical membership/snapshot storage before implementation; alternatively explicitly identify a current-state destination and obtain acceptance of a changed criterion. Do not silently recompute old reports, hide snapshot links or weaken equality tests. The median should be defined as the median of linked durations. Retention's removal of failed inbound-event rows after 90 days also needs a decision for historical drill-down fidelity/regeneration.

| DoD item | Result |
|---|---|
| 1. AC-A1…G5 and AC-X1…X8 pass **in CI** | **Not met.** No GitHub CI run; full local E2E has one failure, and AC-E3 has a separate contract gap |
| 2. A person follows §1–§6 on Windows without assistance | **Pending human acceptance.** Agent-run PowerShell setup and a real-time automated browser walkthrough provide supporting evidence, not an unassisted person's sign-off. Browser-control inventory was empty and `iab` unavailable |
| 3. Real-phone LAN walkthrough | **Pending owner**; checklist in §4 |
| 4. No open issue against any invariant | **Not met.** INV-09/12/17 decisions in §7 remain unresolved |
| 5. Summaries list limitations, none contradicting the DoD | Limitations are listed honestly. **Not met** while the AC-E3/invariant/manual/CI limitations above contradict items 1–4 |

Do not present Phase 6's implemented scope as an accepted Local MVP or advance through Gate 1 on the basis of green automated tests alone.

## 4. Demo steps and Windows/phone evidence

The complete A–G and reset script is [local-development.md §6](../../operations/local-development.md#6-demo-walkthrough-ag-and-reset). The core presentation can take about 15 minutes; all branches with real retries require about 25–35 minutes. Setup is explicit Windows PowerShell, including preserving an existing `.env`, migrations/seed, the worker, frontend and OpenAPI generation. Session 11 did not clone the existing repository again or overwrite the owner's `.env`.

Setup commands were exercised in the existing checkout, with the isolated database/port substitutions above. Dependency installation was checked after the parallel browser runs to avoid removing in-use `node_modules`; it is not claimed as a literal first-time, sequential §1–§6 installation on a fresh machine. Versions: PowerShell 5.1.26100.9711, Python 3.12.15, uv 0.13.1, Node 24.13.0, npm 11.6.2, Git 2.49.0.windows.1 and Docker Compose 5.1.3.

**Windows automated run:** fresh isolated seed; API with reload, ordinary worker and `npm run dev`; Chromium 390×844. A rejects the discrepancy and shows ready; B approves a grounded price reply and demonstrates complaint/injection escalation; C changes price to 7,000 and checks the next draft; D schedules two minutes ahead (15:39:15 UTC) and reaches published at 15:41:13; E opens the report/drill-down/activity; F first shows retry at 15:44:36 and reaches published at 15:50:36 (exactly one new simulator row), then permanent failure and timeout reconciliation. G shows the red banner/critical notification, due post held and resumed reply; the five-send circuit shows amber at 16:02:09; removing all rules gives **checked 1 / recovered 1** at 16:03:47 and connected Home/system health. Reset at 16:03:50 changes the workspace id and restores **6.000 ₺**. The run was resumed at the noted harness/fix checkpoints; it is not claimed to be one uninterrupted unassisted walkthrough.

**Steps requiring corrections to the original instructions:**

- Setup's bash `cp`, `&&` and inline environment assignment examples needed PowerShell equivalents. Existing unrelated dev/E2E stacks require separate ports/database; session 11 records those substitutions rather than claiming default ports or a new-machine installation.
- A's readiness is already **Hazır**, because Phase 4's account and automation review are seeded. The pending discrepancy is reached through **Öneriler**; it is not an instruction to verify the unrelated student price.
- B's visible reason is **Otomatik gönderim kapalı**; complaints show **Size gerek var** and injection is **needs_human**, with no sendable draft.
- C's monthly-price impact requires a scheduled **price feed post**. D's trial Story uses the promotion fact and does not prove that hold by itself.
- Immediate publication's confirmation is **Onayla ve hemen yayınla**; timed scheduling uses **Onayla ve zamanla**. The report menu is **Günlük rapor**, pagination **Daha fazla göster**.
- F's two rules mean two clicks, each covering one call. The seeded publication means the simulator list is not empty. Wait 1 + 5 minutes for the successful third attempt; run-due cannot move the real clock. Ambiguous publish waits about one minute for reconciliation.
- G needs five different customer drafts approved within the failure window. Hold profile calls with transient rules while inspecting degraded state, then remove remaining rules before the manual health check. Otherwise the periodic probe may recover it before inspection. A post must be scheduled **before** revocation to demonstrate due-time hold.
- **Product defect fixed in session 11:** immediately returning Home after approval could show **bağlı** indefinitely while the persisted account was already `needs_reauth`. `useSocialAccounts` had no periodic refresh. It now polls on the existing four-second inbox interval. `home.test.tsx` **updates failure banners and recovery while Home stays open** failed before the fix (no reauth banner within 6 s), then exercises connected → reauth → degraded → connected without navigation. No server contract changed.
- Temporary runner corrections: its report selector expected `Gelen mesaj 4` instead of the actual accessible name `Gelen mesaj: 4`; it incorrectly expected an empty failure-rule list although consumed/seeded rules stay at `(0)`; it compared the displayed `checking` badge to the ledger's `outcome_unknown`; and a resumed run searched for a child link inside a card that was itself the link. These were runner failures, not weakened product assertions. The corrected runner resumed existing data. The original error logs are retained separately from the official suite.
- The runner also had to wait for the failure-rule list to load before removing it: otherwise its initial zero-row observation skipped removal and the health check correctly returned **checked 1 / recovered 0** while transient profile rules remained. Waiting for the list, removing every row, and checking again produced **1 / 1**. This does not change the documented product behavior or count as a successful first attempt.
- Historical snapshot links can disagree with the saved report (AC-E3); documentation calls this out rather than claiming the demo proves unconditional equality.

**Owner's real-phone checklist (DoD 3):**

1. Complete setup/seed and keep the API and worker running. From `frontend/`, start `npm run dev -- --host 0.0.0.0`; keep `COOKIE_SECURE=false` for this local HTTP demo.
2. Run `ipconfig` in PowerShell; take the Wi-Fi adapter's IPv4 address. Allow Node.js through Windows Firewall on **private networks** if prompted. Phone and computer use the same Wi-Fi.
3. Open `http://<LAN-IP>:5173` on the phone. Vite proxies `/api`; no direct phone connection to API port 8000 is required. Sign in as the seeded owner and choose Gölkent.
4. Follow §6 A–G and reset, including the red/amber banner paths and held-post/retry outcomes. Check Home, Inbox and a conversation, Content and detail/scheduling sheet, Approvals, Knowledge, Reports and drill-down, Activity, Notifications, Members, Connections and System health.
5. Look for no horizontal scroll, usable controls/keyboard/sheets, readable error/next-step text, and simulation badges on every simulated result. Confirm the Home banners clear on recovery and a successful response is never shown before send/publication is confirmed.
6. Record date, phone model, OS/browser, elapsed time and any failures here. **No real phone was available to the agent; emulated WebKit is not iOS Safari acceptance.** An independent person should also complete the Windows script and record assistance needed for DoD 2.

## 5. Deviations from the plan

### 5.1 Planning decisions H1–H18

Checked individually in the named docs; no missing resolution was treated as implicit approval.

| # | Resolution / review note | Recorded in |
|---|---|---|
| H1 | One SQL row set per metric, dedicated drill-down; median lists measured bursts. Historical/current-state equality gap remains (§3) | workflows F/F.1; api-design 2.8 |
| H2 | Staff see thirteen inbox keys; other drill-downs forbidden | workflows F.1; permissions matrix |
| H3 | Today live; past dates stored; explicit regeneration; partial/as-of metadata | workflows F; api-design 2.8 |
| H4 | Five templated sections, zero/null sections omitted, no LLM | workflows F |
| H5 | Today/yesterday/last-seven-days from shared periods/metrics; `command.activity_summary` replaces basic result | workflows B.1/F |
| H6 | Newest seven-day content/reply failure; safe operation detail, plain-language cause/time/next step | workflows B.1/G; api-design 2.8 |
| H7 | Workspace audit feed, groups, date/cursor, actor/resource labels at read time | observability 5; api-design 2.8 |
| H8 | Single notification catalog with severity, permission recipients and unread dedup; account key rename | observability 4.4 |
| H9 | Home composes existing report/account/meta/content endpoints; no dashboard endpoint | user-journeys 1/J6; component-design 6 |
| H10 | Migration 0013 adds circuit-window start; five transient failures in ten minutes; success resets | data-model 3.5/4; workflows G |
| H11 | Degraded executors reschedule without spending attempts; reauth/disconnected due posts held | workflows E/G.2 |
| H12 | Health profile read outside transactions, recovery/resume, mock revoked-rule removal | workflows G.2; integrations 3.3; api-design 2.10 |
| H13 | Workspace health counts; invalid-signature counter explicitly system-wide | observability 6; api-design 2.8 |
| H14 | Hash-only single-use seven-day invites; browser-origin QR; last-owner protection. Acceptance has the same CSRF exemption as login | api-design 2.2; data-model 3.1; observability 4/5; security 3 |
| H15 | Reset creates new workspace id; preserves old audit rows, removes local demo data/media | local-development 8; api-design 2.10 |
| H16 | Real seeded history paths, frozen yesterday, one transaction, exact 6 inbound/4 replies/1 escalation/1 published/1 failed; no nonperiodic queued jobs | local-development 5/6 |
| H17 | Global batched retention, count-only audit; no audit purge pending ADR; INV-17 exception unresolved | security 8; environment variables and `.env.example`; background-jobs |
| H18 | Orphan/old-published media cleanup; verified promotion expiry notices at local 09:00 | background-jobs; business-knowledge 4; security 8 |

Session 11 also added the explicit migration 0012–0014 index to data-model, missing invite errors and degraded/recovered notification rows to observability, actual backend package locations and frontend components/routes to component-design, and the precise invite CSRF behavior to api-design. No migration, endpoint, error code, notification type or job contract was introduced in session 11.

### 5.2 Deviations found while building, by session

| Session | Deviation / disposition |
|---|---|
| 1 | Answered burst begins with first inbound in the period and ends with next outbound before period end; deleted inbound ignored, median rounded to one decimal. Half-open periods exclude records at exactly `now`. Messaging-window constant is duplicated in reporting to avoid service imports and checked for equality |
| 2 | Interrupted first attempt resumed from correct commits; rewritten activity executor removes the old Phase 6 placeholder docstring. Missing per-bullet narrative evidence is supplied by the AC map |
| 3 | Activity lives in `app/activity/`, preserving audit's core-only import rule. `operation.*` is system group; activity links are strings. Nonempty report rows use frontend labels and server section titles so values are links. Catalog audit-name corrections recorded. One content rendering test failed once, then passed twice; later worker cap and full tests cover it |
| 4 | `/content?status=on_hold` now maps to Problems, closing session 3's shortcut issue. Bell moved from sheet to page. Home failure card counts today's failed content; needs-human uses the broader attention metric. Old unread account dedup keys are not migrated; one extra notification is possible. Alternate E2E ports avoid stale owner dev servers |
| 5 | Existing publish retry test now expects healthy account/counter 1 when attempts are spread outside ten minutes. Full-suite gap after commit split was closed in session 6 (2,438 passed). Draft policy R1 still requires connected; send/publish pause enforces degraded behavior. Half-open skips quota read for a nonconnected account and lets provider publish enforce it. Unread degraded notifications dedup across cycles |
| 6 | Health fields renamed to `connection_expires_at`, `input_units`, `output_units` to avoid schema secret-field scans; `degraded_until` serialization fixed. Account/on-hold links target Connections. Unknown codes get plain-language fallback. Dev DB migrated to 0013; accidental formatter churn reverted |
| 7 | Invites accept signed out/new or signed in/existing, but the endpoint is **CSRF-exempt in both cases**, matching login; no claim that a CSRF header protects acceptance. This behavior is documented/tested, with security review question in §7 |
| 8 | History construction moved into one transaction after worker/E2E races exposed partial history; handlers loaded before running jobs. Seeded-history E2E assertions updated; product behavior not weakened |
| 9 | Retention implementation is `app/retention/`, not `core/retention.py`. Media deletion has no audit event because the catalog lacked one. Failed inbound-event rows disappear after 90 days, so historical `integration_errors` regeneration can change. All seven planned mutations killed and reverted |
| 10 | Real G3 API/simulator path; G1 future deadline uses existing `FrozenClock` subprocess hook. Accessibility fixes retain all axe rules/elements. Four-worker Vitest cap and complete scenario budgets address resource/deadline races. Corrected iPhone preset viewport to exact 390×844 and reran WebKit, with both-mobile viewport guards |
| 11 | Separate landing work was preserved and excluded; another session committed it as `559c1c4` during this run. Automated Windows walkthrough is supporting evidence only; human acceptance remains open. Stale Home account state fixed with polling and a regression test. E2E CI job budget raised from 25 to 60 minutes after session 10's full run took 42.9 minutes; assertions/retries/test deadlines unchanged. Full-run WebKit failure and snapshot mismatch are reported; neither is silently waived |

## 6. Known limitations

- **Contradicts the DoD:** AC-E3's historical snapshot/list equality is not satisfied after state changes (§3). Retention can also remove historical contributing inbound events. Current green equality tests do not cover that lifecycle.
- **Contradicts the DoD:** one WebKit report-return failure in the full E2E run. The isolated unchanged rerun passes, so it needs investigation rather than a claim that the full suite is green.
- **Contradicts the DoD until reviewed:** invariant interpretation/ADR questions in §7; human Windows/real-phone acceptance and remote CI are absent. No blanket invariant or Local MVP sign-off is claimed.
- No real Meta, deployment, email delivery, Telegram, video, Reels or carousels; these remain explicitly out of this local simulated phase. Fake-model success is not evidence of real-model quality or of the Meta adapter.
- Retention uses global settings only; no audit purge. Audit rows grow, including preserved orphaned rows from demo resets. Media cleanup is now implemented, closing Phase 5's orphan-file limitation.
- Held content requires owner re-approval after reconnect/fact changes. Queued replies resume only while their windows/deadlines allow it. Unread account notification dedup may suppress another cycle until read.
- Phase 5's upload buffering, typed-value grounding by value rather than meaning, optional container media id, mock create-container timeout behavior and CONTAINS_PRICING fake-model limitation remain as recorded there.
- A 20:00 scheduled report remains partial unless explicitly regenerated; reading a stored past day does not automatically complete it. This is H3's documented behavior.

## 7. Open questions for review

**Gate 1 decisions and invariant review:**

| Item | Invariant / criterion | Recommendation |
|---|---|---|
| Historical snapshot membership and retention fidelity | AC-E3; INV-08 reporting evidence | Resolve the H1/H3 conflict, specify immutable contributing membership or explicitly current-state destinations, add lifecycle tests and retain the failing reproduction in the review record. Decide median wording and regeneration after retention together |
| Intermittent WebKit report-return navigation | AC-X4; DoD 1 | Investigate the retained trace and reproduce navigation after the integration-errors drill-down. The isolated case passed, but no root cause/fix was established. Require a clean full run before acceptance; do not hide it with retries |
| Phase 5 Q6: media assets and simulator containers lack `is_simulated` | INV-09 | Reusable uploads may predate account selection; decide whether flags are required there or the invariant explicitly excludes reusable media/internal simulator tables while requiring every exposed provider result to remain flagged. Any invariant-text change needs an ADR; do not waive it in this summary |
| H17 audit purge | INV-12 | Keep **no application audit delete path** in Phase 6. Before a two-year purge, approve an ADR defining a separate privileged purge identity, retention boundaries and production DB privileges. Deferring deletion currently preserves append-only behavior; the retention decision remains open |
| H17 message/draft text redaction at 365 days | INV-17 | The plan/security doc sanctions nulling immutable historical text, but invariants.md does not. Approve an ADR narrowly defining privacy redaction while preserving metadata/audit/report counts; do not edit the invariant without it |
| Media cleanup `ready → deleted` has no audit event | INV-12 | Decide whether this is an important auditable state change. Recommended follow-up: catalog a content-free media-deletion action and record it with the row transition, including retry/idempotency tests. No new action was invented during docs close-out |
| Owner evidence | AC-X8; DoD 1–3 | Independently run the corrected Windows/phone scripts. After review, the owner must push `main` or authorize a branch/PR, run `.github/workflows/ci.yml`, inspect all four jobs (backend/frontend/E2E/security), and add the run URL/results here. Nothing was pushed and GitHub CI has not run |

**Carried operator and Phase 5 questions (not silently closed):**

- Session 1's answered-burst rule/one-decimal median awaits confirmation; recommendation: retain the documented rule and its boundary tests, clarifying that linked durations explain the median.
- Session 6's `ACCOUNT_NEEDS_REAUTH` text still says “Ayarlar'da Yeniden bağla”; the actual connection screen is a direct More entry. Recommendation: align the next wording update with **Instagram bağlantısı**, in both catalogs.
- Phase 5 **Q2:** can the future Meta adapter obtain the optional `ContainerStatus.media_id` used by reconciliation? Verify in the Phase 7 research track before relying on it.
- Phase 5 **Q5:** staff can see the pending item's status/approval expiry. Recommendation: retain read visibility while leaving approval permission server-enforced.
- Phase 5 **Q7:** one deliberately broken T2-commit mutation appeared to hang in Phase 5; unmutated suites pass. Recommendation: investigate with a bounded diagnostic test before changing crash/reconciliation behavior.
- Phase 5 **Q8:** typed caption grounding matches verified values without semantic day/subject matching. Recommendation: keep human review and explicitly decide the limitation before real customers; do not claim semantic grounding.
- Phase 5 **Q9:** mock `timeout_after_success` also affects create-container (documented). Recommendation: retain the documented simulation unless the adapter contract requires narrowing; keep reconciliation/idempotency tests.
- Phase 5 **Q10 residual:** the configured real-model reasoning-effort enum has a documented mismatch. Default fake/local behavior is unaffected; verify the adapter's accepted efforts before enabling a real model. No paid calls or new provider research were performed in session 11.
- Phase 5 Q1/Q3/Q4 and Q10's model-id decision are already resolved in the owner commits preceding this phase. They are not reopened here. Phase 6's missing on-hold shortcut and session 5's final full-suite gap were closed in sessions 4 and 6 respectively.

**Stop for review here.** Session 11 closes the implementation review and records unmet gates; it does not approve them, push changes or start Phase 7.
