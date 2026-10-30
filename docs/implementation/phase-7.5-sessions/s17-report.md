# Session 17 report: evaluation and end-to-end verification

**Status: offline regression checks complete; journey breadth and model-quality gates pending.**
This report records completed checks and keeps open gates visible until their required
evidence exists. Baseline: `main` at `f0d95f9`, clean worktree when work began. Session 18
made independent changes in the shared worktree; its files are outside this
session's implementation scope.

## Implemented verification

- Versioned `s17-scripted-v1` contains 60 two-turn customer prompts across
  beauty/wellness, retail and fitness in Turkish and English. Every row uses
  the same fake `reply.validate` → customer wait → `reply.validate` path through
  real durable jobs, with a new worker for turn two. The test checks current
  verified fact rendering, broker observation and final persisted completion.
  Scenario labels describe prompt inputs; they do **not** prove the fake chose
  the right behavior for owner waits, approvals, moderation, private replies,
  content, injections or unsupported requests. In particular, the generic
  scripted answer may be semantically wrong for those prompts.
- `python -m evals.account_agent` is a separate offline mechanics command and
  CI gate. Alongside the 60 cases, it selects existing integration journeys
  for owner answer/resume through the mock send ledger, exact human approval,
  public context isolation, moderation/reconciliation, private-reply linkage
  and owner content clarification. The legacy
  `evals run --all` remains the bounded-task evaluator.
- CI backend job timeout is 60 minutes. The initial local full backend suite
  took 27.5 minutes before the separate journey gate; the former 20-minute
  timeout could abort the required run. The new value is headroom, not a
  performance claim about Linux CI.
- Corrected a frontend regression test mock: the automation page now requests
  an account-agent overview before showing legacy connection capabilities.
  The mock supplies the actual legacy-mode response.
- Browser regression triage found archived fact cards sharing the same test ID
  as current facts, and E2E expectations referring to the old Harbor Pilates
  seed name and old approvals intro. Archived cards now have an explicit
  `archived-fact-*` test ID; E2E text was aligned to the current product copy.
  A separate content generation failure found that the fake price matcher
  treated "bir gönderi" as a product qualifier and dropped a verified price.
  Those post-objective words are now ignored; its focused unit test passed.
- The next complete browser run found a separate category grouping bug: a broad
  pattern and a fixed template item rendered the same fact twice. Category entries
  now reserve fixed keys and assign each fact once. A focused model test and the
  full frontend unit suite cover the fix.
- The first full backend run exposed four stale or missing cross-cutting
  assertions: the inbox row now includes `social_account_id`; mock accounts
  expose comment capabilities; the permission matrix test lacked Phase 7.5
  keys; and `agent.content_applied` lacked an Activity group and TR/EN text.
  The first three tests now assert the actual contract, and Activity can render
  the new audit action. A focused rerun passed all eight related tests.

## Verification evidence

Windows PowerShell, Python 3.12 through `python -m uv`, PostgreSQL 16 Docker,
fake LLM and mock Instagram. The browser run uses a dedicated disposable
`agentnest_s17_e2e_test` database and `CI=true` production build. No paid model
call or live Instagram action was authorized or run.

| Check | Result |
|---|---|
| `python -m uv run pytest tests/integration/agent/test_initial_journeys.py -q --tb=short` | **61 passed**, 131.49 s; dataset shape plus 60 durable two-turn cases |
| `python -m uv run python -m evals run --all --provider fake --strict --no-report` | **166/166 passed** across four legacy bounded tasks; zero hard failures |
| `npm.cmd test -- --run` | Initial full run: **514 passed, 1 failed** because the old test mock omitted the newly required agent overview response. Fixed mock; clean full rerun: **515 passed** across 33 files. After the category grouping fix: **516 passed** across 33 files. |
| `python -m uv run pytest tests/unit/ai/test_draft_content_task.py -q --tb=short` | **30 passed** after price matcher fix. |
| Frontend lint, typecheck, i18n, build | Passed after the fact-card/E2E changes; production build emitted its existing large-chunk advisory. |
| Generated API client | `export-openapi`, `npm.cmd run gen:api`, and `git diff --exit-code -- openapi.json src/api/schema.d.ts` passed with no drift. |
| Backend Ruff, format, mypy, import rules | Passed after the evaluator and matching changes; Ruff format checked 563 files, mypy checked 298 source files, 19 import contracts kept. |
| Full backend `pytest` | Initial full run: **3300 passed, 10 skipped, 4 failed** in 1647.48 s. Failures were inbox list row, mock capability names, permission matrix and Activity catalog; each was fixed and focused rerun was **8 passed**. First clean rerun was interrupted by a Docker Desktop/Postgres restart; its DB errors are captured in `backend/var/ci/s17-backend-rerun.log` and are not a pass. Final sequential full rerun: **3307 passed, 10 intentionally skipped** in 1851.60 s; log `backend/var/ci/s17-backend-clean.log`. |
| Dedicated agent journey command | First run on separate `agentnest_s17_journey_test`: **66 passed** in 446.44 s. Final run with moderation and private-reply cases: **69 passed** in 112.63 s. |
| Production-build Playwright, all three projects | Initial complete run: **140 passed, 37 failed, 3 skipped** in 27.5 minutes. Its contexts/traces are at `frontend/var/ci/s17-initial-e2e/`. Failure groups: stale Harbor seed name and approvals copy, duplicate fact cards, missed verified price in fake content generation, and one G3 `seed --reset` command failure. The first rerun timed out during Postgres crash recovery before browser tests (`frontend/var/ci/s17-e2e-rerun.log`). The next complete run: **153 passed, 24 failed, 3 skipped** in 22.7 minutes; all 24 failures were eight duplicate-card cases on each browser, with contexts/traces saved at `frontend/var/ci/s17-second-e2e/`. Final clean production-build run: **177 passed, 3 skipped, zero failed** in 24.7 minutes across mobile WebKit, mobile Chromium and desktop Chromium; log `frontend/var/ci/s17-e2e-final.log`. The three skips are `agent-work.spec.ts` on each project because `E2E_FIXTURE_DATABASE_URL` and its dedicated API container were not configured; Session 15 separately ran that spec on all three projects, but this run does not repeat it. Initial launch failed because `uv.exe` was absent from PATH; adding its installed Scripts directory started the stack. |

