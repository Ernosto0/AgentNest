# Phase 7: Implementation Plan and Session Briefs (Meta Instagram Integration)

Phase 7 (`docs/implementation/phases/phase-07-meta-integration.md`) connects a real Instagram Professional account via **Instagram Login** (`graph.instagram.com`) and runs workflows C (inbound DM → grounded draft → approval → send), E (media upload → container → publish), and G (token refresh, auth revocation, reconnect, circuit breaker, disconnect) end-to-end with encrypted tokens, signed webhooks, and S3-compatible media storage.

Phase 7 is split into **4 sequential sessions**. Run strictly in order (`Session 1` → `Session 2` → `Session 3` → `Session 4`), one session at a time on `main`.

**Owner direction (2026-10-23):** “Proceed with offline Sessions 1–4; keep gates pending.” This explicitly permits sequential offline implementation and local verification before the phase prerequisites are met. Gate 1, Gate 2, live Meta/S3 checks and all real-account acceptance remain pending. No production credentials, real-account Meta calls, real S3 calls or pushes are authorized by this exception. P7-00's research-based final re-plan remains pending; record offline contract adaptations as each session proceeds and revisit them against actual research before live acceptance.

**Session 1 contract adaptations:** `S3_ENDPOINT_URL` is optional for AWS; `S3_REGION` defaults to `auto` and AWS requires its actual bucket region. Every environment validates enabled Meta credentials/key ring and selected S3 configuration. Meta requires S3 until a secured public local-media serving contract exists: `MEDIA_PUBLIC_BASE_URL` is reserved and does not bypass this safety check. Missing S3 objects raise the protocol's `StorageObjectNotFound` subclass of `FileNotFoundError`. These choices preserve the mock/local defaults and introduce no public media route.

**Session 2 offline adaptations:** Meta fixtures are explicitly synthetic, not recorded; V-05 and the research re-plan stay pending. `TokenInfo` adds an optional repr-hidden `access_token` for the Session 3 refresh consumer; `registry.account_ref(account, settings)` captures encrypted snapshots and decrypts lazily without ORM access during requests. Migration `0016` admits `delete` webhook events and refuses a lossy downgrade; OAuth therefore uses `0017`. Malformed successful send/publish responses are ambiguous. Media URLs require valid HTTPS, and empty story captions are rejected. Meta container status does not invent a published media ID.

**Session 3 offline adaptations:** Migration `0017` adds `invalidated_at` to OAuth states to fence disconnect-during-exchange callbacks; requested scopes never imply grants, and absent short-exchange `permissions` gives no capabilities. Flat/one-item-wrapped short exchanges are synthetic assumptions; live research remains pending. Disconnected-row reuse requires new OAuth authorization. Refresh recovery uses a two-minute attempt lease and credential/attempt fences; three attempts share the original daily operation even across midnight.

---

## 1. Module Layout & Import Contracts

```text
backend/app/core/
  security.py                          (+ AES-256-GCM token encryption & key ring)
  config.py                            (+ Meta, token key ring, S3, and dev-tunnel settings + safety checks)
backend/app/integrations/instagram/
  error_mapping.py                     (NEW: Graph API error JSON / HTTP status / transport -> Provider*Error)
  meta.py                              (NEW: MetaInstagramProvider implementing InstagramProvider)
  oauth.py                             (NEW: authorize URL builder, code exchange, long-lived token exchange, scope mapping)
  models.py                            (+ OAuthState model; SocialAccount already has token_* columns)
  registry.py                          (+ "meta" provider resolution with on-demand token decryption callable)
  webhook_format.py                    (+ story replies/mentions, message deletions/unsends, app_id echo handling)
backend/app/integrations/storage/
  s3.py                                (NEW: S3MediaStorage with boto3 + presigned GET URLs)
  registry.py                          (+ "s3" backend resolution)
backend/app/operations/
  refresh.py                           (NEW: refresh_tokens & refresh_token logic + ledger integration)
  oauth_service.py                     (NEW: OAuth state creation, callback verification, account upsert/reconnect)
  oauth_router.py                      (NEW: GET /oauth/instagram/callback)
  accounts.py                          (+ full disconnect cascade: token wipe, draft cancels, content holds, optional data delete)
  accounts_router.py                   (+ POST /social-accounts/instagram/connect, disconnect body)
  jobs.py                              (+ refresh_tokens periodic & job, refresh_token job)
backend/migrations/versions/
  20261023_0016_phase_7_webhook_deletions.py (NEW: inbound event delete type; safe downgrade)
  0017_oauth_states.py                 (NEW: oauth_states table)
backend/tests/contract/
  fixtures/meta/*.json                 (NEW: labelled synthetic offline fixtures; recordings pending)
  test_instagram_provider_contract.py  (parameterised for mock + offline meta with fixture transport)
  test_meta_live.py                    (NEW: -m meta_live manual live contract suite against founder account)
frontend/src/features/settings/
  Connections.tsx                      (+ real OAuth connect/reconnect redirect, callback status banner, disconnect data-delete option)
```

### Import Linter Rules (`backend/pyproject.toml`)
- `app.integrations.instagram` continues to import **only** `app.core` (and `app.integrations.storage` for mock). `only the Meta adapter imports boto3/s3` is **not** needed because `MetaInstagramProvider` receives presigned URLs via `ContainerSpec.image_url`; only `app.integrations.storage.s3` imports `boto3` (`ignore_imports = ["app.integrations.storage.s3 -> boto3"]`).
- Add all new service/model modules (`app.integrations.instagram.meta`, `app.integrations.instagram.oauth`, `app.integrations.instagram.error_mapping`, `app.integrations.storage.s3`, `app.operations.refresh`, `app.operations.oauth_service`) to the `"services, repositories and models do not import the API layer"` contract in `backend/pyproject.toml`.

