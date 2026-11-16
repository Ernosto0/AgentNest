# Feature Phase 1, Session 03: Installable app and push subscriptions (F-01, part 1)

**Status:** Implemented and verified locally (backend tests, frontend tests, migration up/down, Chromium installability check on a production build). Not committed. **Nothing is sent**: no push is ever dispatched in this session. Not tested on a real phone, with a real push service, or with a real VAPID key in a deployed environment.
**Baseline:** `main` at `f1cc494` plus the uncommitted Session 01 and 02 work in the tree.
**Migration head:** `0047` (`20261115_0047_push_subscriptions.py`, down revision `0046`; confirmed head was `0046` before I started).

## 1. What was built

### Installable app (frontend)
- `frontend/public/manifest.webmanifest`: name and short name "AgentNest", Turkish description, `lang: tr`, `display: standalone`, `start_url`/`scope`/`id` `/`, `theme_color` and `background_color` `#f7f8f3` (the `--an-canvas` token; the app has no dark theme, so one colour is right), icons 192 and 512 (`any`) and 512 `maskable`.
- Icons generated from `frontend/public/app-icon-1024.png` with Pillow (a scratch script outside the repo): `icon-192.png`, `icon-512.png`, `icon-maskable-512.png`, `apple-touch-icon.png` (180), `favicon-32.png`. **The maskable icon is the same pixels as `icon-512.png`**: the source is already a full-bleed gradient and its logo disc has a radius of 300 of 1024 px (29%), inside the 40% maskable safe zone (409.6 px), which the script measured. I did not add extra padding; shrinking the logo would make the plain icon look small for no gain. A tester should still look at it on an Android adaptive-icon launcher.
- `frontend/index.html` (P-17, overlapping part): manifest link, favicon links (32 and 192), apple-touch-icon, meta description (TR), Open Graph title/description/site name/locale, `theme-color` changed from white to `#f7f8f3`, Apple/Android "web app capable" metas. Not done: `og:image` (needs an absolute URL that is not known at build time) and a dark-mode theme colour (the app has no dark theme). P-17 is therefore mostly, not fully, closed; I did not edit `pre-launch-problems.md`.
- `frontend/public/sw.js`: **push only**. Listeners: `push`, `notificationclick`, plus `install` (`skipWaiting`) and `activate` (`clients.claim`) so a new file takes over at once. **No `fetch` listener and no `caches` use**; a test asserts both. The payload is treated as untrusted: title (120 chars) and body (300) are plain text; a missing or broken payload gives a generic "AgentNest" notification. The link is resolved against `self.location.origin`; anything on another origin, `javascript:`/`data:` URLs, protocol-relative URLs, a look-alike host or an unparsable value becomes `/`. Only the path, query and hash are kept. On click it focuses and navigates an open app window, else opens one, always on the app origin.
- `frontend/src/pwa/push.ts` + `main.tsx`: `registerServiceWorker()` runs on `load` only when `import.meta.env.PROD` or `VITE_ENABLE_SW=true`. The same file has the helpers for the developer test (subscribe, unsubscribe).
- Developer test button: `frontend/src/features/dev/PushTest.tsx`, a section of the existing demo-only Developer tools page (`/more/dev`, hidden unless `DEMO_TOOLS_ENABLED`). "Subscribe this device" asks for permission, subscribes the browser with the server's public key and registers it; "Remove this device" revokes it. No query runs on page load, so the existing dev tests are unaffected. **There is no opt-in UI for users** (Session 04). Strings in TR and EN (`devPanel.push.*`, `errors.WEB_PUSH_NOT_CONFIGURED`).
- `Caddyfile` (production): CSP gains `worker-src 'self'; manifest-src 'self'` (they would have fallen back to `default-src 'self'`; now explicit and the existing packaging test still passes), and `/manifest.webmanifest` is served as `application/manifest+json`. `/sw.js` and the manifest are outside `/assets/*`, so the existing `@spa_entry` rule already serves them `no-cache` (a worker file must not be cached). Vite copies `public/` as is, so no config change was needed. Railway uses this Caddyfile through the web Dockerfile; I did not deploy anything.

