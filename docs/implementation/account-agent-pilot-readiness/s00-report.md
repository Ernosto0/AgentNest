# Session 00 Report — Establish the Current Baseline and Acceptance Inventory

- **Date:** 2026-11-19 (Europe/Istanbul)
- **Plan:** [Account Agent Pilot Readiness](../../../answeres2.md) — Session 00
- **Local Git Baseline:** branch `main`, commit `e1c9f1367f63ed4afcd7e78b075c48a61c408fd8` (`e1c9f13`), up to date with `origin/main`.
- **Alembic Migration Head:** single head `0100` (`20261118_0100_reply_languages_ru_de_ar.py`). Next free migration number: `0101`.
- **Changes Made in Session 00:** Read-only audit and inventory only. Created this report (`docs/implementation/account-agent-pilot-readiness/s00-report.md`). No application code, database schema, configuration, or production deployment was mutated.

---

## 1. Repository, Migration, Tooling, and Local Environment Baseline

### 1.1 Git Status and Commit History
- **Branch:** `main` (tracking `origin/main`, 0 ahead / 0 behind).
- **HEAD Commit:** `e1c9f1367f63ed4afcd7e78b075c48a61c408fd8`
- **Recent Commits on `main`:**
  1. `e1c9f13` — `feat: Feature Phase 5 - WhatsApp owner channel, carousels and Reels, follow-up and Human Agent tag, ru/de/ar replies, lead list`
  2. `5ec7435` — `ci: allowlist the unpatched picomatch advisory in the frontend audit`
  3. `1a58d41` — `feat: Feature Phase 4 - fact import from Instagram profile and website, local package on landing`
  4. `e2fcc23` — `test: provision runtime roles in three Feature Phase 2 isolation tests`
  5. `3d2f5c8` — `feat: Feature Phase 3 - comment-to-DM on real accounts, template images`
- **Working Tree:** Clean on tracked files; `answeres2.md` is present as an untracked file at repo root (preserved untouched per instructions).
- **Historical Summary Drift Note:** The close-out summaries for Feature Phases 1–5 (`docs/implementation/phase-summaries/features-phase-*-summary.md`) and `docs/implementation/roadmap.md` still contain historical notes stating *"Nothing is committed"*. Those phases were subsequently committed to `main` through `e1c9f13`. Per Session 11 rules, historical summaries will receive dated current-status notes during Session 11 close-out without rewriting their historical test records.

### 1.2 Alembic Migration Chain and Head
- **Command:** `uv run alembic heads` in `backend/`
- **Observed Output:** `0100 (head)` (single head).
- **Merged Feature Phase 5 Chain:** `0061 -> 0070 -> 0071 -> 0080 -> 0081 -> 0082 -> 0083 -> 0090 -> 0091 -> 0100`.
- **Next Available Revision:** `0101` (or next agreed sequence block).

### 1.3 Developer Machine and Test Command Baseline (Windows)
- **`uv` Location:** Installed at `%APPDATA%\Python\Python313\Scripts\uv.exe` (`C:\Users\ernos\AppData\Roaming\Python\Python313\Scripts\uv.exe`), which is not on the default non-interactive PowerShell `PATH`. `backend\.venv\Scripts\` also contains the project's Python 3.12 virtual environment binaries directly (`pytest.exe`, `ruff.exe`, `mypy.exe`, `lint-imports.exe`, `alembic.exe`).
- **Node / npm Location:** `C:\Program Files\nodejs\npm.cmd` (on `PATH`).
- **Local `.env` Status:** Neither `.env` nor `backend/.env` is present in the local working tree. As a result, the two historical local `.env` overrides noted in Feature Phase 2–4 reports (`FRONTEND_ORIGIN` CORS mismatch and `trycloudflare.com` invite URL mismatch) are not present in the clean repo defaults, though `DEMO_TOOLS_ENABLED=true` environment exports still affect production-config unit tests if exported globally.
- **Local Docker / PostgreSQL Status (Port `5433`):** During this Session 00 check, the local Docker Desktop Linux engine (`//./pipe/dockerDesktopLinuxEngine`) was not running, so `localhost:5433` was unreachable.
  - **Consequence:** Pure unit tests, static analysis, type checks, import-linter contracts, and frontend Vitest suites run offline immediately. Any `pytest` test requesting the `db_session` or `session_factory` fixture blocks/fails attempting to connect to `localhost:5433` until Docker Desktop and the local PostgreSQL 16 container (`docker compose up -d postgres`) are started.
  - **Rule Compliance:** No inference is made that old per-track test results prove the combined current commit `e1c9f13`. Full DB-backed integration/isolation/E2E verification requires starting the local Postgres container on port `5433`.

### 1.4 Baseline Verification Checks Executed in Session 00

