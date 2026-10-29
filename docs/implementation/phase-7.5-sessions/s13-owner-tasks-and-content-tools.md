# Session 13: Owner tasks and content tools

**Task:** P7.5-13. **Status:** Offline complete; see [report](s13-report.md). **Prerequisite:** Session 12.
Read the [common session rules](phase-7.5-sessions.md) and phase sections 2, 6-7.

## Goal

Let authorized business members give the central agent natural-language tasks and let it use the existing image-content workflow through governed tools.

## Read first

`app/commands/` registry/intake/permissions; `app/content/` generation/service/media/scheduling/impact; `app/operations/{publish,reconcile}.py`; current content approvals and deadline contracts.

## Build

1. Add account-scoped owner-task intake returning a durable task ID and idempotent request outcome. Route it through the coordinator with the actual requester's role, source channel and permissions. Customer inputs cannot enter this route.
2. Keep existing closed commands compatible; route expanded tasks only through the new contract. Resolve ambiguous media/content references with clarification; never let an alias name unseen or foreign content.
3. Register content reads, prepare, schedule, publish and cancel tools over existing services. Drafting remains a separate effect from scheduling/publication. Use selected existing assets; missing imagery or details prompts a business question rather than fabricated media.
4. Apply separate action delegation and exact-action approval bindings. Change the legacy mandatory-publication rule only for deliberately enabled agent accounts and documented grants. Scheduling stores the exact content/media/fact versions, deadlines and account targets.
5. Preserve fact-change holds, deleted-media fences, quotas, publish reconciliation and content edit invalidation. Policy revocation before a scheduled publish prevents dispatch. Report scheduled versus published accurately to the owner task.

## Verify and done when

Test an owner request to prepare and schedule existing image content with automatic delegation, ask-required publishing and disabled publishing. Test staff/task permissions, media ambiguity, missing asset, wrong account, timezone/deadline, fact changes, content edits after approval and timeout-after-publish. Verify a customer telling the agent to publish cannot enter owner task authority. Existing manual content flows and saved reporting remain compatible.

## Handoff

Write `s13-report.md` with owner-task/API contracts, content tool schemas and defaults for migrated accounts. AC75-13/16/24 receive evidence; new media generation or campaign optimization is not included.
