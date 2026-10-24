# ADR-022: Bounded privacy erasure preserves outcome and audit evidence

- **Status:** Accepted by owner, 2026-10-24
- **Date:** 2026-10-24
- **Scope:** Clarifies INV-17; retains INV-12 append-only audits.

## Context

INV-17 forbids rewriting history, while security/privacy section 8 already requires
365-day text redaction. Phase 7 also implements explicitly requested, account-scoped
conversation erasure on disconnect. Those policies must be stated as narrow exceptions,
not an ability to edit a sent reply, published post, fact version or audit record.
The provisional two-year audit retention period has no implemented purge path.

## Decision

Historical business corrections still create new records. Normal editing of sent
messages and published content remains forbidden; fact versions and audit rows remain
insert-only. Permit only the named privacy workflows:

- Retention may null `messages.text` and `reply_drafts.text/template/suggestion_text`
  after the configured age. It preserves IDs, timestamps, direction, provenance,
  outcome, references, saved report membership and original measurements.
- Explicit disconnect erasure may delete that account's conversations, messages,
  drafts and their text-bearing references, and null inbound payloads. It preserves
  immutable audit/operations records and other tenants/accounts. Uncertain sends keep
  reconciliation evidence until resolved; a durable cleanup job and reconnect fence
  prevent erasure from causing duplicate or unverifiable effects.
- Provider deletion markers may record that a message was deleted without replacing
  its historical body with different business content.

INV-17 wording: "Historical business outcomes are never rewritten.
Sent messages, published content, past fact versions and audit logs cannot be edited
to correct history; corrections create new records. Only the bounded retention,
provider-deletion-marker and explicit account-erasure workflows in ADR-022 may remove
personal content. They preserve immutable audit/ledger and saved report evidence,
and keep unresolved-send evidence until reconciliation completes."

No application audit UPDATE/DELETE path is added. Audit rows continue to be retained
indefinitely for the local fictional demo. The proposed two-year production purge is
deferred to Phase 8 and legal review (OQ-12), with a separate ADR required for its
privileged identity, boundaries and database privileges. Deferral does not authorize
production retention forever and does not close Gate 3.

## Alternatives and consequences

Keeping all personal text forever conflicts with the already specified privacy policy.
Allowing unrestricted historical edits would destroy outcome evidence. The bounded
exception must retain edit rejection tests, retention boundary/idempotency/report
tests, and disconnect scoping/uncertain-send tests.

Media cleanup is an important state change under INV-12: `media.deleted` is written
with its row transition, contains only `reason=retention`, and is idempotent. A failed
audit rolls back the row transition; retry repairs a file already removed outside
the transaction and records the transition once. This requires no INV-12 weakening.

## Revisit

Before real customer data, review deletion, retention, backups and database privileges
under Phase 8. Any audit purge requires its own accepted decision and verification.
