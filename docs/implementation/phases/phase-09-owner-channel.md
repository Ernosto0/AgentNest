# Phase 9: Owner Messaging Channel (Telegram, provisional)

> **Gated by OQ-01.** If pilot interviews show that owners would not use Telegram, re-plan this phase for the chosen channel (Web Push via PWA, or WhatsApp after a policy and cost review). The channel abstraction work (P9-01, P9-02) applies regardless.

## Objective
Let owners receive notifications, issue commands, send images and decide approvals from a messenger, using the channel abstraction, with no business logic in the adapter and with replay-safe approval buttons.

## Read first
[ADR-012](../../architecture/decisions/ADR-012-owner-channel-abstraction.md) · [integrations.md §5](../../architecture/integrations.md) · [platform-capabilities.md §2–3](../../research/platform-capabilities.md) · [ADR-014](../../architecture/decisions/ADR-014-approval-and-policy-model.md)

## Scope and tasks (in order)

**Phase 7.5 handoff:** A future owner channel must carry typed, scoped owner-question
notifications and answers into the existing owner-question service. Preserve question ID,
workspace/account/thread, version, expiry and responder identity; a delivered message or
free-text answer is information, never an action approval. Approval buttons remain the
separate exact-payload, single-use approval path. Natural-language owner tasks enter the
authenticated owner-task intake with the requester's current permissions intersected with
account delegation; the channel adapter cannot invoke broker tools or provider effects.
Deduplicate updates before writing a question answer, task or decision. Handle stale
question, takeover, role change and controller epoch by showing the current state rather
than replaying an old response. Keep customer DMs outside this owner command channel.

| ID | Task | Size |
|---|---|---|
| P9-01 | `channel_links` + linking flow (one-time code in web settings → `/link <code>` in the bot); unlink both ways; audit | S |
| P9-02 | Formalise `OwnerChannel`; `notification_deliveries`; delivery policy (which notification types are pushed; quiet hours per user, default 22:00–08:00 local except critical) | M |
| P9-03 | Telegram adapter: webhook with secret header, `update_id` dedup, long-polling mode for local dev, text → `CommandService.submit`, photo → `MediaService.ingest` (≤ 20 MB) + attach to the next command, command results rendered as messages | M |
| P9-04 | Approval buttons: action tokens (16 random bytes, hashed, single use, bound to user, approval, decision and payload hash, expiring with the approval); approval messages carry the full summary and the simulated flag | M |
| P9-05 | Tests: wrong user pressing a forwarded button; replayed button; expired approval; edited subject (stale); unlinked user; duplicate updates; media too large | M |

## Acceptance criteria
1. A linked owner receives an `approval.requested` message for a reply draft with the exact text, approves with a button, and the reply is sent. A second press reports "already decided".
2. "Bugün kaç DM geldi?" in Telegram returns the same number as the web report.
3. Sending a photo with "bu story'yi 19:00'da paylaş" creates a story draft with that media and a schedule proposal requiring explicit approval (never auto-scheduled from free text).
4. No core module imports the Telegram adapter except the channel registry.

## Explicitly excluded
WhatsApp (unless OQ-01 selects it), group chats, voice messages.