### New Backend Dependencies (`backend/pyproject.toml`)
- `cryptography>=43.0` (for `AESGCM` authenticated token encryption, ADR-017).
- `boto3>=1.35` (for S3-compatible object storage & presigned URLs, ADR-015) + `types-boto3-lite` or typed wrapper in `s3.py` so `mypy --strict` passes cleanly.

---

## 2. Settled Design Decisions (`I1`–`I10`)

| ID | Topic | Decision | References |
| :--- | :--- | :--- | :--- |
| **I1** | **Token encryption & key ring** | `security.py` implements `TokenKeyRing(keys, active_key_id)` parsed from `TOKEN_ENCRYPTION_KEYS="k1:<base64-32-bytes>[,k2:...]"`, with `TOKEN_ENCRYPTION_ACTIVE_KEY_ID="k1"`. Encryption uses `AESGCM` (256-bit key, random 12-byte nonce prepended to ciphertext: `nonce (12B) \|\| ciphertext+tag`). Associated data (AAD) is `f"{workspace_id}:{social_account_id}".encode("utf-8")` so a ciphertext cannot be moved across accounts or workspaces. `encrypt(plaintext, *, aad) -> tuple[bytes, str]` returns `(ciphertext, active_key_id)`; `decrypt(ciphertext, key_id, *, aad) -> str` looks up `key_id` in the ring (enabling zero-downtime key rotation). | ADR-017, security-and-privacy T10 |
| **I2** | **S3 storage & dev tunnel config** | `S3MediaStorage` (`app/integrations/storage/s3.py`) wraps `boto3.client("s3", endpoint_url=..., region_name=..., aws_access_key_id=..., aws_secret_access_key=..., config=Config(signature_version="s3v4"))`. Keys are validated with `validate_key(key)` before every call. `public_fetch_url(key, ttl_s)` generates a `get_object` presigned URL with `ExpiresIn=ttl_s`. Startup safety (`config.py`): in `production`, enabling `meta` requires `MEDIA_STORAGE_BACKEND=s3` and required S3, Meta and key-ring settings (endpoint is optional). In every environment, enabling `meta` requires Meta credentials, a valid key ring and S3; secured local-media tunnel serving remains pending and `MEDIA_PUBLIC_BASE_URL` does not bypass the check. `S3_ENDPOINT_URL` is optional for AWS; region defaults to `auto` (set the actual AWS region for AWS). | ADR-015, ADR-017, environment-variables.md |
| **I3** | **Meta Graph API client & ambiguity rule** | `MetaInstagramProvider` uses `httpx.Client` (base URL `https://graph.instagram.com/{version}`, timeout `15.0s`, injectable `httpx.BaseTransport` for tests). Never retries inside the adapter (INV-15). Ambiguity rule (`integrations.md §3.1`): on side-effecting calls (`send_text_message`, `publish_container`), `httpx.ReadTimeout`, `httpx.WriteError`, `httpx.RemoteProtocolError`, or HTTP 5xx raises `ProviderOutcomeUnknown`. On read calls (`get_account_profile`, `get_container_status`, `get_media`, `get_publishing_quota`, `find_recent_outbound`, `refresh_token`) and `create_media_container` (no visible effect), those raise `ProviderTransientError`. Connect timeouts (`httpx.ConnectTimeout`, `httpx.ConnectError`) always raise `ProviderTransientError`. Every call logs `operation`, `provider_kind="meta"`, `duration_ms`, and `outcome` (never tokens or message text). | integrations.md §1, §3.1, §3.4 |
| **I4** | **Meta error mapping** | `error_mapping.py` parses Graph API error JSON `{"error": {"message", "type", "code", "error_subcode", "fbtrace_id"}}` and HTTP headers (`Retry-After`):<br>• HTTP 401 or `code == 190` → `ProviderAuthError`<br>• `code == 10` with `error_subcode == 2534022` (or message indicating outside 24h messaging window) → `ProviderWindowClosed`<br>• HTTP 403 or `code in (10, 200, 294)` → `ProviderPermissionError`<br>• HTTP 429 or `code in (4, 17, 32, 613)` or `error_subcode == 2207051` → `ProviderRateLimited(retry_after_s)`<br>• Media/container codes (`code in (36000, 36001, 36002, 36003, 36004)` or `error_subcode in (2207001..2207085)`) → `ProviderInvalidRequest("MEDIA_REJECTED")`<br>• Other 4xx → `ProviderInvalidRequest("PROVIDER_REJECTED")` | integrations.md §3.4, workflows.md §G.1 |
| **I5** | **Webhook parser hardening & native echo detection** | `webhook_format.py` and `inbox/processing.py` handle real Meta webhook shapes:<br>• **Story replies:** `message.reply_to.story.{url, id}` → added to `attachments` as `{"type": "story_reply", "url": url, "note": id}`.<br>• **Story mentions:** attachment `type == "story_mention"` preserved.<br>• **Message deletion (unsend):** `message.get("is_deleted") is True` → `NormalizedInboundEvent(event_type="delete", mid=mid, ...)`; `inbox/processing.py` marks matching `messages.is_deleted = True` (idempotent).<br>• **Unsupported content:** `message.get("is_unsupported") is True` → attachment note `"unsupported"` so conversation is routed safely.<br>• **Echoes (`is_echo: true`):** `inbox/echoes.py` checks `event.app_id`: if `meta_app_id` is configured and `event.app_id` is present and differs from `meta_app_id` (or has no `app_id` and matches no in-flight/sent operation), it is recorded as `sender_kind="business_native"` and supersedes any open draft (`NATIVE_REPLY`). | integrations.md §3.1, platform-capabilities.md §1.4, workflows.md §C |
| **I6** | **OAuth state & connect/reconnect flow** | Migration `0017` adds table `oauth_states` (`id`, `workspace_id`, `user_id`, `state_hash bytea unique`, `purpose text CHECK IN ('connect','reconnect')`, `social_account_id uuid null`, `expires_at timestamptz`, `used_at timestamptz null`, `created_at timestamptz`).<br>• `POST /api/v1/workspaces/{ws}/social-accounts/instagram/connect` (`integrations.manage`, body `{purpose?: "connect" \| "reconnect", social_account_id?: UUID}`) generates 32-byte URL-safe state, stores `sha256(state)` with 10-min expiry, returns `{authorize_url}` pointing to `https://www.instagram.com/oauth/authorize` with `client_id=META_APP_ID`, `redirect_uri=META_OAUTH_REDIRECT_URI`, `response_type=code`, `scope=instagram_business_basic,instagram_business_manage_messages,instagram_business_content_publish`, `state=<raw_state>`.<br>• `GET /oauth/instagram/callback?code=&state=&error=` verifies the caller's session cookie (`user_id` must match `oauth_states.user_id`), atomically sets `used_at = now` where `used_at IS NULL AND expires_at > now` (else redirects or returns 400 `OAUTH_STATE_INVALID`), exchanges `code` for short-lived token (`POST https://api.instagram.com/oauth/access_token`), exchanges for 60-day long-lived token (`GET https://graph.instagram.com/access_token?grant_type=ig_exchange_token`), fetches profile (`GET /me?fields=user_id,username`), checks reconnect account match (`external_account_id` mismatch → `ACCOUNT_MISMATCH`), encrypts token, upserts `social_accounts`, audits `social_account.connected` (or `account.reconnected` + enqueues `resume_account`), and redirects to `{FRONTEND_ORIGIN}/w/{ws}/more/settings/connections?oauth=connected` (or `?oauth=error&code=<ERROR_CODE>`). | phase-07-meta-integration.md, integrations.md §3.4, security-and-privacy T18 |
| **I7** | **Scope-to-capability detection** | `oauth.compute_capabilities(granted_scopes, stories_enabled=True)` produces:<br>`{"messaging": "instagram_business_manage_messages" in scopes, "publish_feed_image": "instagram_business_content_publish" in scopes, "publish_story_image": "instagram_business_content_publish" in scopes and stories_enabled}`. Stored on `social_accounts.capabilities` and `social_accounts.granted_scopes`. | integrations.md §3.2 |
| **I8** | **Token refresh jobs** | Periodic scheduler in `operations/jobs.py` runs daily at/after `03:00 UTC` (any-status dedup check `refresh_tokens:{date}` like `retention_cleanup`), enqueuing `refresh_tokens`.<br>• `refresh_tokens` scans active `meta` accounts (`status IN ('connected', 'degraded')`): if `token_expires_at <= now`, transitions account to `needs_reauth` (`handle_auth_error`); if `(token_refreshed_at IS NULL OR token_refreshed_at <= now - 24h)` and `token_expires_at <= now + timedelta(days=settings.token_refresh_days_before_expiry)`, enqueues `refresh_token(social_account_id)` with dedup `refresh_token:{account_id}:{date}`.<br>• `refresh_token` creates ledger `Operation(operation_type="refresh_token", idempotency_key=f"refresh_token:{account_id}:{date}")`, calls `provider.refresh_token(account_ref)` outside any DB tx, updates `token_ciphertext`, `token_key_id`, `token_expires_at`, `token_refreshed_at = now`, marks operation `succeeded`, and writes audit `social_account.token_refreshed` (added to `observability.md §5`, `activity/groups.py` under `accounts`, and `core/i18n/{tr,en}.json`). On `ProviderAuthError`, marks operation `failed` (`ACCOUNT_NEEDS_REAUTH`) and calls `health.handle_auth_error`. | workflows.md §G.2, background-jobs.md §4 & §6 |
| **I9** | **Disconnect cascade & optional data deletion** | `accounts.disconnect(session, clock, ctx, account_id, *, delete_conversation_data: bool = False)`:<br>1. Clears `token_ciphertext = None`, `token_key_id = None`, `token_expires_at = None`, `token_refreshed_at = None`.<br>2. Transitions account to `disconnected` (audits `social_account.disconnected` with metadata `delete_conversation_data`).<br>3. Cancels `queued` and `pending_approval` reply drafts for the account (cancelling pending approvals with `ACCOUNT_DISCONNECTED` and queued `send_reply` jobs).<br>4. Places `scheduled` and `retry_scheduled` content items for the account `on_hold` with `hold_reason="ACCOUNT_UNAVAILABLE"`, cancelling their queued `publish_content` jobs and waiting operations.<br>5. If `delete_conversation_data=True`, deletes the account's `conversations` (cascading to `messages`, `reply_drafts`, and `fact_references` for those drafts) and nulls `inbound_events.payload` for that account. | phase-07-meta-integration.md P7-08, security-and-privacy.md §8 |
| **I10** | **Frontend Connections & `/api/v1/meta`** | `GET /api/v1/meta` adds `instagram_providers: list[Literal["mock", "meta"]]`. `Connections.tsx` shows:<br>• **Instagram ile bağlan** button when `"meta"` is enabled (calls `POST /social-accounts/instagram/connect` and navigates to `authorize_url`).<br>• **Demo hesabı bağla** button when `"mock"` is enabled and allowed.<br>• On a `meta` account in `needs_reauth`, **Bağlantıyı yenile** triggers `POST /social-accounts/instagram/connect {purpose: "reconnect", social_account_id}`.<br>• Disconnect confirmation sheet adds a checkbox (`delete_conversation_data`) to also delete conversation/message history.<br>• Displays a status banner when returning from OAuth (`?oauth=connected` or `?oauth=error&code=...`). | phase-07-meta-integration.md P7-02, P7-08 |

