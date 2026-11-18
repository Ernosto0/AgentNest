# ADR-027: WhatsApp owner channel: notifications and buttons only, no free-text commands

- **Status:** Accepted (implementation in Feature Phase 5, Track A; the live number and templates are pending)
- **Date:** 2026-11-18
- **Deciders:** Engineering Lead (the owner asked for all Feature Phase 5 sessions on 2026-11-17/18, which is how OQ-01 is treated as answered; no pilot-interview evidence is recorded yet)
- **Technical Story:** Feature Phase 5, Session 01 (F-06). Extends [ADR-012](ADR-012-owner-channel-abstraction.md).

## Context

[ADR-012](ADR-012-owner-channel-abstraction.md) made WhatsApp an optional second owner channel and deferred it because of cost, business verification and policy risk. The policy part has now been read from the primary sources ([platform-capabilities.md §2.1](../../research/platform-capabilities.md), accessed 2026-11-18):

- The Meta Terms for the WhatsApp Business Platform (section 4.7, "AI Providers") bar providers of LLMs, generative AI platforms and general-purpose AI assistants when that is their **primary** purpose. Meta decides in its sole discretion what counts, and the text has no carve-out for a business's own AI support.
- The Business Messaging Policy allows automation inside the 24-hour window if a clear escalation path exists, and allows only approved templates outside it.
- Since 2026-10-01 service messages are charged after 1,000 per number per month, and utility templates inside an open window are charged too, so every message has a cost.

AgentNest's owner channels already have a strict model: free text never approves anything ([invariants.md](../../invariants.md)), approvals carry single-use hashed action tokens, and the Telegram adapter interprets owner free text into confirmed commands through the AI command interpreter. Doing the same on WhatsApp would put an AI assistant in a free-text conversation on a channel whose terms are aimed at exactly that shape.

## Session 02 addendum (2026-11-18): notification delivery

Decisions made while building delivery, all inside the scope above:

- **Window rule.** The window is anchored on `channel_links.last_inbound_at`, set by the webhook for any message from a linked owner. The send mode is chosen at **send time** by a pure function of that time and the injected clock, with a 5-minute safety margin before 24 hours (Meta may count slightly differently; a rejected session message would be a failed notification). Inside it the message is a session message with the template's text (the free tier makes it cheaper than a utility template); outside it, or if the owner never wrote, only an approved template is sent.
- **Opt-in.** Linking the number is the opt-in. There is no per-category preference yet (unlike Web Push); every supported type reaches a linked owner. A per-category setting is a follow-up if pilot owners find it noisy.
- **No simulated data.** Simulated notifications are never sent on this paid, real channel.
- **Cost.** Category and template/session are recorded per message; no price is stored because no Türkiye rate was verified. `WHATSAPP_TEMPLATES_APPROVED` (default false) keeps the channel from sending templates before Meta approved them.
- **Ambiguity.** A send whose outcome is unknown is failed terminally and never resent, including after a worker crash (a `sending` marker on the ledger row).

## Session 03 addendum (2026-11-18): approval buttons

Decisions made while building the buttons, inside the scope above:

- **Tokens.** The button id is `act:<token>` where the token is the existing Phase 9 action token (`approvals/action_tokens.py`: 16 random bytes, SHA-256 hashed at rest, single-use, bound to approval, member, decision and payload hash, expiring with the approval). No new scheme. `consume_action_token` only gained a `channel` argument (default `telegram`) so the tapping number must be linked on the channel the tap arrived on.
- **Session messages only.** Interactive buttons are sent only inside the 24-hour window (decided at send time, as in Session 02). Outside it the approval request is the plain `agentnest_approval_requested_v1` template, with no buttons and no token, and its text says to open the app. The template registry has no quick-reply button and none was added: a template button needs Meta approval of a new template version, and its payload would have to be a token minted before the window state is known.
- **What the message says: an approval must be informed.** The interactive body shows **what is being approved**, the same fields the Telegram message shows, so the owner never approves blind. *May appear:* the proposed **outgoing** text (a reply draft's text, a post's caption), a post's title, type and schedule, the label and price or time of a price card or reschedule, the resume time of a pause, a fixed kind label (from `approval.action`, never from free data), and the expiry. For unknown kinds only a short allow-list of the summary's own display fields (`label`, `title`, `old_formatted`, `new_formatted`, `price_formatted`). *May not appear:* the **customer's inbound message**, the customer's handle or any other customer-authored text, and internal ids or hashes. *Why:* the proposed text is the business's own outgoing content that the owner is deciding to send, so it carries the decision; the customer's message is a third party's text that the owner reads in the app, and a WhatsApp message is stored by a third party and may be forwarded (rule 2 above). The body is clipped to 1,000 characters (Meta's limit is 1,024). Only the long text (reply or caption) is cut, with an ellipsis and "full text in the app"; short fields are clipped to 80 characters; the expiry and the instruction are never cut. The approval still binds to the **full** payload hash (the tokens carry it, unchanged), so a clipped view never changes what is approved. The earlier Session 03 draft that showed only a kind label was revised on 2026-11-18 at the orchestrator's decision that blind approval is not acceptable.
- **A tap is not free text.** Only a `button_reply` event reaches the approval path. A text message that contains a token, or the word "approve", gets the fixed "open the app" reply and decides nothing.
- **Decision and answer.** The tap resolves the sender through the channel link, consumes the token and decides through `approvals.service.decide` with `channel="whatsapp"` and the token's payload hash, exactly like web and Telegram. The answer is a fixed, localised session message sent after the commit: the decision, or the *current* state for a replayed, expired, stale or withdrawn button. A tap by a number that is not linked to an active member gets no reply; a different linked member who taps a forwarded button gets "this button is not valid", never the approval's state.

