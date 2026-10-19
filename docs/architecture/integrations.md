# External Integration Contracts

**Purpose:** The interfaces that isolate external services, and how mock and real implementations satisfy the same contracts. Covers Instagram (customer channel), owner channels (web, Telegram, WhatsApp), LLM providers and media storage. Platform facts and their verification status are in [platform-capabilities.md](../research/platform-capabilities.md). Do not implement anything here beyond what is marked confirmed there without first completing the listed verification item.

## 1. Integration principles

1. **Interfaces are owned by the core**, not by the vendor. Adapters translate.
2. **Mocks are stateful simulators** that enforce the same constraints as the real service (window, limits, async processing, failures).
3. **Typed errors** cross the boundary. HTTP details never leak into domain code.
4. **Side-effecting methods are only called by `operations`** ([INV-15](../invariants.md)).
5. **No retries inside adapters** for non-idempotent calls. Retry policy belongs to the operations layer.
6. **Every adapter call is logged** with operation ID, duration and outcome code (no secrets, no message text).

## 2. Provider registry

`integrations/registry.py` resolves an adapter by `(platform, provider_kind)`, honouring `INSTAGRAM_ENABLED_PROVIDERS`, `LLM_PROVIDER` and `MEDIA_STORAGE_BACKEND`. Domain code asks `registry.instagram_for(account)`; it never constructs adapters directly.

## 3. Instagram (customer channel)

### 3.1 Contract

```python
class InstagramProvider(Protocol):
    kind: Literal["mock", "meta"]

    # --- webhook side (used by inbox; no side effects) ---
    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool: ...
    def parse_webhook(self, payload: dict) -> list[NormalizedInboundEvent]: ...

    # --- reads (used by operations / health / connect) ---
    def get_account_profile(self, account: AccountRef) -> AccountProfile: ...
    def get_container_status(self, account: AccountRef, container_id: str) -> ContainerStatus: ...
    def get_media(self, account: AccountRef, media_id: str) -> MediaInfo: ...
    def get_publishing_quota(self, account: AccountRef) -> PublishingQuota: ...
    def find_recent_outbound(self, account: AccountRef, recipient_id: str,
                             since: datetime) -> list[OutboundMessageInfo]: ...   # reconciliation

    # --- side effects (operations module only) ---
    def send_text_message(self, account: AccountRef, recipient_id: str, text: str) -> SendResult: ...
    def create_media_container(self, account: AccountRef, spec: ContainerSpec) -> str: ...  # container_id
    def publish_container(self, account: AccountRef, container_id: str) -> str: ...          # media_id
    def refresh_token(self, account: AccountRef) -> TokenInfo: ...
```

Types (Pydantic or dataclasses in `integrations/instagram/base.py`):
- `AccountRef{social_account_id, workspace_id, external_account_id, token_provider}`. `token_provider` is a callable that decrypts the token on demand, so the token never sits in job payloads or logs (`None` for the mock). `workspace_id` scopes the simulator tables.
- `NormalizedInboundEvent{event_type: message|echo|reaction|read|postback|other, account_id, customer_id, mid?, text?, attachments[], provider_timestamp, is_echo, app_id?, raw_item}`. `account_id` is always the business account and `customer_id` always the other party, for customer messages and echoes alike (Meta swaps sender and recipient in an echo). Parsing lives in `webhook_format.py`, shared by the mock and the Meta adapter.
- `AccountProfile{external_account_id, username?}`, `OutboundMessageInfo{message_id, recipient_id, text?, sent_at}`.
- `ContainerSpec{media_type: IMAGE|STORIES, image_url, caption?}` (MVP. `REELS`, `VIDEO` and `CAROUSEL` come later.)
- `ContainerStatus{status_code: IN_PROGRESS|FINISHED|ERROR|EXPIRED|PUBLISHED, error_detail?}`.
- `SendResult{message_id}`, `MediaInfo{media_id, permalink?, timestamp?}`, `PublishingQuota{used, limit, window_hours}`.

Typed errors (`integrations/instagram/errors.py`): `ProviderTransientError`, `ProviderRateLimited(retry_after_s)`, `ProviderAuthError`, `ProviderPermissionError`, `ProviderInvalidRequest(code)`, `ProviderWindowClosed`, `ProviderOutcomeUnknown`. Mapping to app error codes: [workflows.md §G.1](workflows.md).

**Ambiguity rule:** an adapter raises `ProviderOutcomeUnknown` when a side-effecting request **may have been accepted**: a read timeout after sending the request, a 5xx on `media_publish` or `messages`, or a connection reset after the request body was sent. It raises `ProviderTransientError` only when the request certainly did not reach processing (connect timeout, DNS failure, connection refused) or the provider explicitly rejected it with a retryable code.

### 3.2 Capabilities
`social_accounts.capabilities` is computed at connect and refresh:
- `messaging`: scope `instagram_business_manage_messages` granted.
- `publish_feed_image`, `publish_story_image`: scope `instagram_business_content_publish` granted (story: pending V-03; mock: true).
- `comments`: false in MVP.