---

## 3. Session Overview

| # | Session Name | Tasks Covered | Size | Depends On |
| :---: | :--- | :--- | :---: | :--- |
| **1** | **Token Crypto, S3 Storage & Configuration Safety** | `P7-01`, `P7-06` | M | Phase 6 |
| **2** | **`MetaInstagramProvider`, Error Mapping, Webhook Hardening & Offline Contract Suite** | `P7-03`, `P7-04`, `P7-05`, `P7-09` (offline) | L | Session 1 |
| **3** | **OAuth Flow, Token Refresh Jobs & Full Disconnect (Backend)** | `P7-02` (backend), `P7-07`, `P7-08` | L | Session 2 |
| **4** | **Frontend Connections UI, `meta_live` Contract Suite, Docs & Phase 7 Summary** | `P7-00`, `P7-02` (UI), `P7-09` (live), `P7-10` | M | Session 3 |

---

## 4. Detailed Session Specifications

---

### Session 1: Token Crypto, S3 Storage & Configuration Safety (`P7-01`, `P7-06`)

**Goal:** Build the foundational security and storage primitives required before any real Meta token or media URL can be handled: AES-256-GCM token encryption with key rotation support, the S3-compatible media storage backend with presigned URLs, and startup configuration safety rules.

**Commits:**
- `P7-01: AES-GCM token encryption key ring and startup config checks`
- `P7-06: S3 media storage backend with presigned URLs`