| Check / Command | Scope | Result | Notes |
|---|---|---|---|
| `uv run alembic heads` | `backend/` | **PASS** | Single head: `0100 (head)` |
| `uv run ruff check .` | `backend/` | **PASS** | `All checks passed!` |
| `uv run ruff format --check .` | `backend/` | **PASS** | `898 files already formatted` |
| `uv run mypy app` | `backend/` | **PASS** | `Success: no issues found in 463 source files` |
| `uv run lint-imports` | `backend/` | **PASS** | `Analyzed 537 files, 4620 dependencies. Contracts: 27 kept, 0 broken.` |
| `uv run pytest --collect-only -q` | `backend/` | **PASS** | `5986 tests collected in 13.10s` |
| `uv run pytest tests/unit/inbox/test_language_detection_ru_de_ar.py tests/unit/reporting/test_leads_csv.py tests/unit/knowledge/test_claims_ru_de_ar.py tests/unit/knowledge/test_formatting_ru_de_ar.py tests/unit/policy/test_message_tag.py -q` | `backend/` (no-DB unit suites) | **PASS** | `529 passed in 0.68s` |
| `npm.cmd run lint` | `frontend/` | **PASS** | `eslint .` exited 0 with 0 errors |
| `npm.cmd run typecheck` | `frontend/` | **PASS** | `tsc -b --noEmit` exited 0 |
| `npm.cmd run i18n:check` | `frontend/` | **PASS** | `i18n check passed: en, tr \| 2966 keys \| 2117 literal t() calls verified` |
| `npm.cmd test -- --run src/features/settings/settings.test.tsx src/features/test-chat/testChat.test.tsx` | `frontend/` | **PASS** | `2 passed (2), 31 passed (31) in 10.77s` |

---

## 2. Read-Only Deployment and Live Infrastructure Evidence (Railway)

Read-only inspection was performed via `railway_mcp` (`whoami`, `list-projects`, `get-status`, `describe-environment`, `list-deployments`, `list-domains`). No variables, secrets, or logs were mutated or exposed.

- **Authenticated Account:** `Cinar Che Aksoy` (`cinarcheaksoy@gmail.com`)
- **Project:** `agentnest` (`f6dd192d-d9eb-4007-acfa-3c3fd00dda72`)
- **Environment:** `production` (`b6d7dec1-51f5-43a4-90b8-318d046a33e1`), region `sfo`, 0 staged changes, 0 services with issues, 0 recent failures.
- **Live Services Inventory:**

| Service | Service ID | Status | Active Deployment ID | Deployed Timestamp (UTC) | Source / Commit | Public Domain |
|---|---|---|---|---|---|---|
| **api** | `6cfd4455-ad68-4a0f-992b-bbc429d2128a` | `SUCCESS` (Online, 1 replica) | `5e1ceb63-7eed-4d64-89c1-4ca919de1a4e` | `2026-11-18T18:53:45.414Z` | `Ernosto0/AgentNest@main` · `e1c9f13` | None listed in `list-domains` (internal or proxied via `web`) |
| **worker** | `c7cdabc3-c0e2-4b05-8254-b9283541ec65` | `SUCCESS` (Online, 1 replica) | `220546e6-98d0-4e56-a604-9e05bc813b24` | `2026-11-18T18:53:45.411Z` | `Ernosto0/AgentNest@main` · `e1c9f13` | None (background worker) |
| **web** | `9fea5780-98c4-48d1-a63b-3184d073bee0` | `SUCCESS` (Online, 1 replica) | `ecd82504-669d-4180-a2c6-3bf18b23f3ed` | `2026-11-18T18:53:45.412Z` | `Ernosto0/AgentNest@main` · `e1c9f13` | `https://web-production-b2f30.up.railway.app` |
| **landing** | `77541bf2-11f3-44e1-8371-71cc18082ac4` | `SUCCESS` (Online, 1 replica) | `f1656500-b8c7-46ca-8375-775a146b5a6d` | `2026-11-17T20:36:36.600Z` | `Ernosto0/AgentNest@main` · `1a58d41` (`e1c9f13` & `5ec7435` skipped as non-landing diffs) | `https://landing-production-945f7d94.up.railway.app` |
| **Postgres** | `d47a5af2-0a6a-4f93-946f-3b5e2ebab3b2` | `SUCCESS` (Online, 1 replica) | `157faac9-589e-4a89-9cab-b1de9193937b` | `2026-11-05T12:53:09.518Z` | `ghcr.io/railwayapp-templates/postgres-ssl:18` (volume `postgres-volume` 5000 MB at `/var/lib/postgresql/data`) | Internal |

- **Observation:** The live Railway `api`, `worker`, and `web` services are running commit `e1c9f13` (matching local `HEAD`), and `landing` is running `1a58d41` (the latest commit touching `landing/`).

---

## 3. Actual Account Agent Controller Settings and Runtime Inspection

Inspection of `backend/app/agent/` and `backend/app/core/config.py` at commit `e1c9f13` confirms:

