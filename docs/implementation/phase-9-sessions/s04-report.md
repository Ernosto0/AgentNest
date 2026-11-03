# Phase 9 — Session 04 Report: Telegram Adapter, Webhook & Long-Polling Harness

- **Session:** `S04` (`docs/implementation/phase-9-sessions/phase-09-sessions.md` §Session 04, `docs/implementation/phases/phase-09-owner-channel.md` `P9-01`)
- **Date:** 2026-11-04
- **Status:** `complete` (Telegram client, data models, OwnerChannel adapter, ingress pipeline/dispatcher, Alembic migration 0040, webhook HTTP endpoint with secret token validation, CLI long-polling runner, and 100% offline contract/unit tests verified green)
- **Branch / Commit Baseline:** `main` at `bf8ffda` + Sessions 01, 02, and 03 foundation
- **Alembic Migration Head:** `20261104_0040_telegram_updates.py` (revision `0040`, 68 database tables total)

---

## 1. Summary of Implemented Artifacts & Contracts

| Artifact / File | Status | Implementation Summary |
|---|---|---|
| `backend/app/integrations/channels/telegram/models.py` | **Created** | Created `TelegramUpdate` global database model tracking `update_id` (BigInteger PK), `received_at` (timestamptz), `status` ('processed', 'ignored', 'failed'), `channel_user_id`, and `error`. Deduplication occurs at ingress before tenant context resolution (INV-06). |
| `backend/migrations/versions/20261104_0040_telegram_updates.py` | **Created** | Alembic revision 0040: creates `telegram_updates` global table, primary key on `update_id`, status check constraint, indexes on `received_at` and `channel_user_id`; grants permissions to `agentnest_app` and `agentnest_worker`. Verified bidirectional upgrade and rollback. |
| `backend/app/integrations/channels/telegram/webhook_format.py` | **Created** | Implemented Pydantic models with `ConfigDict(populate_by_name=True, extra="ignore")` for Telegram Bot API objects: `TelegramUser`, `TelegramChat`, `PhotoSize`, `TelegramMessage`, `CallbackQuery`, and `Update` (with friendly aliases `User`, `Chat`, `Message`). |
| `backend/app/integrations/channels/telegram/client.py` | **Created** | Created `TelegramClient` (sync) and `AsyncTelegramClient` (async) HTTP client wrappers for the Telegram Bot API (`sendMessage`, `sendPhoto`, `answerCallbackQuery`, `editMessageText`, `editMessageReplyMarkup`, `getFile`, `downloadFile`, `getUpdates`). Configured with 15s timeout, no automatic retry on 4xx, structured `TelegramApiError` mapping, and `httpx.BaseTransport` test injection. |
| `backend/app/integrations/channels/telegram/adapter.py` | **Created** | Implemented `TelegramChannel` conforming to `OwnerChannel` Protocol (ADR-012 §5.1): implements `deliver_notification` (retrieving notification, formatting HTML message with severity indicators, sending via bot API, returning `DeliveryResult`) and `render_command_result`. |
| `backend/app/integrations/channels/telegram/dispatcher.py` | **Created** | Implemented update ingestion pipeline: deduplication against `telegram_updates`, command routing (`/start`, `/link <code>` via `ChannelLinkService.redeem_link_code`, `/unlink` via `ChannelLinkService.unlink_by_channel`, `/status` reporting workspace and active notification count), unlinked user prompt, and extensible `on_linked_message` hook for Session 05 natural language dispatch. |
| `backend/app/integrations/channels/telegram/__init__.py` | **Created** | Exported `TelegramChannel`, `TelegramClient`, `TelegramApiError`, `TelegramUpdate`, `Update`, `process_update`, etc. Allows lazy resolution in `app/integrations/channels/registry.py`. |
| `backend/app/integrations/channels/registry.py` | **Updated** | Enabled live resolution of `"telegram"` channel via `TelegramChannel`. |
| `backend/app/api/v1/telegram_webhook_router.py` | **Created** | Implemented webhook endpoints `POST /webhooks/telegram` and `POST /api/v1/webhooks/telegram`: validates `X-Telegram-Bot-Api-Secret-Token == settings.telegram_webhook_secret` using constant-time comparison (returns 401 if invalid or missing), rejects duplicate `update_id` with 200 `{"status": "duplicate"}`, and dispatches updates. |
| `backend/app/api/deps.py` | **Updated** | Added `/api/v1/webhooks/telegram` to `CSRF_EXEMPT_PATHS`. |
| `backend/app/main.py` | **Updated** | Mounted `telegram_webhook_router` on application root. |
| `backend/app/cli.py` | **Updated** | Implemented `telegram-poll` CLI command and `run_telegram_polling` runner: long-polling loop with `offset` tracking, batching, max iterations, and graceful shutdown. |
| `backend/pyproject.toml` | **Updated** | Added `app.integrations.channels.telegram` submodules to architectural import linter contract. |
| `backend/tests/contract/test_telegram_adapter.py` | **Created** | Full contract test suite covering secret token validation, duplicate `update_id` rejection, `/start`, `/link <code>`, `/unlink`, `/status` flows with mock transport, `deliver_notification` execution, and CLI long-polling runner execution. |