#### Read First
- `CLAUDE.md`, `docs/invariants.md` (especially INV-09, INV-10, INV-14)
- `docs/architecture/decisions/ADR-015-media-storage.md`
- `docs/architecture/decisions/ADR-017-configuration-and-secrets.md`
- `docs/operations/environment-variables.md`
- `backend/app/core/security.py`, `backend/app/core/config.py`
- `backend/app/integrations/storage/base.py`, `backend/app/integrations/storage/local.py`, `backend/app/integrations/storage/registry.py`

#### What to Build
1. **Dependencies (`backend/pyproject.toml`):**
   - Add `cryptography>=43.0` and `boto3>=1.35`. Run `uv sync`.
   - Update `[tool.importlinter]` contracts in `backend/pyproject.toml` for `app.integrations.storage.s3`.
2. **Token Encryption & Key Ring (`backend/app/core/security.py`):**
   - Implement `TokenKeyRing`:
     - Parse `TOKEN_ENCRYPTION_KEYS` (`"k1:<base64-32-bytes>[,k2:<base64-32-bytes>]"`). Reject empty key IDs, duplicate key IDs, invalid base64, or decoded keys whose length is not 32 bytes.
     - Verify `TOKEN_ENCRYPTION_ACTIVE_KEY_ID` is present in the parsed keys.
     - `encrypt(plaintext: str, *, aad: bytes = b"") -> tuple[bytes, str]`: generates a 12-byte random nonce (`secrets.token_bytes(12)`), encrypts with `AESGCM(active_key).encrypt(nonce, plaintext.encode("utf-8"), aad)`, and returns `(nonce + ciphertext, active_key_id)`.
     - `decrypt(blob: bytes, key_id: str, *, aad: bytes = b"") -> str`: looks up `key_id` in the ring, splits `nonce = blob[:12]` and `ct = blob[12:]`, decrypts and verifies tag + AAD, returns UTF-8 string. Raises `TokenCryptoError` on unknown `key_id`, truncated blob, wrong key, or tampered ciphertext/AAD.
   - Add helper `account_token_aad(workspace_id: uuid.UUID, account_id: uuid.UUID) -> bytes`.
3. **Configuration & Startup Safety (`backend/app/core/config.py`, `.env.example`):**
   - Add Phase 7 settings to `Settings`:
     - `meta_app_id: str = ""`
     - `meta_graph_api_version: str = "v25.0"`
     - `meta_oauth_redirect_uri: str = "http://localhost:8000/oauth/instagram/callback"`
     - `meta_stories_enabled: bool = True`
     - `token_encryption_keys: SecretStr = SecretStr("")`
     - `token_encryption_active_key_id: str = ""`
     - `token_refresh_days_before_expiry: int = Field(default=20, ge=1)`
     - `media_public_base_url: str = ""` (reserved; secured local-media tunnel serving remains pending)
     - `s3_endpoint_url: str = ""`
     - `s3_region: str = "auto"`
     - `s3_bucket: str = ""`
     - `s3_access_key_id: SecretStr = SecretStr("")`
     - `s3_secret_access_key: SecretStr = SecretStr("")`
   - Add `"token_encryption_keys"`, `"s3_access_key_id"`, `"s3_secret_access_key"` to `_SECRET_FIELDS` so `public_dict()` never leaks them.
   - Extend `_instagram_problems()` and `safety_problems()`:
     - When `"meta"` is in `instagram_providers` in any environment: require `META_APP_ID`, `META_APP_SECRET`, explicitly set `META_WEBHOOK_VERIFY_TOKEN`, `META_OAUTH_REDIRECT_URI`, and a valid `TokenKeyRing` (`TOKEN_ENCRYPTION_KEYS` + `TOKEN_ENCRYPTION_ACTIVE_KEY_ID`). Validate supplied key ring settings even when Meta is disabled.
     - When `media_storage_backend == "s3"`: require `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`.
     - In every environment, `"meta"` in `instagram_providers` requires `media_storage_backend == "s3"` until secured local-media tunnel serving is implemented.
4. **S3 Storage Backend (`backend/app/integrations/storage/s3.py`, `registry.py`, `local.py`):**
   - Implement `S3MediaStorage(MediaStorage)`:
     - Validates every `key` with `validate_key(key)` from `storage/base.py`.
     - `put(key, data, content_type)` → `client.put_object(Bucket=..., Key=key, Body=data, ContentType=content_type)`.
     - `open(key)` → `client.get_object(Bucket=..., Key=key)["Body"]` read into `io.BytesIO` (maps `NoSuchKey` / 404 `ClientError` to `FileNotFoundError`).
     - `delete(key)` → `client.delete_object(Bucket=..., Key=key)` (idempotent if already absent).
     - `public_fetch_url(key, ttl_s)` → `client.generate_presigned_url("get_object", Params={"Bucket": ..., "Key": key}, ExpiresIn=ttl_s)`.
   - Wire `media_storage_backend == "s3"` in `app/integrations/storage/registry.py`.