1. **Account Agent Activation State (`app/agent/models.py`, `app/agent/control.py`):**
   - `account_agents` has one row per `(workspace_id, social_account_id)`.
   - `controller_mode` is `'legacy'` or `'agent'` (server default `'legacy'`).
   - `state` is `'inactive'`, `'active'`, or `'paused'` (server default `'inactive'`).
   - Cutover is an explicit owner-only action (`POST /api/v1/workspaces/{ws}/accounts/{id}/agent/activate` with `mode="agent"`), which increments `controller_epoch`, `config_version`, and `cutover_generation`, adopts threads, and enqueues `agent_cleanup_approvals`. No migration auto-activates an account.
2. **Delegation Actions and Modes (`app/agent/delegation.py`):**
   - Supported `ActionName` set (13 actions):
     - DMs: `dm.send`
     - Comments: `comment.reply`, `comment.private_reply`, `comment.hide`, `comment.unhide`, `comment.delete`
     - Content (owner tasks): `content.prepare`, `content.schedule`, `content.publish`, `content.cancel`
     - Calendar: `calendar.book`, `calendar.reschedule`, `calendar.cancel`
   - Each action has `ActionRule(mode: "automatic" | "ask" | "off", max_per_day: int | None, sources: frozenset[{"customer", "owner_task"}])`.
   - **Gap for Session 03:** `ActionRule` and `authorize_action()` have no topic-level or basic-versus-complex reply classification restriction. Under `dm.send = automatic`, any grounded reply that passes `validate_reply` and lacks a recent voice transcript (`require_human`) is granted automatic execution. Legacy `automation_policies` (`app/policy/rules_reply.py`) apply only to the legacy `draft_reply` flow, not the Account Agent.
3. **Coordinator Model & Budget Settings (`app/agent/coordinator.py`, `app/core/config.py`):**
   - Step lease: `90s` (`LEASE = timedelta(seconds=90)`).
   - Activation wall-clock deadline: `120s`; max `8` model steps and `12` tool calls per activation; max `24` model steps per unresolved goal.
   - Token reservation: `40,000` tokens per step (`960,000` max reserved per goal); request prompt budget `32,000` UTF-8 bytes (`64,000` total with tool schemas).
   - Repeated identical tool call cap: `3` repeats allowed; 4th fails with `AGENT_LOOP_LIMIT`.
   - Grounding validation failures: `1` repair allowed; 2nd failure fails session with `AGENT_GROUNDING_REJECTED`.
   - Monthly workspace AI reply allowance (`app/plans/service.py`): checked in `coordinator.claim()` (`usage.is_paused`) and consumed in `agent/dm.py`, `comments/actions.py`, and `comments/private_reply.py`.
   - Global model config (`app/core/config.py`): `llm_provider="fake"` (default offline; `"openai"` in production), `llm_model_default="gpt-6-luna"`, `llm_max_calls_per_workspace_per_day=500`, `llm_reasoning_effort="low"`.

---

## 4. Requirement-to-Code-and-Test Mapping (Sessions 01–09)

This table separates **existing code & offline tests**, **missing implementation / regression fixes**, **configuration / operational work**, and **unrecorded live evidence**.

### 4.1 Session 01 — Telegram Notification Delivery

| Aspect | Status / Findings |
|---|---|
| **Existing Code** | • `app/integrations/channels/telegram/adapter.py` (`TelegramChannel`) formats and sends `approval.requested` (with `act:<token>` inline buttons and D-01 fact source lines), `owner_question.requested` (with `Q-<id>` ref), `QUOTA_TEXT` warnings, and generic notifications.<br>• `app/notifications/delivery_ledger.py` (`dispatch_channel_notification`), `app/notifications/delivery_policy.py` (`evaluate_delivery_policy`, quiet hours 22:00–08:00 local, critical & <2h approval expiry bypass), and `app/notifications/jobs.py` (`deliver_channel_notification`) exist.<br>• `app/notifications/push_dispatch.py` and `app/notifications/whatsapp_dispatch.py` exist and are called from `app/notifications/service.py::notify()`. |
| **Existing Tests** | • `tests/contract/test_telegram_adapter.py`, `tests/e2e/test_owner_channel_acceptance.py`, `tests/unit/approvals/test_telegram_action_tokens.py`, `tests/unit/integrations/channels/test_telegram_guarantee.py`, `tests/unit/notifications/test_delivery_policy.py`. (Note: existing tests invoke `TelegramChannel.deliver_notification` or `dispatch_channel_notification` directly rather than via `notifications.service.notify()`). |
| **Missing Implementation / Regression Fixes** | 1. **`notifications/service.py::notify()` never dispatches to Telegram:** `notify()` calls `dispatch_web_push()` and `dispatch_whatsapp()`, but has no `dispatch_telegram()` call. Production notifications never enter `notification_deliveries` or enqueue `deliver_channel_notification` for Telegram.<br>2. **Telegram approval formatting for `agent_action` subjects:** In `TelegramChannel._deliver_approval_notification` (`adapter.py:192-296`), specialized branches exist for `approval.subject_type == "reply_draft"`, `approval.subject_type == "content_item"`, and specific command actions, while everything else falls into the generic `else:` block that dumps raw `approval.summary` keys (`action_type`, `target_ref`, `payload_hash`). On the Account Agent path (`agent/delegation.py:603`), `ask` approvals have `subject_type = "agent_action"` (for `dm.send`, `comment.reply`, `comment.private_reply`, `comment.hide/unhide/delete`, `content.*`, `calendar.book/reschedule/cancel`). Unless `adapter.py` resolves `agent_action` subjects (or their linked `ReplyDraft`, `ContentItem`, comment action, or calendar summary), Telegram approval cards for Agent actions will not show an informed description of the proposed reply/post/booking!<br>3. **Delivery ambiguity & retry behavior:** `TelegramChannel.deliver_notification` catches all exceptions and returns `DeliveryResult(success=False, status="failed")` without `retryable` or `terminal` metadata, and `jobs.py:165` raises `RuntimeError` causing up to 3 job attempts (`max_attempts=3`) even if a read timeout occurred after `sendMessage` was accepted by Telegram. Ambiguity handling and duplicate-dispatch prevention need explicit inspection and hardening. |
| **Configuration / Live Evidence** | • Requires `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_WEBHOOK_SECRET` on Railway and webhook registration (`setWebhook`).<br>• **Unrecorded Live Evidence:** End-to-end delivery of notification + informed approval button tap on a real phone via the live Telegram bot. |

