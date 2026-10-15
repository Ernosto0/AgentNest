# ADR-010: Instagram provider interface; mock and Meta (Instagram Login) adapters

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
The product must be fully demonstrable without Meta permissions, yet later run against the real API without rewriting business logic. Meta offers two API configurations ([platform-capabilities.md §1.1](../../research/platform-capabilities.md)). Mock behaviour that is "too nice" (no failures, no async container processing, no messaging window) would hide design flaws until production.

## Alternatives
**Real configuration:** Instagram Login vs Facebook Login for Business.
**Mock style:** (a) in-memory stub returning success; (b) **stateful simulator persisted in the database**, implementing the same semantics as the real API (containers with statuses, message IDs, window enforcement, injectable failures).

## Decision
- **Real adapter uses Instagram API with Instagram Login.** It does not require a Facebook Page, which suits small businesses, and messaging is native. Facebook Login remains possible as a second adapter.
- **A single `InstagramProvider` protocol** (full contract in [integrations.md §3](../integrations.md)):
  - `get_account_profile()`
  - `send_text_message(recipient_id, text) → SendResult`
  - `lookup_recent_outbound(conversation_ref, since) → list[...]` (reconciliation)
  - `create_media_container(spec) → container_id`
  - `get_container_status(container_id) → ContainerStatus`
  - `publish_container(container_id) → media_id`
  - `get_media(media_id) → MediaInfo` (permalink, timestamp)
  - `get_publishing_quota() → Quota`
  - `refresh_token(...)`
  - Webhook-side: `verify_signature(raw_body, header)` and `parse_webhook(payload) → list[NormalizedInboundEvent]`
- Provider methods raise **typed errors**: `ProviderTransientError`, `ProviderRateLimited(retry_after)`, `ProviderAuthError`, `ProviderPermissionError`, `ProviderInvalidRequest`, `ProviderWindowClosed`, `ProviderOutcomeUnknown`. Business logic only handles these types, never HTTP status codes.
- **Mock = stateful simulator** (`MockInstagramProvider`). It persists simulated remote state in `sim_*` tables (sent messages, containers, published media). It reproduces container lifecycle semantics (`IN_PROGRESS` → `FINISHED` → `PUBLISHED`, expiry), the 24-hour window, the 1000-byte text limit and JPEG-only images. It supports **failure injection** (transient, rate limit, auth revoked, outcome-unknown-after-success) via `sim_failure_rules`.
- **Simulated inbound messages go through the real webhook pipeline.** The simulator builds a payload in Meta's webhook format, signs it with `MOCK_INSTAGRAM_APP_SECRET` and posts it to the same ingestion path. The pipeline cannot tell the difference except by the provider kind of the receiving account.
- A **shared contract test suite** runs against the mock in CI and against Meta manually with a test account (Phase 7).
- Each `social_accounts` row records `provider_kind` ∈ {`mock`, `meta`}. Everything produced through a mock account is `is_simulated = true` ([invariants.md](../../invariants.md) INV-09).

## Rationale
- A stateful mock forces the business logic to handle asynchronous containers, ambiguous outcomes and rate limits from day one. That is where duplicate-post and wrong-status bugs come from.
- Running simulated inbound through the real webhook path tests signature verification, dedup and parsing in every demo.
- Instagram Login reduces onboarding friction for the target users.

## Trade-offs
- The simulator is real code to maintain (~400 lines), and its fidelity is only as good as our knowledge of the real API. Mitigation: contract tests and recorded real fixtures after Phase 7.
- Instagram Login lacks hashtag search and product tagging. They are not needed for the MVP.

## Consequences
- `app/integrations/instagram/{base.py, mock.py, meta.py, webhook.py, errors.py}`.
- `sim_*` tables exist in every environment but are written only by the mock provider. In production config the mock provider is allowed only for workspaces flagged `is_demo` ([ADR-017](ADR-017-configuration-and-secrets.md)).

## Revisit when
- Features that require Facebook Login (product tagging, hashtag search) are requested.
- Meta changes the Instagram Login capability set.
