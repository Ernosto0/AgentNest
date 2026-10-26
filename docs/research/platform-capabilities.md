# External Platform Capabilities: Verified, Conditional, Unverified

**Purpose:** The single source of truth for what external platforms (Instagram/Meta, WhatsApp, Telegram, LLM providers) actually allow. It also records the architectural consequences and what still needs hands-on verification.
**Rule:** No document in this repository may claim a platform capability beyond what is marked **Confirmed (docs)** here. Capabilities marked **Conditional** or **Unverified** must be hidden behind capability flags and verified in the research spike ([roadmap.md](../implementation/roadmap.md), track R) before they are used with real accounts.

**Research method:** Official documentation was fetched on **2026-10-15**, summarised and quoted. Documentation is not the same as behaviour. Items labelled "Confirmed (docs)" are documented but **not yet tested against a live Meta app**. Re-check every item when the real integration is built (Phase 7), because Meta changes these pages frequently.

Status legend:
- **Confirmed (docs)**: stated in official documentation on the check date.
- **Conditional**: documented, but depends on access level, app review, account type or configuration.
- **Unverified**: not found in documentation, documentation is contradictory, or only secondary sources exist.
- **Unavailable**: documented as not supported.

---

## 1. Instagram Platform (Meta)

### 1.1 API configurations and account eligibility

| Capability | Status | Detail | Source (checked 2026-10-15) |
|---|---|---|---|
| Two API configurations exist | Confirmed (docs) | **Instagram API with Instagram Login** (host `graph.instagram.com`, Instagram User tokens, no Facebook Page required) and **Instagram API with Facebook Login for Business** (host `graph.facebook.com`, requires a linked Facebook Page). | https://developers.facebook.com/docs/instagram-platform/overview |
| Account type | Confirmed (docs) | Both require an Instagram **professional** account (business or creator). Personal accounts are not supported. | same |
| Feature parity | Confirmed (docs) | Both support comment moderation, content publishing, insights, mentions and messaging. Instagram Login does **not** support hashtag search, product tagging or partnership ads. | same |
| Instagram Login scopes | Confirmed (docs) | `instagram_business_basic`, `instagram_business_content_publish`, `instagram_business_manage_messages`, `instagram_business_manage_comments`. The old `business_*` scope values were deprecated on 2025-01-27. | https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login |

**Architectural implication:** We use **Instagram Login** first ([ADR-010](../architecture/decisions/ADR-010-instagram-provider-adapter.md)). Small businesses do not need a Facebook Page, and messaging is native. The provider interface must not leak which configuration is used, so a Facebook Login adapter can be added later if product tagging or hashtag search is ever needed.

### 1.2 Access levels, App Review, Business Verification

| Capability | Status | Detail | Source |
|---|---|---|---|
| Standard Access | Confirmed (docs) | Default access level. Intended for development, testing, and apps that serve only accounts the developer owns or manages, or accounts belonging to people with roles on the app. | https://developers.facebook.com/docs/instagram-platform/overview |
| Advanced Access | Confirmed (docs) | Required to serve accounts you do not own or manage. Requires **App Review and Business Verification**. | same |
| Standard Access limitations | Confirmed (docs) | "Some features might not work properly until your app has been granted Advanced Access." No list of which features is given. | same; search results on developers.facebook.com |
| Testers under Instagram Login | Conditional | App testers need a role on the app, must grant all required permissions, and must have a role on the Instagram professional account. Docs reference an "Instagram Tester" role. The exact onboarding flow and tester count limits were **not** found. | https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api |
| Webhooks require Live mode | Confirmed (docs) | "Your app must be set to Live in the App Dashboard for Meta to send webhook notifications." | https://developers.facebook.com/docs/instagram-platform/webhooks |
| Comment webhooks require Advanced Access | Confirmed (docs) | "Advanced Access is required to receive `comments` and `live_comments` webhook notifications." | same |

