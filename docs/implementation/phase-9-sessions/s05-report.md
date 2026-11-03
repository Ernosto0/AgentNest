# Phase 9 — Session 05 Report: Command Dispatch, Photo Ingestion & Owner Tasks

- **Session:** `S05` (`docs/implementation/phase-9-sessions/phase-09-sessions.md` §Session 05, `docs/implementation/phases/phase-09-owner-channel.md` `P9-02`, `P9-03`)
- **Date:** 2026-11-04
- **Status:** `complete` (Natural language text routing, daily summary reporting query with exact matching counts, photo ingestion with 20 MB rejection and audit log, story draft creation with approval required, owner task routing to active account agents, free-text command submission, and 100% test coverage)
- **Branch / Commit Baseline:** `main` at `bf8ffda` + Sessions 01, 02, 03, and 04 foundation
- **Alembic Migration Head:** `20261104_0040_telegram_updates.py` (revision `0040`, 68 database tables total)

---

## 1. Summary of Implemented Artifacts & Contracts

| Artifact / File | Status | Implementation Summary |
|---|---|---|
| `backend/app/integrations/channels/telegram/handlers.py` | **Created** | Dedicated router and handler package for linked Telegram messages: context resolution (`workspace_context`), reporting queries (`is_reporting_query`), photo ingestion (`_handle_photo`), owner tasks routing (`_handle_agent_task`), and general command submission (`_handle_general_command`). |
| `backend/app/integrations/channels/telegram/dispatcher.py` | **Updated** | Wired `handle_linked_message` as the default handler for linked incoming messages when custom hooks are omitted, returning descriptive action names (`reporting_query`, `photo_draft_created`, `photo_cached`, `photo_rejected_size`, `agent_task`, `owner_command`). |
| `backend/app/reporting/service.py` | **Updated** | Added `get_daily_summary(session, clock, ctx)` helper aggregating today's live daily report metrics (`inbound_messages`, `conversations`, `new_conversations`, `pending_approvals`, `replies_sent`) directly from SQL aggregations without LLM estimation (INV-08, AC-2). |
| `backend/app/agent/owner_tasks.py` | **Updated** | Added `source_channel: str = "api"` parameter to `owner_tasks.submit` enabling source channel attribution to `'telegram'` while preserving check constraints and API backwards compatibility. |
| `backend/app/integrations/channels/registry.py` | **Updated** | Narrowed Telegram channel resolution to `app.integrations.channels.telegram.adapter.TelegramChannel` to prevent circular imports into notifications and approvals domains. |
| `backend/pyproject.toml` | **Updated** | Registered `app.integrations.channels.telegram.handlers` under architecture contracts; permitted targeted service imports from Telegram handlers to `CommandService` and `reporting` under strict import linter contracts. |
| `backend/tests/unit/integrations/channels/test_telegram_commands_media.py` | **Created** | Comprehensive unit and workflow test suite with 7 dedicated test cases verifying reporting counts (AC-2), photo ingestion, 20 MB size rejection and audit logging (INV-11), story draft creation requiring approval (AC-3, INV-04), owner-task routing to `AccountAgent` (ADR-024), and policy enforcement preventing free-text direct publish (INV-04). |

---

## 2. Key Workflow Details

