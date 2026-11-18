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
| Story reply and story mention payloads | Unverified | F-04 assumes a story reply is `message.reply_to.story = {id, url}` and a mention is an attachment of type `story_mention` with a CDN `payload.url`. Neither carries a caption; a mention carries no story id. Whether the Graph API can read a story's caption or text is **not confirmed** (a story lasts 24 hours and its media object is not documented with a caption), so AgentNest uses only its own stored content for a story it published, and assumes (unverified, V-03/V-08) that the media id it stored when publishing is the `story.id` of a reply. Our parser and fixtures are synthetic. | V-08 |
| `message_echoes` under Instagram Login | Conditional | Listed in the webhooks field table but **not** in the Instagram Login messaging page's webhook list. Whether echoes arrive for messages sent from the native Instagram app (owner replying manually) must be verified. | messaging-api page vs webhooks page |

**Implications:** we store the raw event, verify the signature, deduplicate on `mid` or a payload hash, acknowledge within the request, and process in a job ([workflows.md §C](../architecture/workflows.md)). Owner-reply detection and send reconciliation **depend on echoes**. If echoes are unavailable, the fallbacks are the Conversations API lookup and treating ambiguous sends as "please check Instagram".

### 1.5 Messaging (Instagram Login)

| Capability | Status | Detail | Source |
|---|---|---|---|
| Customer-initiated only | Confirmed (docs) | "Only the Instagram user can start a conversation." | https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api |
| 24-hour window | Confirmed (docs) | "Your app has 24 hours to respond to any message sent from an Instagram user." | same |
| Human Agent tag | Conditional | Allows responses within **7 days**, "only for support cases that can't be resolved in the standard window". Listed as a separate permission ("Human Agent"). Intended for **human** responses, so it is not usable for AI-generated replies. Researched in detail in [section 1.10](#110-human-agent-message-tag-feature-phase-5-session-09-researched-2026-11-18); implemented behind `META_HUMAN_AGENT_ENABLED` (default off) for a person's own typed replies only. | overview page; section 1.10 |
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
| Reel video specification (Session 06) | Confirmed docs; live acceptance pending | Full specification, deliberate warnings and conflicts below. Session 06 added upload/storage; Session 07 added offline publishing via `poll_reel_container` backoff job; live acceptance pending. | S1–S3 & P1–P5 below, accessed 2026-11-18 |
| Carousels (F-08, researched 2026-11-18) | Confirmed (docs), count conflicting | Flow: one container per item with `is_carousel_item=true`, then a `media_type=CAROUSEL` container with `children` (comma list of container IDs) and `caption`, then `media_publish`. **Item count:** the Meta pages read on 2026-11-18 say "Carousels are limited to 20 images, videos, or a mix of the two" and `children` is "up to 20 container IDs"; earlier documentation and several third-party guides say 10. AgentNest caps a carousel at **10** (the Feature Phase 5 decision) and requires at least **2**, which is valid under either reading; raising the cap is one constant and a doc change. **Aspect ratio:** "Carousel images are all cropped based on the first image in the carousel, with the default being a 1:1 aspect ratio"; each image must also be within 4:5 to 1.91:1 (the general image rule). The docs do not say mixed ratios are rejected, only that they are cropped to the first, so AgentNest rejects mixed ratios at submit to avoid a surprise crop. JPEG only. **Caption:** set on the carousel container only ("Not supported on images or videos in carousels"). `alt_text` is supported on image children; `location_id` and `is_ai_generated` are not supported on children. A carousel counts as one post for the publishing rate limit. Reels cannot be carousel items. | https://developers.facebook.com/docs/instagram-platform/content-publishing ; https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media (accessed 2026-11-18) |

Session 05 (2026-11-18): the documented child -> carousel -> media_publish flow is implemented in mock and Meta adapters with offline request/persistence tests. Meta status values include EXPIRED (24 h), ERROR, FINISHED, IN_PROGRESS and PUBLISHED. Existing polling remains 10 seconds / 5 minutes (Meta recommends once a minute, at most 5 minutes). A carousel counts once at media_publish; children do not consume post quota. Live behaviour remains pending; no live calls were made. Album insights and per-image alt text remain out of scope.

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

### Reel video specification — Feature Phase 5, Session 06

Sources supplied by the session lead, accessed **2026-11-18** (no new web research):
- S1: https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media — Reel Specifications, cover photo, Story Video Specifications and request parameters.
- S2: https://developers.facebook.com/documentation/instagram-platform/content-publishing — Reels posts, polling and resumable upload via `rupload.facebook.com`.
- S3 (advisory only, Facebook Page Reels, not Instagram): https://developers.facebook.com/documentation/video-api/guides/reels-publishing — recommends 1080x1920, minimum 540x960, 24–60 fps.

Verbatim Instagram specification from S1:

| Item | Meta's text |
|---|---|
| Container | "MOV or MP4 (MPEG-4 Part 14), no edit lists, moov atom at the front of the file." |
| Audio codec | "AAC, 48khz sample rate maximum, 1 or 2 channels (mono or stereo)." |
| Video codec | "HEVC or H264, progressive scan, closed GOP, 4:2:0 chroma subsampling." |
| Frame rate | "23-60 FPS." |
| Picture size | "Maximum columns (horizontal pixels): 1920". "Required aspect ratio is between 0.01:1 and 10:1 but we recommend 9:16 to avoid cropping or blank space." |
| Video bitrate | "VBR, 25Mbps maximum" |
| Audio bitrate | "128kbps" (informational; not enforced) |
| Duration | "15 mins maximum, 3 seconds minimum" |
| File size | "300MB maximum" |

Cover photo: JPEG, maximum 8 MB, sRGB, 9:16 recommended. Other ratios are cropped to the central 9:16 rectangle and the central square when shared to feed. `cover_url` (public JPEG) wins over `thumb_offset` (milliseconds, default 0). `share_to_feed` does not guarantee placement.

`media_type=REELS` plus `video_url` requires a public fetchable video (S1: "We cURL the video using the passed-in URL, so it must be on a public server."). Session 07 will use an S3 presigned URL. Acceptance of presigned URLs for video and required URL lifetime are **pending live verification**; `MEDIA_PUBLIC_URL_TTL_SECONDS=3600` must outlast processing. Video containers are asynchronous: poll `GET /<container>?fields=status_code` for `EXPIRED`, `ERROR`, `FINISHED`, `IN_PROGRESS`, `PUBLISHED`. Meta recommends once per minute for at most 5 minutes. Publishing and polling belong to Session 07.

Conflicts and enforcement decisions:
1. S1's Reel ratio lower bound is 0.01:1, while Story Video specifies 0.1:1. Product validation conservatively uses 0.1–10 on displayed dimensions (rotation applied).
2. These pages disagree on 100 vs 50 daily publications; the product retains 50 (Session 04).
3. Closed GOP cannot be reliably reported by ffprobe. Edit lists can be structurally detected but their compatibility cannot be established without decoding/live acceptance. S1 says no edit lists; common iPhone AAC priming uses them. `REJECT_EDIT_LISTS=False` issues `EDIT_LIST_PRESENT` as a non-blocking warning; one boolean flips rejection. Closed GOP and audio bitrate are not checked; edit-list semantics are not checked.

The 300 MB cap is decimal 300,000,000 bytes. Exactly one video track (attached cover pictures ignored), duration 3–900 seconds, H.264/HEVC, progressive 4:2:0, 23–60 fps (0.05 tolerance), displayed width <=1920, both dimensions >=64, <=25 Mbps, optional AAC audio <=48 kHz with 1–2 channels. The first top-level `moov`/`mdat` must be `moov`. Non-9:16 (outside 2%) and width below 540 are warnings; S3's resolution guidance is not an Instagram hard limit. MP4/MOV require `ftyp`; MOV major brand is `qt  `; 3GP/3G2/M4A/MJ2 are refused. Named constants live in `backend/app/content/video.py`.

Third-party guides (adaptlypost.com and website-apn.pages.dev) are not authoritative and are not relied on. See [ADR-028](../architecture/decisions/ADR-028-video-media-probing-and-storage.md).

#### Reels publishing - Feature Phase 5, Session 07

Accessed 2026-11-18.

Sources:
- P1: https://developers.facebook.com/docs/instagram-platform/content-publishing (Reels posts, container status, resumable upload, publishing limit)
- P2: https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media (request parameters, Reel specifications, cover photo)
- P3: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-container (status_code values)
- P4: https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/error-codes.md (error subcodes)
- P5: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/content_publishing_limit (quota)

Findings:
1. **Container creation** (`POST /<IG_ID>/media`): `media_type=REELS` (required for reels), `video_url` ("Path to the video. We cURL the video using the passed-in URL, so it must be on a public server."; P1: publicly accessible "at the time of the attempt"), `caption` ("Maximum 2200 characters, 30 hashtags, and 20 @ tags."), `share_to_feed` ("For Reels only. When `true`, indicates that the reel can appear in both the Feed and Reels tabs."; Meta documents no default, so AgentNest always sends an explicit `true`/`false`; placement is not guaranteed), `cover_url` ("For Reels only. The path to an image to use as the cover image for the Reels tab."; JPEG, max 8 MB, sRGB, 9:16 recommended, other ratios are cropped to the middle 9:16 rectangle and, for the feed post, the middle 1:1 square), `thumb_offset` ("For videos and reels. Location, in milliseconds, of the video or reel frame to be used as the cover thumbnail image." default 0). "If you specify both `cover_url` and `thumb_offset`, we use `cover_url` and ignore `thumb_offset`." AgentNest sends only one of them and rejects both being set. Error subcode 2207057 (P4): offset must be >= 0 and < video duration.
2. **Container status** (`GET /<container>?fields=status_code,status`, P1/P3): `IN_PROGRESS` ("still in the publishing process"), `FINISHED` ("ready to be published"), `PUBLISHED`, `ERROR` ("failed to complete the publishing process"; the `status` field then carries an error subcode, P3), `EXPIRED` ("not published within 24 hours and has expired"; containers expire 24 hours after creation, so a new container is needed).
3. **Polling advice** (P1): "We recommend querying a container's status once per minute, for no more than 5 minutes." P3 gives no extra advice. Video processing is asynchronous and can take longer for long reels; AgentNest polls with a back-off schedule up to a 30-minute budget (deliberately more tolerant than Meta's 5 minutes; polling is a cheap read; **how long real reels take is pending live data**).
4. **Publish** (`POST /<IG_ID>/media_publish` with `creation_id`): returns the media id; a published reel reads back as `media_type=VIDEO` with `media_product_type=REELS`. The publish response can be lost, so it is treated as ambiguous (see ADR-011).
5. **Resumable upload** (P1/P2): `upload_type=resumable` then `POST https://rupload.facebook.com/ig-api-upload/<API_VERSION>/<CONTAINER_ID>` with `Authorization: OAuth <token>` and `offset`/`file_size` headers (local bytes) or a `file_url` header. P1 lists it only for apps using Facebook Login for Business. **Not used**: AgentNest uses `video_url` with an object-storage presigned URL (the 300 MB cap fits). Whether Meta accepts presigned S3 URLs for videos, and the URL lifetime needed, are **pending live verification**; `MEDIA_PUBLIC_URL_TTL_SECONDS` (3600) must outlast Meta's fetch.
6. **Publishing limit**: P1 says 100 API-published posts per moving 24 hours (carousel counts as one), P5 says `quota_total` 50 per `quota_duration` 86400 s; neither says whether a Reel counts differently. AgentNest keeps its existing conservative 50 per 24 h and counts **one post per reel**; this is checked through `get_publishing_quota` before T1 as for images; **live behaviour pending**.
7. **Error subcodes** (P4, Meta's own table): 2207026 "The video format is not supported" (no retry; change format); 2207003 "It takes too long to download the media" (retry); 2207032 "Create media fail, please try to re-create media" (retry); 2207053 "unknown upload error" (retry with a **new container**, video only); 2207057 thumbnail offset out of range (no retry until corrected). 2207076 ("Media upload has failed") appears only in third-party reports and is not in Meta's table; treated as a non-retryable media error. Third-party sources are not authoritative.
8. Product decisions: a reel's caption follows the feed-post rules (required, max 2200 characters, claim validator and facts); the video is not transcoded; the video itself cannot be checked for facts (a price spoken or drawn inside a video is **not** verified by the claim validator; record this as a limitation in the docs and the UI help text, the owner is responsible for it); `publish_reel` capability is derived from the same scope as `publish_feed_image` (**unverified live**).

### 1.7 General API rate limits

| Capability | Status | Detail | Source |
|---|---|---|---|
| Business Use Case (BUC) limits | Confirmed (docs) | Most endpoints: 4800 × impressions calls per 24 h. Hashtag Search and Business Discovery use Platform Rate Limits. Meta recommends webhooks to reduce API calls. | overview page |
| Rate-limit response headers and exact error codes | Unverified | Need verification during Phase 7 (contract tests record real responses). | — |

---

### 1.8 Comment research register (R75-01 to R75-06; refreshed 2026-11-17)

**Feature Phase 3, Session 01 (2026-11-17).** The official Meta pages that were unreachable on 2026-10-26 and 2026-10-29 (HTTP 404, 429 or "inaccessible") could be read on 2026-11-17. Meta has moved the Instagram documentation from `/docs/instagram-platform/...` to `/documentation/instagram-platform/...`, and each page has a Markdown twin with a `.md` suffix. The index is `https://developers.facebook.com/documentation/instagram-platform/llms.txt`. Pages were read through a fetch tool that summarises them, not through a browser, so every statement below is "read in documentation on 2026-11-17", never "verified by test". **No Meta app, token, test account or webhook was used. Nothing here is an authentic recording.** Re-read the cited page before relying on a detail for a rollout or an App Review answer.

Result: the documentation answers parts of R75-01, R75-02, R75-03, R75-04 and R75-05. Everything that depends on observed behaviour (what a request or webhook really returns, error codes, races, quotas) is **carried forward** to Session 02's live probe on a dev-mode test account (or to Session 18-style live evidence). Session 02 keeps real comment capabilities off by default: only scope plus owner opt-in may derive `comment_read` and `comment_private_reply`; `comment_reply` and `comment_moderate` stay false. The OAuth scope request and the new derived capability `comments_permission` (scope granted) enable nothing by themselves.

Sources (all read 2026-11-17):
- S1 [Comment moderation](https://developers.facebook.com/documentation/instagram-platform/comment-moderation.md) (the older `/docs/instagram-platform/instagram-api-with-instagram-login/comment-moderation` URL is the Instagram Login variant of the same page)
- S2 [Private replies](https://developers.facebook.com/documentation/instagram-platform/private-replies.md)
- S3 [Webhooks overview](https://developers.facebook.com/documentation/instagram-platform/webhooks.md), [fields and permissions matrix](https://developers.facebook.com/documentation/instagram-platform/webhooks/fields.md), [setup](https://developers.facebook.com/documentation/instagram-platform/webhooks/setup.md), [examples](https://developers.facebook.com/documentation/instagram-platform/webhooks/examples.md)
- S4 [IG Comment reference](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-comment.md)
- S5 [IG Media comments reference](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-media/comments.md)
- S6 [App Review](https://developers.facebook.com/documentation/instagram-platform/app-review.md)
- S7 [Error codes](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/error-codes.md) (covers publishing codes only; nothing for comments or private replies)

| ID | Question | Answer from documentation (2026-11-17) | Status and what is carried forward |
|---|---|---|---|
| R75-01 | Scopes, access level, webhook subscriptions, permission-return behaviour | **Scopes.** Instagram API with Instagram Login (the product this app uses, `graph.instagram.com`, Instagram User access token): `instagram_business_basic` + `instagram_business_manage_comments` for reading and replying to comments, hide/unhide, delete, and for private replies (S1, S2, S4, S5). For private replies the Instagram Login column lists no messaging permission; the Unified Login column says private replies also need `instagram_manage_messages` (S2). The app already requests `instagram_business_manage_messages`, so both are held. **Access level.** Under S6 `instagram_business_manage_comments` is an Advanced Access permission needing App Review when the app serves businesses you do not own or manage; Standard Access (no review) covers accounts you own or manage and have added to the app (S1, S6). **Webhooks.** Fields `comments` and `live_comments` need `instagram_business_basic` + `instagram_business_manage_comments` under Instagram Login (S3 matrix); `mentions` arrive inside `comments`. Subscribe each account with `POST https://graph.instagram.com/<version>/<IG_ACCOUNT_ID>/subscribed_apps?subscribed_fields=<fields>` using the Instagram User token; success is `{"success": true}`. The app must be Live to receive notifications for app users, and the setup page states that Advanced Access is required for `comments` and `live_comments` notifications (S3 setup). | **Answered from docs.** Carried forward: (a) what the token-exchange `permissions` list actually contains after a user grants or declines the new scope (the existing OAuth code stores whatever Meta returns); (b) whether `comments` delivery works under Standard Access for role users in Development mode (the docs imply it does for owned accounts, but no page says so explicitly); (c) which `subscribed_fields` values this app may subscribe (a 2026-10 live check found `message_echoes` rejected with error 100 and only `messages` accepted, see `oauth-account-identity-fix.md`; `comments` is untested); (d) the app does not call `subscribed_apps` for comments yet (Session 02). |
| R75-02 | Comment event shapes, pagination/order, media ownership, native moderator changes | **Webhook shape (Business Login for Instagram).** `field` is `comments` or `live_comments`; `value` carries the comment `id`, `from` (Instagram-scoped `id` and `username`), `text` when present, and `media` (`id`, `media_product_type`). `parent_id` appears when a comment is made on a comment (S3 examples; the example with `comment_id` and `parent_id` is the Unified Login one, so the exact key for the comment ID and for replies under Instagram Login is **not** confirmed). **Reads.** `GET /<media>/comments` returns top-level comments only, newest first, at most 50 per query, cannot filter by time, and returns `timestamp`, `text`, `id` (replies only through the `replies` field expansion); the token must belong to the media owner (S5). `GET /<comment>` fields: `from`, `hidden`, `id`, `like_count`, `media`, `parent_id`, `replies`, `text`, `timestamp`, `username`; comments on age-gated media and by restricted users are not returned (S4). `ordered_comments` exists for Facebook Login only (S1). Creating comments is unsupported (S4). | **Partly answered.** Carried forward: authentic comment create payload under Instagram Login (key names for the comment ID and reply parent), whether edits and deletes (including deletes by the owner in the Instagram app and moderation changes made natively) produce any webhook (the examples describe none), cursor pagination of `/comments` (not documented; "at most 50" only), ordering guarantees, and media-ownership failure responses. The mock's `changes` shape stays provisional. Session 02 parses documented Instagram Login comment events offline; authentic delivery is pending. |
| R75-03 | Public reply readback, hide/unhide/delete semantics, already-absent cases, reconciliation | **Reply:** `POST /<comment>/replies` with JSON `message`; response `{"id": "<new comment id>"}` (S1). **Hide/unhide:** `POST /<comment>?hide=<true|false>`, `hide` required, media owner's token; response `{"success": true}`; comments by the media owner on their own media always display even with `hide=true`; live-video comments unsupported (S4). **Delete:** `DELETE /<comment>`, response `{"success": true}`; the page says both "token of the user who created the comment" and "only the owner of the object the comment was made on can delete", which it does not reconcile; live-video comments unsupported (S4). Readback exists: `GET /<comment>` returns `hidden` and `replies`. | **Partly answered.** Carried forward: behaviour for an already-deleted or already-hidden comment, the real error for a missing comment, whether `hidden` readback is immediate, response on malformed or ambiguous outcomes, and how to reconcile an unknown reply outcome (a missing reply in `replies` still proves nothing). Hide/delete stay disabled in the adapter. |
| R75-04 | Private-reply eligibility, count/time limits, idempotency, recipient identity | `POST <IG_ID>/messages` with `recipient.comment_id` and `message.text`; success returns `recipient_id` (Instagram-scoped ID) and `message_id` (S2). Eligible comments are on the account's own post, reel, story, Live or ad post. **Time:** within **7 days** of the comment; for Live only **during the broadcast**. **Count:** "Only one message can be sent to the commenter" (S2). Delivery goes to the Inbox if the person follows the account, otherwise to the Request folder, and includes a link to the post. No idempotency key, readback or error list is documented. | **Partly answered.** Carried forward: whether the one-message limit is per comment or per commenter (the wording says "commenter"; until clarified the app must treat it as at most one per commenter per account and never retry an unknown outcome), whether replies to replies are eligible, the exact error for an expired window or a second message, and any way to reconcile an unknown send. The old `/instagram-api-with-instagram-login/private-replies` URL is gone; the page above replaces it. |
| R75-05 | When a recipient's response opens normal DM eligibility; linking comment and DM identity | "Follow-up messages can only be sent if the recipient responds, and must be sent within 24 hours of the response" (S2). `recipient_id` is an Instagram-scoped ID. | **Partly answered.** Carried forward: whether `recipient_id` equals the `sender.id` of the later messaging webhook (both are called Instagram-scoped IDs, but no page states they are the same value, and the commenter ID in the comments webhook is not stated to be either). No username or name matching may be used to link identities; Session 02's live probe must compare the three IDs on a test account before the app links a comment author to a DM conversation. |
| R75-06 | Quotas and errors, moderation/reply races, revoked grants, post deletion, account-type limits | Documentation says only: "We strongly recommend using webhooks to prevent rate limiting" (S1); `live_comments` can produce a heavy notification stream (S1); live comments are readable only while the broadcast is live (S4). The comment pages give **no** numeric quota, no error codes and no race semantics; the error-codes page lists publishing codes only (S7). Standard Access vs Advanced Access is the only account-level distinction stated (S6). | **Carried forward in full** (nothing in documentation to answer it). Session 02's probe must record real quota headers, errors for revoked permission, deleted media and double replies, and account-type limits, on a dev-mode account. Until then the existing typed error mapping and "unknown outcome means no blind retry" stay in force. |

**What this means for the app.** (1) The scope is requested from now on (`instagram_business_manage_comments`, Feature Phase 3 Session 01); existing connections keep working and show "reconnect to enable comments". (2) Granting the scope changes only `granted_scopes` and the derived `comments_permission`. (3) Enabling any real comment action still needs Session 02: a per-account flag, the `subscribed_apps` subscription for `comments`, the production adapter, and the live probe that closes the carried-forward items. (4) Public rollout needs Advanced Access (App Review) for businesses the founder does not own; pilots run on Standard Access with role users. App Review package: [meta-app-review-package.md](../operations/meta-app-review-package.md).

**History.** The first register was opened on 2026-10-26 (Phase 7.5 Session 01) with HEAD-only reachability checks; Session 16 (2026-10-29) could not read the pages ([dated evidence](meta-comments-session16.md)). Both left all six items open. Separately, Phase 7.5 Session 04 must fixture-test the installed OpenAI SDK's step/tool transport against [the function-calling guide](https://platform.openai.com/docs/guides/function-calling); that is model-adapter research, not R75 platform acceptance. Session 18 requires the full application workflow on an authorized account, not only a direct adapter probe.

### 1.9 Profile and recent media reads (F-09)

Checked 2026-11-17 against Meta's [IG User reference](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user) (also the accessible [versioned reference](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/v21.0/)), [IG Media reference](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-media) ([current reference](https://developers.facebook.com/documentation/instagram-platform/reference/instagram-media)), and [media edge](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media). Documentation evidence is separate from live acceptance.

- **Confirmed (docs):** IG User `biography`, `website`, `name`, `username` with Instagram Login, `graph.instagram.com`, Instagram User token, `instagram_business_basic`.
- **Unverified:** the Instagram Login permission for `GET /{ig-user-id}/media` (assumed `instagram_business_basic`, as for IG Media). The edge's permission table lists Facebook Login permissions (`instagram_basic`, etc.). It supports `since`/`until` time pagination and up to 10K recent media, but documents neither per-page size nor sort order. `limit` behaviour and sort order remain unverified; the adapter requests a limit, reads one page and sorts it newest-first itself.
- **Confirmed (docs):** IG Media `timestamp` (ISO 8601 UTC), `permalink`, and `media_type` (`CAROUSEL_ALBUM`, `IMAGE`, `VIDEO`).
- **Unverified / contradictory:** `caption` is marked Facebook Login only in the IG Media field table, excludes album children, and excludes `@` unless the app user has admin-equivalent tasks on the connected Page. Other Meta pages and integrations suggest Instagram Login use; V-12 must establish actual behaviour. The adapter requests captions; rejection or missing permission degrades to profile-only import with `captions_unavailable`.
- **Unavailable via documented API:** contact-button email, phone and address fields are absent from the IG User reference. Phone/email extraction uses bio/caption text only.


### 1.10 Human Agent message tag (Feature Phase 5, Session 09; researched 2026-11-18)

Sources (all read on **2026-11-18**; the Meta pages are served as rendered documentation, so wording is quoted from the fetched text):
- S1 [Human Agent feature reference](https://developers.facebook.com/documentation/development/features-reference/human-agent.md) (also at `https://developers.facebook.com/docs/features-reference/human-agent`)
- S2 [Instagram Platform overview](https://developers.facebook.com/documentation/instagram-platform/overview.md) (permissions and features list, messaging windows)
- S3 [Instagram messaging API with Instagram Login](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api.md) ("Human agent experiences" and "Send a message")
- S4 [Graph API Page `messages` reference](https://developers.facebook.com/docs/graph-api/reference/page/messages) (`messaging_type` and `tag` parameters)
- S5 secondary, not authoritative: [Sinch Instagram channel properties](https://developers.sinch.com/docs/conversation/channel-support/instagram/properties), [Chatwoot on the Human Agent tag](https://www.chatwoot.com/hc/user-guide/articles/1745225158-what-is-human-agent-tag-in-instagram-messenger-channel)

| Question | Finding | Status |
|---|---|---|
| What it is | A feature that lets an app "have a human agent respond to user messages using the `human_agent` tag within 7 days of a user's message" (S1, S2). The Send API reference describes the tag as "for a message sent to a customer from a human agent in response to the customer's inquiries", sendable within 7 days after the customer's last message (S4). | Confirmed (docs) |
| Permission or feature | A **feature**, not an OAuth scope: S2 lists "Human Agent" in the permissions-and-features table for Instagram Login and Facebook Login, and the Instagram Login messaging scopes stay `instagram_business_basic` and `instagram_business_manage_messages` (S3). S1: it "requires successful completion of the App Review process before your app can access live data", "is only available with business verification", and "you may also need to sign additional contracts". S2 states that Advanced Access needs App Review and Business Verification, and Standard Access is limited to people with a role on the app. | Confirmed (docs) |
| Allowed use | "Provide human agent support in cases where a user's issue cannot be resolved in the standard messaging window", for example a business closed for the weekend or an issue that takes more than 24 hours (S1, S2). S3 says a "human agent only" experience needs a custom inbox that can receive messages sent by people, render them correctly and reply through it. | Confirmed (docs) |
| Automation | The Meta pages above state no explicit prohibition and no list of prohibited uses. They describe a **human agent** responding; S5 sources say the tag is for real human replies and that automated use is rejected. AgentNest treats the tag as **human-typed only**: an AI draft, an approved answer, a follow-up, an agent draft or any job never gets it. | Conservative reading (not stated outright by Meta) |
| How it is sent | `POST /<IG_ID>/messages` with `messaging_type: "MESSAGE_TAG"` and `tag: "HUMAN_AGENT"` beside the usual `recipient` and `message` (S4 lists `messaging_type` = `RESPONSE`, `UPDATE`, `MESSAGE_TAG` and `UTILITY`, and the `tag` values; it states "Only `HUMAN_AGENT` is available for Instagram Messaging"). S3 shows no example with a tag, so the exact request under Instagram Login (`graph.instagram.com`) is **assumed** to be the same JSON fields as the documented Page `messages` reference. | Fields confirmed for the Send API reference; Instagram Login host **unverified** |
| Window | Standard window 24 hours; Human Agent window up to 7 days after the user's **last message** (S1, S2, S4). It is separate from the 7-day window of a Click-to-Direct ad (S2, S3). Nothing is documented about the end boundary (seconds). | Confirmed (docs); boundary unspecified |
| Error when not granted | Not documented. A third-party forum report (ManyChat, June 2025) shows HTTP 400 "Unsupported message tag" when the tag is sent without approval; treat as unconfirmed. | Unverified |
| Per-account visibility | Nothing documents how an app learns whether the feature was granted to it (it is not a token permission). | Unverified |

**What AgentNest does (Session 09, offline).** A capability `human_agent` on the Instagram account, true only when the account can message **and** the operator set `META_HUMAN_AGENT_ENABLED=true` after Meta approved the feature (mock accounts carry the capability, the simulator supports the tag). Only a reply typed by a person in the inbox (draft source `owner`, legacy origin, user actor, never started from or equal to an assistant draft) is accepted between 24 hours and 7 days after the customer's last message; the reply carries `message_tag = HUMAN_AGENT` bound into its approval hash and goes through the operations ledger like any send. A single pure policy function (`app/policy/message_tag.py`) decides at creation and again at send time, and a database CHECK keeps the tag off every non-owner draft. See [workflows.md](../architecture/workflows.md) and the [Session 09 report](../implementation/features-phase-5-on-demand/s09-report.md).

**Pending (live):** apply for the Human Agent feature (with Business Verification) before setting `META_HUMAN_AGENT_ENABLED=true`; confirm the request shape under Instagram Login on a dev-mode account; record the error when the feature is not granted; confirm the 7-day boundary against the customer's last message; confirm the app may read whether the feature was granted. Until then the flag stays off on real accounts.

## 2. WhatsApp Business Platform (Cloud API)

| Capability | Status | Detail | Source |
|---|---|---|---|
| Pricing model | Confirmed (docs) | **Per-message pricing since 2025-07-01**, replacing conversation-based pricing. Template categories: marketing, utility, authentication. | https://developers.facebook.com/docs/whatsapp/pricing |
| Customer service window | Confirmed (docs, re-read 2026-11-18) | A user message (or call) opens a **24-hour** window and each new user message resets it. Inside it any non-template **service** message may be sent; outside it only approved templates. Messages from users to the business are free. **Correction to the earlier reading:** service messages were free only until **2026-09-30**. From **2026-10-01** they are charged after a free tier of 1,000 per phone number per month (no rollover), and utility templates sent inside an open window are charged as well (free only in a free-entry-point window from a Click-to-WhatsApp ad). Charges apply to delivered messages; the status webhook carries a `pricing` object (`billable`, `pricing_model`, `category`, `type`). | https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing.md ; https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages |
| Türkiye | Confirmed (docs) | Türkiye is a standalone pricing market. Utility and authentication rates for Türkiye were **lowered effective 2026-04-01**. The billing currency for Türkiye is not stated. | same |
| Policy on AI chatbots | **Confirmed (primary source read 2026-11-18, see §2.1)** | Meta Terms for the WhatsApp Business Platform, section 4.7 "AI Providers" (page last updated 2026-09-23): providers of large language models, generative AI platforms and general-purpose AI assistants are barred from the platform when providing such technology is their **primary** purpose, not incidental or ancillary. Press reports the rule applying to all users from **2026-01-15** (new users from 2025-10-15). The section has no carve-out sentence for a business's own AI support; the primary-function test is the only related language. Antitrust probes (EU, Italy, Brazil) were reported. | https://www.facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform (redirect target of https://www.whatsapp.com/legal/business-solution-terms); TechCrunch 2025-10-18 (https://techcrunch.com/2025/10/18/whatssapp-changes-its-terms-to-bar-general-purpose-chatbots-from-its-platform) |
| Requirements | Unverified | Meta business portfolio, phone number dedicated to the Cloud API, business verification for higher limits, template approval. Needs verification at decision time. | — |

**Implications for this product:** our use would be a business (us) messaging *our own customers* (business owners) with notifications and approvals, plus owner commands interpreted by AI. That is plausibly "business serving its customers", but whether the AI command interface counts as "incidental" is a **policy judgement Meta makes**. WhatsApp is therefore **not** a dependency of the core. Notifications outside the 24-hour window need paid utility templates. Decision deferred to pilot evidence ([ADR-012](../architecture/decisions/ADR-012-owner-channel-abstraction.md), [open-questions.md](open-questions.md) OQ-01). **Update 2026-11-18:** decided in [ADR-027](../architecture/decisions/ADR-027-whatsapp-owner-channel-scope.md) (notifications and buttons only, no free-text commands); see §2.1.

### 2.1 Reading recorded for Feature Phase 5, Session 01 (accessed 2026-11-18)

Read by the session lead from the pages below; the rows above were updated from it. **Limits of this reading:** the Business Solution Terms page was returned in Turkish and was read through a page-to-text tool, so the section 4.7 wording below is a paraphrase, not verbatim English legal text. Re-read the English text and get counsel's view before the first paying WhatsApp owner. No live Meta call was made.

**Policy**

| Source | Access date | What it says |
|---|---|---|
| https://www.facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform (the old address https://www.whatsapp.com/legal/business-solution-terms answers 301 to it) | 2026-11-18 | Section 4.7 "AI Providers": providers of LLMs, generative AI platforms and general-purpose AI assistants accept that they are barred from using the platform to provide such technology when that is their primary purpose (the Turkish text says "esas amacı bu olan", as opposed to "arızi veya yan"). Availability may be limited to businesses in certain countries. A business may use an AI provider as its Solution Provider and may fine-tune a model for its own private use, but may not use platform data to build or train other AI models. No separate effective date in the section. Page last updated 2026-09-23. |
| https://whatsappbusiness.com/policy/ (WhatsApp Business Messaging Policy; https://business.whatsapp.com/policy redirects to it) | 2026-11-18 | Last updated 2026-09-23. Opt-in: the person gave their number or username and agreed to receive later messages. No AI-specific rule. "You may use automation when responding during the 24-hour window", but you "must also have available prompt, clear, and direct escalation paths" (human transfer, phone, e-mail or web). Outside the 24-hour window "you may only send messages via approved Message Templates"; a conversation may only be started with an approved template; a template may only be used for its designated purpose. |
| https://respond.io/blog/whatsapp-chatbot-policy-2026 (secondary) | 2026-11-18 | Reads the 2026-01-15 rule as aimed at AI as the core product. Structured tasks (FAQs, bookings, order tracking, reminders, notifications, authentication, sales) and internal AI tools stay allowed. Not Meta text. |

**Reading for AgentNest.** AgentNest's AI is a supporting feature of a social-media operations product, and on this channel it would only notify the business owner and collect button taps. That is outside the "primary purpose" test of section 4.7. A free-text conversation with an AI assistant on WhatsApp is the shape the rule is aimed at, and it is where "incidental" would become Meta's judgement. [ADR-027](../architecture/decisions/ADR-027-whatsapp-owner-channel-scope.md) therefore limits the channel to notifications, fixed-text replies and buttons, and sends no WhatsApp free text to an LLM. Residual risk: Meta decides in its sole discretion and could review the product as an AI provider; WhatsApp stays optional and is never a dependency of the core. The owner's opt-in is the link flow (the owner sends the one-time code to the business number).

**Cloud API facts the client is built on** (docs read 2026-11-18; the docs examples use Graph API `v27.0`, so the version is a setting, not a constant)

| Topic | Fact | Source |
|---|---|---|
| Send endpoint and auth | `POST https://graph.facebook.com/<version>/<phone-number-id>/messages` with `Authorization: Bearer <access token>` and a JSON body. Common fields: `messaging_product: "whatsapp"`, `recipient_type: "individual"`, `to`, `type`. Success returns `contacts[].wa_id` and `messages[].id` (the `wamid`); this means "accepted" only, the outcome arrives later in a status webhook. | https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages |
| Business-scoped user IDs | The docs now allow `recipient` (a BSUID) in place of `to`, and contacts may carry `user_id` as well as `wa_id`. We key links on the `wa_id` / `from` value and treat a payload without one as unlinkable (limitation to re-check when BSUID-only senders appear). | same |
| Template message | `type: "template"`, `template: {name, language: {code}, components: [{type: "body", parameters: [{type: "text", text}]}]}`. Positional parameters follow `{{1}}`, `{{2}}`; named ones carry `parameter_name`. Categories: authentication, marketing, utility. Only `APPROVED` templates can be sent; review is automatic and can take up to 24 hours; status changes arrive as `message_template_status_update` webhooks; low quality can pause or disable a template. | https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview |
| Interactive reply buttons | `type: "interactive"`, `interactive: {type: "button", body: {text}, footer?, header?, action: {buttons: [{type: "reply", reply: {id, title}}]}}`. At most **3** buttons; title at most **20** characters and unique; id at most **256** characters and unique; body at most **1024**; footer at most **60**. They are a non-template (service) message, so they are only for use inside the 24-hour window. A tap arrives as `messages[].interactive.button_reply.{id,title}`. | https://developers.facebook.com/docs/whatsapp/cloud-api/messages/interactive-reply-buttons-messages |
| Webhook verification (GET) | Meta sends `hub.mode=subscribe`, `hub.verify_token` and `hub.challenge`. Compare the token with the stored one; answer `200` with the challenge value as the body, otherwise a non-200. | https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint |
| Webhook signature (POST) | Header `X-Hub-Signature-256: sha256=<hex>`, an HMAC-SHA256 of the payload keyed with the **app secret**. The page does not say raw bytes versus re-serialised JSON; third-party guides say raw body, so the client verifies the raw bytes before parsing, with a constant-time compare. | same; https://webhookrelay.com/blog/whatsapp-cloud-api-webhooks/ (secondary) |
| Webhook delivery | Up to 1000 updates per batch, each POST must be handled individually. Failures are retried immediately and then with decreasing frequency for **7 days**; duplicates must be tolerated; there is no history API. Answer `200` for a valid POST. | same |
| Envelope | `object: "whatsapp_business_account"`, `entry[].changes[].value` with `metadata.phone_number_id`, `contacts[]`, `messages[]` (`from`, `id`, `timestamp`, `type`, `text.body` or `interactive`) and `statuses[]`. | interactive-reply-buttons page above |
| Cost reporting | The status webhook `pricing` object: `billable`, `pricing_model` ("PMP"), `category`, `type` (`regular`, `free_customer_service`, ...). Session 02 stores it as delivery metadata. | pricing page above |
| Not found in the docs read | The error JSON shape, the error code for "outside the 24-hour window" (the commonly cited `131047` was not on the pages read), rate limits, and number registration steps. The client treats any non-2xx as a failure, keeps the raw `error.code` and does not assume code meanings. | not applicable |

**Requirements still unverified:** Meta business portfolio and business verification for the sending number, a number dedicated to the Cloud API, Turkish template review behaviour, and Türkiye price points on the 2026-10-01 rate card. These are pilot-readiness items for whoever sets up the number, not blockers for the offline client.

### 2.2 Notifications, templates and cost (Feature Phase 5, Session 02; accessed 2026-11-18)

Sources: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview and https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing (both read 2026-11-18). No live call was made; nothing below has been submitted to Meta.

**How the channel chooses.** The owner's last inbound WhatsApp message (stored on the channel link by the webhook, from Meta's own message timestamp when it is valid and not in the future) opens a 24-hour customer-service window. At **send time** (not when the row is recorded), `window.choose_send_mode` decides: inside the window minus a 5-minute safety margin a plain **session** message with the same text is sent; otherwise the **approved template** is sent. No inbound message ever, or a timestamp in the future, means template. A session message is preferred inside the window because the pricing page gives service messages a free tier of 1,000 delivered messages per number per month, while a utility template sent inside an open window has been charged since 2026-10-01.

**Cost metadata (no invented prices).** Every ledger row keeps `delivery_metadata.cost`: `send_mode` (`session` or `template`), `is_template`, `category` (`service` for a session message, `utility` for a template), `template_name`, `template_language`, a `pricing_note` and `price_verified: false` with `price_amount` and `currency` left null. **The Meta pricing page names Türkiye as a standalone market (utility and authentication rates "lower" since 2026-04-01) but states no amount or currency, and the rate card figures were not read, so no Türkiye price is recorded.** When Meta's status webhook sends a `pricing` object, only its flags and labels (`billable`, `pricing_model`, `category`, `type`) are stored under `delivery_metadata.billing`, never an amount. To fill in prices, read the rate card for the sending number's billing currency and add a verified rate table; until then the cost view is category counts only.

**Template submission steps (Meta WhatsApp Manager).** The templates below are the whole registry (`backend/app/integrations/channels/whatsapp/templates.py`); the registry is the source of truth and a test checks that every name appears here. Submit each template **once per language** (Turkish `tr`, English `en`) under the same name:

1. Prerequisites: the Meta business portfolio, the WhatsApp Business Account with the sending number registered, and (for more than 250 templates or higher limits) business verification. Review is automatic and can take up to 24 hours; a Management API alternative is `POST /<waba-id>/message_templates` with `name`, `category`, `language` and `components`.
2. In WhatsApp Manager open the message templates panel and create a template.
3. Category **Utility** (never Marketing or Authentication). Name exactly as listed (lowercase letters, digits, underscores; the `_v1` suffix is part of the name; an approved template cannot be edited in place, so a text change means a new `_v2` name and a registry change).
4. Language `tr` or `en`. Body: the text below. Positional variables `{{1}}`..`{{4}}` are written in the body, and each needs an **example value** at submission (for the daily summary: a date, then three small numbers, e.g. `18.11.2026`, `12`, `5`, `2`). No header, footer or buttons.
5. Submit and wait for the status. Only `Active` (approved) templates can be sent; `In-Review`, `Rejected`, `Paused` and `Disabled` cannot. Status changes arrive as `message_template_status_update` webhooks (not handled yet; check in WhatsApp Manager).
6. When **all 20** (10 templates x 2 languages) show as active, set `WHATSAPP_TEMPLATES_APPROVED=true`. While it is `false` the channel never sends a template and records `whatsapp_templates_not_approved`; session messages inside the window are unaffected.

| Template name (`category: utility`) | Notification type | Variables | Turkish body | English body |
|---|---|---|---|---|
| `agentnest_approval_requested_v1` | `approval.requested` | none | AgentNest: Kararınızı bekleyen bir onay var. Ayrıntılar için uygulamayı açın. | AgentNest: An approval is waiting for your decision. Open the app for details. |
| `agentnest_owner_question_v1` | `owner_question.requested` | none | AgentNest: Asistanınızın size bir sorusu var. Yanıtlamak için uygulamayı açın. | AgentNest: Your assistant has a question for you. Open the app to answer it. |
| `agentnest_question_unanswered_v1` | `owner_question.window_closed` | none | AgentNest: Bir soru yanıtsız kaldı. Ne olduğunu görmek için uygulamayı açın. | AgentNest: A question went unanswered. Open the app to see what happened. |
| `agentnest_content_failed_v1` | `content.failed` | none | AgentNest: Bir paylaşım yayınlanamadı. Ne olduğunu görmek için uygulamayı açın. | AgentNest: A post could not be published. Open the app to see what happened. |
| `agentnest_reply_failed_v1` | `reply.failed` | none | AgentNest: Bir yanıt gönderilemedi. Ne olduğunu görmek için uygulamayı açın. | AgentNest: A reply was not sent. Open the app to see what happened. |
| `agentnest_account_reauth_v1` | `account.needs_reauth` | none | AgentNest: Instagram bağlantısının yenilenmesi gerekiyor. Hesabı yeniden bağlamak için uygulamayı açın. | AgentNest: Your Instagram connection needs to be renewed. Open the app to reconnect your account. |
| `agentnest_quota_warning_v1` | `quota.warning` | none | AgentNest: Yapay zeka yanıt hakkınızın %80'i kullanıldı. Planınızı ve kullanımı Ayarlar'dan görün. | AgentNest: 80% of your AI reply allowance is used. See your plan and usage in Settings. |
| `agentnest_quota_grace_v1` | `quota.grace` | none | AgentNest: Yapay zeka yanıt hakkınıza ulaşıldı. Taslaklar %10 ek hakla devam eder, sonra duraklar. | AgentNest: AI reply allowance reached. Drafting continues within an extra 10%, then pauses. |
| `agentnest_quota_paused_v1` | `quota.paused` | none | AgentNest: Yapay zeka yanıtları duraklatıldı. Mesajlar gelen kutusuna düşmeye devam eder; yeni döneme kadar kendiniz yanıtlayın. | AgentNest: AI replies are paused. Messages still arrive in the inbox; reply yourself until the next period. |
| `agentnest_daily_summary_v1` | `report.daily_ready` | {{1}} local_date, {{2}} inbound_messages, {{3}} replies_sent, {{4}} pending_approvals | AgentNest günlük özet, {{1}} tarihi için: {{2}} yeni mesaj, {{3}} gönderilen yanıt, {{4}} bekleyen onay. Ayrıntılar uygulamada. | AgentNest daily summary for {{1}}: {{2}} new messages, {{3}} replies sent, {{4}} approvals waiting. Details are in the app. |

Variables are numbers or a date only; no customer text, name or handle can become a variable (a test checks this). The UI labels above follow Meta's documentation of 2026-11-18 and may change; check them when submitting.

**Approval buttons (Session 03).** Interactive reply buttons are session messages, so the approval template above stays button-free and its text says to open the app; the registry has no quick-reply button on purpose (it would need a new approved template version and a token minted before the window state is known). Inside the window the channel sends the interactive message instead, with the proposed outgoing text (clipped to 1,000 of the 1,024 body characters) so the owner is informed; the customer's message is never included. **Not verified live:** how a template quick-reply tap would arrive (Meta documents a `button` message type, which the parser does not read), whether a forwarded interactive message keeps working buttons for the new recipient (the design assumes it may, and refuses any tap whose number is not the token's member), and the exact delivery latency of a tap webhook.

**Not verified:** template approval behaviour for Turkish text, the exact per-message Türkiye rates and billing currency, the error code Meta returns for a template-less send outside the window (the channel does not interpret codes and treats any 4xx as a terminal failure), and whether `message_template_status_update` should be subscribed to for automatic status tracking.

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
| V-12 | Instagram Login `GET /{id}/media?fields=caption,...`: caption returned? sort order, `limit`, `@` handling; biography and website on a real professional account. | Connect the founder's test account, call both reads, record fixtures. | F-09 live claim |
| V-HA | Human Agent tag under Instagram Login: is the request `messaging_type=MESSAGE_TAG` plus `tag=HUMAN_AGENT` on `graph.instagram.com/<IG_ID>/messages` accepted; the error when the feature is not granted; the exact 7-day boundary; how the app learns the feature was granted. | After Meta grants the Human Agent feature, send one tagged human-typed reply to a test account on day 2 and one after 7 days, record fixtures (section 1.10). | `META_HUMAN_AGENT_ENABLED` on real accounts |

### Feature Phase 3 Session 02 implementation boundary (2026-11-17)

Offline implementation now supports Meta comment webhooks and private replies behind the default-off persisted account flag. This is not live verification. The **ASSUMED-strict** rules are one reply per commenter/account ever (configurable `COMMENT_PRIVATE_REPLY_LIMIT_SCOPE=commenter|comment`), no replies to replies, and a 10-minute margin inside the documented seven days. Per-comment uniqueness is unconditional. Unknown sends hold reservations forever pending positive evidence; no remote private-reply readback is assumed.

The `meta_comments_live` harness records subscription readback, timestamp/ownership, opt-in first send, repeat-denial and same-commenter second-comment outcome, plus truncated hashed recipient for later DM identity comparison. All outcomes are **pending**. Authentic shapes, permission return, `comments` subscription acceptance, app mode/access, native mutations, identity equivalence, quotas and race errors remain carried forward. Public reply and moderation capabilities remain false.
