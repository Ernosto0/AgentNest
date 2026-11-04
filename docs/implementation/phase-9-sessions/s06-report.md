# Phase 9 — Session 06 Report: Approval Inline Buttons, Action Tokens & Owner Questions

- **Session:** `S06` (`docs/implementation/phase-9-sessions/phase-09-sessions.md` §Session 06, `docs/implementation/phases/phase-09-owner-channel.md` `P9-04`, `P9-05`, `P9-06`)
- **Date:** 2026-11-04
- **Status:** `complete` (Single-use action tokens, Telegram inline approval buttons, callback query dispatch with replay protection, Phase 7.5 owner questions delivery and answering round-trip, and 100% test coverage)
- **Branch / Commit Baseline:** `main` at `bf8ffda` + Sessions 01, 02, 03, 04, and 05 foundation
- **Alembic Migration Head:** `20261104_0041_action_tokens.py` (revision `0041`, down_revision `0040`, 69 database tables total)

---

## 1. Summary of Implemented Artifacts & Contracts

| Artifact / File | Status | Implementation Summary |
|---|---|---|
| `backend/migrations/versions/20261104_0041_action_tokens.py` | **Created** | Migration `0041` creating `action_tokens` table with UUID PK, workspace/approval/user foreign keys (CASCADE), SHA-256 token hash (unique, indexed), decision constraint (`approved`, `rejected`), payload hash, expiry, and used timestamp. RLS enabled and forced with tenant policy. Table grants configured for `agentnest_app`, `agentnest_worker`, and `agentnest_migrator`. Included `resolve_action_token_by_hash` SECURITY DEFINER helper. |
| `backend/app/approvals/models.py` | **Updated** | Added `ActionToken` SQLAlchemy model mapping to `action_tokens` with workspace isolation and composite foreign key relationships. |
| `backend/app/approvals/service.py` | **Updated** | Added `ApprovalService` namespace wrapper providing `decide`, `request`, `cancel_for_subject`, and `assert_executable` helpers for clean modular consumption without leaky direct submodule calls. |
| `backend/app/approvals/action_tokens.py` | **Created** | Implemented `ActionTokenService`: `create_action_token` (generates 16 cryptographically secure random bytes base64url, hashes with SHA-256, stores record, returns raw token) and `consume_action_token` (validates token existence, verifies `used_at IS NULL`, checks `clock.now() < expires_at`, enforces channel user identity binding, and marks token used). |
| `backend/app/integrations/channels/telegram/adapter.py` | **Updated** | Formats `approval.requested` with rich preview, simulated environment badge (`[SİMÜLASYON]`, INV-09), Instagram account name, customer context, and Telegram inline keyboard buttons (`✅ Onayla` / `❌ Reddet` with `act:<token>` callback data and web deep link). Formats `owner_question.created` notifications with question body, category, and reply guidance. |
| `backend/app/integrations/channels/telegram/dispatcher.py` | **Updated** | Added callback query routing: intercepts `callback_query` updates with data starting with `act:` and dispatches them to `handle_approval_callback`. |
| `backend/app/integrations/channels/telegram/handlers.py` | **Updated** | Implemented `handle_approval_callback` (consumes action token, calls `ApprovalService.decide`, answers callback query with toast alert, edits original Telegram message to show decision badge and strip buttons, and handles already decided, expired, unauthorized, and stale states with user-friendly alerts). Added `_handle_owner_question_answer` supporting both reply-to and `cevap:` prefix inputs. |
| `backend/tests/unit/approvals/test_telegram_action_tokens.py` | **Created** | Comprehensive unit and scenario test suite verifying token generation/hashing/consumption (INV-16), single-use approval button tap sending reply (AC-1, INV-15), replay protection preventing duplicate operations (AC-1, INV-06), unauthorized user button tap rejection, expired token rejection, stale subject rejection, owner question delivery & answering, and closed/stale question reporting. |

---

## 2. Key Workflow Details

### 2.1 Action Token Generation & Cryptographic Binding (INV-16)
- When an approval request notification is sent to an owner via Telegram, `ActionTokenService.create_action_token` generates two independent tokens: one for **approve** and one for **reject**.
- Each token is 16 cryptographically random bytes encoded with URL-safe base64 (22 characters).
- The raw token is returned to the channel adapter to embed in Telegram inline keyboard `callback_data` (`act:<raw_token>`).
- The database stores only the SHA-256 hex digest (`token_hash`), bound to:
  - `workspace_id`
  - `approval_id`
  - `user_id` (the specific recipient authorized to decide)
  - `decision` (`approved` or `rejected`)
  - `payload_hash` (exact SHA-256 canonical hash of the action payload)
  - `expires_at` (matches approval expiration)
  - `used_at` (timestamp set atomically upon consumption)

### 2.2 Telegram Approval Notification & Inline Buttons (P9-04)
- Formats rich notification message in HTML containing:
  - Simulation badge (`🧪 [SİMÜLASYON]`) if simulated (INV-09).
  - Target Instagram account (`@username`).
  - Customer information (`@handle` or customer ID).
  - Customer inbound message text preview.
  - Proposed reply draft or action summary.
- Attaches an `InlineKeyboardMarkup`:
  - Row 1: `✅ Onayla` (`act:<token_approve>`) and `❌ Reddet` (`act:<token_reject>`).
  - Row 2: `📱 Uygulamada Aç` (deep link to web approval dashboard).

