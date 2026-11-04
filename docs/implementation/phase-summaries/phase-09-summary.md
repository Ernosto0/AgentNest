# Phase 9 Close-Out Summary: Owner Messaging Channel (Telegram)

- **Phase:** Phase 9 — Owner Messaging Channel
- **Specification:** `docs/implementation/phases/phase-09-owner-channel.md` (Tasks P9-01 through P9-05; Acceptance Criteria 1–4)
- **Sessions Executed:** Sessions 01 through 08 (`docs/implementation/phase-9-sessions/`)
- **Baseline Git Commit:** `bf8ffda` -> Final Session 08 close-out
- **Alembic Migration Head:** `20261104_0041_action_tokens.py` (revision `0041`, 69 database tables total)
- **Status:** **Engineering & E2E Acceptance Complete; Optional Live Bot Harness Delivered**
- **Date:** 2026-11-04

---

## 1. Executive Summary

Phase 9 establishes the **Owner Messaging Channel** using the channel-agnostic core architecture specified in ADR-012. It connects business owners and managers directly to their AgentNest workspace via Telegram, enabling mobile receipt of critical notifications, replay-safe single-use approval decisions, daily business metrics queries, photo ingestion, and conversational task intake without requiring access to a desktop browser.

All engineering deliverables across all 8 sequential sessions are fully implemented and verified offline:
- **Zero core coupling (AC-4):** Architectural isolation verified by `lint-imports` (20 contracts kept, 0 broken) and AST scanning; no core module imports the Telegram adapter except the channel registry and webhook router.
- **Replay-safe approval decisions (AC-1, INV-06, INV-16):** 16-byte cryptographically secure random base64url action tokens stored SHA-256 hashed at rest; atomic consumption guarantees strictly 1 side-effect execution. Duplicate or replayed button presses return modal alerts (*"Already decided"*) and strip inline keyboards.
- **Unified business metrics (AC-2):** Natural-language questions (*"Bugün kaç DM geldi?"*, *"Bugünkü özet"*) route directly to domain reporting (`get_daily_summary`), returning exact counts identical to the web dashboard.
- **Safe media intake & drafting (AC-3, INV-04, INV-11):** Enforces a strict 20 MB upload ceiling evaluated prior to download; photos with captions (e.g., *"bu story'yi 19:00'da paylaş"*) create story draft items with schedule proposals that require explicit owner approval. Free text never auto-schedules or publishes.
- **Quiet hours policy:** Local timezone-aware suppression window (22:00 to 08:00 local time) suppresses non-critical summaries while allowing immediate bypass for critical system alerts, reauth warnings, and urgent approvals expiring within 2 hours.
- **100% passing regressions:** Backend (55 passed, 3 live skips, 0 failed; ruff, mypy, lint-imports green) and Frontend (597 tests passed across 45 suites; ESLint, TypeScript, Vitest, i18n:check, and Vite build green).

---

## 2. Canonical Acceptance Criteria Audit

Phase 9 defines four canonical acceptance criteria (`docs/implementation/phases/phase-09-owner-channel.md` §Acceptance criteria). Below is the comprehensive audit of each criterion against passing tests:

