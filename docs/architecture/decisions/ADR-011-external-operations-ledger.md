# ADR-011: Write-ahead external operations ledger and reconciliation

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
External side effects (send a DM, publish a post) can be retried by job leases, worker crashes, provider timeouts and duplicate webhooks. The Instagram API documents **no idempotency keys** ([platform-capabilities.md](../../research/platform-capabilities.md)). The user must receive an accurate result, and a timeout does not mean failure.

## Alternatives
1. Fire the API call from the job and record the result afterwards ("at least once"). Duplicates are possible.
2. Check-then-act using provider reads only. That is racy, and not all operations have a lookup.
3. **Write-ahead ledger + provider-specific reconciliation**: persist intent and every intermediate handle *before* each external step; on any ambiguity, reconcile before acting again.

## Decision
Option 3. Table `operations` ([data-model.md](../data-model.md)):
- One row per **intended external effect**, keyed by a deterministic `idempotency_key` (unique), for example:
  - `publish:{content_item_id}:v{content_version}`
  - `send_reply:{reply_draft_id}`
  - `refresh_token:{social_account_id}:{yyyy-mm-dd}`
- Status machine: `pending → in_progress → succeeded | failed | outcome_unknown`, plus `retry_wait` and `cancelled` ([state-machines.md §6](../state-machines.md)).
- `provider_ref` stores intermediate handles (container ID) **committed before** the next external call.

Per operation type:
- **Publish** (two-step): (1) if there is no container, create one and commit `provider_ref = container_id`; (2) poll `status_code`; (3) if `PUBLISHED`, treat as succeeded (fetch media ID); if `FINISHED`, call `media_publish`; if `EXPIRED`, create a new container (the old one was never published); if `ERROR`, fail permanently. A timeout during `media_publish` → `outcome_unknown` → reconcile by re-reading container status. **This makes duplicate publication impossible as long as the container status is truthful** (verify in V-04/V-05).
- **Send DM** (single step, no handle): a timeout or 5xx after the request may have been accepted → `outcome_unknown`. **Never auto-resend.** Reconcile by (a) matching a `message_echoes` webhook (recipient + text hash + time window) or (b) the conversation lookup API. If unconfirmed after the reconciliation window (default 10 minutes) → `failed` with `OUTCOME_UNCONFIRMED`, and the owner is told to check Instagram. Errors that are certainly pre-acceptance (connection refused, DNS failure, 429 with explicit rejection) are retryable.
- **Internal-only actions** (fact updates) do not use the ledger. They are DB transactions.

The ledger row is the **only** place a job may consult to decide whether an external effect already happened.

## Rationale
- Converts "exactly once" from an impossible network guarantee into a reconciliation problem with explicit, user-visible outcomes.
- "No auto-resend on ambiguity" accepts a rare manual check over a duplicate message to a customer, which is the right trade-off for trust.

## Trade-offs
- More states and more code paths, each requiring tests (Phase 4/5 test lists include every branch).
- Echo-based reconciliation depends on V-02. If echoes are unavailable, conversation lookup is the fallback, and its rate limit is 2 calls/s per account.

## Consequences
- Provider adapters must return or raise `ProviderOutcomeUnknown` for ambiguous failures and must never retry internally on non-idempotent calls.
- The mock simulates "succeeded remotely but timed out locally" so every reconciliation branch is demoable and testable.
- UI shows `outcome_unknown` as "Checking whether it was sent/published…", never as success or failure until resolved.

## Revisit when
- Meta introduces idempotency keys or client-supplied message IDs. Use them, and keep reconciliation as a safety net.
