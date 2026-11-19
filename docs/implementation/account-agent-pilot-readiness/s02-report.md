# Session 02 Report — Make Notification-Channel Choice Explicit

- **Date:** 2026-11-19 (Europe/Istanbul)
- **Plan:** [Account Agent Pilot Readiness](../../../answeres2.md) — Session 02
- **Local Git Baseline:** branch `main`, commit `e1c9f1367f63ed4afcd7e78b075c48a61c408fd8` (`e1c9f13`) + Session 01 work
- **Alembic Migration Head:** `0101` (`20261119_0101_channel_preferences.py`, parent `0100`)

---

## 1. Changes Made and Why

1. **Explicit Notification Channel Preferences Contract (`channel_preferences` Table & Migration 0101):**
   - Implemented `ChannelPreference` model in `backend/app/identity/models.py` scoped by `(workspace_id, user_id, channel)` with unique constraints, audit triggers, and check constraints (`channel IN ('telegram', 'whatsapp')`).
   - Created Alembic migration `0101` (`backend/migrations/versions/20261119_0101_channel_preferences.py`) with down-revision `0100`.
   - Migration enforces PostgreSQL Row-Level Security (`ENABLE` + `FORCE ROW LEVEL SECURITY`) and registers `tenant_isolation_policy` (`INV-01`).
   - **Migration Seeding:** Migration 0101 seeds active links as `enabled=True` (`INSERT INTO channel_preferences ... SELECT ... FROM channel_links WHERE status = 'active' ON CONFLICT DO NOTHING`) so existing linked owners seamlessly continue receiving notifications without unsolicited subscriptions.
   - Registered `"channel_preferences"` in `TENANT_TABLES` in `backend/app/core/db.py`.

2. **Truthful Channel Delivery State Contract:**
   - In `backend/app/identity/channels.py`, implemented `get_channel_delivery_status` deriving five truthful mutually exclusive states:
     - `unconfigured`: Server lacks credentials for the channel (`telegram_configured == False` or `whatsapp_configured == False`).
     - `unlinked`: Server is configured, but the user has no active link.
     - `disabled`: User has an active link, but channel preference is disabled (`enabled=False`).
     - `delivery_failure`: User has an active link and enabled preference, but the most recent `notification_deliveries` row failed (`status == "failed"`), exposing `last_error`.
     - `connected`: Channel is configured, linked, enabled, and healthy.
   - Added `telegram_configured` property in `backend/app/core/config.py` verifying both bot token and bot username.
   - Updated `ChannelAvailabilityOut` schema in `backend/app/identity/schemas.py` and `/availability` endpoint in `backend/app/api/v1/channels_router.py` to truthfully report both `whatsapp` and `telegram` server credential readiness.

3. **Preference Endpoints (`GET/PUT /workspaces/{ws}/channels/preferences`):**
   - Added `GET /preferences` returning `ChannelPreferencesOut` (`telegram`, `whatsapp`, `app_only`, and detailed `channels` status map).
   - Added `PUT /preferences` accepting `ChannelPreferencesIn` (`telegram`, `whatsapp`, `app_only`):
     - `app_only=True` atomically disables all external channels and sets `app_only=True`.
     - Conflicting requests (`app_only=True` with `telegram=True` or `whatsapp=True`) fail validation with 422 (`app_only_conflict`).
     - Individual channel toggling (`telegram: bool`, `whatsapp: bool`) updates preferences and emits an audit record (`channel_preference.updated`).
     - Foreign workspace or unauthenticated access is rejected via `require_membership("settings.view")` (`INV-01`).

4. **Lifecycle Auto-Enabling and Auto-Disabling:**
   - In `backend/app/identity/channels.py`:
     - `redeem_link_code`: When an owner links a channel via bot code, preference is automatically set to `enabled=True`.
     - `unlink_by_user`: When an owner unlinks via web settings, preference is set to `enabled=False`.
     - `unlink_by_channel`: When an owner sends `/unlink` to the bot, preference is set to `enabled=False`.

5. **Dispatch & Worker Rechecks:**
   - In `backend/app/notifications/telegram_dispatch.py` and `backend/app/notifications/whatsapp_dispatch.py`:
     - Evaluates `is_channel_enabled(session, workspace_id, recipient_user_id, channel)` inside the transaction before recording delivery or enqueueing jobs. Disabled channels are skipped immediately.
   - In `backend/app/notifications/jobs.py` (`deliver_channel_notification`):
     - Rechecks `is_channel_enabled` when the background worker runs. If an owner toggled preference off while the notification was queued in Postgres, the worker marks `delivery.status = "failed"`, records `delivery.last_error = "channel_disabled_by_preference"`, and terminates without making external HTTP requests.
     - Web Push remains an independent device-level opt-in (`push_preferences`).
     - In-app notifications remain unaffected and deliver regardless of external channel choices.

6. **Frontend Settings UI & i18n:**
   - In `frontend/src/features/settings/Channels.tsx`:
     - Added dedicated Notification Channel Preferences section offering Telegram, WhatsApp, and App-only.
     - Rendered truthful status badges (`connected`, `unlinked`, `disabled`, `delivery_failure`, `unconfigured`).
     - Added switches for toggling Telegram and WhatsApp notifications for linked accounts.
     - Added "Yalnızca Uygulama" / "App only" button to switch to app-only notifications with an active indicator banner.
     - Displayed inline error notes when a channel is in `delivery_failure` state (`Son bildirim bu kanala iletilemedi`).
     - Preserved existing WhatsApp conditional rendering (hidden when unconfigured and unlinked).
   - Regenerated OpenAPI types (`frontend/openapi.json` & `frontend/src/api/schema.d.ts`) and updated `frontend/src/api/types.ts`.
   - Added query hooks `useChannelPreferences` and `useUpdateChannelPreferences` in `frontend/src/features/settings/hooks.ts`.
   - Added TR and EN locale strings in `frontend/src/i18n/locales/tr/common.json` and `frontend/src/i18n/locales/en/common.json`.

