# Review correction: Agent enquiries before reply/action admission

Date: 2026-11-19. Reviewed baseline: `4cf8ee3`. Scope: review finding 6.

## Changes

- Migration `0102` adds nullable checked `messages.agent_enquiry_intent` (`pricing` or
  `booking`). This reuses the original message's workspace/account scope, RLS, provenance
  and lifecycle; no separate lead table or customer-text copy is created.
- Agent inbound processing records deterministic typed-text enquiry evidence. Successful
  transcription records the same enum against the original voice message. Calendar
  availability/book tools record the current customer event's original message before
  provider availability or action admission can fail. Owner tasks and unrelated fallback
  messages do not create leads.
- Account-first and message row locking serialize evidence merges; repeated calls are
  idempotent and booking takes precedence over pricing for a combined enquiry.
- Lead SQL unions persisted message enquiries with existing draft/action evidence. Existing
  real-provider, simulation, deletion, period and workspace checks remain. Only confirmed
  eligible linked appointments establish conversion.
- Provider deletion, data-rights erasure, account erasure and message-text retention clear
  the enum. Late processing rejects empty, expired or deleted sources. Data-subject exports
  include the stored enum. Schema, workflow and privacy contracts were updated.

## Verification

- New integration tests plus existing lead-list integration tests: **45 passed** on
  disposable database `pivoris_review_enquiry_test`.
- Expanded enquiry integration tests plus existing lead unit/CSV tests: **62 passed**.
- Final enquiry, transcript-retention and draft-erasure lifecycle regressions: **22 passed**.
- Migration `0102 -> 0101 -> head` completed on that disposable database.
- Ruff lint and format checks passed for the files in this change.
- The tests cover five-language abandoned enquiries, unavailable/disconnected calendar
  paths before any action/draft, source-linked media, repeated calls, conversion/cancellation,
  scope/provenance exclusions, real ingestion/provider deletion, retention/late completion,
  erasure/export and the migrated check constraint.

No production configuration, live provider calls, deployment, commit or push was performed.
Full integrated change verification belongs to the parent review-fix run.
