# Environment Variables

**Purpose:** Every configuration variable, its default per environment, whether it is secret, and the phase that introduces it. `.env.example` must mirror this table (non-secret defaults filled in; secrets left empty, or a clearly fake development value). Rules: [ADR-017](../architecture/decisions/ADR-017-configuration-and-secrets.md).

Legend: **dev** = development default, **prod** = production requirement. 🔒 = secret (never commit, never log, never send to the frontend).

## Core (Phase 1)

| Variable | dev | prod | Description |
|---|---|---|---|
| `APP_ENV` | `development` | `production` | `development` \| `test` \| `production` |
| `DATABASE_URL` | `postgresql+psycopg://agentnest:agentnest@localhost:5433/agentnest` | required 🔒 | Main runtime DB (`agentnest_app` / `agentnest_worker` in Phase 8) |
| `MIGRATION_DATABASE_URL` | empty (= `DATABASE_URL`) | recommended 🔒 | Optional DDL/migration connection URL (`agentnest_migrator` in Phase 8; falls back to `DATABASE_URL` when empty) |
| `TEST_DATABASE_URL` | `…/agentnest_test` | — | Used by pytest |
| `SECRET_KEY` 🔒 | dev placeholder (refused in prod) | required, ≥ 32 bytes random | Signing (OAuth state HMAC, misc) |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | site origin | CORS (dev only) and redirects |
| `APP_BASE_URL` | `http://localhost:8000` | `https://<domain>` | Absolute URLs (OAuth redirect, invites) |
| `COOKIE_SECURE` | `false` | `true` (enforced) | Session cookie Secure flag |
| `SESSION_TTL_HOURS` | `336` | `336` | Sliding session lifetime (14 days) |
| `LOG_LEVEL` | `INFO` | `INFO` | |
| `LOG_FORMAT` | `console` | `json` | |
| `DEMO_TOOLS_ENABLED` | `true` | must be `false` | Mounts `/api/v1/dev/*` and the dev panel |
| `DEMO_PASSWORD` | `demo-password` | unused (seed refuses in prod) | Password for seeded demo users |
| `WORKER_CONCURRENCY` | `2` | `2` | Threads per worker process |
| `WORKER_POLL_INTERVAL_SECONDS` | `1.0` | `1.0` | |
| `JOB_LEASE_SECONDS` | `120` | `120` | |
| `PRODUCT_NAME` | `AgentNest` | configurable | Shown in UI and notifications (OQ-10) |

**Production safety checks (Phase 1, enforced at startup of the API, worker and CLI):** `SECRET_KEY` set explicitly, at least 32 bytes and not the example value; `DATABASE_URL` set explicitly; `DEMO_TOOLS_ENABLED=false`; `COOKIE_SECURE=true`. When these are not set in production they default to the safe values (`DEMO_TOOLS_ENABLED=false`, `COOKIE_SECURE=true`, `LOG_FORMAT=json`); setting an unsafe value explicitly refuses to start, and all problems are listed together. The seed (`seed`) refuses to run when `APP_ENV=production`. Checks for variables introduced later (fake LLM, mock Instagram, Meta keys, S3) are added by the phase that introduces the variable. Variables in `.env` that the current phase does not know yet are ignored.

## AI (Phase 3)