### Push subscriptions (backend)
- **Table `push_subscriptions`** (migration `0047`): `id`, `workspace_id`, `user_id`, `endpoint`, `endpoint_hash`, `p256dh_ciphertext`, `auth_ciphertext`, `key_id`, `device_label`, `last_success_at`, `revoked_at`, `created_at`, `updated_at`. `ENABLE` + `FORCE ROW LEVEL SECURITY`, `tenant_isolation_policy` on `app.workspace_id` (USING and WITH CHECK), grants to `agentnest_app`/`worker`/`migrator` (copied from `0046`), added to `CATEGORY_C_TABLES` (the RLS coverage test count is now 55). Unique `(workspace_id, user_id, endpoint_hash)` and `(workspace_id, id)`. Model: `app/notifications/models.py` (`PushSubscription`).
- **Encryption:** `p256dh` and `auth` are encrypted with the existing `TokenKeyRing` (AES-256-GCM, the helper used for Instagram and Google tokens). The AAD is `push:<part>:<workspace_id>:<subscription_id>`, so a blob copied between rows or between the two columns does not authenticate (tested). `decrypt_keys()` is for the Session 04 sender only.
- **Service** `app/notifications/push_subscriptions.py`, **router** `app/notifications/push_router.py` (registered in `app/api/router.py`).
- **VAPID helpers** in `app/core/security.py` (`generate_vapid_keys`, `vapid_keys_match`, using `cryptography` only), settings in `app/core/config.py`, CLI command `generate-vapid-keys` in `app/cli.py`.
- Error code `WEB_PUSH_NOT_CONFIGURED` (409) in the catalog and both backend languages; audit actions `push_subscription.created` / `.revoked` (added to the observability catalog, the Activity group "members" and both languages, as the template-coverage test requires).

## 2. Endpoints and schema

All under `/api/v1/workspaces/{workspace_id}/push-subscriptions`, any active member, CSRF on unsafe methods (the same dependency as every other route).

| Method & path | Result |
|---|---|
| `GET /config` | `{enabled: bool, public_key: string \| null}`. With no VAPID keys: `{enabled:false, public_key:null}` (200). The private key and subject are never in it |
| `GET ` | `{items: [{id, label, created_at, last_success_at}]}`: the caller's own active devices only |
| `POST ` | body = `PushSubscription.toJSON()`: `{endpoint, expirationTime?, keys:{p256dh, auth}, label?}` (unknown fields 422). 201 `{id,label,created_at,last_success_at}` for a new device, 200 when that endpoint is already registered for the user (keys refreshed). 422 for a bad endpoint or key sizes. 409 `WEB_PUSH_NOT_CONFIGURED` without VAPID or without `TOKEN_ENCRYPTION_KEYS` |
| `DELETE /{id}` | 204, revokes (soft). Another member's id, a foreign workspace's id, a revoked or unknown id: 404 |

Responses never contain the endpoint URL or any key material (asserted in tests by searching the raw response text). The label comes from a short, derived string ("Chrome on Android") or an optional page-supplied label (max 60 characters); the raw user agent is not stored.