#### Done When
- Unit tests in `backend/tests/unit/core/test_token_crypto.py` pass:
  - Round-trip encrypt/decrypt with AAD;
  - Key rotation: ciphertext encrypted with `k1` still decrypts after `TOKEN_ENCRYPTION_ACTIVE_KEY_ID` changes to `k2`, while new encryptions use `k2`;
  - Wrong key, unknown `key_id`, tampered ciphertext byte, or mismatched `workspace_id`/`account_id` AAD raises `TokenCryptoError`;
  - Malformed `TOKEN_ENCRYPTION_KEYS` strings fail validation.
- Unit tests in `backend/tests/unit/core/test_settings_safety.py` cover all new Phase 7 settings, secret redaction in `public_dict()`, and `meta`/`s3` safety checks.
- Unit tests in `backend/tests/unit/integrations/test_media_storage.py` test `S3MediaStorage` (`put`, `open`, missing key → `FileNotFoundError`, `delete`, `public_fetch_url` presigned URL with TTL, and invalid key rejection) using a stubbed/in-memory S3 client (no network).
- `uv run ruff check . && uv run ruff format --check . && uv run mypy app evals && uv run lint-imports && uv run pytest` are all green.

---

### Session 2: `MetaInstagramProvider`, Error Mapping, Webhook Hardening & Offline Contract Suite (`P7-03`, `P7-04`, `P7-05`, `P7-09` offline)

**Goal:** Implement `MetaInstagramProvider` for messaging, publishing, profile, quota, reconciliation lookup, and token refresh; map all Graph API errors and transport edge cases to typed `Provider*Error`s; harden the webhook parser for story replies, mentions, deletions, and echoes; and pass the parameterised offline contract suite using explicitly synthetic JSON fixtures until authentic recordings are authorized.

**Commits:**
- `P7-03: MetaInstagramProvider messaging, profile, lookup and error mapping`
- `P7-04: MetaInstagramProvider publishing, container status, media and quota`
- `P7-05: webhook parser hardening for story replies, deletions and echoes`
- `P7-09a: parameterised Meta contract tests with synthetic offline fixtures`

#### Read First
- `CLAUDE.md`, `docs/invariants.md` (INV-05, INV-06, INV-09, INV-10, INV-15)
- `docs/architecture/integrations.md` (§1–§3.6)
- `docs/architecture/workflows.md` (§C, §E, §G.1)
- `docs/research/platform-capabilities.md` (§1.3–§1.7)
- `backend/app/integrations/instagram/base.py`, `errors.py`, `mock.py`, `registry.py`, `webhook_format.py`
- `backend/app/inbox/ingest.py`, `processing.py`, `echoes.py`
- `backend/tests/contract/test_instagram_provider_contract.py`

#### What to Build
1. **Fixtures (`backend/tests/contract/fixtures/meta/*.json`):**
   - Create explicitly labelled synthetic offline JSON fixtures for (authentic sanitized recordings remain pending V-05):
     - `profile_ok.json`, `send_ok.json`, `conversations_messages_ok.json`
     - `container_create_ok.json`, `container_status_in_progress.json`, `container_status_finished.json`, `container_status_published.json`, `container_status_error.json`, `container_status_expired.json`, `publish_ok.json`, `media_ok.json`, `publishing_limit_ok.json`, `refresh_token_ok.json`
     - Error fixtures: `error_auth_expired_190.json`, `error_permission_10.json`, `error_window_closed_2534022.json`, `error_rate_limit_4.json`, `error_invalid_media_36000.json`, `error_invalid_request_100.json`
     - Webhook fixtures: `webhook_text_message.json`, `webhook_attachments.json`, `webhook_story_reply.json`, `webhook_story_mention.json`, `webhook_echo_app.json`, `webhook_echo_native.json`, `webhook_reaction.json`, `webhook_message_deleted.json`
2. **Error Mapping (`backend/app/integrations/instagram/error_mapping.py`):**
   - Translate HTTP statuses, Graph API `error.code` / `error.error_subcode`, `Retry-After` headers, and `httpx` transport exceptions into `ProviderAuthError`, `ProviderPermissionError`, `ProviderWindowClosed`, `ProviderRateLimited`, `ProviderInvalidRequest`, `ProviderTransientError`, and `ProviderOutcomeUnknown` (strictly enforcing the side-effect vs read ambiguity rule from `integrations.md §3.1`).
3. **Meta Adapter (`backend/app/integrations/instagram/meta.py`) & Registry (`registry.py`):**
   - Implement `MetaInstagramProvider`:
     - `kind = "meta"`
     - `verify_signature` and `parse_webhook` delegating to `WebhookCodec(meta_app_secret)`
     - `get_account_profile(account)` → `GET /{external_account_id}?fields=user_id,username`
     - `send_text_message(account, recipient_id, text)` → pre-validates UTF-8 byte length ≤ 1000 (`ProviderInvalidRequest("MESSAGE_TOO_LONG")` before network); `POST /{external_account_id}/messages` with `{"recipient": {"id": recipient_id}, "message": {"text": text}}`
     - `find_recent_outbound(account, recipient_id, since)` → `GET /{external_account_id}/conversations?user_id={recipient_id}&fields=messages{id,from,to,message,created_time}` filtered to outbound messages with `created_time >= since`
     - `create_media_container(account, spec)` → refuses `localmedia:` URLs (`ProviderInvalidRequest("MEDIA_URL_NOT_PUBLIC")`); rejects captions on `STORIES` (`ProviderInvalidRequest("CAPTION_NOT_ALLOWED")`); `POST /{external_account_id}/media` with `image_url` and `caption` (or `media_type="STORIES"`)
     - `get_container_status(account, container_id)` → `GET /{container_id}?fields=id,status_code,status`
     - `publish_container(account, container_id)` → `POST /{external_account_id}/media_publish` with `{"creation_id": container_id}`
     - `get_media(account, media_id)` → `GET /{media_id}?fields=id,permalink,timestamp`
     - `get_publishing_quota(account)` → `GET /{external_account_id}/content_publishing_limit?fields=config,quota_usage`
     - `refresh_token(account)` → `GET /refresh_access_token?grant_type=ig_refresh_token&access_token=...`
   - Token is obtained only at request time via `account.token_provider()` and passed in the `Authorization: Bearer <token>` header (or query param strictly for `refresh_access_token`), never logged or cached on the instance.
   - Update `app/integrations/instagram/registry.py` and `AccountRef` creation in `operations` (`send.py`, `publish.py`, `reconcile.py`, `health_check.py`) so `meta` accounts get a `token_provider` callable that decrypts `account.token_ciphertext` with `TokenKeyRing` and `account_token_aad`.