7. **Documentation & Contracts:**
   - Documented `channel_preferences` contract, truthful channel states, migration seeding, and worker recheck rules in `docs/architecture/integrations.md` §5.1a.
   - Documented `/channels/preferences` and `/channels/availability` routes in `docs/architecture/api-design.md`.

---

## 2. Files and Migrations Changed

### Files Created:
- `backend/migrations/versions/20261119_0101_channel_preferences.py`
- `backend/tests/unit/identity/test_channel_preferences_unit.py`
- `backend/tests/isolation/test_channel_preferences_isolation.py`
- `docs/implementation/account-agent-pilot-readiness/s02-report.md`

### Files Modified:
- `backend/app/api/v1/channels_router.py`
- `backend/app/core/config.py`
- `backend/app/core/db.py`
- `backend/app/identity/channels.py`
- `backend/app/identity/models.py`
- `backend/app/identity/schemas.py`
- `backend/app/notifications/jobs.py`
- `backend/app/notifications/telegram_dispatch.py`
- `backend/app/notifications/whatsapp_dispatch.py`
- `docs/architecture/api-design.md`
- `docs/architecture/integrations.md`
- `frontend/openapi.json`
- `frontend/src/api/schema.d.ts`
- `frontend/src/api/types.ts`
- `frontend/src/features/settings/Channels.tsx`
- `frontend/src/features/settings/channels.test.tsx`
- `frontend/src/features/settings/hooks.ts`
- `frontend/src/i18n/locales/en/common.json`
- `frontend/src/i18n/locales/tr/common.json`

### Migration Revision:
- `0101` (head, parent `0100`).

---

## 3. Checks Actually Executed and Their Results

| Check / Command | Scope | Result | Notes |
|---|---|---|---|
| `uv run alembic heads` | `backend/` | **PASS** | Single head `0101 (head)` |
| `uv run ruff check .` | `backend/` | **PASS** | Clean, 0 errors |
| `uv run ruff format --check .` | `backend/` | **PASS** | 904 files already formatted |
| `uv run mypy app` | `backend/` | **PASS** | Success: 0 issues in 464 source files |
| `uv run lint-imports` | `backend/` | **PASS** | Contracts: 27 kept, 0 broken |
| `uv run pytest tests/unit/identity/test_channel_preferences_unit.py -v` | `backend/` (13 unit tests) | **PASS** | 13 passed in 0.25s (offline, in-memory double) |
| `npm.cmd run lint` | `frontend/` | **PASS** | `eslint .` exited 0 with 0 errors |
| `npm.cmd run typecheck` | `frontend/` | **PASS** | `tsc -b --noEmit` exited 0 with 0 errors |
| `npm.cmd run i18n:check` | `frontend/` | **PASS** | 2977 keys, 2125 literal `t()` calls verified |
| `npm.cmd test -- --run src/features/settings/channels.test.tsx` | `frontend/` (10 tests) | **PASS** | 10 passed in 1.92s |

---

## 4. Acceptance Criteria Satisfied

- [x] **Owner can select and change channels:** Dedicated settings controls allow toggling Telegram and WhatsApp preferences independently.
- [x] **Multiple opt-ins supported:** An owner can opt into both Telegram and WhatsApp at the same time.
- [x] **App-only choice supported:** Owners can select "App only", which turns off all external channel delivery while keeping in-app notifications active.
- [x] **Truthful channel states shown:** UI badges and API truthfully reflect `connected`, `unlinked`, `disabled`, `unconfigured`, and `delivery_failure`.
- [x] **Deselected/unlinked channels stop delivering:** `dispatch_telegram` and `dispatch_whatsapp` check `is_channel_enabled` before recording delivery rows or enqueuing jobs.
- [x] **Queued delivery rechecked at runtime:** `deliver_channel_notification` in `jobs.py` checks `is_channel_enabled` and aborts delivery if preferences changed while queued.
- [x] **Failure isolation:** Delivery failure in one channel does not alter or remove the in-app notification or block other selected channels.
- [x] **Foreign-workspace and unauthorized changes rejected:** `require_membership("settings.view")` rejects foreign workspace IDs with 404 (`INV-01`).
- [x] **Migration 0101 seeds active links:** Active links are seeded as `enabled=True` without unsolicited new subscriptions.
- [x] **WhatsApp boundaries preserved:** Button-only boundary, approved templates, and quiet hours retained; no free-text commands added to WhatsApp.

---

## 5. Remaining Failures, External Dependencies, and Unresolved Decisions

- **Local PostgreSQL (port 5433):** Docker engine remains stopped on the developer machine, so DB-backed isolation tests (`test_channel_preferences_isolation.py`) were authored and linted, and will run when the PostgreSQL container is started in Session 10.
- **Unresolved Product Decision (from `answeres2.md` Section B):** Owner decision on basic-versus-complex topic classification matrix before activating autonomous Agent replies (scheduled for Session 03).

