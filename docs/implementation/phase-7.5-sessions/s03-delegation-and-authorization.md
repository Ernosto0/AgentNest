# Session 03: Delegation and authorization

**Task:** P7.5-03. **Status:** Planned. **Prerequisite:** Session 02.
Read the [common session rules](phase-7.5-sessions.md) and phase sections 6-7.

## Goal

Let an owner delegate account actions once, including autonomous deletion, while preserving exact-action authorization and immediate revocation for unexecuted work.

## Read first

`app/policy/{classes,service,rules_reply,schemas}.py`, `app/identity/permissions.py`, `app/approvals/{grants,service,models}.py`, existing reply/content executor eligibility; Session 01 permission and policy contracts.

## Build

1. Implement account-scoped action modes/constraints, immutable policy versions, grantor provenance and preview/apply APIs. Add pause/resume permissions and moderation approver roles. Natural-language configuration yields a structured diff through the owner-authorized path.
2. Build a deterministic decision service for automatic/ask/off plus unavailable/blocked outcomes. Check actual capabilities, account/target scope, visibility, limits and action-specific readiness. The new agent path does not inherit unconditional topic escalation or require all workspace facts for every conversation.
3. Extend approval action/subject constraints and policy-grant metadata. Bind approved action version/hash, delegation version and one operation. Preserve existing explicit UI approval mechanics and legacy behavior.
4. Define and implement revocation/pause/configuration epoch checks consumed by executors. A policy edit, owner-authority change or disconnect fences queued automatic work. Human approval checks the actor's current permission; a previous approval cannot waive missing provider eligibility.
5. Add backend configuration APIs, typed errors and audit/notification catalog entries. Keep new accounts inactive until configured; migrated accounts retain prior authority.

## Verify and done when

Table-test each action across automatic/ask/off, roles, capability/readiness and current/stale policy versions. Prove autonomous deletion creates a policy grant without requesting a human click, while ask creates a pending approval. Test foreign IDs, unauthorized policy edits, concurrent policy changes, stale hashes and pause-before-dispatch. Verify policy grants never impersonate a human decision. Test greeting permitted with missing prices while an unsupported price claim remains blocked.

## Handoff

Write `s03-report.md` with the decision API, role matrix, policy-version rules and executor integration points. AC75-05/07/10/17/19 receive foundational evidence, not final end-to-end completion.
