# Session 09: Owner questions and continuation

**Task:** P7.5-09. **Status:** Offline complete, operator reviewed ([report](s09-report.md)). **Prerequisite:** Session 08.
Read the [common session rules](phase-7.5-sessions.md) and phase sections 6, 8-9.

## Goal

Let the agent ask the business for missing information, wait durably and continue the correct customer conversation when answered.

## Read first

Existing approvals/subject callbacks, notifications, knowledge candidates/verification and commands clarification; new run waits/events and customer memory lifecycle.

## Build

1. Add `app/owner_requests/` records, state transitions and APIs for pending/answered/expired/cancelled questions and versioned answers. Include originating thread/cursor, required information, visibility and continuation keys.
2. Register ask-owner and request-approval tools with distinct outputs. Route authoritative business questions to owner/manager; staff can propose answers under the finalized role contract. Use existing in-app notifications with deduplication.
3. Submit answers transactionally with expected version, idempotency and one wakeup. Free-text information does not approve an action. Existing explicit approval controls still authorize only the bound payload.
4. Resume through the coordinator after rereading current messages, delegation, facts, takeover and provider eligibility. Support one-conversation answers and explicit reusable-knowledge candidates without converting exceptions into permanent policy.
5. Handle declined/expired questions, repeated missing-information requests, conflicting answers and late owner responses. Send a truthful holding response only when useful and eligible; track it to avoid repeated apologies/notifications. Keep unanswered work visible without infinite retries.

## Verify and done when

Exercise missing information -> owner question -> answer -> grounded customer response end to end. Race duplicate answers, answer-after-takeover, a changed customer request, expired message eligibility and policy revocation. Test question visibility, unauthorized staff decisions and accidental "okay" authorization. Prove no lease/DB transaction stays open while awaiting a person and no cross-customer question deduplication leaks context.

## Handoff

Write `s09-report.md` with question APIs/events and frontend payload examples. AC75-06/07/08 is demonstrated through the actual jobs/send path. External owner messengers remain Phase 9 work.
