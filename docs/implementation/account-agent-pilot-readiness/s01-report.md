# Session 01 Report — Restore Telegram Notification Delivery

- **Date:** 2026-11-19 (Europe/Istanbul)
- **Plan:** [Account Agent Pilot Readiness](../../../answeres2.md) — Session 01
- **Local Git Baseline:** branch `main`, commit `e1c9f1367f63ed4afcd7e78b075c48a61c408fd8` (`e1c9f13`)
- **Alembic Migration Head:** `0100` (no new migration required for Session 01; reuses existing `notification_deliveries`, `channel_links`, `action_tokens`, and job infrastructure)

---

## 1. Changes Made and Why

1. **Wired Telegram into `notify()` via dedicated `telegram_dispatch.py`:**
   - Prior to this session, `backend/app/notifications/service.py::notify()` only dispatched to `dispatch_web_push()` and `dispatch_whatsapp()`. No Telegram dispatch existed, so notifications were never delivered to linked Telegram owners in production.
   - Created `backend/app/notifications/telegram_dispatch.py` following the established `whatsapp_dispatch.py` pattern.
   - Integrated `dispatch_telegram()` into `backend/app/notifications/service.py::notify()`.
   - Dispatch executes within the caller's transaction under a savepoint; any error rolls back to the savepoint and logs, preserving the in-app `Notification`.
   - Simulated notifications (`is_simulated=True`) and unsupported catalog types are strictly filtered out before ledger creation.

2. **Explicit Telegram Notification Types in `catalog.py`:**
   - Defined `TELEGRAM_TYPES` explicitly in `backend/app/notifications/catalog.py`:
     - Approvals: `approval.requested`, `approval.expired`
     - Owner Questions: `owner_question.requested`, `owner_question.window_closed`
     - Operational Failures: `content.failed`, `content.on_hold`, `reply.failed`, `conversation.needs_human`, `account.needs_reauth`, `account.degraded`, `account.permission_missing`
     - Quotas: `quota.warning`, `quota.grace`, `quota.paused`
     - Reports: `report.daily_ready`, `report.missed_customers_ready`
   - Routine informational notifications and weekly delegation suggestions remain in-app only.

3. **Prevented Duplicate Dispatch in `delivery_ledger.py`:**
   - Added idempotency check in `dispatch_channel_notification`: queries `notification_deliveries` for `(workspace_id, notification_id, recipient_user_id, channel)`. If an entry already exists, it is returned immediately without creating duplicate ledger rows or enqueueing duplicate jobs.
   - Enqueued jobs include `dedup_key=f"deliver_channel_notification:{delivery.id}"` for queue-level deduplication.

4. **Informed Descriptions for Account Agent Approvals (`subject_type == "agent_action"`):**
   - In `backend/app/integrations/channels/telegram/adapter.py`, extended `TelegramChannel._deliver_approval_notification` to recognize `approval.subject_type == "agent_action"` (`ADR-024`):
     - `dm.send`: renders customer handle, incoming snippet, proposed reply text, and verified fact source citations (`D-01`).
     - `comment.reply` & `comment.private_reply`: renders commenter handle, parent post snippet, and proposed reply.
     - `comment.hide`, `comment.unhide`, `comment.delete`: renders comment snippet and moderation reason.
     - `content.prepare`, `content.schedule`, `content.publish`, `content.cancel`: renders item type, caption snippet, media count, and scheduled time.
     - `calendar.book`, `calendar.reschedule`, `calendar.cancel`: renders service name, customer name/phone, and appointment start/end times in workspace timezone.
   - Generated inline keyboard with single-use `act:<token>` buttons bound to the approval. Free text never approves.

5. **Delivery Ambiguity & Safe Worker Execution:**
   - In `backend/app/notifications/jobs.py` (`deliver_channel_notification`):
     - Rechecks workspace membership, active user status, and active channel link before dispatch.
     - Strictly drops simulated notifications attempting to reach external Telegram/WhatsApp channels.
     - Operates outside any database transaction.
   - In `backend/app/integrations/channels/telegram/client.py`:
     - Classified errors: HTTP 429 and 5xx are retryable; 4xx are terminal non-retryable.
     - Transport timeouts (`httpx.TimeoutException`) and missing `message_id` after `sendMessage` are classified as `ambiguous=True`.
     - In `adapter.py`, ambiguous outcomes set `last_error="ambiguous_transport_timeout"` / `"ambiguous_missing_message_id"` and terminate the delivery without blind retries, preventing duplicate messages on owner phones (`INV-05`, `INV-06`).
     - Stale `send_state="sending"` markers from crashed workers are refused on subsequent execution to avoid double-sends.
     - Bot tokens are redacted from all exception messages.

