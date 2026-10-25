# Session 08: Customer memory and privacy

**Task:** P7.5-08. **Status:** Planned. **Prerequisite:** Session 07.
Read the [common session rules](phase-7.5-sessions.md) and phase sections 7-8.

## Goal

Remember relevant customer context across conversations while making memory scoped, correctable, attributable and erasable.

## Read first

ADR-022, retention/export/disconnect erasure services; new thread/context records; existing message deletion handling; privacy tests and workspace permission conventions.

## Build

1. Add account-scoped customer identities, memory records, source links and summary versions with additive migrations. Identity evidence is explicit; usernames/display names are not merge keys.
2. Implement bounded relevance retrieval and typed memory-write proposals. Customer statements can update preferences/customer claims; they cannot update verified business facts or permission policy.
3. Generate incremental thread summaries with source cursor/version and freshness checks. Persist open goals and relevant preferences across new runs and worker restarts. Treat summaries as derived context, not critical-fact authority.
4. Add source inspection/correction/forget APIs and role checks. Integrate memory/summaries into retention, export, provider erasure and account disconnect cleanup, including cached/context snapshots.
5. Fence concurrent writes with correction/deletion generations so a slow model result cannot resurrect erased memory. Public-facing contexts and tools cannot load private customer memory. Avoid storing irrelevant or inferred sensitive traits.

## Verify and done when

Test returning-customer continuity, relevant-versus-irrelevant retrieval, stale summary refresh, conflicting preferences and explicit correction. Test cross-workspace/account/customer reads and public-private leaks. Exercise deletion with a model call in flight, source-message removal, retention sweep and unresolved operation reconciliation. Verify only minimal permitted reconciliation evidence persists and the UI/API never returns deleted personal bodies. Preserve existing erasure contracts.

## Handoff

Write `s08-report.md` with retention defaults, identity-link evidence rules, retrieval limits and memory provenance/correction examples. AC75-04/05/12/18/19 require real integration evidence, not merely a new table or prompt memory field.