**Implications:**
1. **Early pilot path (to verify in research spike R-2):** with Standard Access, add each pilot business's Instagram account as a tester, so that the founder can connect it without App Review. This fits the assisted-onboarding strategy, but it is a stop-gap: it does not scale, and some features may not work. Tester limits and UX must be verified.
2. **App Review and Business Verification are on the critical path to self-service SaaS.** App Review typically needs a working app, a screencast per permission, a privacy policy URL and a data deletion mechanism. Start the application as soon as Phase 7 produces a working real flow.
3. **Comment automation** (likely valuable in Türkiye, see [mvp-scope.md](../product/mvp-scope.md)) cannot be piloted under Standard Access via webhooks.

### 1.3 OAuth and tokens (Instagram Login)

| Capability | Status | Detail | Source |
|---|---|---|---|
| Authorization URL | Confirmed (docs) | `https://www.instagram.com/oauth/authorize` with `client_id`, `redirect_uri`, `response_type=code`, `scope`. | business-login page |
| Authorization code | Confirmed (docs) | Valid **1 hour**, single use. | same |
| Code exchange | Confirmed (docs) | `POST https://api.instagram.com/oauth/access_token` → short-lived token. | same |
| Long-lived token | Confirmed (docs) | `GET https://graph.instagram.com/access_token` with `grant_type=ig_exchange_token`, **server-side only**. Valid **60 days**. | same |
| Refresh | Confirmed (docs) | `GET https://graph.instagram.com/refresh_access_token` with `grant_type=ig_refresh_token`. Conditions: token is **≥ 24 hours old**, **not expired**, and the user granted `instagram_business_basic`. "Tokens that have not been refreshed in 60 days will expire and can no longer be refreshed." | same |
| Deauthorize callback / data deletion callback for Instagram Login apps | Unverified | The Meta app-level data deletion callback (signed request, HMAC-SHA256 with app secret, response `{url, confirmation_code}`) is documented for Meta apps. The page does not say whether it covers Instagram Login apps, and no deauthorize callback was found. | https://developers.facebook.com/docs/development/create-an-app/app-dashboard/data-deletion-callback |

**Implications:** tokens are encrypted at rest. A daily job refreshes tokens that are older than 24 hours and expire within N days (default 20). Refresh failure moves the account to `needs_reauth` and notifies the owner. Data deletion must be possible even if the callback semantics differ ([workflows.md §G](../architecture/workflows.md), [security-and-privacy.md](../architecture/security-and-privacy.md)).

### 1.4 Webhooks

| Capability | Status | Detail | Source |
|---|---|---|---|
| Verification handshake | Confirmed (docs) | GET with `hub.mode=subscribe`, `hub.verify_token`, `hub.challenge`. Echo `hub.challenge` if the token matches. | https://developers.facebook.com/docs/instagram-platform/webhooks |
| Payload signature | Confirmed (docs) | Header `X-Hub-Signature-256: sha256=<hex>`. HMAC-SHA256 of the **raw payload** with the **App Secret**. Validation is optional per docs; **we make it mandatory**. | same |
| Response | Confirmed (docs) | Respond `200 OK` (HTTPS). No time limit is stated, so we respond immediately and process asynchronously. | same |
| Retries | Confirmed (docs) | Failed deliveries are retried immediately, then with decreasing frequency over **36 hours**, then dropped. | same |
| Batching | Confirmed (docs) | Up to **1000 updates** per batch; batching is not guaranteed. | same |
| Deduplication | Confirmed (docs) | "Your server should handle deduplication." | same |
| Ordering | Unverified | No ordering guarantee is documented, so we **assume none**. | same |
| HTTPS / mTLS | Confirmed (docs) | HTTPS required. Optional mTLS with Meta's client certificate (CN `client.webhooks.fbclientcerts.com`). The page notes a certificate change after the previous certificate expired on 2026-04-15. | same |
| Subscribable Instagram fields | Confirmed (docs) | `comments`, `live_comments`, `mentions`, `message_echoes`, `message_reactions`, `messages`, `messaging_handover`, `messaging_optins`, `messaging_policy_enforcement`, `messaging_postbacks`, `messaging_referral`, `messaging_seen`, `response_feedback`, `standby`, `story_insights`. | same |
| `message_echoes` under Instagram Login | Conditional | Listed in the webhooks field table but **not** in the Instagram Login messaging page's webhook list. Whether echoes arrive for messages sent from the native Instagram app (owner replying manually) must be verified. | messaging-api page vs webhooks page |

