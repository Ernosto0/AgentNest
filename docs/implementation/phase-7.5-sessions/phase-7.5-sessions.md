# Phase 7.5: Implementation Sessions

**Status:** Sessions 01-12 and 14-15 are offline implemented and operator reviewed; Session 13 is offline complete and ready for review. Session 16 has an operator-reviewed offline scaffold, with real Meta capabilities externally pending. See individual reports for actual evidence and remaining gates.
**Canonical phase:** [phase-7.5.md](../phases/phase-7.5.md).
**Target decision:** [ADR-024](../../architecture/decisions/ADR-024-account-agent-and-delegated-autonomy.md).

## Execution order

Run the following 18 sessions in order. Each brief is an implementable unit with its own scope, dependencies, tests and handoff. If a session needs multiple work periods, retain its scope and record partial progress instead of declaring it complete. Do not advance implementation beyond the session the user assigned. This plan does not itself authorize execution.

| Session | Brief | Task | Status |
|---|---|---|---|
| 01 | [Contracts and architecture alignment](s01-contracts-and-architecture.md) | P7.5-01 | Operator reviewed |
| 02 | [Persistence and migrations](s02-persistence-and-migrations.md) | P7.5-02 | Operator reviewed |
| 03 | [Delegation and authorization](s03-delegation-and-authorization.md) | P7.5-03 | Operator reviewed |
| 04 | [Model step and tool broker](s04-model-step-and-tool-broker.md) | P7.5-04 | Operator reviewed |
| 05 | [Durable coordinator](s05-durable-coordinator.md) | P7.5-05 | Offline complete, operator reviewed |
| 06 | [Knowledge, grounding and personality](s06-knowledge-grounding-and-personality.md) | P7.5-06 | Offline complete, operator reviewed |
| 07 | [Autonomous DM conversations](s07-autonomous-dm-conversations.md) | P7.5-07 | Offline complete, operator reviewed |
| 08 | [Customer memory and privacy](s08-customer-memory-and-privacy.md) | P7.5-08 | Offline complete, operator reviewed |
| 09 | [Owner questions and continuation](s09-owner-questions-and-continuation.md) | P7.5-09 | Offline complete, operator reviewed |
| 10 | [Comment ingestion and context](s10-comment-ingestion-and-context.md) | P7.5-10 | Offline complete, operator reviewed |
| 11 | [Public replies and moderation](s11-public-replies-and-moderation.md) | P7.5-11 | Offline complete, operator reviewed |
| 12 | [Comment-to-DM](s12-comment-to-dm.md) | P7.5-12 | Offline complete, operator reviewed |
| 13 | [Owner tasks and content tools](s13-owner-tasks-and-content-tools.md) | P7.5-13 | Offline complete; see [report](s13-report.md) |
| 14 | [Agent settings and overview UI](s14-agent-settings-and-overview-ui.md) | P7.5-14 | Offline complete, operator reviewed; see [report](s14-report.md) |
| 15 | [Conversations, questions and memory UI](s15-conversations-questions-and-memory-ui.md) | P7.5-15 | Offline complete, operator reviewed; see [report](s15-report.md) |
| 16 | [Meta capability adapters](s16-meta-capability-adapters.md) | P7.5-16 | Offline scaffold reviewed, real capabilities externally pending; see [report](s16-report.md) |
| 17 | [Evaluation and end-to-end verification](s17-evaluation-and-e2e.md) | P7.5-17 | Planned |
| 18 | [Rollout and close-out](s18-rollout-and-closeout.md) | P7.5-18 | Planned |

Research is a continuing dependency: Session 01 opens R75-01 through R75-06; Session 16 resolves adapter contracts against it; Session 18 records live evidence. Unavailable research does not turn synthetic fixtures into recordings. Independent offline work may continue with explicitly provisional assumptions and disabled real capabilities.

## Common read-first and working rules

Every session reads this index, its own brief, [the phase plan](../phases/phase-7.5.md), [CLAUDE.md](../../../CLAUDE.md), [invariants](../../invariants.md), current [roadmap](../roadmap.md) and the prior session report if one exists. Session-specific paths add to this list.

1. Inspect branch/worktree and recent commits. Preserve unrelated work, particularly current OAuth corrections. Resume completed portions rather than restarting them. No automatic commit/push follows from a session brief.
2. Distinguish existing behavior, target contracts and implementation evidence. Session 01 resolves the existing no-tool architecture before agent code is enabled. Update affected contracts with code in subsequent sessions.
3. Keep fake/mock/local usable without credentials. No silent fallback from a real model to fake in production. New Meta features remain capability-gated until evidenced.
4. Add tests that prove the session's behavior and failure boundaries; run relevant existing regressions. Include isolation for new routes and new composite FK relationships.
5. No external call inside a database transaction. Use `Clock`. Job payloads contain IDs and routing metadata, not personal bodies or credentials. Persist execution evidence before side effects.
6. Public and private context are separate broker capabilities. Neither a prompt instruction nor a shared display name authorizes a data or identity merge.
7. Keep new APIs typed, paginated and permission-checked; regenerate OpenAPI/client types when contracts change. Add Turkish and English error/notification/UI strings together.
8. Each session produces `sNN-report.md` in this directory with the exact evidence below. Reports are created when work happens, not populated in advance with expected passes.

## Verification commands and environment

Use existing commands from [local-development.md](../../operations/local-development.md). In `backend/`, run applicable commands separately:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy app evals
uv run lint-imports
uv run pytest <session-test-paths>
```

For frontend sessions, from `frontend/`:

```powershell
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run i18n:check
npm.cmd run build
```

For the combined verification session, also run full backend tests, strict existing fake evals and the new agent evals introduced by Session 17, generated-client drift checks and production-build E2E on all configured browser projects. The current existing eval command is `uv run python -m evals run --all --provider fake --strict`; Session 17 must explicitly wire account-agent journeys into the evaluator rather than assuming the current command covers them.

Use a dedicated disposable test database for migration/commit tests and E2E. Existing E2E re-seeds data; do not point it at a workspace containing data to preserve. Record environment, model/prompt/tool versions and exact commands. Real-model evaluations need a specified spending budget; live Instagram probes need separately authorized account actions. Planning and offline test authorization do not imply either.

## Required session report

- Status: not started / in progress / offline complete / externally pending / complete, with unmet criteria listed.
- Baseline branch/commit and unrelated changes preserved.
- Implemented behavior and affected contracts/migrations; concrete demo steps.
- Tests and exact outcomes, failures, skipped checks and evidence paths. No expected counts represented as results.
- Acceptance IDs from the phase plan and which are actually proved by the session.
- Research/platform/model assumptions, remaining risks and any deviations with rationale.
- Next-session handoff: stable interfaces, migration heads, unresolved dependencies and how to resume.

Full-suite failures remain unresolved until a clean required rerun; a focused retry alone is not acceptance. Automated mobile tests do not count as a real-phone owner walkthrough. A fake tool sequence does not prove a real model selects tools well. A successful direct adapter probe does not prove the application workflow.

## Session invocation

Use this instruction with the desired number:

> Implement Phase 7.5 Session NN using `docs/implementation/phase-7.5-sessions/phase-7.5-sessions.md` and its linked session brief. Inspect the current worktree and previous report, complete that session's implementation and checks, update its report, and stop at its boundary. Preserve unrelated work. Do not infer authorization for live account actions, paid evaluations, deployment, commit or push.

Session 18 has an explicit offline/live split. If external evidence is unavailable, finish its independent rollback/runbook work and report pending gates. Do not mark the phase fully complete until its requested capabilities and acceptance evidence are complete.