The policy engine (R1) and the content submit validation check capabilities. Missing capability → `CAPABILITY_MISSING`.

### 3.3 Mock simulator (`MockInstagramProvider`)

| Behaviour | Simulation |
|---|---|
| Signature | HMAC-SHA256 with `MOCK_INSTAGRAM_APP_SECRET`, same header format as Meta, delivered to `POST /webhooks/instagram/mock` (mounted only when `mock` is enabled) |
| Inbound messages | `demo.simulate_customer_message(workspace, customer_alias, text)` builds a Meta-format payload (`object: "instagram"`, `entry[].messaging[]` with `sender.id`, `recipient.id`, `timestamp`, `message.mid`, `message.text`), signs it, and submits the signed raw bytes to the **same ingestion function** that serves `POST /webhooks/instagram` (with provider kind `mock`). The CLI posts over HTTP to the running API. The dev panel endpoint and tests call `inbox.ingest_webhook(raw_body, headers)` in-process, which avoids the API calling itself. |
| Echo of native owner reply | `demo.simulate_owner_native_reply(...)` emits an echo event with an unknown `mid` |
| `send_text_message` | Enforces window (based on the last simulated inbound for that recipient, read from `sim_inbound_messages`), ≤ 1000 bytes; writes `sim_sent_messages`; returns `message_id`; can emit an echo event (enqueued as a simulated webhook after 1 s) |
| `create_media_container` | Requires a JPEG at the URL (reads from local storage); writes `sim_containers(status=IN_PROGRESS, ready_at=now+SIM_CONTAINER_DELAY (default 2 s), expires_at=now+24h)` |
| `get_container_status` | `IN_PROGRESS` until `ready_at`, then `FINISHED`; `PUBLISHED` once published; `EXPIRED` after `expires_at` |
| `publish_container` | Requires `FINISHED`; inserts `sim_published_media` (`unique(container_id)`, so publishing twice is a DB error mapped to `ProviderInvalidRequest`); returns `media_id`; permalink `https://instagram.example/sim/{media_id}` (clearly fake domain) |
| `get_publishing_quota` | Counts `sim_published_media` in the last 24 h; limit 50 |
| `refresh_token` | No-op success (mock accounts have no token) |
| Failure injection | `sim_failure_rules`: `operation ∈ {send, lookup, create_container, container_status, publish, refresh, profile, any}` (`lookup` = `find_recent_outbound`, so reconciliation can be made unavailable), `mode ∈ {transient, rate_limited, auth_revoked, permission_missing, invalid_media, timeout_after_success, window_closed}`, `remaining` (null = always), `retry_after_s`. `timeout_after_success` performs the effect and **then** raises `ProviderOutcomeUnknown`. |
| Time | Uses the injected `Clock`, so tests control expiry and readiness. |

### 3.4 Meta adapter (`MetaInstagramProvider`): Phase 7

- Host `graph.instagram.com`, API version from `META_GRAPH_API_VERSION` (pinned; upgrade deliberately).
- **OAuth connect flow:**
  1. `POST /social-accounts/instagram/connect` → the server creates a `state` (random, stored hashed with workspace, user and expiry 10 min) → returns the authorize URL (`https://www.instagram.com/oauth/authorize`, scopes `instagram_business_basic,instagram_business_manage_messages,instagram_business_content_publish`).
  2. `GET /oauth/instagram/callback?code&state` → verify state (single use, same user session) → exchange the code (server-side) → exchange for a long-lived token (server-side) → `get_account_profile` → encrypt the token → upsert `social_accounts(meta, connected, capabilities, granted_scopes, token_expires_at)` → subscribe the app to webhooks for the account if required (V-01) → audit `account.connected` → redirect to the SPA settings page with a status.
  3. Reconnect for an existing account verifies the same `external_account_id`; a mismatch → error `ACCOUNT_MISMATCH`.
- **Webhook endpoint:** `GET /webhooks/instagram` for the verification handshake (`hub.verify_token == META_WEBHOOK_VERIFY_TOKEN` → echo `hub.challenge`). `POST` with signature verification against `META_APP_SECRET`.
- **Send:** `POST /{ig_id}/messages` with `recipient.id` and `message.text`.
- **Publish:** `POST /{ig_id}/media` (`image_url`, `caption` or `media_type=STORIES`) → `GET /{container_id}?fields=status_code` → `POST /{ig_id}/media_publish` (`creation_id`) → `GET /{media_id}?fields=permalink,timestamp`.
- **Quota:** `GET /{ig_id}/content_publishing_limit`.
- **Error mapping:** built from recorded responses in V-05 and stored as fixtures in `tests/contract/fixtures/meta/`. Unknown errors map to `ProviderTransientError` if 5xx (or `OutcomeUnknown` for side-effecting calls) and to `ProviderInvalidRequest` if 4xx.
- **Disconnect:** delete the token ciphertext immediately, status `disconnected`, cancel queued sends, hold scheduled content, audit. Data deletion follows [security-and-privacy.md §8](security-and-privacy.md).
- **Meta callbacks (Phase 8, V-06):** deauthorize and data-deletion endpoints verify the `signed_request` (HMAC-SHA256 with the app secret) and respond with `{url, confirmation_code}` for data deletion.

