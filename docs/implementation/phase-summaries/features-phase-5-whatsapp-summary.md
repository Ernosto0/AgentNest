# Feature Phase 5, Track A close-out: WhatsApp owner channel (F-06)

- **Track:** A of Feature Phase 5 (`docs/implementation/features-phase-5-on-demand/sessions.md`), Sessions 01 to 03
- **Decision record:** [ADR-027](../../architecture/decisions/ADR-027-whatsapp-owner-channel-scope.md)
- **Baseline:** `1a58d41`. **Migrations:** `0070` (WhatsApp channel values and `whatsapp_webhook_events`), `0071` (`channel_links.last_inbound_at`), chained `0061 -> 0070 -> 0071` (re-chained at merge; merged chain `0061 → 0070 → 0071 → 0080 → 0081 → 0082 → 0083 → 0090 → 0091 → 0100`). No migration in Session 03.
- **Status:** Implemented offline, stopped for review. Nothing is committed. Everything live is **pending**.
- **Trigger:** OQ-01 was treated as answered by the owner's request of 2026-11-17/18 to implement all Feature Phase 5 sessions. Trigger evidence (pilot owners will not use Telegram or push) is **not yet recorded**; no pilot feedback was invented.

## 1. What the track delivers

WhatsApp as an optional, off-by-default second owner channel that is deliberately narrower than Telegram: notifications, fixed replies and approve/reject buttons only. Owner free text never reaches commands, the agent or any LLM, and never decides anything.

| Session | Change |
|---|---|
| 01 | Meta policy reading (Terms section 4.7 "AI Providers", Business Messaging Policy, pricing change of 2026-10-01) and ADR-027; `WhatsAppClient` (template, interactive buttons, text; limit validation, no retries, ambiguity flagged, token redaction); signed webhook (`GET` handshake, `POST` with `X-Hub-Signature-256` checked before parsing, dedup by message id in `whatsapp_webhook_events`); linking by the existing one-time code sent to the business number; settings (all optional); import-linter contracts; a minimal Settings block in the UI |
| 02 | `WhatsAppChannel` on the existing delivery ledger; pure 24-hour window rule from `channel_links.last_inbound_at` and the injected clock (5-minute margin); template registry (10 templates x TR/EN, utility); dispatch for the Web Push types plus the daily summary with quiet hours; cost metadata (category only, no invented price); ambiguous sends never re-sent (`sending` marker) |
| 03 | Approve and reject reply buttons carrying the Phase 9 action tokens; button replies decide through `approvals.service.decide(channel="whatsapp")`; fixed replies with the current state for replay, expiry, stale and withdrawn approvals; template without buttons outside the window; skipped-by-default live probe |

## 2. Proof, by item

| Item | Tests |
|---|---|
| Signature, handshake, parsing, dedup, status events | `tests/unit/integrations/channels/test_whatsapp_webhook_format.py`, `tests/contract/test_whatsapp_adapter.py` |
| Client payloads, limits, errors, ambiguity, token redaction | `tests/unit/integrations/channels/test_whatsapp_client.py` |
| Linking, supersede, forced RLS, cross-workspace codes | `tests/contract/test_whatsapp_adapter.py`, `tests/isolation/test_whatsapp_link_isolation.py`, `tests/unit/identity/test_channel_links.py` |
| No owner text reaches commands or AI | `test_free_text_never_commands_or_ai`, import-linter contract `whatsapp-no-commands-or-ai` |
| Window rule and template-versus-session | `tests/unit/integrations/channels/test_whatsapp_templates.py`, `tests/integration/notifications/test_whatsapp_channel.py` |
| Delivery isolation and ledger | `tests/isolation/test_whatsapp_delivery_isolation.py` |
| Buttons out with the proposed text shown, truncation, customer text never present | same file (`test_a_reply_approval_shows_...`, `test_a_long_reply_is_cut_...`, `test_a_content_approval_shows_the_post`) |
| Buttons out, tokens hashed and bound, no token in metadata or logs | `tests/integration/notifications/test_whatsapp_approval_buttons.py` |
| Outside the window: template, no buttons | same file, `test_outside_the_window_...`, `test_the_window_is_judged_at_send_time_...` |
| Decision through the approval service, replay, expiry, stale, forwarded, unlinked, revoked, decided on the web, duplicate webhook, free text | same file (38 cases) |
| Live probe skipped without credentials, never uses app settings | `tests/contract/test_whatsapp_live.py`, `tests/unit/integrations/channels/test_whatsapp_live_safety.py` |

Check results are in the [Session 03 report](../features-phase-5-on-demand/s03-report.md).

## 3. Demo steps (offline, mock transport)

1. In `backend/.env` set the WhatsApp variables to dummy values (`docs/operations/environment-variables.md`); there is no network call without a real token. Run the contract and integration tests above; they replace Meta with `httpx.MockTransport`.
2. Settings, Channels: "Connect WhatsApp" shows a one-time code and a `wa.me` link (visible only when the server is configured).
3. Send the code to the business number: the webhook links the number and replies with a fixed sentence.
4. A new approval request reaches a linked owner as a two-button message if the owner wrote within 24 hours, otherwise as the approval template (buttons absent, "open the app").
5. Tapping a button decides the approval once; tapping it again answers with the current state.

## 4. Deviations

- Session 01 corrected the earlier claim that service messages are free (charged after 1,000 per number per month since 2026-10-01).
- No per-category WhatsApp preference (linking is the opt-in); quiet hours hold and do not release (existing policy).
- The approval button message shows what is being approved (the proposed outgoing reply or caption, title, schedule, price or time change, clipped to 1,000 characters with "full text in the app"; the approval binds to the full payload hash) but never the customer's inbound message or handle (ADR-027). Changed from a kind-label-only first draft after review: approval must be informed.
- `consume_action_token` gained a `channel` argument and `lookup_action_token` was added (Phase 9 code, backwards compatible).

## 5. Limitations

- Everything runs against a mock transport. No verified number, no approved template, no real window or tap has been exercised.
- Template status is a manual switch (`WHATSAPP_TEMPLATES_APPROVED`); `message_template_status_update` webhooks are not handled.
- A BSUID-only sender (no phone number in the payload) cannot be linked.
- No Türkiye price is recorded (`price_verified: false`); costs are category counts.
- No quick-reply button on a template and no deep link in any message.
- The Terms section 4.7 text was read in Turkish through a page-to-text tool; counsel's read in English is needed before the first paying WhatsApp owner.
- A WhatsApp number has one active link; linking it elsewhere supersedes the first.
- Meta decides in its sole discretion whether the product is an "AI provider"; WhatsApp can be switched off by removing the credentials and nothing in the core depends on it.

## 6. Pending live (do not claim)

A verified Meta business number and app; the webhook subscription and callback; a real link-code round trip; approval of 20 template versions (10 x tr/en); Meta's error code for a template-less send outside the window; a real status webhook with `pricing`; the Türkiye rate card and billing currency; a real interactive message, a real tap and the behaviour of forwarded buttons; counsel's English read of section 4.7. The probe harness (`pytest -m whatsapp_live` with the three `WHATSAPP_LIVE_*` variables) covers the first send and the interactive message.

## 7. Questions

1. (Resolved 2026-11-18: approval must be informed; the message shows the proposed text.)
2. Per-category WhatsApp preference before the first pilot owner is linked?
3. Should a summary held by quiet hours be released when quiet hours end (a policy change for all external channels)?
4. Who reads the Türkiye rate card for the sending number so `price_verified` can become true?
5. Should the Settings UI show the business number outside the code modal?
