# Session 11: Public replies and moderation

**Task:** P7.5-11. **Status:** Planned. **Prerequisite:** Session 10.
Read the [common session rules](phase-7.5-sessions.md) and phase sections 6, 10.

## Goal

Let the agent choose public replies or hide/unhide/delete actions under the owner's delegated moderation authority.

## Read first

New comments services, broker and delegation; `app/operations/` ledger/executor/reconciliation patterns; approval subjects and R75-03/06 evidence.

## Build

1. Extend provider/mock contracts for public reply, hide, unhide and delete. Add explicit operation types, subject/version payloads, exact-action policy/human approvals and dedicated executors; update database constraints.
2. Register tools with media-ownership, target-version, capability, quota, visibility and delegation checks. Broad deletion delegation permits model judgment without another owner click. Ask/off configurations still apply.
3. Return real operation observations to the coordinator. A reply can be unnecessary; support no-action completion. Moderation choices use post/thread context and owner instructions, not only keyword triggers.
4. Serialize conflicting reply/hide/delete intents for a target. Native changes or another moderator's action invalidate stale dependent work. Preserve provider errors and verified-versus-unknown hidden/deleted status.
5. Implement stateful failure injection and reconciliation contracts. Do not interpret all missing comments/404s as proof of successful deletion. Where evidence is inconclusive, keep the action unresolved and block duplicates rather than retrying blindly.

## Verify and done when

Test automatic public response, contextual no-op, automatic hide/unhide/delete, and human-required moderation. Cover complaints versus spam, arbitrary criticism under configured criteria, foreign targets, concurrent deletion/reply, target already gone, revoked delegation and timeout-after-success. Prove repeated events/replans cannot duplicate a public reply. Inspection APIs distinguish queued, performed and unknown outcomes; immutable audit history does not retain prohibited raw comment bodies.

## Handoff

Write `s11-report.md` with per-action verification/retry semantics and reproducible moderation demos. AC75-09/10/15/16 has offline evidence; real behavior remains Session 16/18 work.