### 4.2 Session 02 — Explicit Notification-Channel Choice

| Aspect | Status / Findings |
|---|---|
| **Existing Code** | • `app/identity/channels.py` and `app/api/v1/channels_router.py` manage `channel_links` (`telegram`, `whatsapp`) and `/channels/availability` (`whatsapp_configured`).<br>• `app/notifications/push_preferences.py` manages per-user `push_preferences` (`approvals`, `questions`, `failures`) for Web Push.<br>• `frontend/src/features/settings/Channels.tsx` renders Telegram link status and (when configured or linked) WhatsApp link status. |
| **Existing Tests** | • `tests/integration/identity/test_channel_links_api.py`, `tests/isolation/test_channel_links_isolation.py`, `tests/integration/notifications/test_push_preferences.py`, `frontend/src/features/settings/push.test.tsx`. |
| **Missing Implementation / Regression Fixes** | 1. **No explicit per-workspace/per-user external channel preference contract:** Currently, linking WhatsApp or Telegram implicitly opts the user in (or for Telegram, nothing dispatches). Users cannot explicitly toggle external channels on/off, choose "app-only" while keeping a link or understanding their active delivery path, or see whether Telegram is unconfigured vs disabled vs failing delivery.<br>2. **`/channels/availability` only reports `whatsapp`:** `ChannelAvailabilityOut` (`identity/schemas.py`) does not report `telegram` configuration availability (`telegram_bot_token` / `telegram_bot_username`) or current delivery status.<br>3. **Queued delivery preference recheck:** `deliver_channel_notification` (`notifications/jobs.py`) checks `link.status == "active"`, but does not check a channel preference setting when the worker runs. |
| **Configuration / Live Evidence** | • **Unrecorded Live Evidence:** Live verification of Telegram, WhatsApp, and app-only channel choices and opt-out behavior. |

### 4.3 Session 03 — Basic-versus-Complex Agent Reply Policy (Semi-Automation)

| Aspect | Status / Findings |
|---|---|
| **Existing Code** | • `app/agent/delegation.py` implements action-level `DelegationPolicy` (`dm.send`, `comment.reply`, `comment.private_reply`, etc. with `automatic`, `ask`, `off`).<br>• `app/agent/dm.py` checks `recent_transcript_present` (`require_human=True`) to force `ask` when a voice transcript is in the last 10 inbound messages.<br>• `app/policy/rules_reply.py` and `app/inbox/escalation.py` implement deterministic keyword flags (`complaint`, `refund`, `discount`, `legal`, `health_safety`, `abusive`, `personal_data`), injection detection (`app/ai/injection.py`), and topic action classes on the **legacy** path only. |
| **Existing Tests** | • `tests/integration/agent/test_delegation.py`, `tests/integration/agent/test_dm.py`, `tests/unit/policy/test_reply_rules.py`, `tests/unit/inbox/test_escalation_ru_de_ar.py`. |
| **Missing Implementation / Regression Fixes** | 1. **No basic-vs-complex topic restriction on the Account Agent path:** When an owner sets `dm.send` (or `comment.reply` / `comment.private_reply`) to `automatic` on the Account Agent, `agent/delegation.py` and `agent/dm.py` do not restrict auto-send to basic verified questions (greetings, hours, location/contact, service descriptions, and allowed verified standard prices).<br>2. **No deterministic server-side complex/mixed/sensitive check on Agent DM/comment sends:** Customer messages containing escalation keywords (complaints, refunds, discounts, custom quotes, legal/health, injection signals), mixed/unclear topics, or owner-answer / calendar mutations need deterministic server-side classification and policy enforcement so they require approval (or handoff/block) even when `dm.send` is `automatic`, and recheck at approval decision and send execution (`revalidate` / `fence_action`).<br>3. **Owner-facing Agent delegation UI:** Needs clear TR/EN examples showing what auto-sends vs what requires approval under semi-automation. |
| **Open Owner Decision** | • **Pending Decision (Section B):** Owner confirmation of the proposed basic-versus-complex policy matrix in `answeres2.md` Session 03 before activating automatic replies on a pilot workspace. |

