# Session 10: Comment ingestion and context

**Task:** P7.5-10. **Status:** Planned. **Prerequisite:** Session 09.
Read the [common session rules](phase-7.5-sessions.md) and phase sections 7-8, 10.

## Goal

Make public comments a first-class durable event and conversation surface with correct media ownership and context.

## Read first

`app/integrations/instagram/{base,webhook_format,mock,models}.py`; `app/inbox/{ingest,processing}.py`; webhook signatures, event deduplication and provider capability contracts; R75-01/02 evidence register.

## Build

1. Add `app/comments/` media/comment/thread records with external IDs scoped to the connected account, parent relationships, text lifecycle, provider timestamps and unknown/hidden/deleted state as documented.
2. Extend normalized events for verified comment formats without breaking existing messaging events. Signature verification precedes processing; durable receipt and deduplication survive retries and out-of-order delivery.
3. Build scoped comment/media/thread reads and agent tools. Supply public post context and only eligible public thread data. Ignore own echoes/replies as new customer tasks where appropriate.
4. Extend the stateful mock and developer simulator through the actual signed ingestion path. Include parent replies, edited/deleted comments, unknown authors, missing media and native owner activity; label provisional assumptions.
5. Add paginated comment/thread APIs and isolation tests. Connect source events to the coordinator, but leave public/moderation side effects to Session 11. Native changes update source versions and fence obsolete proposals.

## Verify and done when

Test duplicate deliveries, delete-before-create, parent ordering, pagination boundaries, foreign media IDs, invalid signatures and absent identity fields. Confirm an event from one connected account cannot resolve another account's media/thread. Verify private-memory tools are unavailable in public response context and a signed simulated comment reaches one agent thread.

## Handoff

Write `s10-report.md` with provider/event schema changes, media ownership checks, mock scenarios and research assumptions. AC75-09/12/15/19 has ingestion/context evidence; no comment send or real Meta success is claimed yet.