**Implications:** we store the raw event, verify the signature, deduplicate on `mid` or a payload hash, acknowledge within the request, and process in a job ([workflows.md §C](../architecture/workflows.md)). Owner-reply detection and send reconciliation **depend on echoes**. If echoes are unavailable, the fallbacks are the Conversations API lookup and treating ambiguous sends as "please check Instagram".

### 1.5 Messaging (Instagram Login)

| Capability | Status | Detail | Source |
|---|---|---|---|
| Customer-initiated only | Confirmed (docs) | "Only the Instagram user can start a conversation." | https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api |
| 24-hour window | Confirmed (docs) | "Your app has 24 hours to respond to any message sent from an Instagram user." | same |
| Human Agent tag | Conditional | Allows responses within **7 days**, "only for support cases that can't be resolved in the standard window". Listed as a separate permission ("Human Agent"). Intended for **human** responses, so it is not usable for AI-generated replies. | overview page |
| Send endpoint | Confirmed (docs) | `POST https://graph.instagram.com/v25.0/<IG_ID>/messages` (or `/me/messages`) with `recipient.id` = IGSID. | messaging-api page |
| Text limit | Confirmed (docs) | UTF-8, **≤ 1000 bytes**. | same |
| Attachments | Confirmed (docs) | Images png/jpeg ≤ 8 MB (up to 10 per message), audio ≤ 25 MB, video ≤ 25 MB, PDF ≤ 25 MB, heart sticker, reactions, shares of own posts. Quick replies and generic templates are documented separately. | same |
| Rate limits | Confirmed (docs) | Per account: Send API **100 calls/s** for text, **10 calls/s** for audio/video. Conversations API **2 calls/s**. Private Replies **750 calls/hour** for posts and reels. | overview page |
| Inbox folders | Confirmed (docs) | Non-follower conversations land in **Requests**. Replies sent via third-party apps move conversations to **General**. Requests inactive for 30 days are not returned by the API. Folders are not exposed via API. | messaging-api + overview |
| Group conversations | Unavailable | Not supported. | messaging-api page |
| Idempotency key on send | Unverified (assumed **unavailable**) | No idempotency mechanism is documented. | — |
| Automation disclosure | Confirmed (docs) | "Automated chats must disclose they are automated where legally required." | overview page |
| Required permissions | Confirmed (docs) | `instagram_business_basic`, `instagram_business_manage_messages`. | messaging-api page |

### 1.6 Content publishing

| Capability | Status | Detail | Source |
|---|---|---|---|
| Types | Confirmed (docs) | Single image, single video, Reels, Stories, carousels (up to 10 items). | https://developers.facebook.com/docs/instagram-platform/content-publishing |
| Two-step flow | Confirmed (docs) | `POST /<IG_ID>/media` creates a **container** (from `image_url`/`video_url`; resumable upload exists for large video), then `POST /<IG_ID>/media_publish` with `creation_id` publishes and returns the media ID. | same |
| Public media URL | Confirmed (docs) | "The media must be hosted on a publicly accessible server at the time of the attempt." | same |
| Image format | Confirmed (docs) | **JPEG only** (MPO/JPS unsupported). Feed images ≤ 8 MB, aspect ratio 4:5 to 1.91:1, width 320–1440 (scaled), sRGB. | content-publishing; https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media |
| Container status | Confirmed (docs) | `status_code` ∈ `FINISHED`, `IN_PROGRESS`, `ERROR`, `EXPIRED`, `PUBLISHED`. Containers expire if not published within **24 hours**. Polling is recommended once per minute for up to 5 minutes. | content-publishing |
| Publishing rate limit | Unverified (contradictory) | The same page says "**100** API-published posts within a 24-hour moving period" and, in the carousel section, "**50** published posts within a 24-hour period". `GET /<IG_ID>/content_publishing_limit` returns current usage. Separately, **400 containers** per rolling 24 hours. | content-publishing; ig-user/media |
| Native scheduling | Unavailable (not documented) | No scheduled-publish parameter is documented. Apps schedule themselves. | content-publishing |
| Stories | Conditional | `media_type=STORIES`. Images JPEG ≤ 8 MB (9:16 recommended). Video MOV/MP4, H.264/HEVC, 3–60 s, ≤ 100 MB. **No caption parameter documented.** Stickers, links and music are not documented. Business accounts only is commonly reported but **unverified**. | ig-user/media |
| Reels | Confirmed (docs) | `media_type=REELS`, MOV/MP4, H.264/HEVC, AAC ≤ 48 kHz, 23–60 FPS, 3 s – 15 min, ≤ 300 MB, ≤ 25 Mbps, 9:16 recommended. | ig-user/media |
| Unsupported | Unavailable | Shopping tags, filters (and product tagging under Instagram Login). | content-publishing; overview |
| Required permissions | Confirmed (docs) | Instagram Login: `instagram_business_basic`, `instagram_business_content_publish`. | content-publishing |

