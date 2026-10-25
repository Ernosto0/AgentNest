# Session 07: Autonomous DM conversations

**Task:** P7.5-07. **Status:** Planned. **Prerequisite:** Session 06.
Read the [common session rules](phase-7.5-sessions.md) and phase sections 5-7, 14.

## Goal

Deliver the first complete agent conversation through the existing inbox and send ledger, with exclusive controller ownership and human takeover.

## Read first

`app/inbox/{processing,jobs,reply_workflow,service,echoes,models}.py`; `app/operations/{send,reconcile}.py`; reply approval callbacks, fact references and existing send/takeover/echo tests.

## Build

1. Route each inbound conversation event to legacy or agent according to the atomic account/thread controller epoch. Suppress stale legacy draft jobs on agent-owned threads and vice versa.
2. Register the DM tool. Project a validated agent reply into the existing reply-draft/send subject with explicit action origin. Use action policy grants or human approvals as configured; preserve message window/byte checks and the existing ledger.
3. Implement natural clarification/follow-up using durable thread state and relevant turns. Remove legacy topic-only and three-per-hour gating from the agent path while applying meaningful spam/loop/provider controls.
4. Deduplicate actions by durable event/intent identity across replans; a model-selected fresh text or tool-call ID must not bypass unresolved-send fencing. Coalesce bursts and preserve event ordering.
5. Integrate native owner replies, manual takeover/release, account pause/disconnect and new customer messages. Fence unsubmitted work; keep in-flight outcome reconciliation active. Return verified results to the coordinator.

## Verify and done when

Run a complete simulated multi-turn enquiry, clarification and recommendation with automatic sending and no per-message owner taps. Test ask/off policies, late inbound, duplicate webhooks, old/new controller races, native echoes and policy revocation between planning and send. Inject timeout-after-success and prove no reworded second send. Existing manual replies, staff approval, legacy drafts and OAuth-bound sending tests still pass.

## Handoff

Write `s07-report.md` with reproducible local demo steps, migration/cutover mechanics and acceptance evidence for AC75-01/02/08/15/16/17. This establishes an agent DM slice; memory and owner-question continuations remain the next sessions.