| Variable | dev | prod | Description |
|---|---|---|---|
| `LLM_PROVIDER` | `fake` | `openai` (fake refused) | `fake` \| `openai` |
| `OPENAI_API_KEY` 🔒 | empty | required if openai | |
| `LLM_MODEL_DEFAULT` | `gpt-6-luna` | per OQ-09 (required if openai) | `gpt-6-luna` is the cheapest GPT-6 model; the ID was confirmed on OpenAI's model page on 2026-10-21 |
| `LLM_MODEL_INTERPRET_COMMAND`, `LLM_MODEL_DRAFT_REPLY`, `LLM_MODEL_DRAFT_CONTENT`, `LLM_MODEL_EXTRACT_FACTS` | empty (= default) | optional | Per-task overrides |
| `LLM_TIMEOUT_SECONDS` | `30` | `30` | Default; per-task values in code |
| `LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY` | `500` | per plan | Budget guard |
| `TEST_CHAT_MAX_MESSAGES_PER_HOUR` | `20` | `20` | Owner test chat (F-02): messages per workspace per rolling hour; over it the API answers 429 `TEST_CHAT_RATE_LIMITED` |
| `TEST_CHAT_MAX_MESSAGES_PER_DAY` | `60` | `60` | Same, per rolling 24 h. Each message is one LLM call that also counts against `LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY` |
| `WEB_PUSH_VAPID_PUBLIC_KEY` | empty | set with the other two | Web Push (F-01). The public VAPID key (unpadded base64url, 65-byte P-256 point), served to the app by `GET /…/push-subscriptions/config`. All three `WEB_PUSH_*` values empty = push off (the config endpoint answers `enabled: false`, subscribing is 409). Set only some = the app refuses to start. Replacing the pair invalidates every stored subscription (browsers must re-subscribe) |
| `WEB_PUSH_VAPID_PRIVATE_KEY` 🔒 | empty | set with the other two | The matching private key (unpadded base64url, 32 bytes). Never returned, logged or put in a job. Startup checks that it matches the public key. Generate the pair once with `uv run python -m app.cli generate-vapid-keys`, which prints both as `.env` lines on stdout |
| `WEB_PUSH_SUBJECT` | empty | set with the other two | VAPID contact (RFC 8292): `mailto:ops@example.com` or an `https://` URL. Push services use it to reach the operator. Web Push also needs `TOKEN_ENCRYPTION_KEYS` (subscription keys are stored encrypted) |
| `DELEGATION_SUGGESTION_WINDOW_DAYS` | `28` | `28` | Approval-ladder suggestions (D-02): the look-back window (7-90 days) for counting approved, edited, rejected and failed replies per topic |
| `DELEGATION_SUGGESTION_MIN_UNCHANGED` | `20` | `20` | Unchanged owner approvals a topic needs in the window (with no edit, rejection or failure) before the weekly job suggests sending it automatically (minimum 5) |
| `DELEGATION_SUGGESTION_COOLDOWN_DAYS` | `30` | `30` | How long a dismissed suggestion silences that topic (minimum 7 days) |
| `LLM_REASONING_EFFORT` | `low` | `low` | `` (off) \| `minimal` \| `low` \| `medium` \| `high`. Reasoning tokens count against each task's `max_output_tokens` |
| `LLM_PRICE_TABLE` | empty | optional JSON | `{"<model>": {"input_per_mtok": 0.0, "output_per_mtok": 0.0}}` (USD). Cost estimates in evals and system health; unpriced models have no estimate |

## Voice notes (Feature Phase 2, F-03)

A customer's voice note is downloaded and sent to the transcription provider (the audio leaves the platform: see [sub-processor-register.md](../legal/sub-processor-register.md)). Nothing is sent when `TRANSCRIPTION_PROVIDER=off`; the voice note then stays a person-handled attachment.