**Implications:**
- The scheduler is ours ([ADR-006](../architecture/decisions/ADR-006-postgres-job-queue.md)).
- The container ID is the **reconciliation handle** that prevents duplicate posts ([ADR-011](../architecture/decisions/ADR-011-external-operations-ledger.md)).
- Media storage must produce public or signed URLs reachable by Meta ([ADR-015](../architecture/decisions/ADR-015-media-storage.md)).
- PNG uploads are converted to JPEG.
- Story text lives in the image.
- The MVP publishes **feed images and story images** only. Video and Reels need transcoding and validation (ffprobe) and are deferred.
- The publish limit is enforced conservatively at **min(documented values) = 50 per 24 h**, and the `content_publishing_limit` endpoint is checked before each publish.

### 1.7 General API rate limits

| Capability | Status | Detail | Source |
|---|---|---|---|
| Business Use Case (BUC) limits | Confirmed (docs) | Most endpoints: 4800 × impressions calls per 24 h. Hashtag Search and Business Discovery use Platform Rate Limits. Meta recommends webhooks to reduce API calls. | overview page |
| Rate-limit response headers and exact error codes | Unverified | Need verification during Phase 7 (contract tests record real responses). | — |

---

### 1.8 Phase 7.5 research register (opened 2026-10-26)

The following are **open capability questions**, not evidence that a real account can perform an action. On 2026-10-26 an unauthenticated HTTP HEAD request reached the official Meta webhook, comment-moderation and messaging pages (HTTP 200 after redirects). The old private-replies URL below returned HTTP 404; this does not prove the feature was removed. The OpenAI function-calling guide redirected to `developers.openai.com` and returned HTTP 200. HEAD availability alone does not verify page contents, permissions, event payloads, quota semantics or actual behavior. No Meta app, token or live account was used. Retain real-capability flags off until fresh primary text and authentic sanitized observations are captured.