## Acceptance mapping

The applicable automated checks in Sessions 01–16 remain the baseline evidence.
This session adds the clean full-suite and browser results above; no row below is a
claim of complete phase acceptance. The 60 scripted prompts share one mechanical
path, so the requested 60 varied behavioral journeys and real-model quality gate
remain open even though the regression suites pass.

| AC75 | Current evidence and remaining gate |
|---|---|
| 01 | Multi-topic/unclassified prompts appear in the 60-case set, but the fixed fake replies do not prove useful handling. Session 06 grounding and Session 07 DM tests support mechanics; real-model quality pending. |
| 02 | 60 scripted two-turn cases pass after a worker restart; Session 07 DM tests cover conversation progression. Their fixed replies do not prove that customer details affect later answers. |
| 03 | Session 06 personality persistence and Session 14 settings/UI tests provide offline evidence; TR/EN real-model tone and continuity pending. |
| 04 | Session 08 memory retrieval/restart and exclusion tests provide offline evidence; this scripted set does not test memory relevance. |
| 05 | Session 03 delegation, Session 06 grounding/injection and Session 08 memory scope tests enforce no promotion of customer claims; full backend regression passed. |
| 06 | Session 09 owner-question report; focused owner answer/resume journey selected for command. Real-model choice pending. |
| 07 | Session 09 owner-question/permission tests; full backend regression passed. |
| 08 | Session 07/09 stale-message, fact and takeover tests; full backend regression passed. |
| 09 | Session 10/11 comment reports and comment integration tests; authentic Meta evidence pending. |
| 10 | Session 11 moderation operation/policy tests; authentic Meta evidence pending. |
| 11 | Session 12 reservation and Session 16 adapter tests; real eligibility and DM linkage pending. |
| 12 | Session 08 memory and Session 10/12 public/private scope tests; focused public broker isolation selected for command. |
| 13 | Session 13 owner-content tests; focused owner clarification selected for command; full backend regression passed. |
| 14 | Session 04 model step/adapter contract tests; real-model tool selection unmeasured. |
| 15 | Session 05/07/11/12 commit-level recovery tests; full backend regression passed. |
| 16 | Session 07 and 16 unknown-outcome tests; full backend regression passed; real reconciliation pending. |
| 17 | Session 03/07 lifecycle tests and Session 18 rollback rehearsal; full backend regression passed. |
| 18 | Session 08 privacy/erasure tests; full backend regression passed. |
| 19 | Earlier isolation/security suites and Session 16 source-ownership checks; full backend regression passed. |
| 20 | Frontend unit suite passed after fix; three-project production E2E passed. Real phone TR/EN walkthrough pending. |
| 21 | Session 04/05 budget/runtime tests; full backend regression passed; real cost/latency ceiling unset. |
| 22 | Legacy fake evals 166/166; backend/browser regression passed. |
| 23 | Session 16 synthetic adapter only; real Meta application evidence pending and capabilities disabled. |
| 24 | Session 13 owner-task integration/UI tests; full backend regression passed. |

## Quality, performance and handoff

G7.5-C is **pending**. There is no authorized real-model spend budget, model
journey run or 20-journey human-rated sample. Accordingly, success, tone,
unnecessary interruption, privacy and critical-value rates cannot be inferred
from this scripted fake set. No model/prompt price or per-turn latency/cost
report is claimed. The durable test's total runtime is a test-run metric, not
customer latency. The phase thresholds remain unchanged.

Session 18 can use the implemented offline paths for rollback/runbook work but
must retain real-model, authentic platform, founder account and real-phone
gates as pending. Real capabilities remain disabled per Session 16. Migration
head remains `0030`; this session adds no schema or production permission.
