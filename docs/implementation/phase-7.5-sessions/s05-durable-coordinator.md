# Session 05: Durable coordinator

**Task:** P7.5-05. **Status:** Planned. **Prerequisite:** Session 04.
Read the [common session rules](phase-7.5-sessions.md) and phase sections 4-5, 14.

## Goal

Run the agent as a resumable, bounded event-driven loop that survives restarts and waits without holding workers.

## Read first

New agent repositories and broker; `app/jobs/{queue,scheduler,registry}.py`, `app/handlers.py`, worker lease/recovery tests; canonical transition/job contracts.

## Build

1. Implement event routing/coalescing and thread-scoped claims. Claim, call model, validate freshness and dispatch in separate transaction stages. Persist a monotonic cursor, controller epoch and claim token.
2. Drive typed tool results back into the loop; completion and wait decisions create explicit states. Wake on customer/owner/approval/operation events and scheduled tasks using durable jobs.
3. Implement activation and cumulative goal budgets, atomic quota reservations, maximum repeated identical calls and retry classification. A new job/repair/restart cannot reset spend/step accounting.
4. Add expired-lease recovery, abandoned model-step handling, dead-job outcomes and health visibility. Waiting on a human or operation does not consume ordinary failure attempts.
5. Invalidate stale model results after new inbound, takeover, policy changes or controller switch. Independent customer threads can progress while one waits. Prevent own-message/echo events from causing conversational loops.

## Verify and done when

Script a read-result-follow-up-action sequence and a wait/wakeup sequence through real job execution. Kill/recreate workers between claim/model-result/dispatch/result-commit stages; prove no second action intent is admitted. Race duplicate wakeups, expired claims and new inbound events with real commits. Frozen-clock tests cover scheduled wakeup, budget reset boundaries and indefinite human waits. Confirm no model/tool/network call holds a DB transaction and one waiting thread does not block the account.

## Handoff

Write `s05-report.md` with jobs/transitions, recovery decisions, initial budget settings and race evidence. Map foundational AC75-02/08/14/15/21 coverage and list external tool handlers still pending.