### 3.5 Contract tests
`tests/contract/test_instagram_provider_contract.py` defines behaviour that every adapter must satisfy (parameterised by adapter):
- Signature valid/invalid; parse fixtures for message, echo, reaction, attachments and unknown items.
- Send within window → message ID; outside window → `ProviderWindowClosed`; oversize text → `ProviderInvalidRequest`.
- Container lifecycle → `FINISHED` → publish → `PUBLISHED`; publishing twice is rejected; expiry → `EXPIRED`.
- Error mapping for each injected failure mode.

CI runs them against `mock`. The `meta` run is manual (`-m meta_live`, requires a test account and environment variables) and records fixtures.

### 3.6 Content-type constraints (from verified docs)
| Type | MVP | Constraints enforced |
|---|---|---|
| `feed_image` | yes | JPEG, ≤ 8 MB, aspect 4:5–1.91:1, width 320–1440 (scaled), caption ≤ 2200 chars (to verify) |
| `story_image` | yes (story publishing behaviour pending V-03) | JPEG, ≤ 8 MB, 9:16 recommended, **no caption**: text must be in the image |
| Reels / video / carousel | no | — |

## 4. LLM provider
Contract and behaviour: [ADR-009](decisions/ADR-009-llm-provider-abstraction.md), [agent-runtime.md](agent-runtime.md). Adapters: `fake` (default), `openai`. Only `app/ai` imports `integrations.llm`.

## 5. Owner channels

### 5.1 Contract

```python
class OwnerChannel(Protocol):
    name: Literal["web", "telegram", "whatsapp"]
    def deliver(self, notification: Notification, recipient: ChannelRecipient) -> DeliveryResult: ...
    def render_command_result(self, command: OwnerCommand, recipient: ChannelRecipient) -> None: ...
    # inbound is handled by channel-specific webhook routes that normalise into:
    #   ChannelInbound{channel, external_user_id, chat_id, text?, attachments[], callback_token?, update_id}
```

Flow through the core (identical for every channel):

```mermaid
sequenceDiagram
  participant CH as Channel adapter
  participant ID as identity (channel_links)
  participant CMD as CommandService
  participant APR as ApprovalService
  participant MED as MediaService
  participant N as Notifications

  CH->>ID: resolve(external_user_id) → user + default workspace
  alt text message
    CH->>CMD: submit(user, workspace, text, channel)
    CMD-->>N: result / confirmation (as notification with actions)
  else attachment
    CH->>MED: ingest(file) → media_asset_id (attached to next command)
  else button press (callback_token)
    CH->>APR: decide(token → approval_id, payload_hash, decision, user, channel)
  end
  N->>CH: deliver(notification with action tokens)
```

**Action tokens** (for buttons): a random 16-byte token (base64url, 22 chars, within Telegram's 64-byte `callback_data` limit), stored hashed with `(approval_id, decision, user_id, payload_hash, expires_at, used_at)`. Single use; it must be pressed by the linked user; it expires with the approval.

**Linking:** the user generates a one-time code in the web app (Settings → Channels) and sends `/link <code>` to the bot → `channel_links` row. Unlinking is available from both sides.

### 5.2 Web channel (MVP)
- Commands: `POST /commands`. Results: polled command resource. Notifications: `notifications` table + bell. Approvals: approval screens.
- `deliver()` is a no-op beyond the stored notification.

### 5.3 Telegram (Phase 9, provisional per OQ-01)
- Inbound: `POST /webhooks/telegram`, verifying `X-Telegram-Bot-Api-Secret-Token == TELEGRAM_WEBHOOK_SECRET`. Dedup on `update_id`. Local development may use `getUpdates` long polling (`python -m app.cli telegram-poll`) instead of a public webhook.
- Outbound: `sendMessage` with an inline keyboard. Photos ≤ 20 MB downloadable via `getFile`.
- Approval messages include the full summary (text to be sent or published, schedule, account, simulated flag) and two buttons (Approve / Reject), plus an "Open in app" link.

### 5.4 WhatsApp (deferred, OQ-01)
Same contract. Additional constraints: per-message pricing, free-form only within 24 h of the owner's last message (otherwise paid utility templates), template approval, business verification, and the AI-provider policy review ([platform-capabilities.md §2](../research/platform-capabilities.md)). It must never become a dependency of core flows.

## 6. Media storage
Contract and rules: [ADR-015](decisions/ADR-015-media-storage.md). Backends `local` (default), `s3` (Phase 7). The real Meta adapter requires `public_fetch_url()` to return an Internet-reachable URL.
