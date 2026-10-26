# Session 08 audit: customer memory and privacy

**Status:** Preparatory audit only. Sessions 01–04 were implemented after this baseline audit; Sessions 05–07 and Session 08 remain unfinished. No Session 08 acceptance criterion is proved.

## Baseline and scope

- Inspected `main` at `b5cdee1` on 2026-10-26. The worktree was clean at the start of this audit. No Session 01–07 reports, `app/agent/`, or `app/memory/` existed; the latest migration was `20261024_0018_general_business_categories.py`.
- No runtime code, schema, API contract, test, model call, provider action, commit, or push was made for Session 08. No test result is claimed.

## Existing integration points

- `app/inbox/models.py` has account-scoped conversations keyed by `customer_external_id` and messages linked to conversations. A customer handle is stored, but is not sufficient evidence to merge identities across public and private surfaces.
- `app/retention/cleanup.py` batches and commits privacy cleanup. Current global defaults include 30-day model-input redaction and 365-day message/draft-text redaction. New memory, summaries, source links, and cached context need explicit lifecycle rules and retention counts.
- `app/operations/conversation_deletion.py` wipes account conversations after unresolved sends are reconciled; `app/operations/accounts.py` invokes it on optional disconnect erasure. New memory and derived context must be erased or fenced here without removing operation/audit evidence or permitting resurrection by a slow model result.
- `app/identity/permissions.py` defines owner-only `data.export` and `data.delete`. The current code has no customer data export or subject-deletion service or route; the roadmap lists deletion/export under Phase 8. Session 08's required integration with “existing” export therefore needs a scoped contract decision before implementation.
- Relevant baseline regression tests include `tests/integration/retention/test_retention.py` and `tests/integration/integrations/test_disconnect.py`. New Session 08 tests must cover tenant/account/customer isolation, public/private visibility, and deletion races.

## Remaining handoff

Wait for Session 07's implemented and reported DM thread/controller/context path and Session 06's grounding/context contract. Session 02's persisted agent-thread schema is now implemented. Session 08 owns customer-identity and memory tables unless the finalized FK contract requires an earlier skeleton. Confirm the current migration head and shared worktree again before editing. Session 01's account-agent contract specifies a memory-specific internal export/erase service for Session 08 and leaves the general rights API to Phase 8. Do not represent a permission constant as a working export API.

## Continuation prompt

> Resume Phase 7.5 Session 08 after Session 07 has a verified handoff. Read `phase-7.5-sessions.md`, `s08-customer-memory-and-privacy.md`, the phase plan, ADR-022, invariants, current migration head, and Sessions 06–07 reports. Preserve unrelated changes. Implement account-scoped, evidence-linked customer identities and typed memory records; bounded retrieval and incremental versioned summaries; correction, source inspection, and forget APIs with workspace/role checks; and generation fences against model results arriving after correction or erasure. Keep customer claims out of verified business knowledge and private memory out of public tool/context access. Integrate all derived data into retention, disconnect erasure, and the agreed export/deletion contract, preserving unresolved operation evidence. Add meaningful restart, race, relevance, isolation, and privacy lifecycle tests; run focused regressions and static checks. Write the final `s08-report.md` with exact results and AC75-04/05/12/18/19 evidence, and stop at the Session 08 boundary. Do not commit, push, use live accounts, or run paid evaluations.