## Alternatives

1. **Full parity with Telegram**: free-text commands interpreted by the AI, notifications, buttons.
2. **Notifications and buttons only**: templates and fixed-text service messages out; reply-button taps and a one-time link code in; no free text reaches an LLM or the command system.
3. **Do not build WhatsApp**: rely on Web Push and Telegram.

## Decision

Option 2.

1. **What WhatsApp does.** (a) Sends owner notifications and the daily summary as approved **templates** outside the 24-hour window and as plain service messages inside it (Session 02). (b) Sends **interactive reply buttons** (approve, reject, maximum 3 buttons, titles of at most 20 characters) whose button ids are the existing opaque action tokens (Session 03). (c) Accepts a **one-time link code** as the only free text it understands (Session 01).
2. **What WhatsApp never does.** No owner free text is sent to the command interpreter, the account agent or any LLM. No free text decides an approval, changes a setting or creates content. A text message that is not a link code gets a fixed, localised, non-AI reply that points to the app (or, from an unknown number, no reply). Customer message text is never put in a WhatsApp message (same rule as Web Push: counts, types and links only), because the WhatsApp message is stored by a third party and may be forwarded.
3. **Why no free-text commands.** (i) Policy: a conversational AI on WhatsApp invites the section 4.7 "AI provider" review and a number ban would take the channel down with no appeal path we control. (ii) Safety: the invariants already say free text never approves, and a chat transcript can be forwarded, so only a server-resolved single-use token may decide. (iii) Cost: every inbound-triggered reply is a billable service message after the free tier. (iv) Scope: the web app and Telegram already serve commands.
4. **Linking.** The existing channel-link flow is reused: the owner generates a code in the web app (`POST /workspaces/{id}/channels/link-code` with `channel="whatsapp"`), then sends it to the business WhatsApp number. The inbound message is the owner's opt-in under the Business Messaging Policy and opens the 24-hour window, so the confirmation reply is a free-form service message. `channel_links.channel_user_id` and `channel_chat_id` hold the sender's `wa_id` (the number in international format without `+`). A number can have only one active link, as on Telegram.
5. **Webhook.** One endpoint `GET/POST /api/v1/webhooks/whatsapp`. GET answers the `hub.challenge` handshake after comparing `hub.verify_token` in constant time. POST verifies `X-Hub-Signature-256` (HMAC-SHA256 of the raw body with the app secret) before parsing anything, rejects a bad or missing signature with 401, and deduplicates by message id (Meta retries for up to 7 days). Replies are sent after the database transaction, never inside it.
6. **Boundary.** The adapter lives in `app/integrations/channels/whatsapp/`. Core modules (`app.core`, `identity`, `notifications`, `approvals`, `operations`, `inbox`, `content`, `commands`, and the rest listed in the contract in `backend/pyproject.toml`) never import it. Only the channel registry (lazily), the webhook router and the CLI/tests may. The core never learns that WhatsApp exists except through the `OwnerChannel` protocol and the channel name constants.
7. **Everything is off by default.** With no credentials the channel is unavailable: no route accepts traffic, the registry raises, link codes for `whatsapp` are refused with a clear error. CI uses a mock transport only. Live results stay "pending" until a verified number sends and receives for real.

## Consequences

- The WhatsApp channel is deliberately less capable than Telegram. An owner who wants to ask the assistant something uses the app or Telegram. This is a product limit we accept for policy safety.
- Template texts and their Meta approval are needed before notifications reach owners outside the window (Session 02). Until a template is approved, the channel only reaches owners who recently wrote to the number.
- Costs per message are real and are recorded in the delivery metadata (Session 02).
- A BSUID-only sender (no phone number in the payload) cannot be linked yet. This is a recorded limitation, not a silent fallback.
- If Meta judges the product an "AI provider", the channel can be switched off by removing the credentials; nothing in the core depends on it.

## Revisit when

- Meta changes section 4.7 or the messaging policy, or states how it treats business AI support.
- Pilot evidence shows owners need free-text commands on WhatsApp (this would need counsel's view and a new ADR).
- Meta ships first-party AI agent features for businesses on the platform that make a different design cheaper and safer.