| ID | Primary source and question | Evidence status / implementation assumption |
|---|---|---|
| R75-01 | [Instagram webhooks](https://developers.facebook.com/docs/instagram-platform/webhooks), [overview](https://developers.facebook.com/docs/instagram-platform/overview) and [comment moderation](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/comment-moderation): current scopes, access level, webhook subscriptions and actual permission-return behavior for comments/private replies | Open. HEAD 200 for webhook and moderation pages on 2026-10-26; no authenticated permission response. A requested scope is not a granted capability. |
| R75-02 | [Instagram webhooks](https://developers.facebook.com/docs/instagram-platform/webhooks) and [comment moderation](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/comment-moderation): authentic comment create/update/delete/reply shapes, pagination/order, media ownership and native moderator changes | Open. No sanitized event/readback. Session 10 mock `changes` shapes are provisional; a signed mock event does not prove Meta delivery. Foreign media is always rejected. |
| R75-03 | [Comment moderation](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/comment-moderation): public reply readback, hide/unhide/delete response semantics, already-absent cases and outcome reconciliation | Open. HEAD 200 after redirect is only reachability. Real effects remain disabled until direct outcomes and readback are evidenced; a 404 alone does not prove deletion. |
| R75-04 | [Private replies (old path)](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/private-replies) and [messaging API](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api): source-comment eligibility, exact count/time limits, idempotency/reconciliation possibilities and returned recipient identity | Open. Old URL returned HTTP 404, messaging page HEAD 200. Treat one-shot/expiry as conservative provisional mock assumptions; real send disabled pending new primary source and account probe. |
| R75-05 | [Messaging API](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api) and [webhooks](https://developers.facebook.com/docs/instagram-platform/webhooks): when a private-reply recipient's response establishes ordinary DM eligibility and how comment and DM identities can be linked safely | Open. No authentic cross-surface identity/eligibility evidence; no handle/name merge. Existing uncertain-send reconciliation stays active. |
| R75-06 | [Instagram overview](https://developers.facebook.com/docs/instagram-platform/overview), [comment moderation](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/comment-moderation) and [webhooks](https://developers.facebook.com/docs/instagram-platform/webhooks): quotas/errors, moderation/reply races, revoked grants, post deletion and live account-type limitations | Open. No live error/race observations; Session 16 must capture authentic sanitized outcomes before enabling affected real actions. |

For each R75 item, Session 16 must record the document title/version or access failure, checked date, exact permission/access level, sanitized request/response or webhook fixture where applicable, and the specific account capability enabled. Separately, Session 04 must fixture-test the installed OpenAI SDK's current step/tool transport against [the official function-calling guide](https://platform.openai.com/docs/guides/function-calling) (HEAD 200 after redirect on 2026-10-26); that is model-adapter research, not R75 platform acceptance. Session 18 requires the full application workflow on an authorized account, not only a direct adapter probe. Offline work may use labelled provisional mock assumptions without presenting these questions as resolved.

## 2. WhatsApp Business Platform (Cloud API)

| Capability | Status | Detail | Source |
|---|---|---|---|
| Pricing model | Confirmed (docs) | **Per-message pricing since 2025-07-01**, replacing conversation-based pricing. Template categories: marketing, utility, authentication. | https://developers.facebook.com/docs/whatsapp/pricing |
| Customer service window | Confirmed (docs) | A user message opens a **24-hour** window. Non-template messages are only allowed, and are **free**, inside the window. Utility templates inside the window are free. | same |
| Türkiye | Confirmed (docs) | Türkiye is a standalone pricing market. Utility and authentication rates for Türkiye were **lowered effective 2026-04-01**. The billing currency for Türkiye is not stated. | same |
| Policy on AI chatbots | Conditional (secondary sources) | WhatsApp Business Solution terms effective **2026-01-15** bar providers whose **primary** functionality is a general-purpose AI assistant. Meta stated that businesses using AI to serve their own customers are not affected. Antitrust probes (EU, Italy, Brazil) were reported. **Primary source not yet read.** | TechCrunch 2025-10-18 (https://techcrunch.com/2025/10/18/whatssapp-changes-its-terms-to-bar-general-purpose-chatbots-from-its-platform) and other press |
| Requirements | Unverified | Meta business portfolio, phone number dedicated to the Cloud API, business verification for higher limits, template approval. Needs verification at decision time. | — |

**Implications for this product:** our use would be a business (us) messaging *our own customers* (business owners) with notifications and approvals, plus owner commands interpreted by AI. That is plausibly "business serving its customers", but whether the AI command interface counts as "incidental" is a **policy judgement Meta makes**. WhatsApp is therefore **not** a dependency of the core. Notifications outside the 24-hour window need paid utility templates. Decision deferred to pilot evidence ([ADR-012](../architecture/decisions/ADR-012-owner-channel-abstraction.md), [open-questions.md](open-questions.md) OQ-01).

---

## 3. Telegram Bot API

| Capability | Status | Detail | Source |
|---|---|---|---|
| Webhook with secret | Confirmed (docs) | `setWebhook` with `secret_token` (1–256 chars, `A-Za-z0-9_-`). Sent in the `X-Telegram-Bot-Api-Secret-Token` header. HTTPS on ports 443/80/88/8443. | https://core.telegram.org/bots/api |
| Long polling | Confirmed (docs) | `getUpdates` (does not work while a webhook is set). Useful for local development without a public URL. | same |
| Dedup | Confirmed (docs) | `update_id` is unique and increasing. Updates are kept ≤ 24 h. | same |
| Inline buttons | Confirmed (docs) | `callback_data` is 1–64 bytes, so approval buttons must carry an opaque short token, not a payload. | https://core.telegram.org/bots/api (search-confirmed) |
| File limits | Confirmed (docs) | Bots download ≤ **20 MB** via `getFile`. Upload ≤ **50 MB**. Photos via URL ≤ 5 MB. | same; https://core.telegram.org/bots/faq |
| Cost | Confirmed (general knowledge, not re-checked) | The Bot API is free. No business verification. | — |

**Implications:** Telegram is the cheapest way to build and test the owner-channel abstraction with a real external messenger. Owner adoption of Telegram in Türkiye is **unverified** and is a product question, not a technical one.

---

## 4. LLM provider (OpenAI API) facts used in the design

| Capability | Status | Detail | Source |
|---|---|---|---|
| Structured outputs | Confirmed in code (Phase 3: `openai` SDK 3.x, adapter and request body tested against a stubbed transport) | The Responses API accepts a Pydantic model as `text_format` and sends a strict JSON schema. Strict mode needs an object at the root, closed objects with all fields required and `anyOf` (not `oneOf`) unions. `responses.parse` returns the parsed object and the raw text. | SDK source, adapter tests |
| No retention | Confirmed in code | `store=false` on every request. | Adapter test |
| Reasoning tokens | Per SDK signature (`reasoning={"effort": ...}`); behaviour to be measured in the manual eval | Reasoning models spend output tokens on reasoning, so `max_output_tokens` must leave room: low effort by default. | SDK |
| Current model IDs | **Confirmed (2026-10-21)** on OpenAI's official docs: the GPT-6 family is `gpt-6-astra` ($10 / $50 per 1M tokens, input / output), `gpt-6.1-sol` ($2 / $10) and `gpt-6-luna` ($0.10 / $0.50, "our most efficient model for focused, high-volume tasks"; model ID and only snapshot `gpt-6-luna`, Responses API supported, `structured_outputs` listed); `gpt-6-sol` also appears on the pricing page only. | `LLM_MODEL_DEFAULT=gpt-6-luna`, the cheapest GPT-6 model. Not yet run against the real API (no key used): the strict-schema behaviour of the adapter is still unproven. | developers.openai.com/api/docs/models, /pricing and /models/gpt-6-luna |
| Data retention / processing location | Unverified for this use case | Needed for KVKK/GDPR analysis (sub-processor terms, regional processing options). | — |

**Implications:** the LLM adapter uses structured outputs, **not tools**, for all four LLM tasks ([ADR-009](../architecture/decisions/ADR-009-llm-provider-abstraction.md)). Outputs are re-validated with Pydantic regardless of provider guarantees, because other providers (or local models) may not enforce schemas. The model is configurable per task. Other model tiers are a cost decision for the founder, measured with the eval suite ([open-questions.md](open-questions.md) OQ-09).

---|---|---|---|
| Structured outputs | Confirmed (docs, via Claude API reference bundled with tooling, cached 2026-10-06) | `output_config: {format: {...}}` constrains the response to a JSON schema. The SDK provides a parse helper. The older `output_format` parameter is deprecated. | Claude API skill reference |
| Strict tool schemas | Confirmed (same) | `strict: true` on tool definitions guarantees schema-valid tool inputs. Forced `tool_choice` (`any`/`tool`) returns 400 on the newest models (Opus 5.5, Sonnet 5.5, Fable 5.1). | same |
| Current model IDs | Confirmed (same) | `claude-opus-5-5` (default), `claude-sonnet-5-5`, `claude-haiku-5-5`. | same |
| Data retention / processing location | Unverified for this use case | Needed for KVKK/GDPR analysis (sub-processor terms, regional inference options). | — |

**Implications:** the LLM adapter uses structured outputs, **not tools**, for all four LLM tasks ([ADR-009](../architecture/decisions/ADR-009-llm-provider-abstraction.md)). Outputs are re-validated with Pydantic regardless of provider guarantees, because other providers (or local models) may not enforce schemas. The model is configurable per task. Cheaper models are a cost decision for the founder, measured with the eval suite ([open-questions.md](open-questions.md) OQ-09).

---

## 5. KVKK (Türkiye personal data law): items relevant to architecture

**Not legal advice.** These items drive engineering requirements and must be reviewed by a qualified lawyer before commercial pilots.

| Item | Status | Detail | Source |
|---|---|---|---|
| Cross-border transfer regime changed in 2024 | Conditional (secondary sources) | Law No. 7499 amended Art. 9 of KVKK (6698). Standard contracts became an appropriate safeguard for transfers abroad. Standard contracts must be **notified to the Authority within 5 business days** of signature. An online notification module was launched (Board decision 2024/1793, 2024-10-17). Explicit-consent-based transfers were accepted only until 2024-09-01. | Secondary: https://www.alomaliye.com/2024/10/30/kvkk-standart-sozlesme-bildirim-modulu/, https://www.erdem-erdem.av.tr/bilgi-bankasi/kisisel-verilerin-yurt-disina-aktarilmasinda-yasanan-son-gelismeler |
| Fines for missing notification | Unverified | A secondary source cites 2026 administrative fine ranges. Verify against official publications. | cottgroup.com (secondary) |

**Implications:** hosting outside Türkiye, using a foreign LLM API, or using foreign object storage are each potentially cross-border transfers of end-customer personal data (DM content, usernames). The architecture minimises personal data sent to the LLM (no usernames or IDs in prompts) and keeps a sub-processor register. It also allows a region choice for hosting. See [security-and-privacy.md §7](../architecture/security-and-privacy.md).

---

## 6. Verification backlog (feeds research track R in the roadmap)
**Phase 7 offline update (2026-10-23):** Sessions 1-4 implement synthetic fixture contracts, OAuth/refresh/disconnect and UI, plus a manually opted-in adapter harness. They provide no live platform evidence. V-01/V-02/V-03/V-05/V-08/V-09, Gate 2 and P7-00's final research-based re-plan remain pending. Story support, actual scope/token response envelopes, native echo delivery, account webhook subscription and signed media fetch behavior must be verified before real acceptance. All committed Meta JSON fixtures remain explicitly synthetic; there are no authentic recordings.

Official Meta [business-login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login) and [webhook](https://developers.facebook.com/docs/instagram-platform/webhooks/) pages returned HTTP 429 on 2026-10-23. Unreachable pages do not reconfirm the older 2026-10-15 claims. The local setup checklist records provisional dashboard steps and required future verification. Public [Vite host allow-list](https://vite.dev/config/server-options#server-allowedhosts) and [Cloudflare Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) docs were accessible and support the same-origin development setup only; no public tunnel was launched. The `meta_live` harness remains unrun; no provider/bucket/tester facts were promoted by this session.


| ID | What to verify | How | Blocks |
|---|---|---|---|
| V-01 | Tester onboarding under Instagram Login + Standard Access: can a non-owned business account be added as a tester, and how many? Do messaging webhooks and publishing work under Standard Access with Live mode? | Create Meta app, add founder's own test IG business account, then one friendly business. | Pilot plan (Phase 7) |
| V-02 | `message_echoes` delivery under Instagram Login, including for replies typed in the native Instagram app. | Subscribe, send from app and from API, inspect payloads. | Owner-reply detection, send reconciliation |
| V-03 | Story publishing via API: account types, captions/overlays, behaviour and errors. | Publish test story. | Story support claim |
| V-04 | Actual publish limit (50 vs 100) and `content_publishing_limit` response shape. | Call endpoint. | Rate guard config |
| V-05 | Error codes for expired token, revoked permission, rate limit, window closed and invalid media. | Trigger deliberately, record fixtures for contract tests. | Error mapping in `MetaInstagramProvider` |
| V-06 | Data deletion / deauthorization callbacks for Instagram Login apps. | App dashboard and docs. | Production readiness |
| V-07 | App Review requirements and timeline for `instagram_business_manage_messages` and `instagram_business_content_publish`; Business Verification documents for the founder's legal entity in Türkiye. | Start the application. | Self-service SaaS |
| V-08 | Webhook payload shape for messages with attachments, story replies, story mentions, reactions and deleted messages. | Live capture. | Inbound parser |
| V-09 | Media fetch behaviour with signed URLs (expiry tolerance, redirects, content-type requirements). | Publish with S3 presigned URL. | Media storage |
| V-10 | WhatsApp terms primary text regarding AI functionality; business verification requirements in Türkiye. | Read terms; consult Meta partner if needed. | OQ-01 decision |
| V-11 | LLM provider data retention, sub-processor terms, regional processing options. | Provider terms. | KVKK assessment |