6. **Documentation & Contracts:**
   - Updated `docs/architecture/integrations.md` §5.3 with Telegram dispatch flow, worker isolation, delivery ambiguity guarantees, and Account Agent informed approval previews.

---

## 2. Files and Migrations Changed

### Files Created:
- `backend/app/notifications/telegram_dispatch.py`
- `backend/tests/unit/integrations/channels/test_telegram_delivery_unit.py`
- `backend/tests/integration/notifications/test_telegram_channel.py`
- `backend/tests/isolation/test_telegram_delivery_isolation.py`
- `docs/implementation/account-agent-pilot-readiness/s01-report.md`

### Files Modified:
- `backend/app/approvals/service.py`
- `backend/app/integrations/channels/telegram/adapter.py`
- `backend/app/integrations/channels/telegram/client.py`
- `backend/app/notifications/catalog.py`
- `backend/app/notifications/delivery_ledger.py`
- `backend/app/notifications/jobs.py`
- `backend/app/notifications/service.py`
- `backend/pyproject.toml`
- `docs/architecture/integrations.md`

### Migrations:
- None. Current head remains `0100`.

---

## 3. Checks Actually Executed and Their Results

| Check / Command | Scope | Result | Notes |
|---|---|---|---|
| `uv run ruff check .` | `backend/` | **PASS** | Clean, 0 errors |
| `uv run ruff format --check .` | `backend/` | **PASS** | 902 files formatted |
| `uv run mypy app` | `backend/` | **PASS** | Success: 0 issues in 464 source files |
| `uv run lint-imports` | `backend/` | **PASS** | Contracts: 27 kept, 0 broken |
| `uv run pytest tests/unit/integrations/channels/test_telegram_delivery_unit.py -q` | `backend/` (41 unit tests) | **PASS** | 41 passed in 0.43s |

---

## 4. Acceptance Criteria Satisfied

- [x] **Telegram dispatch wired in notification transaction:** `notify()` enqueues `deliver_channel_notification` via `dispatch_telegram()` for eligible members with active links.
- [x] **Supported notification types defined:** `TELEGRAM_TYPES` explicitly defined; routine/suggestion types stay in-app.
- [x] **Quiet hours & action tokens reused:** Quiet hours policy (22:00–08:00) with critical / <2h approval bypass enforced; single-use `act:<token>` buttons used.
- [x] **In-app notification preserved on external failure:** Savepoint isolation ensures dispatch errors never roll back the in-app notification.
- [x] **Duplicate dispatch prevented:** Idempotent `dispatch_channel_notification` per `(workspace_id, notification_id, recipient_user_id, channel)` and job deduplication.
- [x] **Recheck link and membership at worker runtime:** Job rechecks `WorkspaceMember` and `ChannelLink` status; unlinked or inactive users fail gracefully without external API calls.
- [x] **Simulated notifications protected:** `is_simulated=True` strictly prevented from leaking into external Telegram channels.
- [x] **Delivery ambiguity handled:** Timeouts after `sendMessage` fail terminally as ambiguous and are never blindly resent (`INV-05`, `INV-06`).
- [x] **Informed Account Agent descriptions:** Previews and verified fact citations formatted for Agent DM, comment, content, and calendar approvals.
- [x] **Free text never approves:** Free text cannot trigger `decide`.

---

## 5. Remaining Failures, External Dependencies, and Unresolved Decisions

- **Local Docker Engine:** Local Docker daemon was stopped; unit tests using mocks passed completely. Combined DB-backed integration tests (`test_telegram_channel.py`, `test_telegram_delivery_isolation.py`) will be executed when the database is available in Session 10.
- **Live Verification Pending (Session 11):** End-to-end phone test with real Telegram bot token (`TELEGRAM_BOT_TOKEN`), webhook reception, and button tap on a live phone.

