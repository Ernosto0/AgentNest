# Session 02: Persistence and migrations

**Task:** P7.5-02. **Status:** Planned. **Prerequisite:** Session 01 / G7.5-A.
Read the [common session rules](phase-7.5-sessions.md) and phase sections 5, 7 and 14.

## Goal

Persist account agents, delegation versions, durable thread/run/step state and action identities without altering existing account behavior.

## Read first

Canonical data/state/job contracts from Session 01; `backend/app/{core/db.py,jobs/models.py,ai/models.py,inbox/models.py,approvals/models.py,operations/models.py}`; current migration heads and isolation fixtures.

## Build

1. Add core `app/agent/` records/repositories, account-agent config, thread ownership epoch, durable events, sessions/steps and action intent records. Add delegation storage for Session 03. Stage customer-memory/question/comment tables in their owning later sessions unless the finalized FK contract requires an earlier skeleton.
2. Link individual existing `agent_runs` model calls to durable steps. Add action origin links needed by existing reply/content subjects without changing their execution path yet.
3. Allocate additive migrations from the actual head. Add workspace composite FKs, unique source-event keys, unique action intent keys, one active thread run constraint/claim rule and query indexes.
4. Implement repository transactions for event insertion plus job enqueue, version comparisons and run/step state transitions. Job payloads carry references only. Allocate action IDs before model/executor retries so an identical intent cannot become a second operation after a crash.
5. Backfill existing accounts to legacy/inactive agent state. Add isolated fixtures and a seeded agent configuration for tests; migration must not enable automation or grant new authority.

## Verify and done when

Test upgrade of an empty database and a populated pre-phase database, foreign tenant FKs, duplicate event/action admission, concurrent run claims and stale compare-and-swap rejection. Use commit-level tests for races. Existing manual reply/approval/operation rows remain readable and executable under their original contracts. Test downgrade behavior and refuse evidence-losing rollback rather than silently deleting new records.

## Handoff

Write `s02-report.md` with migration IDs, tables/indexes, transaction helpers, backfill behavior and relevant test results. Session 03 receives stable versioned delegation/action records; Session 05 receives durable transitions rather than in-memory placeholders.