4. **Webhook Parser & Processing Hardening (`webhook_format.py`, `inbox/processing.py`, `inbox/echoes.py`):**
   - `webhook_format.py`: parse `reply_to.story` into attachments, preserve `story_mention`, detect `message.is_deleted == True` as `event_type="delete"`, handle `message.is_unsupported == True`.
   - `inbox/processing.py`: handle `event_type == "delete"` by setting `messages.is_deleted = True` on the matching `(social_account_id, external_message_id)` row without creating a draft.
   - `inbox/echoes.py`: use `event.app_id` and `settings.meta_app_id` when distinguishing app-sent echoes from native Instagram app replies (`business_native`).

#### Done When
- Unit tests for `error_mapping.py` and `MetaInstagramProvider` cover every fixture, error code, HTTP 5xx/timeout ambiguity rule (side-effect → `ProviderOutcomeUnknown`; read/container-create → `ProviderTransientError`), and verify tokens never appear in logs or exception messages.
- `tests/contract/test_instagram_provider_contract.py` runs parameterised against both `mock` and `meta` (using a deterministic `httpx.MockTransport` backed by `tests/contract/fixtures/meta/*.json`) and passes 100%.
- Integration tests in `tests/integration/inbox/` prove story reply ingestion, message deletion (`is_deleted=True`), and `app_id`-based native echo draft supersession.
- `uv run ruff check . && uv run ruff format --check . && uv run mypy app evals && uv run lint-imports && uv run pytest` are all green.

---

### Session 3: OAuth Flow, Token Refresh Jobs & Full Disconnect (`P7-02` backend, `P7-07`, `P7-08`)

**Goal:** Build the OAuth connect/callback/reconnect endpoints with single-use hashed state, the daily `refresh_tokens` / `refresh_token` background jobs through the operations ledger, and the full disconnect flow (immediate token deletion, queued reply cancellations, scheduled content holds, and optional conversation data deletion).

**Commits:**
- `P7-02a: OAuth state migration, connect/callback/reconnect service and routes`
- `P7-07: refresh_tokens and refresh_token jobs with ledger and reauth handling`
- `P7-08: disconnect token deletion, draft/content cascades and optional conversation wipe`

#### Read First
- `CLAUDE.md`, `docs/invariants.md` (INV-01, INV-05, INV-09, INV-10, INV-12, INV-15)
- `docs/architecture/integrations.md` (§3.2, §3.4)
- `docs/architecture/workflows.md` (§G.1, §G.2)
- `docs/architecture/background-jobs.md` (§4, §6)
- `docs/architecture/security-and-privacy.md` (T10, T18, §8)
- `docs/architecture/observability.md` (§4.4, §5)
- `backend/app/operations/accounts.py`, `accounts_router.py`, `jobs.py`, `health.py`, `models.py`
- `backend/app/activity/groups.py`, `backend/app/core/i18n/tr.json`, `backend/app/core/i18n/en.json`

#### What to Build
1. **Migration `0017` & `OAuthState` Model (`backend/migrations/versions/0017_oauth_states.py`, `integrations/instagram/models.py`):**
   - Create `oauth_states` table with `id`, `workspace_id`, `user_id`, `state_hash` (`LargeBinary`, unique), `purpose` (`connect` | `reconnect`), `social_account_id` (`UUID`, nullable), `expires_at` (`DateTime(timezone=True)`), `used_at` (`DateTime(timezone=True)`, nullable), `created_at`.
