# Environment Variables

**Purpose:** Every configuration variable, its default per environment, whether it is secret, and the phase that introduces it. `.env.example` must mirror this table (non-secret defaults filled in; secrets left empty, or a clearly fake development value). Rules: [ADR-017](../architecture/decisions/ADR-017-configuration-and-secrets.md).

Legend: **dev** = development default, **prod** = production requirement. 🔒 = secret (never commit, never log, never send to the frontend).

## Core (Phase 1)

| Variable | dev | prod | Description |
|---|---|---|---|
| `APP_ENV` | `development` | `production` | `development` \| `test` \| `production` |
| `DATABASE_URL` | `postgresql+psycopg://agentnest:agentnest@localhost:5433/agentnest` | required 🔒 | Main DB |
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
| `LLM_REASONING_EFFORT` | `low` | `low` | `` (off) \| `minimal` \| `low` \| `medium` \| `high`. Reasoning tokens count against each task's `max_output_tokens` |
| `LLM_PRICE_TABLE` | empty | optional JSON | `{"<model>": {"input_per_mtok": 0.0, "output_per_mtok": 0.0}}` (USD). Cost estimates in evals and system health; unpriced models have no estimate |

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

## Owner channels and ops (Phases 8–9)

| Variable | dev | prod | Description |
|---|---|---|---|
| `SMTP_URL` 🔒 | empty | required for email | Phase 8 |
| `MAIL_FROM` | empty | required for email | |
| `SENTRY_DSN` 🔒 | empty | optional | Phase 8 |
| `OPERATOR_ALERT_EMAIL` | empty | recommended | Phase 8 |
| `TELEGRAM_BOT_TOKEN` 🔒 | empty | required if Telegram | Phase 9 |
| `TELEGRAM_WEBHOOK_SECRET` 🔒 | empty | required if Telegram webhook | Phase 9 |

## Manual Meta diagnostics (private process environment)

Manual Phase 7 probes read process environment variables directly, not application configuration: `META_LIVE_ACCESS_TOKEN` (secret) and `META_LIVE_IG_USER_ID` are both required. `META_LIVE_RECIPIENT_ID` separately opts into a real DM; `META_LIVE_IMAGE_URL` (potentially a secret presigned URL) separately opts into a real feed post. All are empty by default in `.env.example`. Ordinary pytest/CI must explicitly blank the two required variables. These diagnostics do not enable any product workflow or replace OAuth/ledger acceptance. For a future local HTTPS tunnel, Vite's process-only `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` must contain the exact assigned frontend tunnel hostname; see [local-development.md §12](local-development.md#12-real-instagram-development-phase-7-optional).
## Frontend (build time)

| Variable | dev | prod | Description |
|---|---|---|---|
| `VITE_API_BASE_URL` | empty (uses the Vite proxy) | empty (same origin) | Never put secrets in `VITE_*` variables |

## Landing page (`landing/`, build time)

| Variable | dev | prod | Description |
|---|---|---|---|
| `VITE_WAITLIST_ENDPOINT` | empty (preview mode) | required to collect signups | URL that accepts a JSON `POST` of `{ business, instagram, contact, city, lang }`. When empty, the form says nothing was sent. The destination is not chosen yet. |

**Phase 7 provider/storage checks (all environments):** enabling `meta` requires the Meta app ID/secret, an explicitly configured webhook verification token, OAuth redirect URI, a valid encryption key ring and S3. A supplied key ring is validated even when Meta is disabled. Selecting S3 requires bucket, region and explicit access/secret keys; endpoint is optional for AWS. `MEDIA_PUBLIC_BASE_URL` is reserved until secured public local-media serving exists and does not allow Meta with local storage. Mock/local defaults still require no external credentials. S3 presigned GET TTLs are restricted to 1 through 604800 seconds. Live verification and both phase gates remain pending.
