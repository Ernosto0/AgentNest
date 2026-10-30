# Phase 7.5 close-out status

**Status: offline regression checks passed; journey breadth, model, live and manual
acceptance pending.** Phase 7.5 is not fully accepted, and real comment capabilities
remain disabled. The [Session 17](../phase-7.5-sessions/s17-report.md) and
[Session 18](../phase-7.5-sessions/s18-report.md) reports contain the exact checks,
failure history and remaining gates.

## Delivered and controlled

Sessions 01-16 built the account-scoped coordinator, delegation, typed broker,
conversation, memory, owner questions, comment/private-reply mock flows, content tools,
UI and an explicitly provisional Meta comment adapter scaffold. Their individual
[session reports](../phase-7.5-sessions/phase-7.5-sessions.md) state what was actually
checked. Additive migrations **0019-0030** are current; existing accounts default to
`legacy`/`inactive`, and downgrade with agent evidence is refused. No Session 18 schema,
API or provider capability change was needed.

The [rollout runbook](../../operations/account-agent-rollout.md) describes one-account
activation, pause, legacy rollback and uncertain-operation reconciliation. Session 18's
four dedicated-DB mock rehearsals passed; see its report for the exact command and limit.
Phase 8 receives tenant/data/security/monitoring checks for the new tables; Phase 9
receives a typed owner-question/task handoff contract. Neither phase was implemented here.

Session 17's clean required regressions passed locally: backend **3307 passed, 10
intentional live-probe skips**; frontend **516 passed**; strict legacy fake eval
**166/166**; dedicated agent journey command **69 passed**; and production-build
Playwright **177 passed, 3 intentional skips** across all three browser projects.
Static/type/import/i18n/build and generated-client drift checks passed. Initial
failing runs, fixes and the Docker interruption are retained in the Session 17 report.
The three skips are the opt-in `agent-work.spec.ts` fixture test without its dedicated
API container/database; Session 15 separately passed that test on all three projects.
The 60 scripted customer prompts all use one two-turn fake path; focused tests cover
other flows, but the requested 60 varied behavioral journeys and real-model quality
thresholds have not been proved.

## Capability inventory

| Capability | Current status |
|---|---|
| Mock account DM, owner questions, public comments, moderation, private replies and content tools | Available for the local simulated account agent under delegation, approval and operation checks. |
| Real account controller | Inactive by default; no real account was switched in Sessions 17-18. |
| Real comment/media read, public reply, hide/unhide/delete, private reply and comment webhook/DM identity | Disabled in the production adapter pending R75-01 through R75-06 and authentic application evidence. |
| Real-model step execution | Adapter exists; the 60-journey quality threshold and spending/latency ceiling have not been measured. |

## Acceptance map

| ID | Current evidence and missing gate |
|---|---|
| AC75-01 | Sessions 06–07 report offline open-ended DM behavior; Session 17 multi-turn and real-model results pending. |
| AC75-02 | Session 07 reports conversation progression; Session 17 scripted two-turn mechanics passed; behavioral breadth pending. |
| AC75-03 | Sessions 06/14 report persisted persona and UI; real-model tone rating pending. |
| AC75-04 | Session 08 reports memory retrieval/restart; Session 17 cross-journey results pending. |
| AC75-05 | Sessions 03/06/08 report authority and fact-grounding tests; Session 17 adversarial results pending. |
| AC75-06 | Sessions 09/15 report scoped owner question and UI; real-model and live flow pending. |
| AC75-07 | Sessions 03/09/15 report separated answer, approval and takeover permissions; three-project E2E passed. |
| AC75-08 | Sessions 05/07/09 report stale-result races; full failure matrix pending. |
| AC75-09 | Sessions 10–11 report mock public comment context/reply; real model and Meta flow pending. |
| AC75-10 | Sessions 03/11/15 report mock moderation modes and UI; real capability pending. |
| AC75-11 | Sessions 12/16 report mock private-reply reservation and transport; real eligibility and continuation pending. |
| AC75-12 | Sessions 08/10/12 report public/private separation; full backend isolation suite passed. |
| AC75-13 | Session 13 reports content-tool offline tests; authorized live application publish pending. |
| AC75-14 | Sessions 04–05 report runtime/tool contracts; real-model tool-selection evidence pending. |
| AC75-15 | Sessions 02/05/07/11/12 report recovery and idempotency tests; Session 17 full failure suite pending. |
| AC75-16 | Sessions 07/11–13/16 report operation uncertainty tests; Session 18 adds ambiguous-send rollback rehearsal; real outcome handling pending. |
| AC75-17 | Session 18's four mock rollback rehearsals passed; live cutover/worker-crash interleaving pending. |
| AC75-18 | Session 08 reports memory/privacy service tests; Session 17 race verification and Phase 8 general data-rights API pending. |
| AC75-19 | Per-session isolation tests reported; full backend security/isolation suite passed. |
| AC75-20 | Sessions 14–15 report UI checks; production browser suite passed; real-phone TR/EN walkthrough pending. |
| AC75-21 | Sessions 04–05 report durable budget/loop limits; Session 17 cumulative journey evidence pending. |
| AC75-22 | Prior sessions report focused regressions; Session 17 full backend/frontend/eval/build suites passed. |
| AC75-23 | Session 16 authentic R75-01–06 Meta contract/capability evidence unresolved; no new real comment capability accepted. |
| AC75-24 | Session 13 reports owner-task flow and Session 15 UI; scripted/mock end-to-end evidence passed; real-model/live evidence pending. |

## Gates and next actions

G7.5-A was accepted in Session 01. G7.5-B has clean scripted/mock regression suites,
but its 60 varied-journey coverage remains open, so the gate is not closed. G7.5-C requires explicitly budgeted
real-model journeys, thresholds and at least 20 human ratings. G7.5-D requires fresh
primary Meta contract and authentic sanitized grant/webhook/application evidence for each
new capability. G7.5-E requires named-action founder-account workflow, rollback and
Windows/real-phone TR/EN acceptance after prior gates. Existing Phase 7 real-account and
Phase 8 production/data gates remain separate prerequisites for a real customer pilot.

Keep unsupported real capabilities off. Record the authorized model, prompt, policy,
adapter and capability versions, costs, latency, provider operation IDs and failures in
the final report. No live effects, paid evaluation, deployment or App Review submission
are represented by this provisional close-out.