| # | Acceptance Criterion | Status | Verified Evidence & Passing Tests |
|---|---|---|---|
| **AC-1** | **A linked owner receives an `approval.requested` message for a reply draft with the exact text, approves with a button, and the reply is sent. A second press reports "already decided".** | **MET** | • `tests/e2e/test_owner_channel_acceptance.py::test_ac1_owner_approval_workflow_reply_draft_single_use_send`<br>• `tests/unit/approvals/test_telegram_action_tokens.py::test_telegram_approval_button_single_use_and_replay_protection`<br>• `tests/security/test_owner_channel_security.py::test_security_case_2_replayed_button_protection`<br>• Proves: exact proposed reply text delivered in Telegram message; inline keyboard contains `act:<token>` buttons; first press updates `Approval` to `approved`, transitions `ReplyDraft` to `queued`, and enqueues exactly 1 `send_reply` job; second press returns modal alert (*"Bu onay zaten karara bağlandı / Already decided"*), leaves exactly 1 job in queue, and executes zero duplicate side-effects. |
| **AC-2** | **"Bugün kaç DM geldi?" in Telegram returns the same number as the web report.** | **MET** | • `tests/e2e/test_owner_channel_acceptance.py::test_ac2_telegram_daily_summary_matches_web_report`<br>• `tests/unit/integrations/channels/test_telegram_commands_media.py::test_telegram_reporting_query_exact_matching_counts`<br>• Proves: seeds inbound messages for the current day; calls `get_daily_summary` domain service; asks bot *"Bugün kaç DM geldi?"*; bot parses question via `ReportingHandler` and returns formatted message with the exact matching integer count. |
| **AC-3** | **Sending a photo with "bu story'yi 19:00'da paylaş" creates a story draft with that media and a schedule proposal requiring explicit approval (never auto-scheduled from free text).** | **MET** | • `tests/e2e/test_owner_channel_acceptance.py::test_ac3_photo_with_schedule_caption_creates_story_draft_not_auto_scheduled`<br>• `tests/unit/integrations/channels/test_telegram_commands_media.py::test_telegram_photo_with_caption_creates_story_draft_approval_required`<br>• `tests/security/test_owner_channel_security.py::test_security_case_7_oversized_media_upload_rejected`<br>• Proves: photo ingested via `MediaService.ingest` and linked as `MediaAsset`; `ContentItem` created with `content_type='story_image'` and caption; item status is `draft` or `pending_approval` (never `published`); confirmation sent to owner highlights 19:00 schedule proposal and explicitly reminds that explicit approval is required before publishing (`INV-04`). |
| **AC-4** | **No core module imports the Telegram adapter except the channel registry.** | **MET** | • `tests/e2e/test_owner_channel_acceptance.py::test_ac4_core_architectural_isolation_import_linter`<br>• `pyproject.toml` contract `only channel registry and telegram webhook router import telegram channel adapter (AC-4)`<br>• Verified via `uv run lint-imports` (20 contracts kept, 0 broken).<br>• AST scanning confirms zero imports of `app.integrations.channels.telegram` across `app.commands`, `app.approvals`, `app.inbox`, `app.policy`, `app.identity`, `app.knowledge`, `app.core`, `app.audit`, `app.jobs`, `app.ai`, `app.notifications`, `app.operations`, `app.content`, `app.reporting`, `app.activity`, and `app.retention`. |

---

## 3. Database Schema Changes & Migrations

Phase 9 added four sequential migrations, expanding the schema from 64 to 69 tables:

| Revision | Migration File | Primary Tables Created / Altered | Invariants & Governance |
|---|---|---|---|
| `0038` | `20261104_0038_channel_links.py` | `channel_links`, `channel_link_codes` | Enforces `FORCE ROW LEVEL SECURITY`. Unique index on `(workspace_id, channel, channel_user_id)`. Linking codes expire after 10 minutes. Audit actions: `channel.linked`, `channel.unlinked`. |
| `0039` | `20261104_0039_notification_deliveries.py` | `notification_deliveries` | Enforces `FORCE ROW LEVEL SECURITY`. Multi-channel delivery ledger tracking delivery states (`pending`, `delivered`, `failed`, `skipped_quiet_hours`), retry counts, quiet hours bypass flags, and provider references. |
| `0040` | `20261104_0040_telegram_updates.py` | `telegram_updates` | System ledger on `update_id` (primary key) preventing duplicate webhook deliveries from triggering duplicate commands or actions (`INV-06`). |
| `0041` | `20261104_0041_action_tokens.py` | `action_tokens` | Enforces `FORCE ROW LEVEL SECURITY`. Cryptographic single-use replay-safe tokens stored as SHA-256 hashes (`token_hash`), bound to `(approval_id, decision, user_id, payload_hash)`. Atomic consumption prevents double-execution (`INV-16`). |

---

## 4. Implemented Architecture and Files

### 4.1 Backend Components
- **Identity & Channel Linking (`app/identity/channels.py`, `app/identity/models.py`):**
  One-time alphanumeric code generation, rate-limited redeem, mutual unlinking (web and chat), and user resolution by channel identity.
- **Channel Abstraction & Registry (`app/integrations/channels/`):**
  Formal `OwnerChannel` protocol, `ChannelRecipient`, `ChannelDeliveryResult`, and dynamic registration (`app.integrations.channels.registry`).
- **Notification Delivery Engine (`app/notifications/delivery.py`):**
  Orchestrates multi-channel delivery, applies per-user quiet hours policy (suppressing non-critical notifications between 22:00 and 08:00 local time while bypassing critical alerts).
- **Telegram Adapter (`app/integrations/channels/telegram/`):**
  - `client.py`: Synchronous and asynchronous Telegram Bot API HTTP client (`httpx`).
  - `adapter.py`: Concrete `TelegramChannel` implementation delivering notifications with rich HTML formatting and inline buttons.
  - `handlers.py`: Inbound update dispatcher handling `/start`, `/link`, `/unlink`, `/status`, reporting queries, owner tasks, and photo ingestion.
  - `runner.py`: CLI long-polling daemon (`python -m app.cli telegram-poll`) for local development without tunnels.
