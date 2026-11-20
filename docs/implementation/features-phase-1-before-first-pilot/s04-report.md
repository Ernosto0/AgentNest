# Feature Phase 1, Session 04: Web Push owner channel (F-01, part 2)

**Status:** Implemented and verified offline (backend tests, frontend tests, migration up/down). Not committed.
**Real-device test: NOT DONE.** Nothing was sent to a real push service, and no Android or iOS device was used. Every push in the tests goes to a fake sender or a fake HTTP transport. The exact manual steps are in section 7.
**Baseline:** `main` at `f1cc494` plus the uncommitted Sessions 01 to 03.
**Migration head:** `0048` (`20261116_0048_web_push_delivery.py`, down revision `0047`). The next free migration is `0049`.

## 1. What was built

### Backend
- **`WebPushChannel`** (`app/integrations/channels/web_push/adapter.py`) implements `OwnerChannel`; `registry.get_channel("web_push")` imports it lazily, so web-only operation never loads `pywebpush`.
- **`payloads.py`**: title and body are fixed text per notification type and language (plus a "[Simulation]" marker, INV-09); the link is a same-origin path built only from UUIDs; the tag is `type:notification id`. Nothing else is read from the notification.
- **`endpoint_policy.py`** and **`sender.py`**: the SSRF guard and the only module that imports `pywebpush` / `py_vapid` (section 3).
- **Supported types** (`notifications/catalog.py`, `PUSH_TYPES`, three opt-in categories): `approvals` = `approval.requested`; `questions` = `owner_question.requested`, `owner_question.window_closed`; `failures` = `content.failed`, `reply.failed`, `account.needs_reauth`.
- **Opt-in** (`push_preferences.py`, table `push_preferences`, migration `0048`, tenant, forced RLS): one row per (workspace, user, category), no row means off. `GET` and `PUT /…/push-subscriptions/preferences` (own preferences only).
- **Dispatch** (`push_dispatch.py`, called from `notify()` inside the notification's transaction): only when push is configured, the type is pushable, the recipient opted into the category and has an active device. It runs inside a savepoint and never raises into `notify`, so a push problem cannot lose a notification or the state change behind it.
- **Ledger and policy**: the existing `notification_deliveries` ledger and `delivery_policy.py` (quiet hours 22:00 to 08:00 workspace time; critical severity, `account.needs_reauth` and an approval expiring within 2 hours bypass). Migration `0048` adds `web_push` to the ledger's `channel` CHECK constraint (it only allowed `web` and `telegram`). `dispatch_channel_notification` and its payload model moved to `notifications/delivery_ledger.py` and are re-exported from `notifications/jobs.py` (see deviations: importing the job module from `notify` would have made every module that uses `notify` reach the Telegram adapter and break two more import contracts).
- **Delivery job**: the existing `deliver_channel_notification` (3 attempts, backoff 5/30/120 s). Changes: a recipient needs no chat link for `web_push`; a channel can mark a result `retryable` (the row stays `pending`, the job raises `RetryableError`, the worker retries, the last attempt marks the row `failed` and the job dead) or `terminal` (row `failed`, job succeeds, no retry). Telegram sets neither flag and behaves as before.
- **Outside transactions**: the adapter reads everything it needs, calls `session.rollback()` to end its read transaction, sends to each device, then records results in a second short transaction (a test asserts the session has no open transaction inside the sender).
- **Result handling**: 404 or 410 revokes that device (`revoked_at`, audit `push_subscription.revoked` by the system actor with a `reason`); a send that succeeds sets `last_success_at`; a device whose endpoint is never allowed is revoked; an address or DNS problem keeps the device and fails the send. Delivered when at least one device accepted. 5xx, 429, timeout and DNS errors retry. Opted out meanwhile, user left the workspace or deactivated, no device: terminal `failed` with a fixed `last_error`.
- **Dependency note (handoff item 3)**: the sender calls the synchronous `pywebpush.webpush()` (uses `requests`). **`aiohttp` is still required**: `pywebpush/__init__.py` imports it at module load, so it cannot be removed while we import `pywebpush`; it is never used by our code.
- **Import-linter** (`pyproject.toml`, three contracts with ids): only the registry (and nothing in core) imports `web_push`; only `web_push.sender` imports `pywebpush` / `py_vapid` (mirrors the OpenAI SDK contract); the web push package cannot import inbox, ai, knowledge, content, commands, approvals, owner_requests, memory, agent or api. I proved by temporary probe files that each one fails when violated. `tests/unit/test_import_rules.py::test_the_web_push_contracts_are_kept` runs just these three, so they stay enforced although `test_import_contracts_are_kept` is already red. mypy: `ignore_missing_imports` for the two untyped libraries only.

### Frontend
- **Settings** (`features/settings/PushSettings.tsx`, in the Connections page under the Telegram card): this device on/off, the three category checkboxes (off until switched on), the list of the user's devices with Remove, the quiet-hours note. Renders nothing when `/config` says `enabled:false` (or fails). A blocked permission shows an explanation instead of a button; an unsupported browser says so; iOS Safari outside the installed app shows the guide.
- **Prompt** (`features/notifications/PushPrompt.tsx`, mounted in `AppShell`): offered once after the owner's first successful **approve** decision (`useDecideApproval` records it), never on first load, and it makes no request until then. "Turn on notifications" subscribes this device and switches the approvals category on. "Not now" is remembered per user and workspace. Hidden when push is not configured, the browser cannot receive pushes, the permission is already denied, or this device is already registered. On iOS Safari outside standalone mode it shows the short Add to Home Screen guide instead (iOS 16.4+ delivers pushes only to an installed app).
- **Sign-out and account switch** (`pwa/push.ts`, `useLogout`): the browser remembers which user its subscription belongs to and which server row it registered per workspace. Signing out revokes those rows (best effort, before the session ends) and drops the browser subscription; a different user subscribing on the same browser first drops the previous user's subscription; turning it off in the last workspace that uses it drops the browser subscription. Switching workspace needs nothing (the subscription belongs to user and device; a workspace only pushes to a device registered there by a user who opted in).
- TR and EN strings in a new `push.json` namespace; `openapi.json` and `schema.d.ts` patched additively (patience diff shows only added lines); `mockApi` background route for `/config` (disabled) so existing screens are unaffected.

## 2. Delivery flow, jobs, ledger and policy

1. `notify()` creates the notification (existing code), then `dispatch_web_push`.
2. If applicable: `evaluate_delivery_policy(channel="web_push")`, a `notification_deliveries` row (`pending`, or `skipped_quiet_hours`), and for `pending` an enqueued `deliver_channel_notification` job, all in the notification's transaction. A held push is not replayed in the morning; it stays in the in-app list.
3. The worker claims the row, checks the recipient is still an active member, calls `WebPushChannel.deliver_notification` with no transaction open, then records `delivered` or `failed` (or leaves `pending` for a retry).

## 3. SSRF decision (handoff item 1)

An **allowlist** is enforced on every send: `fcm.googleapis.com` (Chrome, Edge, Opera, Brave, Samsung), `*.push.services.mozilla.com`, `*.push.apple.com`, `*.notify.windows.com`. Anything else is refused and its device revoked (adding a push service is a code change). On top of that the host is resolved at every send and every address must be globally routable (loopback, private, link-local including `169.254.169.254`, CGNAT, reserved, multicast, and IPv4-in-IPv6 forms are refused; the device is kept). Redirects are never followed (`max_redirects = 0`, and a test with a redirecting transport proves the redirect target is never contacted), the timeout is 8 s, and nothing identifying is logged (a test captures the log events of a revoke, a retry and a success and searches for the endpoints, keys and VAPID key). Documented in `security-and-privacy.md`. Residual risk: the HTTP client resolves the name again when it connects; acceptable because the allowlisted names belong to the push-service operators.

The subscribe endpoint (Session 03) still accepts any public `https` host; I did not tighten it because Session 03's tests register `push.example.com`. Such a device is revoked at its first send. Tightening subscribe to the allowlist is a one-line change plus test edits; say if you want it.

## 4. Payload rule and its enforcement (handoff: payloads)

Rule written in `security-and-privacy.md` (§7.2, "Web Push payloads"): title, short fixed body, same-origin deep link, tag; no customer text, names or handles, drafts, captions, prices or titles. Enforcement: (a) the builder reads only UUIDs from `params`; (b) import-linter forbids the channel from importing any module that holds customer text; (c) `test_web_push_payloads.py` stuffs every field with distinctive customer strings for **every** supported type in tr, en, none and an unknown locale and asserts none appears (and no `http` anywhere); (d) `inbox/test_web_push_privacy.py` pushes a real inbound message and its real draft through the real pipeline and job and checks the payload the fake push service received; a message that goes to a human triggers no push.

## 5. Checks run

Environment: `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN=` (and `DEMO_TOOLS_ENABLED=true` for the broad runs), `TEST_DATABASE_URL` on my own databases `pivoris_p1s04_test` and `pivoris_p1s04b_test` (the two broad runs in parallel), `pivoris_p1s04_mig` for migrations. All dropped at the end.

| Command (from `backend/`) | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 2 files would be reformatted, both pre-existing: `app/operations/calendar.py`, `tests/integration/test_hardening_integration_regressions.py`. `app/notifications/jobs.py` is now formatted (my edit touched its one unformatted block) |
| `uv run mypy app` | Success, 359 files |
| `uv run lint-imports` | 19 kept, 4 broken (the same four as before: `narrator`, `notifications.jobs -> registry`, `reporting.home_router -> api.deps`, `commands.service -> telegram.client`); my 3 contracts KEPT. An intermediate version of my change broke 2 more contracts (see deviations); fixed |
| New tests | `test_web_push_sender.py` 69, `test_web_push_payloads.py` 54, `test_web_push_channel.py` 33, `test_push_preferences.py` 6, `test_push_preferences_isolation.py` 4, `test_web_push_privacy.py` 2, import contracts 1: all pass |
| Run A: `pytest tests/unit tests/contract tests/security tests/isolation tests/integration/notifications tests/integration/approvals tests/integration/operations tests/integration/test_cli.py tests/integration/test_health_and_errors.py` | **2217 passed, 13 skipped, 10 failed**, all 10 known pre-existing (below) |
| Run B: `pytest tests/integration/inbox tests/integration/agent tests/integration/commands tests/integration/jobs` | **768 passed, 15 failed, 1 error** (27 min). All 16 are in `agent/test_calendar_agent.py` (calendar tool `TOOL_ARGUMENT_INVALID`, the same family s03 saw), `commands/test_content_commands.py`, `commands/test_explain_reply_failure.py` and `commands/test_queries_failures_permissions.py` (reply text and message mismatches). They are not push related: re-running just those four files with `dispatch_web_push` patched to a no-op gives the identical result (15 failed, 56 passed, 1 error), and push is off in those runs anyway. I could not run them at `HEAD` (no stash or checkout), so "pre-existing" is inferred from that and from s03 seeing early failures in the same area; they are not in the known list you gave me, so please confirm |
| Migration `alembic upgrade head` / `downgrade 0047` / `upgrade head` on a scratch database | Clean both ways; constraint and table verified with `\d`; `alembic check` shows no drift for `push_preferences` |

Run A failures (all in your known list; attribution): `test_cli_migration_status_head_only_and_check_config` (hard-coded head), `test_telegram_reporting_query_exact_matching_counts` and `test_deliver_channel_notification_failure_records_error` (I ran this pair **before** my change: the same 2 failed, 16 passed; after: the same 2 fail, so nothing new; the second fails because the test has no Telegram channel link), `test_every_action_the_code_writes_is_known_to_the_feed` (only `auth.password_reset_throttled`), `test_import_contracts_are_kept` (the same 4), the two `test_invite_secrets` tests, isolation `cancel-deletion` 404, `test_meta_exposes_only_public_configuration`, `test_cors_allows_only_the_frontend_origin`.

Frontend (from `frontend/`):

| Command | Result |
|---|---|
| `npm.cmd run lint` | 3 errors, the pre-existing `no-explicit-any` in `src/app/router.tsx` |
| `npm.cmd run typecheck` | passes |
| `npm.cmd test` (PowerShell) | 52 files, 779 tests passed (18 new in `src/features/notifications/push.test.tsx`) |
| `npm.cmd run i18n:check` | passes (2428 keys) |
| `npm.cmd run build` | built OK |

Not run: `tests/browser`, `tests/e2e`, the rest of `tests/integration` (content, knowledge, reporting, policy, activity, identity, ai, demo, retention, integrations), and the frontend `scripts/ui-*.mjs` browser scripts.

## 6. Deviations, decisions and open questions

1. **Delivery was never wired.** `dispatch_channel_notification` existed but nothing called it, so Telegram notification delivery is not triggered by `notify()` either. I wired only `web_push`; Telegram is untouched. Say if Telegram should be wired the same way.
2. **Existing job did not retry.** The worker treats any exception except `RetryableError` as dead on the first attempt, so the old `raise RuntimeError` never retried. I added the opt-in `retryable` / `terminal` result flags; Telegram behaviour is unchanged (so it still does not retry).
3. **`delivery_ledger.py` split.** Calling the job module from `notify` made every module using `notify` reach the Telegram adapter and `commands`, which broke two more import contracts. The ledger entry point moved to a module that does not import the registry; `jobs.py` re-exports it, so existing imports still work.
4. **Preferences are per category, not per notification type** (three toggles over six types). Per type would be six rows of near-identical settings. The type to category map is one dictionary.
5. **A held push is not replayed.** Quiet hours record `skipped_quiet_hours` and nothing is sent later (existing policy semantics). The notification remains in the app.
6. **Partial success is delivered.** If at least one device accepted the push the delivery counts as delivered, and a device that failed transiently in that same attempt is not retried. If no device accepted and one failed transiently, all are retried; the shared `tag` makes a device replace a repeat instead of stacking it.
7. The prompt stores "first approval" and "dismissed" in `localStorage` per user and workspace; it is per browser, not synced across devices.
8. Subscribe still accepts non-allowlisted public hosts (section 3). `/config` stays workspace-scoped (it is only needed after sign-in).
9. `SENTRY`/VAPID: no new environment variable; `.env.example` unchanged.
10. Retry of a 429 uses the fixed backoff; `Retry-After` is not honoured.

## 7. Manual device test (not done; for the owner)

Prerequisites: HTTPS deployment (or a tunnel) with `WEB_PUSH_VAPID_PUBLIC_KEY`, `WEB_PUSH_VAPID_PRIVATE_KEY` (from `uv run python -m app.cli generate-vapid-keys`), `WEB_PUSH_SUBJECT` and `TOKEN_ENCRYPTION_KEYS` set; the worker running; `LLM_PROVIDER=fake` and the mock Instagram account are enough.

**Android Chrome**
1. Open the site, sign in as the owner, open Settings > Connections: the "Telefon bildirimleri" card is visible.
2. Approve one item (Approvals, or a reply draft). The prompt appears. Tap "Bildirimleri aç" and allow the browser permission. The card should say the device is on and list "Chrome on Android".
3. Create another approval (send a mock customer message so a draft needs approval). Within seconds the phone shows "Onayınız bekleniyor" with no customer text. Tap it: the app opens on Approvals. Check `notification_deliveries` has a `web_push` row `delivered` and `push_subscriptions.last_success_at` is set.
4. Quiet hours: set the phone or workspace time to 23:00 and repeat with a reply failure: expect `skipped_quiet_hours` and no push; an Instagram reauth (critical) still pushes.
5. Revoke: in Chrome site settings clear the notification permission or "Remove" the device in the app, then create an approval: no push; if you removed the subscription in the browser only, the first push gets a 404/410 and the device row gets `revoked_at` and an audit entry.
6. Sign out, sign in as another user on the same phone: the first user's device row is revoked and no push reaches that phone for the first user.

**iPhone (iOS 16.4 or later)**
1. In Safari (not installed) open the site, approve something: the prompt shows the Add to Home Screen guide instead of a permission button; Settings shows the same guide.
2. Share > Add to Home Screen, open Pivoris from the icon, sign in, open Settings > Connections > "Bu cihazda aç", allow notifications.
3. Repeat the approval test; the push should show on the lock screen with no customer text; tapping opens the installed app on Approvals.
4. Check the icon and the maskable icon on an Android adaptive launcher (Session 03 open item).

## 8. Invariants

INV-01 (new tenant table with forced RLS and policy; every query workspace-scoped; another user's, another workspace's devices and preferences are never used; tests at API, RLS and delivery level); INV-05/15 (no push is a side effect on Instagram; the send is outside any transaction); INV-06 (re-running the job on a resolved row does nothing); INV-07 (the push is a durable job); INV-09 (simulated notifications are marked in the title); INV-10 (endpoint, keys and payload never logged or stored in the ledger); INV-12 (system-initiated revoke audited in the same transaction as the state change); INV-14 (defaults unchanged: push off, nothing needs credentials); INV-19 (quiet hours in the workspace timezone through the existing policy).

## 9. Handoff to Session 05

Nothing in Session 05 (D-01) depends on this session. Open items for the owner: the device test above, the Telegram wiring question (deviation 1), and whether to restrict subscribe to the allowlist (section 3).