### 2.3 Callback Query Processing & Replay Protection (AC-1, INV-06, INV-15)
1. **First Button Tap:**
   - Telegram webhook receives `callback_query` update with `data="act:<token>"`.
   - `ActionTokenService.consume_action_token` locates the token record by SHA-256 hash.
   - Verifies:
     - Token has not been consumed (`used_at IS NULL`).
     - Token has not expired (`clock.now() < expires_at`).
     - Channel user ID matches the linked user's identity.
   - Atomically updates `used_at = clock.now()`.
   - Invokes `ApprovalService.decide(session, clock, ctx, approval.id, decision=..., payload_hash=..., channel="telegram")`.
   - The approval's domain handler executes (e.g. For `reply_draft`, transitions draft status to `queued` and enqueues a `send_reply` job in `jobs` ledger preceded by committed operation record, satisfying INV-15).
   - Calls `tg_client.answer_callback_query(callback_query.id, text="✅ Onaylandı")`.
   - Edits the Telegram message via `tg_client.edit_message_text` to append decision confirmation with decider's name and removes the inline keyboard buttons.
2. **Second Button Tap (Replay / Concurrent Click):**
   - Replaying the same token or tapping the sister token after decision fails with `APPROVAL_ALREADY_DECIDED`.
   - Handled gracefully:
     - Displays a modal alert to the user: `Bu onay zaten karara bağlandı / Already decided` (`show_alert=True`).
     - Removes any remaining buttons via `edit_message_reply_markup`.
     - Zero side effects: no duplicate jobs, no duplicate messages sent (INV-06, AC-1).
3. **Security Boundaries:**
   - **Unauthorized User:** If a forwarded approval message button is tapped by another user, returns `FORBIDDEN` / `Bu onay için yetkiniz yok / Unauthorized` modal alert without altering approval state.
   - **Expired Approval:** Tapping an expired token displays `Onay süresi doldu / Approval expired` modal alert.
   - **Stale Approval:** If the underlying subject was edited (e.g. Reply draft text changed, incrementing version), `ApprovalService.decide` rejects with `APPROVAL_STALE` (`Onay içeriği değişti / Approval stale` alert).

### 2.4 Phase 7.5 Owner Questions Round-Trip (ADR-024)
- **Delivery:** Notifications for `owner_question.created` format question details, category (e.g. *Müsaitlik / Randevu*), and customer context with a reminder that replying to the message supplies business information.
- **Inbound Answering:**
  - Owner replies to the notification message or types `cevap: <text>`.
  - Routed to `_handle_owner_question_answer`, which invokes `app.owner_requests.service.decide(..., AnswerRequest(...))`.
  - Serves strictly as **informational input** to the assistant agent, never direct action approval (INV-04).
  - Confirms delivery to Telegram: `✅ Bilgi kaydedildi ve asistana iletildi`.
- **Freshness & Stale Handling:**
  - If the question was already answered, expired, or cancelled, reports current status cleanly: `⚠️ Bu soru artık yanıt beklememektedir. Mevcut durum: <code>answered</code>`.

---

## 3. Verification Outcomes

### 3.1 Static Analysis & Quality
| Check | Command | Exit Code | Result Summary |
|---|---|---|---|
| Backend Lint | `uv run --directory backend ruff check .` | `0` | All checks passed cleanly across 614 files |
| Backend Formatting | `uv run --directory backend ruff format --check .` | `0` | 614 files verified formatted |
| Backend Typecheck | `uv run --directory backend mypy app` | `0` | Success: no issues found in 320 source files |
| Import Architecture | `uv run --directory backend lint-imports` | `0` | 19 contracts kept, 0 broken |

### 3.2 Test Suite Execution
| Test Suite | Command | Exit Code | Result Summary |
|---|---|---|---|
| Telegram Action Tokens Unit & Scenario Suite | `uv run --directory backend pytest tests/unit/approvals/test_telegram_action_tokens.py -v` | `0` | `8 passed in 5.57s` |
| Combined Session 04, 05, 06 Channel Regression Suite | `uv run --directory backend pytest tests/unit/approvals/test_telegram_action_tokens.py tests/unit/integrations/channels/test_telegram_commands_media.py tests/contract/test_telegram_adapter.py -v` | `0` | `26 passed in 10.20s` |

---

## 4. Invariant & Security Compliance

- **INV-04 (No Direct Execution from Untrusted / Free Text):** Inbound answers to owner questions provide grounding information to the agent thread; they never directly publish content or bypass approvals.
- **INV-06 (Idempotency & Replay Protection):** Action tokens are consumed exactly once in the database (`used_at`). Duplicate webhook deliveries or second button presses return `APPROVAL_ALREADY_DECIDED` and never generate duplicate ledger jobs or outbound messages.
- **INV-09 (Simulation Transparency):** Simulated notifications prominently display `🧪 [SİMÜLASYON]` in Turkish and `🧪 [SIMULATED]` in English.
- **INV-15 (Committed Operation Record Before External Side Effects):** Deciding an approval triggers atomic domain execution which commits the operation record before enqueueing the background delivery job.
- **INV-16 (Cryptographic Action Token Binding):** Action tokens bind exact workspace, approval, authorized user ID, decision (`approved`/`rejected`), and payload hash; they expire with the approval and are stored as SHA-256 hashes.
- **ADR-012 & ADR-014 (Owner Channel & Approval Model):** Channel-agnostic approval decisions are cleanly orchestrated through `ApprovalService.decide` with single-use guarantee.
- **ADR-024 (Agent Authority & Owner Questions):** Owner answers seamlessly update `OwnerQuestion` and emit agent events without breaking tenant isolation.

---

## 5. Next Steps

With the completion of Session 06, all core functional and security objectives of **Phase 9 (Owner Channel — Telegram Integration)** are fully implemented:
1. Channel link token lifecycle and security isolation (Session 01-03).
2. Telegram Bot API adapter, client, and webhook ingestion (Session 04).
3. Natural language query routing, photo ingestion, and command dispatch (Session 05).
4. Inline approval buttons, action tokens, single-use replay protection, and owner question answering round-trip (Session 06).