### 2.1 Natural Language Reporting Queries (AC-2)
- Queries matching daily summary phrases (e.g. *"Bugün kaç DM geldi?"*, *"Bugünkü özet"*, *"How many DMs today?"*) are parsed via regex.
- Metrics are queried live from `app.reporting.service.get_daily_summary` (which executes deterministic SQL aggregations via `compute_metrics` over `messages` within the workspace's local day bounds).
- Responses format identical numbers to the web dashboard (`inbound_messages`, `new_conversations`, `conversations`, `pending_approvals`), rendered in HTML in the user's preferred language (TR/EN).

### 2.2 Inbound Photo Ingestion & Size Limits (AC-3, INV-11)
- The highest resolution `PhotoSize` from `message.photo` is extracted.
- Before downloading or processing, `photo.file_size` and Telegram `getFile` metadata are validated against the 20 MB limit (`20 * 1024 * 1024` bytes).
- Oversized uploads (> 20 MB) are rejected immediately without storing files or assets, and recorded in `audit_logs` under `action="media.rejected"` with `reason="too_large"` (INV-11).
- Valid JPEG/PNG images are ingested via `app.content.media.ingest` and stored in configured `MediaStorage`.
- **Photo with caption** (e.g. *"bu story'yi 19:00'da paylaş"*):
  - Detects content type (`story_image` vs `feed_image`) and proposed time (`19:00` in workspace timezone).
  - Creates a draft content item using `app.content.service.create_draft` with the attached `media_asset_id`.
  - Submits a schedule proposal with `self_approve=False`, requiring explicit human approval (never auto-scheduled or published directly from free text, INV-04, AC-3).
- **Photo without caption**:
  - Caches the ingested `media_asset_id` in temporary memory (`_PENDING_MEDIA`) with a 15-minute TTL, and prompts the user in Telegram on how they wish to use the uploaded photo.

### 2.3 Account Agent Task Routing (ADR-024)
- Checks whether the workspace has an active `AccountAgent` where `controller_mode == "agent"` and `state == "active"`.
- If an active agent exists and the user's text contains agent task cues (e.g. *"Ahmet Bey'e randevu için dönüş yap"*), the instruction is routed directly to `app.agent.owner_tasks.submit(...)` with `source_channel="telegram"`.
- Creates an `OwnerTask` row and wakes the agent thread while returning a confirmation message to Telegram.

### 2.4 General Commands & Safety Bounds (INV-04)
- Non-reporting, non-agent messages submit to `CommandService.submit(session, clock, ctx, text=text, client_request_id=f"tg:{update_id}", channel="telegram")`.
- Clarifications, confirmations, and execution outcomes render formatted HTML to Telegram.
- Free-text commands can never bypass approval policies or directly publish content (INV-04).

---

## 3. Verification Outcomes

### 3.1 Static Analysis & Quality
| Check | Command | Exit Code | Result Summary |
|---|---|---|---|
| Backend Lint | `uv run --directory backend ruff check .` | `0` | All checks passed cleanly across 612 files |
| Backend Formatting | `uv run --directory backend ruff format --check .` | `0` | 612 files verified formatted |
| Backend Typecheck | `uv run --directory backend mypy app` | `0` | Success: no issues found in 319 source files |
| Import Architecture | `uv run --directory backend lint-imports` | `0` | 19 contracts kept, 0 broken |

### 3.2 Test Suite Execution
| Test Suite | Command | Exit Code | Result Summary |
|---|---|---|---|
| Telegram Commands & Media Unit Suite | `uv run --directory backend pytest tests/unit/integrations/channels/test_telegram_commands_media.py -v` | `0` | `7 passed in 9.30s` |
| Prior Contract & Unit Suites | `uv run --directory backend pytest tests/contract/test_telegram_adapter.py tests/unit/notifications/test_delivery_policy.py tests/unit/identity/test_channel_links.py tests/integration/identity/test_channel_links_api.py -v` | `0` | `38 passed in 9.45s` |
| Combined Regression Suite | `uv run --directory backend pytest tests/unit/integrations/channels/test_telegram_commands_media.py tests/contract/test_telegram_adapter.py tests/unit/notifications/test_delivery_policy.py tests/unit/identity/test_channel_links.py tests/integration/identity/test_channel_links_api.py -v` | `0` | `45 passed in 12.25s` |

---

## 4. Invariant & Security Compliance

- **INV-04 (No Direct Execution from Untrusted / Free Text):** Free-text messages and captions never directly publish content items or bypass approvals. A photo with caption creates a draft and an approval proposal (`self_approve=False`); status is never set to `"published"` from ingress.
- **INV-08 (Deterministic Reporting Calculations):** "Bugün kaç DM geldi?" queries use SQL aggregations via `reporting_service.get_daily_summary` identical to the web dashboard, without any language model estimation.
- **INV-11 (Media Size Limits & Audit Trail):** Telegram photos exceeding 20 MB are rejected immediately before storage download or asset creation, recording `media.rejected` with `reason="too_large"` in `audit_logs`.
- **ADR-012 & ADR-024 (Owner Channel & Delegated Autonomy):** Inbound owner messages correctly branch between reporting queries, active account agent owner tasks, and general owner commands.

---

## 5. Next-Session Handoff (Session 06)

- Session 06 can build upon `handlers.py`, `dispatcher.py`, and `client.py` for:
  - Database model and migration for `action_tokens` (`20261104_0041_action_tokens.py`).
  - Telegram inline approval buttons (`act:<token>`) for `approval.requested` notifications.
  - Webhook callback query consumption (`answerCallbackQuery`, `ApprovalService.decide`).
  - Owner questions intake and round-trip answering (`OwnerRequestService.submit_answer`).