Rules worth knowing:
- Endpoint validation (SSRF, because the server will POST to it in Session 04): `https` only, port 443, no credentials or fragment, a dotted host name, not an IP literal, not `.local`/`.internal`, at most 2048 characters. Keys must decode to 65 bytes (P-256 point) and 16 bytes. This is static only; **the Session 04 sender must also resolve the host and refuse private addresses at send time** (a DNS name can point inward).
- Shared device: if another user of the same workspace subscribes the same endpoint, the earlier user's row is revoked, so a push can never reach whoever is signed in on a phone set up for someone else.
- At most 10 active devices per user per workspace; the oldest is revoked past that.
- `openapi.json` was patched by inserting only the 3 new paths and 5 new schemas (the CLI export rewrites the file); I checked that every path and schema of `HEAD` is unchanged and that the file equals a fresh export. `schema.d.ts` was regenerated with `npm run gen:api` (additive: 477 inserted lines in total against `HEAD`, of which 239 are Session 01's).

## 3. Settings and CLI

`WEB_PUSH_VAPID_PUBLIC_KEY`, `WEB_PUSH_VAPID_PRIVATE_KEY` (secret, in `_SECRET_FIELDS`, `SecretStr`, absent from `public_dict()` and `repr`), `WEB_PUSH_SUBJECT`. Push is on only when all three are set (`Settings.web_push_enabled`). All empty is the default and is valid, so dev and tests need no keys. Startup refuses: only some of the three set; a subject that is not `mailto:` or `https://`; a public key that is not the pair of the private key (derived and compared); no `TOKEN_ENCRYPTION_KEYS`. Also `VITE_ENABLE_SW` (frontend, dev only). Documented in `docs/operations/environment-variables.md` and `.env.example`.

`uv run python -m app.cli generate-vapid-keys` prints two `.env` lines on stdout (public, private) and a reminder on stderr; nothing is stored or logged. Keys are unpadded base64url (public: 65-byte uncompressed P-256 point; private: raw 32-byte scalar). A test proves `py_vapid` (inside `pywebpush`) can sign with a generated private key and that the signed header carries the matching public key.

## 4. Dependency

`uv add pywebpush` in `backend/`: **`pywebpush` 2.5.0**, added as `pywebpush>=2.5.0`. It is the standard maintained Web Push library (VAPID signing, RFC 8291 payload encryption, error mapping for 404/410 gone subscriptions), and writing aes128gcm payload encryption ourselves would be riskier. It brings `py-vapid` 1.9.6 and `http-ece` 1.2.1 and, in this release, `aiohttp` 3.14.5 with its transitive packages (`aiohappyeyeballs`, `aiosignal`, `attrs`, `frozenlist`, `multidict`, `propcache`, `yarl`): 11 new packages; `uv.lock` only gained lines (217 added, none removed). It is **not imported by app code yet** (Session 04 does the sending; the only use is a test of key compatibility). Open item for Session 04: `aiohttp` is a sizeable extra dependency for a sync app; if it matters, call `pywebpush.webpush()` (sync, uses `requests`) and consider pinning. Dependency audit runbook (`docs/operations/dependency-auditing-runbook.md` §5): `uv run pip-audit` after the add: **No known vulnerabilities found**. (A first run before the add failed with a PyPI read timeout, so I have no separate baseline.) `npm audit` was not run: no npm dependency was added.

## 5. Checks run

Environment for backend runs: `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local` (and `DEMO_TOOLS_ENABLED=true` for the broad runs), `TEST_DATABASE_URL` pointing at my own databases (`agentnest_p1s03_test`, `agentnest_p1s03b_test`, `agentnest_p1s03c_test`; `agentnest_p1s03_mig` for migrations). All were dropped at the end. From `backend/` unless noted.

| Command | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 3 files would be reformatted: `app/notifications/jobs.py`, `app/operations/calendar.py`, `tests/integration/test_hardening_integration_regressions.py` (the 3 known pre-existing ones; every file I wrote or changed is formatted) |
| `uv run mypy app` | Success: no issues found in 351 source files |
| `uv run lint-imports` | 4 contracts broken, none involving my modules (`narrator`, `notifications.jobs -> channels.registry`, `reporting.home_router -> api.deps`, `commands.service -> telegram.client`); the known pre-existing ones |
| `uv run pytest tests/integration/notifications/test_push_subscriptions.py` | 45 passed (before the last label-test edit: 44 passed and 1 failed because my test assumed an over-long label was truncated; the API correctly returns 422 for it, so I fixed the test). The final file was run as part of the broad run below |
| `uv run pytest tests/isolation/test_push_subscriptions_isolation.py` | 4 passed (forced RLS and policy; fail-closed without tenant; A cannot read, update, delete or insert into B under the `agentnest_app` role; unique key) |
| `uv run pytest tests/unit/core/test_web_push_settings.py` | 7 passed (key shape and match, `py_vapid` can sign with a generated key, partial/mismatched/bad-subject/no-key-ring configuration refused, private key absent from `public_dict`/`repr`, CLI prints only `.env` lines on stdout) |
| Broad run: `uv run pytest tests/unit tests/contract tests/security tests/isolation tests/integration/notifications tests/integration/test_cli.py tests/integration/test_health_and_errors.py` (`DEMO_TOOLS_ENABLED=true`) | 1954 passed, 13 skipped, **10 failed** (below) |
| Focused run: `tests/integration/activity tests/integration/identity tests/integration/inbox/test_assistant_test_chat.py tests/integration/test_seed.py tests/integration/test_hardening_integration_regressions.py` | 154 passed, **5 failed** (below) |
| Migration `uv run alembic upgrade head` / `downgrade 0046` / `upgrade head` on a scratch database | Clean both ways: head `0047`; after downgrade `alembic current` = `0046` and `to_regclass('push_subscriptions')` is null; re-upgrade OK; `\d` shows the table, forced RLS and the policy; roles got their grants. `alembic check` reports nothing for `push_subscriptions` (it reports other, pre-existing drift) |
| `uv run pip-audit` | No known vulnerabilities found |

Failures in the broad and focused runs, none caused by this session as far as I can tell (I did not re-run them at `HEAD`, since I may not stash or switch branches; the first eight match the list you gave me):
- `tests/isolation/test_workspace_isolation.py::test_the_same_requests_succeed_for_the_member_own_workspace` (`cancel-deletion` 404)
- `tests/unit/core/test_deployment_workflow_and_rollback.py::test_cli_migration_status_head_only_and_check_config` (expects head `0044`)
- `tests/unit/integrations/channels/test_telegram_commands_media.py::test_telegram_reporting_query_exact_matching_counts` and `tests/unit/notifications/test_delivery_policy.py::test_deliver_channel_notification_failure_records_error`
- `tests/unit/test_activity_templates.py::test_every_action_the_code_writes_is_known_to_the_feed` (`auth.password_reset_throttled` only; my two actions pass)
- `tests/unit/test_import_rules.py::test_import_contracts_are_kept` (the 4 broken contracts)
- `tests/security/test_invite_secrets.py` (2 tests) and `tests/integration/identity/test_members_and_invites.py` (2 tests): invite response has `email`
- `tests/integration/test_health_and_errors.py::test_meta_exposes_only_public_configuration` (`/meta` has an extra `calendar_providers` field, from other work) and `::test_cors_allows_only_the_frontend_origin` (no `access-control-allow-origin`; I did not touch CORS or `/meta`; probably the repo `.env`)
- `tests/integration/test_seed.py::test_seed_refuses_to_run_in_production`: caused by my exporting `DEMO_TOOLS_ENABLED=true` for these runs (the config refuses it in production)
- `tests/integration/test_hardening_integration_regressions.py` (`serious5...`, `serious8...`): a calendar tool argument error and an `agent_sessions` unique violation; unrelated to push

**Not run:** the full backend suite and `tests/browser`, `tests/e2e`, and most of `tests/integration` (inbox, content, operations, agent, approvals...). A full run at about 5% progress after 15 minutes showed it would take hours, so I stopped it. Those directories exercise code that my changes touch only through shared settings, the error catalog, `CATEGORY_C_TABLES` and the route list, but they are **not** proven green by me. The first characters of both aborted runs showed a handful of early failures (`F.F`, `FF.FFE`) in `tests/integration/agent` or `activity` that I did not identify; the activity directory then passed in the focused run except for the items above.

Frontend, from `frontend/`:

| Command | Result |
|---|---|
| `npm.cmd run typecheck` | passes |
| `npm.cmd run i18n:check` | passes (en, tr, 2387 keys, 1736 literal `t()` calls) |
| `npm.cmd run lint` | 3 errors, all the pre-existing `no-explicit-any` in `src/app/router.tsx` (lines 9, 13, 22); nothing from my files |
| `npm.cmd test` (PowerShell) | 51 files, 761 tests passed (17 new: `src/pwa/pwa.test.ts` covers the worker's listeners, absence of fetch/cache, plain-text rendering, bad payloads, 8 hostile link forms, same-origin absolute URLs, click behaviour with and without an open window, the manifest and the page links, and the key decoder) |
| `npm.cmd run build` | built OK (existing Rollup warnings) |


## 6. Installability evidence

Production build (`npm.cmd run build`, built OK, existing `INEFFECTIVE_DYNAMIC_IMPORT` warnings only; `dist/` contains `manifest.webmanifest`, `sw.js` and the icons), served with `npx vite preview --port 5197 --strictPort --host localhost` (5173 and 5175 were in use by other sessions; I stopped my server afterwards and confirmed nothing listens on 5197). Playwright 1.x Chromium (headless) through a CDP session, script in the session scratchpad (outside the repo). Output, verbatim:

```
MANIFEST url: http://localhost:5197/manifest.webmanifest
MANIFEST errors: []
MANIFEST name/display/start_url: AgentNest standalone /
MANIFEST icons: 192x192/any, 512x512/any, 512x512/maskable
INSTALLABILITY errors: []
SERVICE WORKER: {"scope":"http://localhost:5197/","script":"http://localhost:5197/sw.js","state":"activated","controllerAfter":true}
HEAD: {"manifest":"http://localhost:5197/manifest.webmanifest","apple":"http://localhost:5197/apple-touch-icon.png","theme":"#f7f8f3","desc":true}
CACHE STORAGE entries: 0
sw.js has fetch listener: false
PAGE errors: []
```

`Page.getInstallabilityErrors` returned an empty list and `Page.getAppManifest` returned no errors. The worker registered on its own on the production build, activated and controls the page, and the Cache Storage is empty. I did not run Lighthouse (the brief allows either). `vite preview` served `/manifest.webmanifest` as `application/manifest+json` and `/sw.js` as `text/javascript`. **Not verified:** the `Caddyfile` itself (not run; the changes are one CSP clause and one header), installation on a real Android or iOS device, iOS "Add to Home Screen" push (iOS needs 16.4+ and an installed app), and an actual push delivery.

## 7. Invariants

INV-01 (workspace_id NOT NULL, forced RLS, every lookup workspace-scoped, foreign and other-member ids are 404, tested at API and RLS level, and the generic isolation harness now has a real foreign `subscription_id`); INV-10 (keys encrypted at rest, never in responses, logs, audit metadata or jobs; the private VAPID key is a `SecretStr` outside `public_dict`); INV-12 (create and revoke audited in the same transaction, ids only); INV-14 (default config has push off and nothing needs credentials); INV-18 (the dev button reports "subscribed" only after the server returned the device); INV-19 and INV-05/15 not touched (no time interpretation, no external call: nothing is sent, and no HTTP is done inside a transaction).

## 8. Deviations and open questions

1. **Uniqueness is per (workspace, user, endpoint), not per (user, endpoint).** The brief says "unique per user". A browser has one subscription per origin, and one person can own several workspaces; a global per-user key would force one workspace's row to move to the other, and Session 04 sends per workspace. Cross-workspace duplicates of one endpoint are therefore possible and fine. The shared-device protection (section 2) only sees one workspace because RLS hides the rest; a user who logs out of one account and into another on the same browser and subscribes in a **different** workspace will leave the first user's row active there. Session 04 should make logout/switch unsubscribe the device, and the sender should skip rows whose user is no longer an active member.
2. **Key rotation does not cover these rows.** `operations/key_rotation.py` re-encrypts `social_accounts` only. Retired `TOKEN_ENCRYPTION_KEYS` entries must stay until devices re-subscribe (documented in `data-model.md`). Extending the job is small but was out of scope.
3. **Maskable icon has no extra padding** (reasoning in section 1).
4. Subscribing without VAPID is a 409 rather than silently accepted, because the browser subscription is bound to the server's key and would be useless.
5. The key endpoint lives under the workspace (`/config`), not as an unauthenticated global route, so it follows the same membership rules as everything else. It could move to `/meta` if the app should know about push before sign-in; Session 04 decides.
6. P-17 is only partly closed (no `og:image`, no dark theme colour); see section 1.
7. `0046` (Session 01) names its `(workspace_id, id)` unique constraint `uq_assistant_test_turns_workspace_id`, which differs from the naming convention (`..._workspace_id_id`), so `alembic check` reports drift for that table. I noticed it when checking mine (mine is named correctly and `alembic check` shows no `push_subscriptions` drift). `alembic check` reports other pre-existing drift too (several foreign keys and indexes). I did not change `0046`.
8. Not verified: a real push service accepting a subscription from this server, iOS behaviour, a real device install, behaviour of `Caddy`'s headers (not run).

## 9. Handoff to Session 04

- Read rows with `PushSubscription` where `revoked_at IS NULL`, for the target `user_id` in the workspace; decrypt with `push_subscriptions.decrypt_keys(settings, row)`; send with `pywebpush` using `WEB_PUSH_VAPID_PRIVATE_KEY` and `WEB_PUSH_SUBJECT`. Set `last_success_at` on success; on 404/410 from the push service set `revoked_at` (that is also the place to remove dead devices).
- Before any POST: re-validate the endpoint with `push_subscriptions.validate_endpoint` and refuse hosts that resolve to private addresses; no network call inside a DB transaction.
- The service worker expects a JSON payload `{title, body, url, tag?}`; `url` is same-origin path only. Keep personal data out of the payload (the lock screen shows it).
- Use `GET /…/push-subscriptions/config` for `enabled` and the key, and the helpers in `frontend/src/pwa/push.ts` for the real opt-in UI. iOS only delivers to an installed app (the dev panel already says so).
- The next migration is `0048`.