| Variable | dev | prod | Description |
|---|---|---|---|
| `TRANSCRIPTION_PROVIDER` | `auto` | `auto` (= `openai` when `LLM_PROVIDER=openai`) \| `openai` \| `off` (`fake` refused) | `auto` \| `off` \| `fake` \| `openai`. `auto` follows `LLM_PROVIDER` (`fake` offline, `openai` live). `off` disables downloading and transcribing. `openai` needs `OPENAI_API_KEY` |
| `TRANSCRIPTION_MODEL` | `gpt-4o-mini-transcribe` | same | OpenAI speech-to-text model ID, read only when the provider is `openai`. The ID is listed in the installed OpenAI SDK's documentation; it was **not confirmed on OpenAI's own model page and has never been run against the real API**. `whisper-1` is also supported (it additionally reports duration and language). Check before the first live run |
| `TRANSCRIPTION_MAX_AUDIO_BYTES` | `10485760` | same | 10 MiB. A longer `Content-Length`, or a body that grows past it, is refused (`VOICE_TOO_LARGE`). At most 26 214 400 (the provider's own 25 MB limit) |
| `TRANSCRIPTION_MAX_AUDIO_SECONDS` | `120` | same | Longer clips are refused before the provider call when the container (MP4/M4A, WAV) states its duration, otherwise after it (`VOICE_TOO_LONG`). At most 1 800 |
| `TRANSCRIPTION_TIMEOUT_SECONDS` | `60` | same | One provider call |
| `TRANSCRIPTION_DOWNLOAD_TIMEOUT_SECONDS` | `20` | same | One download; the whole download is cut off at twice this |
| `TRANSCRIPTION_MAX_PER_WORKSPACE_PER_DAY` | `200` | per plan | Cost guard: provider calls per workspace in a rolling 24 h; over it a voice note fails with `VOICE_QUOTA_EXCEEDED` |

## Photos and screenshots (Feature Phase 2, F-03 Session 03)

A customer's photo or screenshot is downloaded and sent to the LLM provider's vision model (`LLM_PROVIDER`) to be described for the owner (the image leaves the platform: see [sub-processor-register.md](../legal/sub-processor-register.md)). Nothing is downloaded or sent when `IMAGE_DESCRIPTION_ENABLED=false`; the image then stays a plain attachment. The model call counts against `LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY` as well.

| Variable | dev | prod | Description |
|---|---|---|---|
| `IMAGE_DESCRIPTION_ENABLED` | `true` | `true` after the sub-processor notice | `false` disables downloading and describing images |
| `LLM_MODEL_DESCRIBE_IMAGE` | empty (= `LLM_MODEL_DEFAULT`) | a model that **accepts images** | Per-task model override. Image support of the default `gpt-6-luna` is **unverified**, and the adapter has never been run against the real API with an image. Check before the first live run |
| `IMAGE_DESCRIPTION_MAX_BYTES` | `5242880` | same | 5 MiB. A longer `Content-Length`, or a body that grows past it, is refused (`IMAGE_TOO_LARGE`). At most 20 971 520 |
| `IMAGE_DESCRIPTION_DOWNLOAD_TIMEOUT_SECONDS` | `20` | same | One download; the whole download is cut off at twice this |
| `IMAGE_DESCRIPTION_MAX_PER_MESSAGE` | `3` | same | Images described per message (the first ones; 1 to 10) |
| `IMAGE_DESCRIPTION_MAX_PER_WORKSPACE_PER_DAY` | `100` | per plan | Cost guard: model calls for images per workspace in a rolling 24 h; over it an image fails with `IMAGE_QUOTA_EXCEEDED` |

## Instagram and inbox (Phase 4; Meta in Phase 7)

| Variable | dev | prod | Description |
|---|---|---|---|
| `INSTAGRAM_ENABLED_PROVIDERS` | `mock` | `meta` (+`mock` only with `ALLOW_SIMULATED_WORKSPACES`) | Comma list |
| `ALLOW_SIMULATED_WORKSPACES` | `true` | `false` (default) | Permits mock accounts on `is_demo` workspaces in prod. Production refuses `mock` in `INSTAGRAM_ENABLED_PROVIDERS` unless this is `true`, and refuses a missing mock/Meta secret for an enabled provider (Phase 4) |
| `MOCK_INSTAGRAM_APP_SECRET` 🔒 | dev placeholder | required if mock enabled | Signs simulated webhooks |
| `META_WEBHOOK_VERIFY_TOKEN` 🔒 | dev placeholder | required if meta | Handshake token |
| `META_APP_ID` | empty | required if meta | |
| `META_APP_SECRET` 🔒 | empty | required if meta | Webhook signatures, OAuth |
| `META_GRAPH_API_VERSION` | `v25.0` (verify current at P7) | pinned | |
| `META_OAUTH_REDIRECT_URI` | `http://localhost:8000/oauth/instagram/callback` | `https://<domain>/oauth/instagram/callback` | Must match the app config |
| `META_STORIES_ENABLED` | `true` | capability switch | Live story support remains pending V-03; the switch alone does not establish it |
| `TOKEN_ENCRYPTION_KEYS` 🔒 | empty | required if meta | `k1:<base64-32-bytes>[,k2:…]` |
| `TOKEN_ENCRYPTION_ACTIVE_KEY_ID` | empty | required if meta | |
| `TOKEN_REFRESH_DAYS_BEFORE_EXPIRY` | `20` | `20` | Positive refresh horizon in days; refresh jobs are implemented in Session 3 |
| `REPLY_DEBOUNCE_SECONDS` | `8` | `8` | |
| `SEND_RECONCILE_WINDOW_MINUTES` | `10` | `10` | |
| `CIRCUIT_FAILURE_THRESHOLD` / `CIRCUIT_WINDOW_MINUTES` / `CIRCUIT_COOLDOWN_MINUTES` | `5` / `10` / `10` | same | Circuit breaker (workflows.md §G.2): failures within the window open it; the cooldown is how long the account is left alone before it is probed |

## Content and media (Phase 5; S3 in Phase 7)

| Variable | dev | prod | Description |
|---|---|---|---|
| `MEDIA_STORAGE_BACKEND` | `local` | `s3` (required if meta) | `local` or `s3`. Production refuses `local` while `meta` is enabled. `s3` itself arrives in Phase 7 (selecting it earlier fails when the storage is first used) |
| `MEDIA_LOCAL_ROOT` | `./var/media` | — | Relative to `backend/` (git-ignored under `backend/var/`); an absolute path is used as is |
| `MEDIA_MAX_IMAGE_BYTES` | `8388608` | same | 8 MB. Larger uploads are refused with 413 `MEDIA_TOO_LARGE` |
| `MEDIA_PUBLIC_URL_TTL_SECONDS` | `3600` | `3600` | Presigned URL lifetime for Meta fetch; for `local`, the expiry in the `localmedia:` reference |
| `MEDIA_PUBLIC_BASE_URL` | empty | unused | Reserved for a future secured local-media tunnel contract; does not enable Meta with local storage |
| `S3_ENDPOINT_URL` | empty | optional | Empty selects AWS's default endpoint; set for R2, MinIO or another S3-compatible provider |
| `S3_REGION` | `auto` | non-empty if s3 | Use the bucket's actual AWS region for AWS; `auto` is suitable for R2 |
| `S3_BUCKET` | empty | required if s3 | Private bucket |
| `S3_ACCESS_KEY_ID` 🔒, `S3_SECRET_ACCESS_KEY` 🔒 | empty | required if s3 | |
| `SIM_CONTAINER_DELAY_SECONDS` | `2` | `2` | Mock container processing time: a container is `IN_PROGRESS` for this long after creation, then `FINISHED`. `0` finishes at once |
| `PUBLISH_DAILY_LIMIT` | `50` | `50` | Conservative (OQ-18). Posts per rolling 24 h: the mock reports it as the quota `limit` and refuses to publish beyond it (`ProviderRateLimited`) |

## Retention (Phase 6; final values Phase 8)

Global values, in whole days (at least 1); per-workspace values are deferred. The daily jobs `retention_cleanup` and `media_cleanup` apply them, with the injected clock ([security-and-privacy.md §8](../architecture/security-and-privacy.md)).

| Variable | Default | Rule |
|---|---|---|
| `RETENTION_WEBHOOK_PAYLOAD_DAYS` | `30` | `inbound_events.payload` is nulled after this age (measured from `received_at`) |
| `RETENTION_INBOUND_EVENT_ROW_DAYS` | `90` | the `inbound_events` row is deleted after this age |
| `RETENTION_AGENT_INPUT_DAYS` | `30` | `agent_runs.input_snapshot` is nulled (runs that are still `queued` or `running` keep it) |
| `RETENTION_MESSAGE_TEXT_DAYS` | `365` | `messages.text` (age = `provider_timestamp`) and `reply_drafts.text/template/suggestion_text` (age = `created_at`) are nulled; the rows and their metadata stay |
| `RETENTION_CUSTOMER_MEMORY_DAYS` | `365` | Customer memory expiry sweep; invalidates source-derived history/summaries/cached proposals and fences old writes while preserving content-free tombstones |
| `RETENTION_NOTIFICATIONS_READ_DAYS` | `90` | a notification is deleted this long after it was read; an unread one is never deleted |
| `RETENTION_JOBS_SUCCEEDED_DAYS` | `7` | `succeeded` and `cancelled` jobs are deleted (age = `finished_at`) |
| `RETENTION_JOBS_DEAD_DAYS` | `90` | `dead` jobs are deleted |
| `RETENTION_MEDIA_ORPHAN_DAYS` | `7` | a media asset that no content item references is deleted after this age |
| `RETENTION_PUBLISHED_MEDIA_DAYS` | `90` | a media asset used only by items published longer ago than this is deleted |

There is **no audit setting**: audit rows are never deleted in Phase 6 (plan H17; the two-year purge needs an ADR with the Phase 8 database privileges). The earlier draft variable `RETENTION_AUDIT_DAYS` was therefore not introduced.

## Owner channels, proxy boundary, backups, and ops (Phases 8–9)

| Variable | dev | prod | Description |
|---|---|---|---|
| `TRUSTED_PROXY_CIDRS` | `127.0.0.1/32,::1/128` | internal proxy CIDR(s) | Comma-separated IPs/CIDRs permitted to supply `X-Forwarded-For` (`ADR-025` §2.1). Invalid CIDRs fail startup |
| `BACKUP_ENCRYPTION_KEY` 🔒 | empty | required for backups | AES-256-GCM key ring (`b1:<base64-32-bytes>[,b2:…]`) for encrypting `pg_dump -Fc` archives (`P8-02`). Store off-host alongside `TOKEN_ENCRYPTION_KEYS` |
| `BACKUP_ENCRYPTION_ACTIVE_KEY_ID` | `b1` | `b1` | Active key ID in `BACKUP_ENCRYPTION_KEY` used when encrypting new backups |
| `BACKUP_S3_BUCKET` | empty | required for off-site backups | S3-compatible bucket for encrypted nightly backups (`P8-02`) |
| `BACKUP_S3_ENDPOINT_URL` | empty | optional | S3 endpoint URL for off-site backup bucket (falls back to `S3_ENDPOINT_URL` if unset) |
| `BACKUP_S3_REGION` | `auto` | bucket region | Region for `BACKUP_S3_BUCKET` |
| `BACKUP_S3_PREFIX` | `backups/postgres` | `backups/postgres` | Object key prefix inside `BACKUP_S3_BUCKET` |
| `BACKUP_S3_ACCESS_KEY_ID` 🔒, `BACKUP_S3_SECRET_ACCESS_KEY` 🔒 | empty | recommended least-privilege 🔒 | Dedicated backup bucket credentials scoped to `BACKUP_S3_BUCKET`/`BACKUP_S3_PREFIX` |
| `BACKUP_LOCAL_DIR` | empty | optional | Local directory target for offline backup/restore drills or local staging copies |
| `BACKUP_RETENTION_DAYS` | `35` | `35` | Canonical 35-day backup retention window (`security-and-privacy.md` §9); expired archives are pruned after verified upload |
| `BACKUP_STATUS_FILE` | `.backup-status.json` | `.backup-status.json` | Durable heartbeat status file read by `system_health.backup_health()` (`> 26h` staleness threshold per `ADR-025` §4.3) |
| `SMTP_URL` 🔒 | empty | required for email | SMTP connection URL (Phase 8, `OQ-16`). Requires `MAIL_FROM` when set |
| `MAIL_FROM` | empty | required when `SMTP_URL` is set | Sender address for transactional emails |
| `SENTRY_DSN` 🔒 | empty | optional | Optional Sentry-compatible DSN (Phase 8, `P8-07`) |
| `OPERATOR_ALERT_EMAIL` | empty | recommended | Operator alert destination (Phase 8, `P8-07`) |
| `TELEGRAM_BOT_TOKEN` 🔒 | empty | required if Telegram | Phase 9 |
| `TELEGRAM_WEBHOOK_SECRET` 🔒 | empty | required if Telegram webhook | Phase 9 |

## Production Compose and Caddy packaging parameters (`compose.prod.yml` / `Caddyfile`, Phase 8)

These host-level Compose/Caddy variables parameterize `compose.prod.yml` and `Caddyfile` so production, optional staging (`P8-12`), and local container rehearsals use the exact same files without forking:

| Variable | Default | Description |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | `agentnest` | Docker Compose stack/volume/network prefix (`agentnest-prod`, `agentnest-staging`, etc.) |
| `ENV_FILE` | `.env` | Path to the environment file loaded by `api`, `worker`, and `migrate` |
| `APP_DOMAIN` | `:80` | Site address in `Caddyfile` (`app.example.com` for production ACME HTTPS, `staging.example.com` for staging, `:80` for local HTTP rehearsal) |
| `CADDY_TLS_CONFIG` | empty | Optional Caddy TLS directive (`tls internal` for local self-signed HTTPS, `tls ops@example.com` for explicit ACME contact, or empty for automatic HTTPS) |
| `API_UPSTREAM` | `api:8000` | Upstream FastAPI address proxied by Caddy |
| `IMAGE_TAG` | `latest` | Container image tag for `AGENTNEST_BACKEND_IMAGE` and `AGENTNEST_CADDY_IMAGE` |
| `WEB_CONCURRENCY` | `2` | Uvicorn worker process count in the `api` container |
| `HTTP_PORT` / `HTTPS_PORT` | `80` / `443` | Host ports published by `caddy` |
| `DOCKER_LOG_MAX_SIZE` / `DOCKER_LOG_MAX_FILE` | `10m` / `5` | Bounded `json-file` container log rotation limits |

### Server `.env` ownership and secret handling (`ADR-017`, `INV-10`)

- On production and staging hosts, `.env` (and `.env.staging` if used) must be owned by the non-root deploy user with `0600` permissions (`chown deploy:deploy /opt/agentnest/.env && chmod 600 /opt/agentnest/.env`).
- `.dockerignore` excludes `.env`, `.env.*`, key/certificate files, `.git`, `.venv`, `node_modules`, and `var/` from the Docker build context so secrets never enter image layers or build history.
- The frontend build stage receives only `VITE_API_BASE_URL` (empty for same-origin production); no secret is ever passed to `VITE_*` variables.

## Manual Meta diagnostics (private process environment)

Session 16 additionally defines optional `META_LIVE_COMMENT_MEDIA_ID`,
`META_LIVE_COMMENT_ID` (exact founder-owned test targets) and
`META_LIVE_COMMENT_EFFECT` (one explicit `reply`, `private_reply`, `hide`, `unhide`
or `delete`). These are harness inputs, not application settings or capability flags.
All new comment probes remain disabled pending R75 evidence, even when inputs exist.

Manual Phase 7 probes read process environment variables directly, not application configuration: `META_LIVE_ACCESS_TOKEN` (secret) and `META_LIVE_IG_USER_ID` are both required. `META_LIVE_RECIPIENT_ID` separately opts into a real DM; `META_LIVE_IMAGE_URL` (potentially a secret presigned URL) separately opts into a real feed post. All are empty by default in `.env.example`. Ordinary pytest/CI must explicitly blank the two required variables. These diagnostics do not enable any product workflow or replace OAuth/ledger acceptance. For a future local HTTPS tunnel, Vite's process-only `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` must contain the exact assigned frontend tunnel hostname; see [local-development.md §12](local-development.md#12-real-instagram-development-phase-7-optional).
## Frontend (build time)

| Variable | dev | prod | Description |
|---|---|---|---|
| `VITE_API_BASE_URL` | empty (uses the Vite proxy) | empty (same origin) | Never put secrets in `VITE_*` variables |
| `VITE_ENABLE_SW` | unset | not needed | `true` registers the push-only service worker (`/sw.js`) on a dev server. Production builds always register it. It has no fetch handler and no cache. |

## Landing page (`landing/`, build time)

| Variable | dev | prod | Description |
|---|---|---|---|
| `VITE_WAITLIST_ENDPOINT` | empty (preview mode) | required to collect signups | URL that accepts a JSON `POST` of `{ business, category, instagram, contact, city, lang }`. When empty, the form says nothing was sent. The destination is not chosen yet. |
| `VITE_WAITLIST_WHATSAPP` | empty (link hidden) | optional | The founders' contact number (digits) or a full `https://` link for the form's "message us on WhatsApp" fallback. A contact path only, not a product channel. |
| `LANDING_CONNECT_SRC` | empty (same origin only) | when `VITE_WAITLIST_ENDPOINT` is on another origin | Runtime variable of the landing container (`landing/Caddyfile`): extra origin allowed in the page's CSP `connect-src`, e.g. `https://forms.example.com`. |

**Phase 7 provider/storage checks (all environments):** enabling `meta` requires the Meta app ID/secret, an explicitly configured webhook verification token, OAuth redirect URI, a valid encryption key ring and S3. A supplied key ring is validated even when Meta is disabled. Selecting S3 requires bucket, region and explicit access/secret keys; endpoint is optional for AWS. `MEDIA_PUBLIC_BASE_URL` is reserved until secured public local-media serving exists and does not allow Meta with local storage. Mock/local defaults still require no external credentials. S3 presigned GET TTLs are restricted to 1 through 604800 seconds. Live verification and both phase gates remain pending.
