# Session 17: Evaluation and end-to-end verification

**Task:** P7.5-17. **Status:** Planned. **Prerequisite:** Sessions 01-16 offline deliverables; external capability gaps explicitly listed.
Read the [common session rules](phase-7.5-sessions.md) and phase section 13 in full.

## Goal

Prove the complete agent workflow, model behavior, isolation and recovery under realistic multi-turn and failure scenarios.

## Read first

Existing eval runner/datasets, backend test fixtures/commit markers, import and invariant checks, Playwright configuration and CI workflows; all prior session reports and AC75 matrix.

## Build and evaluate

1. Extend the eval harness to drive durable multi-turn agent journeys with scripted customers/owner answers and mock Instagram. Preserve old bounded-task evals. Real-model runs use the same broker/runtime and never real account effects.
2. Complete at least 60 journeys across three or more business categories and TR/EN. Cover open-ended enquiries, mixed topics, memory, unknown information, owner waits, approval exceptions, moderation, private replies, content, private/public separation and prompt/tool injection.
3. Add missing cross-cutting failure tests: restart at every transaction boundary, concurrent wakeups, controller switch, deletion/correction races, new facts during waits, outcome-unknown fencing, capability loss, owner demotion and cumulative budget exhaustion.
4. Run full backend/static/type/import/isolation/security suites, frontend checks/build, generated API drift, strict fake evals and production-build E2E on all configured projects. Use dedicated test data; retain failing traces/logs and fix causes.
5. Run the real-model quality gate only with explicit spend authorization. Record dataset/model/prompt/tool versions, denominators, total cost, per-turn/whole-journey latency and failures. Human-rate at least 20 fixed journeys using the phase rubric; do not declare model quality from fake-only results.

## Done when

Offline tests and regressions are green with honest evidence; no unresolved full-suite failure is hidden by retries. AC75-01 through AC75-22/24 have the applicable automated evidence or precisely identified external/model/manual gaps. G7.5-C requires the phase thresholds, including zero observed authorization/critical-fact/privacy/duplicate violations and the stated success/tone/interruption targets. A failed quality gate leads to focused fixes and rerun, not silent threshold relaxation.

## Handoff

Write `s17-report.md` with the full acceptance mapping, model-quality report or pending reason, CI evidence, performance settings and remaining live/manual tasks. Session 18 receives a release candidate plus explicit gaps, not an assumed pass.
