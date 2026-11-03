# Phase 9: Implementation Plan and Sessions (Owner Messaging Channel)

**Status:** Planned; no Phase 9 implementation or acceptance is claimed by this document.  
**Canonical phase:** [Owner messaging channel (Telegram, provisional)](../phases/phase-09-owner-channel.md).  
**Architectural decisions and contracts:**  
- [ADR-012: Owner channel abstraction; web first](../../architecture/decisions/ADR-012-owner-channel-abstraction.md)  
- [ADR-014: Deterministic policy engine and version-bound approvals](../../architecture/decisions/ADR-014-approval-and-policy-model.md)  
- [ADR-024: Account agent with memory and delegated autonomy](../../architecture/decisions/ADR-024-account-agent-and-delegated-autonomy.md)  
- [ADR-025: Phase 8 hardening contracts](../../architecture/decisions/ADR-025-phase-8-hardening-contracts.md)  
- [integrations.md §5 (Owner channels)](../../architecture/integrations.md#5-owner-channels)  
- [platform-capabilities.md §2–3](../../research/platform-capabilities.md)  
**Session count:** 8 sequential sessions. Each session is an explicit scope boundary, not a promise that it fits into one work period.

---

## 1. Short Plan

Phase 9 establishes the **Owner Messaging Channel** using the channel-agnostic core architecture defined in ADR-012. It enables business owners and managers to link their personal Telegram account securely to their workspace via a one-time code, receive push notifications and approval requests on their phone, decide approvals replay-safely with single-use action tokens, submit natural-language commands and photos, query business reports, and answer account-agent clarification questions without opening the web browser.

1. **Session 01:** Establish baseline, design contracts, database migration `0038` (`channel_links`, `channel_link_codes`), RLS policies, audit catalog, and the server-side linking service.
2. **Session 02:** Build the web settings channel management surface (`Settings -> Channels / Connections`), link-code generator modal, active links view, and unlinking API with TR/EN localization.
3. **Session 03:** Formalise the `OwnerChannel` protocol, channel registry, `notification_deliveries` ledger, and delivery policy engine with per-user quiet hours and timezone awareness.
4. **Session 04:** Implement the Telegram channel adapter (`POST /webhooks/telegram`), `update_id` deduplication table, CLI long-polling runner (`python -m app.cli telegram-poll`), and offline synthetic test transport.
5. **Session 05:** Implement inbound command routing (`CommandService.submit`), Telegram markdown result rendering, photo ingestion via `MediaService.ingest` (≤ 20 MB) with draft attachment, and natural-language owner-task intake.
6. **Session 06:** Implement replay-safe approval buttons with 16-byte hashed action tokens, Telegram inline keyboards, callback query decision processing, and Phase 7.5 owner-question notifications and answers.
7. **Session 07:** Implement comprehensive resilience and security tests (P9-05 edge cases: forwarded buttons, replay, expiry, stale approvals, unlinked users, duplicate updates, oversized media) and verify import linter isolation.
8. **Session 08:** Execute end-to-end acceptance across all 4 canonical criteria, provide the optional live Telegram bot harness, run full backend/frontend regressions, and write the Phase 9 close-out summary.

---

## 2. Execution Order and Task Coverage

| Session | Scope | Phase Task Coverage | Primary Deliverables |
|:---:|---|---|---|
| **01** | Baseline, Contracts, Migration & Linking Core | P9-01 (backend foundation) | Migration `0038`, `channel_links`, `channel_link_codes`, RLS, audit actions, `ChannelLinkService` |
| **02** | Web Settings Channel Management UI & API | P9-01 (web surface & API) | REST endpoints for link code generation/unlinking, React UI in Settings, TR/EN translations, unit tests |
| **03** | Channel Abstraction, Delivery Engine & Quiet Hours | P9-02 | `OwnerChannel` protocol, channel registry, `notification_deliveries` table, delivery policy, quiet hours |
| **04** | Telegram Adapter, Webhook & Long-Polling Harness | P9-03 (inbound foundation) | Telegram client, `POST /webhooks/telegram`, `update_id` dedup, `telegram-poll` CLI, bot command routing |
| **05** | Command Dispatch, Photo Ingestion & Owner Tasks | P9-03 (commands & media), P7.5 handoff | Text → `CommandService`, photo → `MediaService` (≤ 20 MB), owner tasks, daily report Telegram query |
| **06** | Approval Buttons, Action Tokens & Owner Questions | P9-04, P7.5 owner questions | `action_tokens` table, inline keyboards, callback handler, single-use decision, owner questions |
| **07** | Security Hardening, Edge Cases & Import Linter | P9-05, INV-03/04/06/16, Linter | 7 security/resilience edge-case test suites, import linter contract enforcement |
| **08** | E2E Acceptance, Live Bot Harness & Phase Close-Out | All ACs (1–4), Phase Summary | Full E2E suite, optional live probe harness, regressions, `phase-09-summary.md` |

Run one assigned session at a time in strict numerical order. An externally pending item (such as waiting for live Telegram Bot API credentials or live founder phone testing) must be carried forward explicitly without blocking offline verification or declaring unverified criteria met.

---

## 3. Starting State, Gates and Constraints

- **Phase 8 baseline:** Commit `7990869`+ with migration head `20261103_0037_operator_alert_states.py` (64 tables). PostgreSQL Row-Level Security (`FORCE ROW LEVEL SECURITY`) is active on all tenant tables. Runtime application roles connect as `agentnest_app` / `agentnest_worker` without superuser or bypass privileges.
- **Phase 8.5 UI baseline:** Warm workspace design system is active across all web views (`frontend/src/`). Settings and Connections surfaces use TanStack Query, typed OpenAPI clients, and bilingual i18n (`tr` / `en`).
- **Gate 4 / OQ-01 status:** Telegram is the provisional second channel per ADR-012 and `docs/implementation/phases/phase-09-owner-channel.md`. WhatsApp is explicitly deferred due to per-message utility costs, business verification requirements, and Meta platform policies. The channel abstraction in Sessions 01–03 remains strictly provider-agnostic.
- **Phase 7.5 handoff contracts:**
  1. *Owner questions:* Typed, scoped notifications and answers route into `OwnerRequestService`. A delivered message or free-text reply is informational input, never an action approval.
  2. *Owner tasks:* Natural-language owner tasks enter authenticated owner-task intake with the requester's permissions intersected with account delegation; the channel adapter cannot invoke broker tools or provider effects.
  3. *Controller epoch & freshness:* Stale questions, thread takeovers, role changes, and controller epochs display the current state rather than replaying outdated actions.
  4. *Customer DM boundary:* Customer DMs remain strictly on Instagram; owner commands and notifications remain on the owner channel. Customer content can never invoke the owner channel or `CommandService` (INV-03).
- **Offline testability (INV-14):** All Telegram flows must be completely testable offline with deterministic synthetic fixtures and `httpx.MockTransport`. No real Telegram Bot token or public HTTPS tunnel is required for CI or local unit/contract testing.

---

## 4. Common Working Rules

Before starting each session, read this document, the specific session brief below, [CLAUDE.md](../../../CLAUDE.md), [invariants.md](../../invariants.md), [phase-09-owner-channel.md](../phases/phase-09-owner-channel.md), [ADR-012](../../architecture/decisions/ADR-012-owner-channel-abstraction.md), [ADR-014](../../architecture/decisions/ADR-014-approval-and-policy-model.md), and the preceding session report.

1. **Preserve unrelated work:** Inspect branch status, current migration head, and uncommitted changes before editing. Never overwrite or reseed active databases.
2. **PostgreSQL RLS on all tenant tables:** Every newly created tenant table (`channel_links`, `channel_link_codes`, `notification_deliveries`, `action_tokens`) must include `workspace_id NOT NULL`, composite foreign keys where appropriate, and `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` with policies matching `current_setting('app.workspace_id', true)`. Global tables (e.g. `telegram_updates`) must have explicit justification and zero tenant data.
3. **Architectural import boundaries:**
   - Channel adapters live in `app/integrations/channels/`.
   - Core modules (`commands`, `approvals`, `inbox`, `policy`, `identity`, `knowledge`) must never import the Telegram adapter.
   - Only the channel registry in `app/integrations/channels/registry.py` and the API webhook router may import the Telegram adapter (Acceptance Criterion 4).
   - Add explicit contracts in `backend/pyproject.toml` under `tool.importlinter`.
4. **No external side effects inside database transactions (INV-15):** Outbound Telegram API calls (`sendMessage`, `sendPhoto`, `answerCallbackQuery`, `getFile`) must never execute while a database transaction is open.
5. **Replay-safety and token security (INV-16):** Approval button callbacks carry an opaque 16-byte random token (`base64url`, ≤ 64 bytes). The database stores `sha256(token)`. A token is single-use, bound to `(approval_id, decision, user_id, payload_hash)`, and expires with the approval. Free text never decides an approval.
6. **Time and quiet hours (INV-19):** All timestamps are stored in UTC with timezone (`timestamptz`). Quiet hours (default 22:00–08:00) evaluate against the recipient's configured timezone (or workspace timezone) using the injected `Clock`. Critical system/security alerts bypass quiet hours.
7. **Bilingual TR/EN completeness:** Every user-facing bot message, button label, web setting, and error notification must be provided in both Turkish and English.
8. **Truthful reporting:** Session reports distinguish between offline implemented behavior, locally verified tests, and external/live acceptance. Do not pre-populate reports with expected passes.

---

## 5. Detailed Session Briefs

---

### Session 01 — Baseline, Contracts, Migration & Linking Core

**Depends on:** Phase 8 close-out (revision `0037`), Phase 8.5 UI baseline, and ADR-012 / ADR-025 contracts.

**Work:**
- Inventory existing channel references across `app.commands.models` (`COMMAND_CHANNELS = ("web", "telegram")`), `app.approvals.models` (`DECISION_CHANNELS`), and `app.agent.models` (`OwnerTask.source_channel`).
- Design the data models for owner channel identity linking:
  - `channel_links`: `id` (UUID PK), `workspace_id` (UUID FK), `user_id` (UUID FK), `channel` (Text, check `'telegram'`), `channel_user_id` (Text, external platform user ID), `channel_chat_id` (Text, direct message chat ID), `channel_username` (Text nullable), `status` (Text, check `'active', 'unlinked'`), `linked_at` (timestamptz), `unlinked_at` (timestamptz nullable), `created_at`, `updated_at`.
  - `channel_link_codes`: `id` (UUID PK), `workspace_id` (UUID FK), `user_id` (UUID FK), `channel` (Text), `code_hash` (Text, SHA-256 of 8-character uppercase alphanumeric code), `expires_at` (timestamptz, default 15 minutes), `used_at` (timestamptz nullable), `created_at`.
- Create Alembic migration `20261104_0038_owner_channel_links.py`:
  - Create `channel_links` and `channel_link_codes` tables with foreign keys and unique constraints.
  - Add partial unique index: `channel_links(channel, channel_user_id) WHERE status = 'active'`.
  - Add partial unique index: `channel_links(workspace_id, user_id, channel) WHERE status = 'active'`.
  - Add `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` with policies matching `current_setting('app.workspace_id', true)`.
  - Update `OwnerTask` table check constraint `source_channel` to admit `'telegram'` alongside `'api'`.
  - Grant table permissions to `agentnest_app`, `agentnest_worker`, and `agentnest_migrator`.
- Add audit catalog events (`app/audit/`):
  - `channel_link.code_generated` (workspace_id, actor_user_id, channel, expires_at).
  - `channel_link.created` (workspace_id, user_id, channel, channel_user_id).
  - `channel_link.unlinked` (workspace_id, user_id, channel, initiated_by: `"web"` | `"bot"`).
- Implement `ChannelLinkService` in `app/identity/channels.py`:
  - `generate_link_code(db, clock, ctx, channel="telegram") -> tuple[str, datetime]`: Generates cryptographically secure 8-character code, stores `sha256(code)`, returns plaintext code and expiry instant. Throttled to 3 active codes per user.
  - `redeem_link_code(db, clock, channel, channel_user_id, channel_chat_id, raw_code, channel_username=None) -> ChannelLink`: Looks up active code by hash, verifies not expired, verifies not used, marks `used_at`, unlinks any existing active link for that channel identity, creates `channel_links(status="active")`, writes audit log.
  - `unlink_by_user(db, clock, ctx, channel_link_id) -> None`: Unlinks from the web application.
  - `unlink_by_channel(db, clock, channel, channel_user_id) -> None`: Unlinks when owner issues `/unlink` in the bot.
  - `resolve_channel_user(db, channel, channel_user_id) -> tuple[User, Workspace, ChannelLink] | None`: Resolves incoming webhook author to user and default workspace context.
- Write comprehensive unit and isolation tests (`tests/unit/identity/test_channel_links.py` and `tests/isolation/test_channel_links_isolation.py`).

**Verify and finish:**
- Run `uv run alembic upgrade head` against a disposable database; verify migration `0038` applies cleanly and downgrades cleanly.
- Verify RLS tests prove that querying `channel_links` without setting `app.workspace_id` returns 0 rows.
- Verify code expiry, replay of used code, invalid code, multiple active link prevention, and audit log generation.
- Produce `s01-report.md` detailing migration head, test results, and next-session API handoff.

---

### Session 02 — Web Settings Channel Management UI & API

**Depends on:** Session 01 `ChannelLinkService` and database migration `0038`.

**Work:**
- Create the REST API router in `app/api/v1/channels_router.py` mounted at `/api/v1/workspaces/{ws}/channels`:
  - `POST /link-code`: Body `{ "channel": "telegram" }`. Requires `settings.view` permission. Returns `{ "code": "ABC12XYZ", "expires_at": "...", "bot_username": "...", "deep_link_url": "https://t.me/bot?start=ABC12XYZ" }`.
  - `GET /links`: Returns list of linked channels for current user (`id`, `channel`, `channel_username`, `linked_at`, `status`).
  - `DELETE /links/{link_id}`: Unlinks the channel link. Requires owner/manager or the link's user.
- Add configuration settings in `app/core/config.py`:
  - `TELEGRAM_BOT_USERNAME: str | None = None`
  - `TELEGRAM_BOT_TOKEN: SecretStr | None = None`
  - `TELEGRAM_WEBHOOK_SECRET: SecretStr | None = None`
  - Include validation: if Telegram is enabled in production, bot username and token must be present.
- Regenerate OpenAPI schema and TypeScript client types:
  - Run `uv run python -m app.cli openapi` and generate frontend types in `frontend/src/api/types.ts`.
- Build the frontend channel settings view:
  - Create `frontend/src/features/settings/Channels.tsx` (or integrate as a tab/section in `frontend/src/features/settings/Connections.tsx` and `MorePage.tsx`).
  - Add query hook `useChannelLinks()` and mutation hooks `useGenerateChannelLinkCode()`, `useUnlinkChannel()`.
  - Display "Telegram Bağlantısı" / "Telegram Connection" card:
    - If unlinked: "Bağla" / "Connect" button opening modal with generated 8-character code, countdown timer, step-by-step instructions ("1. Telegram'da @AgentNestBot'u açın, 2. /link <code> komutunu gönderin"), and direct `t.me` deep-link button.
    - If linked: Active badge, connected Telegram username, linked date, and "Bağlantıyı Kaldır" / "Disconnect" button with confirmation sheet.
- Update localization catalogs (`frontend/src/locales/tr.json` and `en.json`) with all channel linking strings.
- Write frontend component and hook tests (`frontend/src/features/settings/channels.test.tsx`).

**Verify and finish:**
- Run `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd test`, `npm.cmd run i18n:check`.
- Verify link code countdown, copy-to-clipboard, deep link URL, and unlinking confirmation in browser.
- Verify API permission checks (non-members cannot generate codes or view links).
- Produce `s02-report.md` with UI screenshots/traces and next-session delivery handoff.

---

### Session 03 — Channel Abstraction, Delivery Engine & Quiet Hours

**Depends on:** Session 01 data models and Session 02 configuration.

**Work:**
- Create `app/integrations/channels/base.py` formalizing the `OwnerChannel` protocol (ADR-012 §5.1):
  ```python
  class OwnerChannel(Protocol):
      name: Literal["web", "telegram"]
      def deliver_notification(
          self, session: Session, clock: Clock, delivery: NotificationDelivery, recipient: ChannelRecipient
      ) -> DeliveryResult: ...
      def render_command_result(
          self, session: Session, clock: Clock, command: OwnerCommand, recipient: ChannelRecipient
      ) -> None: ...
  ```
- Create the channel registry in `app/integrations/channels/registry.py`:
  - Registers `"web"` (in-app notification default) and `"telegram"`.
  - Lazy resolution of channel instances based on configuration.
- Create Alembic migration `20261104_0039_notification_deliveries.py`:
  - Table `notification_deliveries`: `id` (UUID PK), `workspace_id` (UUID FK), `notification_id` (UUID FK to `notifications.id`, ondelete CASCADE), `recipient_user_id` (UUID FK to `users.id`, ondelete CASCADE), `channel` (Text), `channel_link_id` (UUID FK nullable), `status` (Text: `'pending'`, `'delivered'`, `'failed'`, `'skipped_quiet_hours'`), `attempt_count` (Integer default 0), `last_error` (Text nullable), `sent_at` (timestamptz nullable), `created_at`, `updated_at`.
  - Add RLS policies and table grants.
- Implement delivery policy engine (`app/notifications/delivery_policy.py`):
  - Notification routing matrix:
    - `approval.requested`, `approval.expired`: pushed immediately.
    - `owner_question.created`: pushed immediately.
    - `system.integration_error`, `account.needs_reauth`: pushed immediately (critical).
    - `report.daily_ready`, `content.scheduled`: pushed subject to quiet hours.
    - Routine info notifications: web-only by default.
  - Quiet hours rules:
    - Default quiet window: 22:00 to 08:00 in user's local timezone (or workspace timezone).
    - Critical notifications (`severity == 'critical'` or `approval.requested` with window expiry < 2 hours) bypass quiet hours.
    - Non-critical notifications during quiet hours are marked `skipped_quiet_hours` or queued for morning dispatch.
- Implement durable delivery job (`app/notifications/jobs.py`):
  - Job `deliver_channel_notification(delivery_id)`: Claims delivery row, resolves channel via registry, calls `channel.deliver_notification` outside database transaction, updates delivery status (`delivered` / `failed`), logs audit.
- Write unit tests for delivery policy, quiet hours calculation across timezones, and job execution (`tests/unit/notifications/test_delivery_policy.py`).

**Verify and finish:**
- Run backend test suite on notification delivery, quiet hours edge cases (21:59 vs 22:01, crossing midnight, DST transitions).
- Verify database isolation for `notification_deliveries`.
- Produce `s03-report.md` and hand off delivery contracts to Session 04.

---

### Session 04 — Telegram Adapter, Webhook & Long-Polling Harness

**Depends on:** Session 01 identity linking, Session 02 configuration, and Session 03 delivery engine.

**Work:**
- Create `app/integrations/channels/telegram/` package:
  - `client.py`: Async/Sync `httpx.Client` wrapper for Telegram Bot API (`https://api.telegram.org/bot<token>/`):
    - Methods: `send_message`, `send_photo`, `answer_callback_query`, `edit_message_text`, `edit_message_reply_markup`, `get_file`, `download_file`.
    - Timeout 15s, no automatic retry on 4xx, structured error handling (`TelegramApiError`).
    - Test transport injection (`httpx.BaseTransport`) for deterministic offline mock tests.
  - `adapter.py`: Implements `OwnerChannel` protocol.
  - `webhook_format.py`: Parsers for Telegram Update JSON (`message`, `callback_query`).
- Create table `telegram_updates` in Alembic migration `20261104_0040_telegram_updates.py`:
  - `update_id` (BigInteger PK), `received_at` (timestamptz), `status` (Text: `'processed'`, `'ignored'`, `'failed'`), `channel_user_id` (Text nullable), `error` (Text nullable).
  - Explicit global table (no `workspace_id` because deduplication occurs at ingress before tenant resolution).
- Implement webhook router in `app/api/v1/telegram_webhook_router.py`:
  - Endpoint `POST /webhooks/telegram`:
    - Validates `X-Telegram-Bot-Api-Secret-Token == settings.telegram_webhook_secret`. Invalid secret returns 401 without processing.
    - Deduplicates on `update_id` (INV-06): duplicate `update_id` immediately returns 200 `{"status": "duplicate"}`.
    - Parses update: routes to command handler, callback query handler, or link command.
- Implement local development long-polling runner in `app/cli.py` (`python -m app.cli telegram-poll`):
  - Calls `getUpdates(offset, timeout=30)` in a controlled loop.
  - Hands received updates to the exact same update processing pipeline as the webhook endpoint.
  - Allows zero-credential testing via synthetic fixture server or local bot testing without ngrok/tunnel.
- Add Telegram bot base command handlers:
  - `/start`: Greeting message explaining AgentNest bot capabilities and `/link <code>` instruction.
  - `/link <code>`: Calls `ChannelLinkService.redeem_link_code`. Responds with success message naming the linked workspace and user, or an error.
  - `/unlink`: Unlinks current Telegram account from AgentNest.
  - `/status`: Reports current link status, workspace name, and active notifications count.
  - Unknown commands from unlinked users: prompt to link with the web app.
- Write unit and contract tests with offline fixtures (`tests/contract/test_telegram_adapter.py`).

**Verify and finish:**
- Run test suite verifying secret token check, duplicate `update_id` rejection, `/start`, `/link`, `/unlink` and `/status` flows.
- Verify CLI long-polling command runs in test mode with mocked updates.
- Produce `s04-report.md` and hand off inbound routing to Session 05.

---

### Session 05 — Command Dispatch, Photo Ingestion & Owner Tasks

**Depends on:** Session 04 Telegram adapter and baseline Command / Media / Agent services.

**Work:**
- Inbound natural-language text routing:
  - When an authorized linked owner sends text (not a command like `/link`):
    - Resolve user, workspace, and role via `channel_links`.
    - Check if workspace account has active `account_agent` in `agent` mode:
      - If user input is an owner instruction/task (e.g. "Ahmet Bey'e randevu için dönüş yap"): route to `app.agent.owner_tasks.submit(account_id, text, client_request_id, source_channel="telegram")`.
      - Otherwise submit to `CommandService.submit(session, clock, ctx, text=text, client_request_id=f"tg:{update_id}", channel="telegram")`.
    - Render command execution results back to Telegram:
      - Formatted response text (MarkdownV2 or HTML).
      - If command returns a clarification or confirmation: send message with next steps.
- Reporting queries (AC-2):
  - Natural language questions such as "Bugün kaç DM geldi?" or "Bugünkü özet":
    - Command interpreter resolves to reporting query.
    - Aggregates metrics from `app/reporting/service.py` (`get_daily_summary`).
    - Format and return identical metrics as shown in web dashboard (`total_inbound_messages`, `new_conversations`, `approvals_pending`).
- Inbound photo ingestion (AC-3, P9-03):
  - When owner sends a photo (with or without caption):
    - Retrieve Telegram file metadata via `getFile`.
    - Enforce file size limit: if `file_size > 20 * 1024 * 1024` (20 MB), reject immediately with message "Fotoğraf 20 MB'tan büyük olamaz" / "Photo exceeds 20 MB limit" and log rejection (INV-11).
    - Download photo bytes via `client.download_file`.
    - Call `app.content.media.ingest(db, clock, settings, storage, ctx, file=BytesIO(photo_bytes), filename="telegram_upload.jpg", content_type="image/jpeg")`.
    - If photo has caption (e.g. "bu story'yi 19:00'da paylaş"):
      - Parse scheduling instruction: target type (`story` or `post`), proposed time (`19:00` in workspace timezone).
      - Create story content draft with attached `media_asset_id`.
      - Create schedule proposal requiring explicit approval (never auto-scheduled from free text, INV-04, AC-3).
      - Send confirmation message to Telegram with story preview details and approval request.
    - If photo has no caption:
      - Store as temporary pending media for user's next command (expires in 15 minutes).
- Write unit and workflow tests (`tests/unit/integrations/channels/test_telegram_commands_media.py`).

**Verify and finish:**
- Test "Bugün kaç DM geldi?" returns exact matching counts against seeded database.
- Test photo ingestion with JPEG validation, 20 MB limit rejection, and story draft creation with approval required.
- Test that free text never bypasses policy or directly publishes content.
- Produce `s05-report.md` and hand off to Session 06.

---

### Session 06 — Approval Buttons, Action Tokens & Owner Questions

**Depends on:** Session 04 Telegram adapter, Session 05 messaging, and `app/approvals/service.py`.

**Work:**
- Create `action_tokens` data model and Alembic migration `20261104_0041_action_tokens.py`:
  - `id`: UUID PK
  - `workspace_id`: UUID FK
  - `token_hash`: Text unique (SHA-256 of 16-byte cryptographically random token)
  - `approval_id`: UUID FK to `approvals.id` ondelete CASCADE
  - `decision`: Text (check `'approved'`, `'rejected'`)
  - `user_id`: UUID FK to `users.id` ondelete CASCADE
  - `payload_hash`: Text (exact payload hash of the approval snapshot)
  - `expires_at`: timestamptz (matching approval expiry)
  - `used_at`: timestamptz nullable
  - `created_at`: timestamptz
  - Add RLS policies and table grants.
- Implement `ActionTokenService` (`app/approvals/action_tokens.py`):
  - `create_action_token(db, clock, ctx, approval, decision, user_id) -> str`: Generates 16 random bytes (`base64url`, 22 chars), stores hash, returns token string.
  - `consume_action_token(db, clock, token_str, channel_user_id) -> tuple[Approval, str]`: Validates token hash, checks `used_at IS NULL`, checks `now < expires_at`, resolves linked user, atomically sets `used_at = now`.
- Telegram approval notification renderer:
  - Formats `approval.requested` notification for Telegram:
    - Subject type: Reply draft or Content item.
    - Full summary text (customer message excerpt, proposed reply text, or content caption/media info).
    - Target Instagram account name.
    - Scheduled time (if applicable) in workspace timezone.
    - Simulated badge if `is_simulated` is true (INV-09).
    - Inline keyboard with two buttons:
      - `✅ Onayla` / `Approve` (`callback_data = "act:<token_approve>"`)
      - `❌ Reddet` / `Reject` (`callback_data = "act:<token_reject>"`)
      - URL button: `📱 Uygulamada Aç` / `Open in App` (deep link to web approval screen).
- Callback query handling in Telegram webhook:
  - Parses `callback_query.data` starting with `act:`.
  - Consumes action token:
    - If token already used: `answerCallbackQuery(text="Bu onay zaten karara bağlandı / Already decided", show_alert=True)`.
    - If expired: `answerCallbackQuery(text="Onay süresi doldu / Approval expired", show_alert=True)`.
    - If user mismatch: `answerCallbackQuery(text="Bu onay için yetkiniz yok / Unauthorized", show_alert=True)`.
    - If valid: Calls `ApprovalService.decide(session, clock, ctx, approval_id, decision=token.decision, payload_hash=token.payload_hash, channel="telegram")`.
    - Updates Telegram message: removes buttons, appends decision badge (`✅ Onaylandı - <name>` / `❌ Reddedildi - <name>`).
- Phase 7.5 Owner Questions intake (ADR-024, Phase 7.5 handoff):
  - Delivery of `owner_question.created` to Telegram:
    - Displays question text, required info category, requesting thread/customer context.
    - Quick response instruction: "Bu mesaja yanıt vererek (Reply) veya doğrudan yazarak cevaplayabilirsiniz".
  - Inbound reply to an owner question:
    - Matches active `OwnerQuestion` for that thread.
    - Calls `OwnerRequestService.submit_answer(db, clock, ctx, question_id, body=text)`.
    - Verifies question version and controller epoch; if stale, returns current state.
    - Clearly recorded as informational input, never as an action approval.
- Write unit and scenario tests (`tests/unit/approvals/test_telegram_action_tokens.py`).

**Verify and finish:**
- Test approval notification delivery, token generation, and single-use button press.
- Test second button press returns 409 "Already decided" and performs no second send (AC-1).
- Test forwarded button pressed by another user is rejected.
- Test owner question notification and answer round-trip.
- Produce `s06-report.md` and hand off to Session 07.

---

### Session 07 — Security Hardening, Edge Cases & Import Linter

**Depends on:** Sessions 01–06 implementation.

**Work:**
- Implement dedicated security and resilience test suite (`tests/security/test_owner_channel_security.py`):
  1. *Wrong user pressing forwarded button:* User B receives a forwarded message from User A with action buttons; User B taps button; system rejects because token is bound to User A's ID.
  2. *Replayed button:* Token is submitted twice concurrently or sequentially; exactly one call executes `ApprovalService.decide`, second call raises conflict/already decided.
  3. *Expired approval:* Approval passes its expiry instant; button tap returns expired notification; no side effect is dispatched.
  4. *Edited subject (stale approval):* Content draft or reply text is edited on the web (incrementing `subject_version`); old Telegram button carries stale `payload_hash`; decision rejected with `APPROVAL_STALE`.
  5. *Unlinked user interaction:* Unlinked Telegram user sends messages, commands, or forged callback data; system executes no business logic and returns polite linking prompt.
  6. *Duplicate update delivery:* Telegram sends same `update_id` 3 times in rapid succession; `telegram_updates` deduplication processes it exactly once (INV-06).
  7. *Oversized media upload:* User uploads 25 MB photo; adapter checks file size before processing, rejects with `MEDIA_TOO_LARGE`, stores no file in storage, and logs rejection audit.
  8. *Quiet hours enforcement:* Test non-critical notifications are suppressed or delayed between 22:00 and 08:00 local time, while critical alerts bypass.
- Enforce architectural import linter rules (Acceptance Criterion 4):
  - Update `backend/pyproject.toml` under `[[tool.importlinter.contracts]]`:
    - Add rule: `"only channel registry and telegram webhook router import telegram channel adapter"`.
    - Verify that `app.commands`, `app.approvals`, `app.inbox`, `app.policy`, `app.identity`, `app.knowledge` contain zero imports of `app.integrations.channels.telegram`.
  - Run `uv run lint-imports` and verify green output.
- Add penetration and injection tests:
  - Malformed callback data, SQL injection attempts in `/link <code>`, command injection heuristics.

**Verify and finish:**
- All 8 security edge-case tests pass cleanly.
- `uv run lint-imports` passes with zero violations.
- Run complete backend test suite to ensure no regressions across Phase 1–8.
- Produce `s07-report.md` with security test evidence.

---

### Session 08 — E2E Acceptance, Live Bot Harness & Phase Close-Out

**Depends on:** Sessions 01–07 implementation and test suites.

**Work:**
- Execute and verify the four canonical Phase 9 Acceptance Criteria:
  - **AC-1:** A linked owner receives an `approval.requested` message for a reply draft with exact text, approves with a button, and the reply is sent. A second press reports "already decided".
  - **AC-2:** "Bugün kaç DM geldi?" in Telegram returns the same number as the web report.
  - **AC-3:** Sending a photo with "bu story'yi 19:00'da paylaş" creates a story draft with that media and a schedule proposal requiring explicit approval (never auto-scheduled from free text).
  - **AC-4:** No core module imports the Telegram adapter except the channel registry.
- Provide the optional live Telegram bot probe harness (`tests/contract/test_telegram_live.py`):
  - Marked with `@pytest.mark.telegram_live`, skipped by default in CI unless `TELEGRAM_LIVE_BOT_TOKEN` and `TELEGRAM_LIVE_CHAT_ID` are set.
  - Tests real outbound message, photo delivery, and callback roundtrip against live Telegram API.
- Perform complete regression test suites:
  - Backend:
    ```powershell
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy app
    uv run lint-imports
    uv run pytest tests/unit/identity/test_channel_links.py tests/contract/test_telegram_adapter.py tests/security/test_owner_channel_security.py
    ```
  - Frontend:
    ```powershell
    npm.cmd run lint
    npm.cmd run typecheck
    npm.cmd test
    npm.cmd run i18n:check
    npm.cmd run build
    ```
- Update documentation:
  - Update `docs/architecture/integrations.md §5` reflecting implemented Telegram adapter details.
  - Update `docs/operations/local-development.md` with instructions for `python -m app.cli telegram-poll`.
  - Update `docs/implementation/roadmap.md` and `task-breakdown.md` marking Phase 9 tasks complete.
- Author `docs/implementation/phase-summaries/phase-09-summary.md` detailing:
  - Implemented architecture and files.
  - Database schema changes (migrations `0038`, `0039`, `0040`, `0041`).
  - Canonical acceptance criteria audit with passing test names.
  - Security and invariant compliance.
  - Pilot readiness and live Telegram operational notes.

**Verify and finish:**
- All tests pass cleanly, documentation is synchronized, and Phase 9 summary is published.
- Stop at the Phase 9 boundary for user review and approval.

---

## 6. Verification and Reporting Commands

After each session slice, execute the appropriate commands:

### Backend
```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run lint-imports
uv run pytest <session-test-paths>
```

### Frontend
```powershell
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run i18n:check
npm.cmd run build
```

### Required Session Report (`sNN-report.md`)
Each executed session creates `docs/implementation/phase-9-sessions/sNN-report.md` with:
- **Status:** offline complete / externally pending / complete.
- **Baseline Git commit** and migration head.
- **Implemented behavior,** created/edited files, and API contracts.
- **Exact test results,** execution command line, passing count, and evidence paths.
- **Invariant and security compliance** (RLS, audit logs, deduplication, import linter).
- **Next-session handoff** and instructions.

---

## 7. Session Invocation Prompt

To invoke an implementation session, use the standard prompt format:

> Implement Phase 9 Session NN using `docs/implementation/phase-9-sessions/phase-09-sessions.md`. Read the common rules, the selected session brief, current phase status, and the previous session report. Complete that session's authorized work and checks, create `sNN-report.md`, and stop at its boundary. Preserve unrelated work. Do not infer authorization for production deployment, live messaging actions, commit, or push.