2. **OAuth Client & Service (`integrations/instagram/oauth.py`, `operations/oauth_service.py`, `operations/oauth_router.py`, `operations/accounts_router.py`):**
   - `oauth.py`:
     - `build_authorize_url(settings, state)` → `https://www.instagram.com/oauth/authorize?...`
     - `exchange_code_for_long_lived_token(settings, code, transport=...) -> TokenExchangeResult(access_token, expires_in_seconds, ig_user_id, granted_scopes)`: performs short-lived `POST https://api.instagram.com/oauth/access_token` followed by long-lived `GET https://graph.instagram.com/access_token?grant_type=ig_exchange_token`.
     - `compute_capabilities(granted_scopes, stories_enabled)` → `{"messaging": ..., "publish_feed_image": ..., "publish_story_image": ...}`.
   - `oauth_service.py`:
     - `start_connect(session, clock, ctx, settings, *, purpose="connect", social_account_id=None) -> str`: checks `"meta" in settings.instagram_providers` (else 403 `FORBIDDEN`), validates active account rules (for `connect`, no other connected account in workspace unless reconnecting/replacing disconnected; for `reconnect`, target account must belong to workspace, be `meta`, and be in `needs_reauth` or `degraded`/`connected`), inserts `OAuthState` (TTL 10 min), commits, returns `authorize_url`.
     - `complete_callback(session_factory, clock, settings, user_id, *, code, state, error)`:
       - Step 1 (DB tx): lock `OAuthState` by `state_hash`, verify `user_id == state_row.user_id`, `used_at is None`, and `expires_at > clock.now()`, mark `used_at = clock.now()`, commit immediately so a replay can never succeed even if downstream fails (T18).
       - Step 2 (no DB tx): call `exchange_code_for_long_lived_token` and `provider.get_account_profile`.
       - Step 3 (DB tx): if `purpose == "reconnect"`, verify `profile.external_account_id == account.external_account_id` (mismatch → raise `AppError("ACCOUNT_MISMATCH")`). Check that `external_account_id` is not actively connected to another workspace (`CONFLICT_STATE`). Encrypt token with `TokenKeyRing` and `account_token_aad`. Upsert `SocialAccount(provider_kind="meta", status="connected", is_simulated=False, capabilities=..., granted_scopes=..., token_ciphertext=..., token_key_id=..., token_expires_at=..., token_refreshed_at=now, connected_at=now)`. Audit `social_account.connected` (or `account.reconnected` and enqueue `resume_account` on reconnect).
   - Routes:
     - `POST /api/v1/workspaces/{workspace_id}/social-accounts/instagram/connect` (`integrations.manage`) → `{authorize_url}`.
     - `GET /oauth/instagram/callback` (mounted on `app` outside `/api/v1` in `main.py`): reads session user, runs `complete_callback`, redirects to `{FRONTEND_ORIGIN}/w/{workspace_id}/more/settings/connections?oauth=connected` (or `?oauth=error&code=...` on error).
3. **Token Refresh Jobs (`backend/app/operations/refresh.py`, `operations/jobs.py`, `operations/payloads.py`):**
   - Add `RefreshTokensPayload` (`{}`) and `RefreshTokenPayload` (`{social_account_id: UUID}`).
   - Register periodic `enqueue_token_refreshes` (daily at/after `03:00 UTC`, dedup `refresh_tokens:{yyyy-mm-dd}` with any-status check).
   - Implement `refresh_tokens` job handler and `refresh_token` job handler (3 attempts):
     - If `account.token_expires_at <= now`: transition account to `needs_reauth` (`health.handle_auth_error`).
     - Otherwise, record `Operation(operation_type="refresh_token", idempotency_key=f"refresh_token:{account.id}:{date}")`, call `provider.refresh_token(ref)` outside DB tx, encrypt and store new token + `token_expires_at` + `token_refreshed_at = now`, complete operation, and audit `social_account.token_refreshed`.
     - Add `social_account.token_refreshed` to `app/activity/groups.py` (`accounts`) and `app/core/i18n/{tr,en}.json` (`activity.social_account.token_refreshed`), plus error code `ACCOUNT_MISMATCH` and `OAUTH_STATE_INVALID` to `app/core/errors.py` and i18n catalogs.
4. **Full Disconnect (`backend/app/operations/accounts.py`, `accounts_router.py`, `schemas.py`):**
   - Extend `POST /api/v1/workspaces/{workspace_id}/social-accounts/{account_id}/disconnect` to accept optional `DisconnectRequest(delete_conversation_data: bool = False)`.
   - In `accounts.disconnect`:
     - Wipe `token_ciphertext = None`, `token_key_id = None`, `token_expires_at = None`, `token_refreshed_at = None`.
     - Transition account to `disconnected`.
     - Cancel `queued` and `pending_approval` reply drafts of the account (`ACCOUNT_DISCONNECTED`), cancel their pending approvals and queued `send_reply` jobs.
     - Move `scheduled` and `retry_scheduled` content items of the account to `on_hold` (`hold_reason="ACCOUNT_UNAVAILABLE"`), cancel their queued `publish_content` jobs and waiting operations, and emit `content.on_hold`.
     - If `delete_conversation_data=True`: delete the account's `conversations` (cascading `messages` and `reply_drafts`, plus cleaning `fact_references` for those drafts) and null `inbound_events.payload` for that account.

#### Done When
- Integration tests in `backend/tests/integration/integrations/test_oauth.py` pass:
  - Connect flow creates `OAuthState`, callback exchanges code & long-lived token, encrypts token in DB (`token_ciphertext` non-null, decrypts with ring, never returned in API), sets capabilities from scopes, audits `social_account.connected`;
  - Security (T18): expired `state`, replayed `state` (second call), unknown `state`, or callback called by a different logged-in user is rejected;
  - Reconnect flow for `needs_reauth` Meta account restores `connected`, audits `account.reconnected`, enqueues `resume_account`, and resumes queued replies;
  - Reconnect with a different `external_account_id` fails with `ACCOUNT_MISMATCH` and does not overwrite the account.
- Integration tests in `backend/tests/integration/integrations/test_token_refresh.py` pass:
  - Account with `token_refreshed_at < now - 24h` and `token_expires_at < now + 20d` refreshes via ledger `Operation`, rotates ciphertext, updates expiry, audits `social_account.token_refreshed`;
  - Refresh returning `ProviderAuthError` transitions account to `needs_reauth` and emits critical `account.needs_reauth` notification;
  - Account refreshed `< 24h` ago or expiring `> 20d` out is skipped.
- Integration tests in `backend/tests/integration/integrations/test_disconnect.py` pass:
  - Disconnect wipes `token_ciphertext`, cancels queued sends, holds scheduled content;
  - Disconnect with `delete_conversation_data=True` removes the account's conversations, messages, and drafts while leaving other workspaces untouched.
- Workspace isolation tests (`tests/isolation/`) and activity template coverage tests pass.
- `uv run ruff check . && uv run ruff format --check . && uv run mypy app evals && uv run lint-imports && uv run pytest` are all green.

---

### Session 4: Frontend Connections UI, `meta_live` Contract Suite, Docs & Phase 7 Summary (`P7-00`, `P7-02` UI, `P7-09` live, `P7-10`)