- **Action Tokens & Replay-Safe Decisions (`app/approvals/action_tokens.py`, `app/approvals/models.py`):**
  Generates 16-byte base64url tokens, computes SHA-256 hashes, atomically validates user identity, payload hash, and expiry, transitioning approvals safely.
- **API Webhook Router (`app/api/v1/webhooks.py`, `app/api/v1/channels.py`):**
  `POST /webhooks/telegram` validating `X-Telegram-Bot-Api-Secret-Token` header and handling callback queries.

### 4.2 Frontend Surfaces
- **Channels Settings Surface (`frontend/src/features/settings/OwnerChannelsSettings.tsx`):**
  Mounted under `Settings -> Channels / Connections`, displays linked Telegram accounts, status badges, and connect/disconnect controls.
- **Link Code Modal (`frontend/src/features/settings/ChannelLinkModal.tsx`):**
  Generates 8-character link code, displays 10-minute countdown timer, one-click copy, and deep link (`t.me/<bot>?start=<CODE>`).
- **Disconnect Confirmation Modal (`frontend/src/features/settings/DisconnectConfirmModal.tsx`):**
  Confirms channel unlinking with explicit warning.
- **Localization (`frontend/src/i18n/locales/`):**
  Complete Turkish (`tr`) and English (`en`) translations verified by `npm run i18n:check`.

---

## 5. Security & Invariant Compliance

Phase 9 maintains strict conformance with all system invariants and security standards:

1. **Least-Privilege & Row-Level Security (`ADR-013`, `INV-19`):**
   All Phase 9 tables (`channel_links`, `channel_link_codes`, `notification_deliveries`, `action_tokens`) enforce `FORCE ROW LEVEL SECURITY`. Queries execute within the active `app.workspace_id` tenant boundary.
2. **Replay & Concurrency Protection (`INV-06`, `INV-16`):**
   Action tokens are consumed atomically in a single database transaction. Concurrency or replay attempts immediately fail with `APPROVAL_ALREADY_DECIDED`.
3. **Double-Dispatch Prevention (`INV-05`):**
   Deciding an approval enqueues an asynchronous worker job (`send_reply`, `publish_content`) through the idempotent operations ledger; the channel adapter never invokes provider APIs directly.
4. **Media Security & Denial-of-Service Defense (`INV-11`):**
   Incoming photos are checked for file size before downloading. Files exceeding 20 MB are rejected immediately, preventing memory exhaustion and disk exhaustion.
5. **No Autonomous Publishing from Free Text (`INV-04`):**
   Natural-language requests to publish or schedule content always create draft items requiring explicit approval. Free text never auto-schedules or publishes.
6. **Architectural Isolation (`ADR-012`, `AC-4`):**
   Zero core modules import the Telegram adapter. Adding new owner messaging channels (e.g. WhatsApp or Web Push) requires zero changes to core business logic.

---

## 6. Pilot Readiness & Live Operational Notes

### 6.1 Live Bot Configuration
To enable Telegram messaging in staging or production:
1. Register a bot via `@BotFather` and obtain `TELEGRAM_BOT_TOKEN`.
2. Generate a high-entropy secret for `TELEGRAM_WEBHOOK_SECRET` via `python -m app.cli generate-key`.
3. Set the public webhook:
   ```bash
   curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://<DOMAIN>/api/v1/webhooks/telegram", "secret_token": "<SECRET>"}'
   ```
4. Verify webhook status:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
   ```

### 6.2 Local Development Runner
Developers run the long-polling runner without tunnels or public URLs:
```powershell
cd backend
uv run python -m app.cli telegram-poll
```

### 6.3 Live Adapter Probes
The optional live probe harness (`tests/contract/test_telegram_live.py`) is marked with `@pytest.mark.telegram_live`. When live credentials are supplied via environment variables (`TELEGRAM_LIVE_BOT_TOKEN`, `TELEGRAM_LIVE_CHAT_ID`), it verifies real token validity, outbound text delivery, and photo upload. In CI and regular test runs without credentials, it skips automatically without failing.

---

## 7. Sign-Off and Handoff

Phase 9 is complete. All code, database migrations, security hardening tests, E2E acceptance criteria, and documentation are verified and synchronized. The project is positioned for Phase 8.5 UI implementation or live founder pilot onboarding.