### 4.4 Session 04 — Five-Language Support on All Account Agent Reply Paths (`tr`, `en`, `ru`, `de`, `ar`)

| Aspect | Status / Findings |
|---|---|
| **Existing Code** | • `app/core/reply_languages.py` defines `REPLY_LANGUAGES = ("tr", "en", "ru", "de", "ar")` and `RTL_REPLY_LANGUAGES = frozenset({"ar"})`.<br>• `app/inbox/language.py`, `app/knowledge/formatting.py`, `app/knowledge/claims.py`, `app/inbox/escalation.py`, and `app/ai/injection.py` already support `tr`, `en`, `ru`, `de`, `ar` (implemented in Feature Phase 5 Track D for the legacy pipeline). |
| **Existing Tests** | • `tests/unit/inbox/test_language_detection_ru_de_ar.py`, `tests/unit/knowledge/test_claims_ru_de_ar.py`, `tests/unit/knowledge/test_formatting_ru_de_ar.py`, `tests/integration/agent/test_agent_language_failclosed.py` (currently asserts that `ru`/`de`/`ar` fail closed on the Agent!). |
| **Missing Implementation / Regression Fixes** | Hard-coded `("tr", "en")` restrictions remain across the Account Agent and Approved Answers UI:<br>1. `app/agent/context.py:102`: `reply_languages=[code for code in workspace.reply_languages if code in ("tr", "en")]` filters out `ru`, `de`, `ar` and causes `coordinator.py:510` to fail the session with `AGENT_UNSUPPORTED_LANGUAGE`.<br>2. `app/agent/grounding.py:63`: `ReplyValidationArgs.language: Literal["tr", "en"]` rejects `ru`, `de`, `ar` in `reply.validate`, `dm.send`, `approval.request`, `comment.reply`, `comment.private_reply`, and `content.prepare`.<br>3. `app/agent/grounding.py:133-137` & `167-172`: Server-rendered `owner_answer` wrapper and `customer_clarification` date/time question only have `tr` and `en` templates.<br>4. `app/agent/knowledge.py:151`: `answers_page()` raises `ValueError("invalid answer page")` when `language not in {"tr", "en"}`.<br>5. `app/agent/tools/broker.py:200`: `AnswersReadArgs.language: Literal["tr", "en"]` restricts `knowledge.answers` tool schema to `tr`/`en`.<br>6. `app/agent/calendar.py:530-644`: `render_calendar_reply()` takes `language: Literal["tr", "en"]` and only localizes `booked`, `rescheduled`, `cancelled`, `pending_approval`, and `available_slot` responses in Turkish and English.<br>7. `app/owner_requests/service.py:204-211`: `ask()` holding response only checks `language in {"tr", "en"}` and only has TR/EN holding text.<br>8. **Frontend Approved Answers Editor & Settings warning:** `WorkspaceSection.tsx` still displays a warning that the Account Agent only supports Turkish and English, and the approved-answer editor language selector only offers TR/EN. |
| **Configuration / Live Evidence** | • **Unrecorded Live Evidence:** Real-model (`LLM_PROVIDER=openai`) multilingual Agent journeys in `tr`, `en`, `ru`, `de`, `ar` and native-speaker review. |

### 4.5 Session 05 — Voice Notes and Image Descriptions on the Account Agent Path

| Aspect | Status / Findings |
|---|---|
| **Existing Code** | • `app/inbox/transcription.py` downloads and transcribes audio attachments into `message_transcripts`.<br>• `app/inbox/image_description.py` downloads and describes image attachments into `message_image_descriptions`.<br>• `app/policy/transcripts.py::recent_transcript_present` and `app/agent/dm.py:235` force human approval (`require_human=True`) when a succeeded transcript is among the newest 10 inbound messages. |
| **Existing Tests** | • `tests/integration/inbox/test_voice_transcription.py`, `tests/integration/inbox/test_voice_reply_path.py`, `tests/integration/inbox/test_image_description.py`, `tests/integration/agent/test_dm_transcript.py`. |
| **Missing Implementation / Regression Fixes** | 1. **No Agent wake on transcript completion/failure:** `app/inbox/transcription.py:229-238` (`wake_drafting`) explicitly checks `if controller is not None and controller.controller_mode == "agent": return`. When a voice note arrives on an agent-controlled account, the initial message webhook wakes the agent *before* transcription finishes (while the message has no text, only `[attachment: audio]`), and when `transcribe_voice_note` completes, the agent thread is never woken with a new durable `AgentEvent`!<br>2. **No Agent wake on image description completion/failure:** `app/inbox/image_description.py` never wakes either drafting or the Account Agent when `describe_message_image` finishes.<br>3. **Agent context omits transcripts and image descriptions:** `app/agent/context.py:128-144` and `app/agent/tools/broker.py:283-298` (`_thread_read`) format each turn using only `(row.text or "")[:500] or "[attachment: ...]"`. They never load `MessageTranscript` or `MessageImageDescription`, and if a customer sends typed text *with* an image, `row.text` is non-empty so even the `[attachment: image]` indicator is omitted.<br>4. **Pending media coordination:** If the agent runs while a voice note or image description on the current inbound message is still `pending`, the agent has no awareness that media processing is in progress. |
| **Configuration / Live Evidence** | • Requires `OPENAI_API_KEY`, `TRANSCRIPTION_PROVIDER=openai` (or `auto`), `IMAGE_DESCRIPTION_ENABLED=true`, and sub-processor notice / terms confirmation.<br>• **Unrecorded Live Evidence:** Live Instagram audio/image CDN fetch, transcription and vision quality on real customer voice notes and photos. |