**Goal:** Connect the frontend `Connections.tsx` screen to the real OAuth connect/reconnect and disconnect flows, regenerate OpenAPI types, add the manual `meta_live` contract test harness for the founder's professional account, update documentation (`platform-capabilities.md`, `local-development.md`, architecture docs), run the full verification suites, and write `phase-07-summary.md`.

**Commits:**
- `P7-02b: frontend Connections OAuth connect, reconnect, callback banner and disconnect options`
- `P7-09b: live Meta contract test suite (-m meta_live)`
- `P7-10: tunnel and Meta setup docs, platform capabilities update and Phase 7 summary`

#### Read First
- `CLAUDE.md`, `docs/invariants.md`
- `docs/implementation/phases/phase-07-meta-integration.md`
- `docs/research/platform-capabilities.md`
- `docs/operations/local-development.md`
- `frontend/src/features/settings/Connections.tsx`, `frontend/src/features/settings/hooks.ts`, `frontend/src/features/inbox/hooks.ts`

#### What to Build
1. **Public Meta Endpoint & OpenAPI Regeneration (`backend/app/api/router.py`, `frontend/openapi.json`, `frontend/src/api/schema.d.ts`):**
   - Expose `instagram_providers: list[str]` on `GET /api/v1/meta`.
   - Run `uv run python -m app.cli export-openapi -o ../frontend/openapi.json` and `npm run gen:api`.
2. **Frontend Connections Screen (`frontend/src/features/settings/Connections.tsx`, `hooks.ts`, `frontend/src/i18n/{tr,en}/...`):**
   - When no account is connected:
     - If `"meta"` is in `meta.instagram_providers`, show **Instagram ile bağlan** (`connections.connectInstagram`), which calls `POST /api/v1/workspaces/{ws}/social-accounts/instagram/connect` and redirects via `window.location.assign(authorize_url)`.
     - If `"mock"` is enabled (and allowed), show **Demo hesabı bağla** (`connections.connectMock`).
   - When an account is connected:
     - Real (`provider_kind === "meta"`) accounts do **not** show `<SimulatedBadge />` (INV-09).
     - When `status === "needs_reauth"` and `provider_kind === "meta"`, **Bağlantıyı yenile** calls `POST /social-accounts/instagram/connect` with `{purpose: "reconnect", social_account_id: account.id}` and redirects to `authorize_url`.
     - Disconnect bottom sheet includes the checkbox `connections.deleteConversationData` ("Konuşma ve mesaj geçmişini de sil") and passes `{delete_conversation_data}` to `POST /social-accounts/{id}/disconnect`.
   - Handle `?oauth=connected` and `?oauth=error&code=...` query parameters on `/more/settings/connections` with a dismissible success/error banner (using `useErrorText()` for the error code).
   - Add tr/en i18n keys and Vitest component tests in `frontend/src/features/settings/`.
3. **Live Meta Contract Suite (`backend/tests/contract/test_meta_live.py`):**
   - Marked with `@pytest.mark.meta_live` and skipped automatically unless `META_LIVE_ACCESS_TOKEN` and `META_LIVE_IG_USER_ID` are set in the environment (so CI never runs it).
   - Exercises against the live Graph API:
     1. `get_account_profile` returns `external_account_id` and `username`;
     2. `get_publishing_quota` returns `PublishingQuota(used, limit, window_hours=24)`;
     3. Optional live DM send & `find_recent_outbound` when `META_LIVE_RECIPIENT_ID` is provided;
     4. Optional live image container creation (`create_media_container`), status poll (`get_container_status`), publish (`publish_container`), and permalink fetch (`get_media`) when `META_LIVE_IMAGE_URL` is provided;
     5. Optional sanitised fixture recorder helper to dump real response shapes into `backend/tests/contract/fixtures/meta/`.
4. **Documentation & Phase 7 Summary (`P7-00`, `P7-10`):**
   - `docs/operations/local-development.md`: add section on running Phase 7 locally with a tunnel (`cloudflared tunnel --url http://localhost:8000`), configuring the Meta Developer App (Instagram Login redirect URI, webhook callback URL + `META_WEBHOOK_VERIFY_TOKEN`, subscribing to `messages` and `message_echoes`), S3/R2/MinIO setup, and generating `TOKEN_ENCRYPTION_KEYS` via `uv run python -m app.cli generate-key`.
   - Sync `docs/architecture/{api-design,data-model,integrations,workflows,observability,security-and-privacy}.md`, `docs/research/platform-capabilities.md`, `docs/implementation/{roadmap,task-breakdown}.md`, and `.env.example`.
   - Write `docs/implementation/phase-summaries/phase-07-summary.md` mapping every Phase 7 acceptance criterion (AC 1–7) to its proving automated tests and live verification checklist.

#### Done When
- Frontend checks pass: `npm run lint && npm run typecheck && npm test && npm run i18n:check`.
- OpenAPI schema has zero drift (`export-openapi` + `npm run gen:api` + `git diff --exit-code -- openapi.json src/api/schema.d.ts`).
- Backend checks pass: `uv run ruff check . && uv run ruff format --check . && uv run mypy app evals && uv run lint-imports && uv run pytest`.
- Eval suite passes: `uv run python -m evals run --all --provider fake --strict`.
- `phase-07-summary.md` is written and committed, and working tree is clean.

---

## 5. How to Run Each Session

Open a fresh agent session for each session `1..4` and paste:

> Read `CLAUDE.md`, `docs/invariants.md`, `docs/implementation/phases/phase-07-meta-integration.md`, and `docs/implementation/phase-07-sessions.md`. Execute **Session N** in `docs/implementation/phase-07-sessions.md`. Keep changes scoped to that session, run all required checks, make the session's local commits on `main` (do not push), and stop with a session report when its "Done When" criteria are met.

