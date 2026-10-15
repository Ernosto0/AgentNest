# ADR-012: Owner channel abstraction; web first

- **Status:** Accepted (choice of the second channel is provisional, see OQ-01)
- **Date:** 2026-10-15

## Context
Owners should eventually issue commands, receive notifications, submit media and approve actions from a messenger (Telegram, WhatsApp) as well as the mobile web app. The core must not depend on any messaging provider. Platform facts are in [platform-capabilities.md §2–3](../../research/platform-capabilities.md): WhatsApp has per-message pricing, a 24-hour window with paid templates outside it, business verification, and January 2026 terms on AI assistants. Telegram is free and has 64-byte callback data.

Note the distinction: **customer channels** (Instagram DMs, where the business's customers write) are integrations under [ADR-010](ADR-010-instagram-provider-adapter.md). **Owner channels** (how the business owner talks to *our* product) are covered here.

## Alternatives
1. Build business logic in each bot handler.
2. **Channel-agnostic core** with thin channel adapters that translate between provider formats and four core message types.

## Decision
Option 2. The core exposes four channel-neutral flows (details in [integrations.md §5](../integrations.md)):

| Flow | Core contract |
|---|---|
| **Command in** | `ChannelInbound{channel, channel_user_ref, text?, attachments[], reply_to_ref?}` → identity resolution via `channel_links` → `CommandService.submit(user, workspace, text, channel)` (same as web). |
| **Attachment in** | Adapter downloads the file (Telegram ≤ 20 MB) → `MediaService.ingest(...)` → `media_asset_id` is attached to the command. |
| **Approval decision in** | Button press carries an opaque **action token** (≤ 64 bytes) → resolved server-side to `(approval_id, payload_hash, decision, user)` → `ApprovalService.decide(...)`. This is the same call as the web button. Free text never decides an approval. |
| **Notification / result out** | `Notification{type, severity, params, subject_ref, actions[]}` → per-channel renderer (localised text + buttons) → delivery record. |

- **Channel #1: the web app** (MVP). It uses the same `CommandService`, `ApprovalService` and `Notification` records. Delivery is the in-app notification centre.
- **Channel #2 (provisional): Telegram** in Phase 9, unless pilot interviews (OQ-01) show that owners would not use it, in which case WhatsApp is evaluated first.
- **WhatsApp is never a hard dependency.** If built, it is just another adapter. Its template costs and policy review are tracked in OQ-01.

## Rationale for web first, then Telegram
- Web is required anyway (knowledge editing, content review with images), costs nothing, and has no third-party approval.
- Telegram: free API, rich buttons, file upload, no business verification. It is the cheapest real test of the abstraction.
- WhatsApp is the most familiar channel for Turkish owners but brings recurring cost, verification and policy uncertainty. It should be built once evidence shows it is worth it.

## Trade-offs
- The MVP has no push to the owner's phone. Mitigation: daily report and a notification badge. Web Push is a cheap addition with the PWA. Pilots will reveal whether that is acceptable.

## Consequences
- `owner_commands.channel` and `approvals.decision_channel` exist from Phase 3.
- `notifications` are channel-neutral records. Deliveries are per channel.
- Channel adapters live in `app/integrations/channels/`. They contain no business rules.

## Revisit when
- OQ-01 is resolved by pilot interviews.
- WhatsApp terms or pricing change materially.