### 4.6 Session 06 — Booking and Lead-List Coverage on the Account Agent Path

| Aspect | Status / Findings |
|---|---|
| **Existing Code** | • `app/agent/calendar.py` and `app/operations/calendar.py` implement `calendar.availability`, `calendar.list_appointments`, `calendar.book`, `calendar.modify` (reschedule/cancel), tentative busy holds for pending approvals, and operations-ledger execution with reconciliation.<br>• `app/reporting/leads.py`, `leads_csv.py`, `leads_router.py` implement the call-back lead list and audited CSV export. |
| **Existing Tests** | • `tests/integration/agent/test_calendar_agent.py`, `tests/integration/test_calendar_api.py`, `tests/unit/operations/test_calendar_unit.py`, `tests/integration/reporting/test_leads.py`, `tests/isolation/test_leads_isolation.py`, `tests/unit/reporting/test_leads_csv.py`. |
| **Missing Implementation / Regression Fixes** | 1. **Booking-only Account Agent enquiries are invisible to the Lead List:** `app/reporting/leads.py:81-116` joins `Message` to `ReplyDraft` (`ReplyDraft.covers_through_message_id == Message.id`) and requires `or_(ReplyDraft.intent.in_(("pricing", "booking")), (ReplyDraft.origin == "agent") & agent_price)`. On the Account Agent path:<br>   - `ReplyDraft.intent` is always `None`.<br>   - A booking enquiry that quotes no `pricing`-category `BusinessFact` (or uses `calendar.availability` / `calendar.book` / server-rendered `calendar_evidence` reply, or an abandoned/failed booking proposal that never creates a pricing `FactReference`) never satisfies `agent_price` and never appears on the lead list.<br>2. **Persisted enquiry evidence contract needed:** Need a minimal, scoped enquiry evidence signal for Account Agent pricing and booking enquiries (including booking-only enquiries, availability checks, or pending/failed/abandoned booking attempts) while keeping conversion strictly tied to a non-cancelled `CalendarAppointment` linked to `conversation_id` created at or after `first_at`. |
| **Configuration / Live Evidence** | • Requires Google Calendar OAuth (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI`) if live Google Calendar is used instead of mock calendar.<br>• **Unrecorded Live Evidence:** Live booking flow and lead-list conversion check on an Account Agent workspace. |

### 4.7 Session 07 — Practice Chat (`sandbox.py`) Parity for the Selected Controller

| Aspect | Status / Findings |
|---|---|
| **Existing Code** | • `app/inbox/sandbox.py` and `app/inbox/sandbox_router.py` implement `/workspaces/{id}/assistant/test-chat` (`GET`, `POST /messages`, `POST /reset`) using `AssistantTestTurn` (`migration 0046`).<br>• `frontend/src/features/test-chat/` renders the practice chat UI. |
| **Existing Tests** | • `tests/integration/inbox/test_assistant_test_chat.py` (33 tests), `frontend/src/features/test-chat/testChat.test.tsx` (16 tests). |
| **Missing Implementation / Regression Fixes** | 1. **Practice chat always runs the legacy pipeline:** `app/inbox/sandbox.py:231-275` (`prepare`) and `apply_plan` always build a legacy `DraftContext`, run legacy `drafting.make_plan`, and evaluate legacy `reply_workflow.decide`. It never inspects `AccountAgent.controller_mode`.<br>2. **Dry-run Account Agent mode needed:** When a workspace's account is configured for the Account Agent (or for pilot onboarding where all workspaces use the Account Agent), practice chat must truthfully exercise the Account Agent's language, grounding, and basic-vs-complex delegation/policy logic with simulated read/tool outcomes and a strict sandbox effect boundary (zero writes to `conversations`, `messages`, `reply_drafts`, `approvals`, `operations`, `notifications`, `customer_memories`, or `calendar_appointments`), and display the active controller mode in the UI. |
| **Configuration / Live Evidence** | • Offline and live practice chat verification with the Account Agent controller active. |

### 4.8 Session 08 — Combined Offline Acceptance Across All Six Required Feature Areas on Account Agent Accounts

| Aspect | Status / Findings |
|---|---|
| **Existing Code & Tests** | • Individual feature suites exist in `tests/integration/agent/`, `tests/integration/content/`, `tests/integration/inbox/`, `tests/integration/reporting/`, and `frontend/e2e/`.<br>• **Gap:** Carousel (`feed_carousel`) and Reel (`reel`) publishing exist in `app/content/` and `app/operations/publish.py`, while `app/agent/content.py:75,107,219` explicitly restricts Agent owner-task content tools to `feed_image` and `story_image` (`"carousel or reel content is not available to the agent"`), whereas the Web UI / Content module supports all five formats (Feed image, Story image, Template card, Carousel, Reel).<br>• **Follow-up Gap (`app/inbox/follow_up.py`):** Follow-ups explicitly exclude agent-controlled accounts (`workflows.md §Follow-up message`). Per `answeres2.md` Session 08, follow-ups must either be explicitly implemented/tested for Agent accounts or recorded as disabled by default without excluding any of the six required feature areas (DMs, publishing, comments, voice notes, bookings, lead lists). |
| **Missing Verification** | • Combined offline acceptance suite running all required journeys together on an Account Agent workspace after Sessions 01–07 land, plus starting the local PostgreSQL container (`localhost:5433`) to run the full combined DB-backed test suite. |

### 4.9 Session 09 — Assisted Onboarding Runbook, Pilot Terms, and Measurement Alignment

| Aspect | Status / Findings |
|---|---|
| **Existing Docs & Code** | • `docs/operations/pilot-onboarding-checklist.md` (currently written for 1–5 businesses, legacy topic policies set to "Önce bana sor", and TR/EN only).<br>• `docs/product/pricing-and-unit-economics.md` (Section 3.1 specifies 30-day free pilot + 990 TRY/month + KDV founder package; Section 8 P-19 table is dated 2026-11-16 and still marks WhatsApp, `ru`/`de` languages, and comment-to-DM as "Planned" / not built).<br>• `app/plans/cli.py` provides `plan-usage`, `plan-set`, `plan-reset`, `plan-extend`. |
| **Missing Implementation / Docs Alignment** | 1. Update `pilot-onboarding-checklist.md` for the 10–15 local business target, Account Agent activation, Telegram-first channel choice (with WhatsApp/app-only options), 5 reply languages, and confirmed semi-automation policy.<br>2. Add a structured onboarding record template (without credentials) covering business, verified facts, languages, channel checks, trial start/end (7 or 30 days), agreed package, operator, and acceptance evidence.<br>3. Reconcile `pricing-and-unit-economics.md` Section 8 with Feature Phases 1–5 and Pilot Readiness deliverables without inventing automated billing.<br>4. Define persisted-record pilot measurement queries/report fields for first-response time, reply/approval workload, linked appointments, and failure/unknown outcomes, keeping the 5% missed-customer money estimate explicitly illustrative. |

---

## 5. Inventory of Live Acceptance: Completed vs. Pending

Per Session 00 instructions, owner-reported readiness is respected as the starting context, while distinguishing what has recorded live evidence in the repository versus what remains unrecorded or pending live verification.

### 5.1 Live Infrastructure Confirmed in Session 00
1. **Railway Production Environment (`agentnest` project):**
   - Verified read-only via Railway MCP on 2026-11-19: `Postgres`, `api`, `worker`, `web` (`https://web-production-b2f30.up.railway.app`), and `landing` (`https://landing-production-945f7d94.up.railway.app`) are **Online** (`SUCCESS`), with `api`, `worker`, and `web` deployed from commit `e1c9f13` on 2026-11-18T18:53:45Z.
2. **GitHub Actions Main CI (Historical Gate 1):**
   - Recorded in `roadmap.md` / `gate-1-closeout.md` at commit `dadf673` (2026-10-25), and updated through commit `e1c9f13` on `main`.
3. ** Earlier Meta Dev-Mode Probe Note (2026-10):**
   - `platform-capabilities.md` §1.8 notes one 2026-10 check on `subscribed_apps` where `messages` was accepted and `message_echoes` returned error 100 (`oauth-account-identity-fix.md`).

### 5.2 Unrecorded / Pending Live Acceptance (Must Be Completed or Explicitly Flagged in Session 11)
None of the following have recorded live execution evidence in `docs/` yet:
1. **Telegram Live Bot E2E (Priority 1 after Session 01 fix):** Real notification dispatch from `notify()` -> worker delivery -> real phone Telegram receipt -> single-use `act:<token>` inline approval button tap -> exact operation execution.
2. **Channel Choice Live Check:** Switching between Telegram, WhatsApp (if configured with a Meta WABA number and approved templates), Web Push (on Android Chrome / iOS 16.4+ PWA), and app-only.
3. **Real-Model (`LLM_PROVIDER=openai`, `gpt-6-luna`) Account Agent Evals & Journeys:** Running the Account Agent and legacy evals against the live OpenAI Responses API across all five languages (`tr`, `en`, `ru`, `de`, `ar`), recording model IDs, token usage, latency, and human quality review.
4. **Live Voice Note & Image Description Quality:** Real Instagram CDN audio/image download (`HttpsAudioFetcher`, `HttpsImageFetcher`), `gpt-4o-mini-transcribe` transcription accuracy, and vision description accuracy on real customer media.
5. **Live Meta Instagram End-to-End Workflows (V-01 to V-09, V-12, R75-01 to R75-06):**
   - Real Instagram OAuth connect/reconnect and profile/caption import (V-12).
   - Real customer DM webhook -> Account Agent basic auto-reply & complex approval-gated reply -> real Instagram DM delivery and native-app echo supersession (V-02, V-08).
   - Real comment webhook (`subscribed_apps` for `comments`) -> Account Agent `comment.private_reply` one-shot DM and customer reply continuation (R75-01..06; note that public comment reply and moderation remain disabled on real accounts).
   - Real S3/R2 presigned URL media fetch and publishing for Feed image, Story image (V-03, V-09), template card, Carousel, and Reel.
6. **Live Calendar Booking & Lead List Conversion:** Booking an appointment through the Account Agent, verifying calendar provider creation, and confirming the conversation leaves the call-back lead list upon confirmed appointment creation.

---

## 6. Unresolved Owner & Product Decisions (Tracked for Sessions 02–09)

These open items from `answeres2.md` Section B are explicitly labelled and separated from engineering bugs:

| # | Decision / Unknown | Current Baseline State | Required Resolution Boundary |
|---|---|---|---|
| **U-01** | **Basic vs. Complex Reply Policy Matrix** | Proposed matrix is in `answeres2.md` Session 03 (greetings, hours, location/contact, services, and allowed verified standard prices = basic automatic; mixed/unclear, custom quotes, discounts, complaints/refunds/sensitive, voice-derived, and bookings/publishing/moderation = approval or handoff). | Must be confirmed by owner before enabling automatic replies on a pilot workspace (Session 03). |
| **U-02** | **Free Pilot Duration (1 Week vs. 1 Month)** | `pricing-and-unit-economics.md` §3.1 states 30 days free + 990 TRY/month + KDV founder package; owner's latest answer left 1 week or 1 month open. | Support both 7 and 30 days in the onboarding record; owner to settle before pitching the first business (Session 09). |
| **U-03** | **"Other Languages" Beyond `tr`, `en`, `ru`, `de`, `ar`** | Central registry `REPLY_LANGUAGES` has the 5 named languages; other languages fail closed to human handling. | Deliver the 5 named languages in Session 04; name any additional language before promising it. |
| **U-04** | **Pilot Success Numeric Targets & Measurement Period** | Outcomes are defined (faster replies, less owner work, more appointments, reliable features), but numeric targets and review window are unset. | Record baseline and pilot measurements from persisted records (Session 09); owner to set numeric targets before evaluating pilot success. |
| **U-05** | **Follow-Ups on Account Agent Accounts** | `app/inbox/follow_up.py` is default-off, approval-required, and currently skips Account Agent accounts. | Keep opt-in and approval-required; either keep disabled on Agent pilot accounts or explicitly add an Agent-compatible follow-up path in Session 08. |
| **U-06** | **Legal / KVKK Counsel Review (Gate 3 & Sub-Processor Notice)** | Legal templates exist (`docs/legal/`), including OpenAI speech/vision sub-processor entries and lead-list KVKK question, marked awaiting counsel sign-off. | Tracked under Gate 3 before commercial rollout. |

---

## 7. Session 00 Acceptance Checklist

- [x] **Dated baseline recorded:** 2026-11-19, Git commit `e1c9f13` on `main`, single Alembic migration head `0100`.
- [x] **Actual agent controller settings inspected:** `account_agents`, `agent_delegations`, `coordinator.py`, `context.py`, `grounding.py`, `dm.py`, `calendar.py`, `content.py`, and `config.py` verified and documented.
- [x] **Existing test commands and static checks verified:** `alembic heads`, `ruff check`, `ruff format --check`, `mypy app`, `lint-imports`, `pytest --collect-only` (5,986 tests), 529 pure unit tests, `npm run lint`, `npm run typecheck`, `npm run i18n:check`, and targeted Vitest suites executed and recorded. Local Docker Postgres port `5433` offline status explicitly noted.
- [x] **Read-only deployment evidence recorded:** Railway `agentnest` production environment inspected read-only (`api`, `worker`, `web` online at `e1c9f13`; `landing` online at `1a58d41`; `Postgres` online).
- [x] **Requirement-to-code-and-test checklist complete:** Every session requirement (Sessions 01–09) mapped to exact files, existing tests, missing implementation gaps, and live verification dependencies.
- [x] **Every unknown labelled:** Unresolved product decisions (`U-01` through `U-06`) and unrecorded live evidence items explicitly separated from offline test results.