---

## 2. Verification Outcomes

### 2.1 Static Analysis & Quality

| Check | Command | Exit Code | Result Summary |
|---|---|---|---|
| Backend Lint | `uv run --directory backend ruff check .` | `0` | All checks passed cleanly across 610 files |
| Backend Formatting | `uv run --directory backend ruff format --check .` | `0` | 610 files verified formatted |
| Backend Typecheck | `uv run --directory backend mypy app` | `0` | Success: no issues found in 318 source files |
| Import Architecture | `uv run --directory backend lint-imports` | `0` | 19 contracts kept, 0 broken |
| Frontend Typecheck | `npm.cmd --prefix frontend run typecheck` | `0` | `tsc -b --noEmit` passed cleanly |

### 2.2 Database Migration & Schema Reversibility

| Check | Command | Exit Code | Result Summary |
|---|---|---|---|
| Migration Upgrade | `uv run --directory backend alembic upgrade head` | `0` | Clean upgrade to `0040 (head)` |
| Migration Downgrade | `uv run --directory backend alembic downgrade -1` | `0` | Clean rollback to `0039` |
| Migration Re-upgrade | `uv run --directory backend alembic upgrade head` | `0` | Clean upgrade back to `0040 (head)` |

### 2.3 Test Suite Execution

| Test Suite | Command | Exit Code | Result Summary |
|---|---|---|---|
| Telegram Adapter Contract Suite | `uv run --directory backend pytest tests/contract/test_telegram_adapter.py -v` | `0` | `11 passed in 7.45s` |
| Delivery Policy Unit Suite | `uv run --directory backend pytest tests/unit/notifications/test_delivery_policy.py -v` | `0` | `11 passed in 2.12s` |
| Channel Links Unit & Integration Suites | `uv run --directory backend pytest tests/unit/identity/test_channel_links.py tests/integration/identity/test_channel_links_api.py -v` | `0` | `16 passed in 3.41s` |
| Combined Regression Suite | `uv run --directory backend pytest tests/contract/test_telegram_adapter.py tests/unit/notifications/test_delivery_policy.py tests/unit/identity/test_channel_links.py tests/integration/identity/test_channel_links_api.py -v` | `0` | `38 passed in 9.64s` |

---

## 3. Invariant & Security Compliance

- **INV-01 / Global Table Boundary:** `telegram_updates` is an explicit global table (without `workspace_id` or RLS) because deduplication happens at ingress before tenant identity resolution.
- **INV-03 (Command System Boundary):** Telegram adapter and dispatcher components do not import `app.commands`, preserving import-linter contract 19/19 intact.
- **INV-06 (Idempotent Delivery & Deduplication):** Both the webhook endpoint and long-polling runner check incoming `update_id` against `telegram_updates`. Replay of the same `update_id` immediately exits with 200 `{"status": "duplicate"}` and causes no duplicate downstream actions.
- **INV-12 (Least Privilege Database Roles):** Table permissions on `telegram_updates` were granted explicitly to `agentnest_app` and `agentnest_worker`.
- **Secret Token Validation:** The webhook router checks `X-Telegram-Bot-Api-Secret-Token` using `hmac.compare_digest` against `settings.telegram_webhook_secret`. Missing or mismatched headers return 401 without executing any database transactions or dispatcher logic.

---

## 4. Next-Session Handoff (Session 05)

- Database schema head is `20261104_0040_telegram_updates.py`.
- `TelegramChannel` is registered in `app/integrations/channels/registry.py` under the name `"telegram"`.
- The webhook endpoint is available at `POST /webhooks/telegram` and `POST /api/v1/webhooks/telegram`.
- The long-polling developer harness is runnable via `python -m app.cli telegram-poll`.
- `dispatcher.py` provides the `on_linked_message` hook ready to be plugged into:
  - Session 05: Command dispatch, photo ingestion (`MediaService.ingest`), owner task execution, and approval callback queries.
