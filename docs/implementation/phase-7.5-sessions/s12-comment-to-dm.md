# Session 12: Comment-to-DM

**Task:** P7.5-12. **Status:** Planned. **Prerequisite:** Session 11.
Read the [common session rules](phase-7.5-sessions.md) and phase sections 8, 10.

## Goal

Allow the agent to move an eligible comment interaction into a private conversation while preserving source context, identity evidence and private-reply limits.

## Read first

R75-04/05 evidence; comments and DM actions; memory identity linking; operation admission/reconciliation and provider contracts.

## Build

1. Define a separate private-reply action/provider method and eligibility service based on the verified contract. Provisional offline limits must be explicit fixtures/settings, not undocumented assumptions copied from ordinary DM rules.
2. Persist and atomically reserve the source comment's private-reply opportunity. Bind reservation/action/operation and current source/policy versions; concurrent workers and different automation triggers share the same reservation.
3. Register the tool and executor with appropriate delegation, deadline, media ownership and capability checks. Support useful public/private combinations as separate authorized effects with explicit ordering and result handling.
4. Record provider-returned identity evidence and associate a subsequent inbound DM only when supported. Carry public source context into the private thread; never expose private details back into public context. Unproven identities remain separate.
5. Continue normal conversation only after required provider eligibility is established. An unanswered private reply cannot become permission for repeated unsolicited DMs. Unknown outcomes retain the reservation pending reconciliation; do not release it on a generic timeout.

## Verify and done when

Run comment -> private reply -> customer response -> normal agent DM through signed mock ingestion. Race two workers, two tool calls and duplicate webhooks. Test expiry, no customer response, missing grants, ambiguous send, deleted source comment and unmatchable identities. Verify retry/replan cannot consume the opportunity twice or invent a normal DM window.

## Handoff

Write `s12-report.md` with eligibility/reservation lifecycle, identity evidence and private-to-public visibility tests. AC75-11/12/15/16 has simulated contract evidence; the live capability stays disabled until research/verification establishes support.
