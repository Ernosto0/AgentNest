# Feature Phase 3, Session 02 report: comment-to-DM on real accounts

**Status:** done offline (code, tests, rollout docs). Every live result is **pending**: nothing was run against Meta, no token, test account, webhook subscription or message was used, and nothing was submitted to App Review.
**Baseline:** `main` at `06c5d64` plus Session 01's uncommitted work (kept and built on) in the detached worktree `pivoris-p3/s01`. Nothing committed or pushed.
**Migration head:** `0059` (`20261117_0059_comment_automation.py`, `down_revision = "0057"`). Session 03 uses `0058`; the orchestrator re-chains at merge (0059 -> 0058).

## Who built what
- **Codex (gpt-6.1-sol, medium)** wrote almost all the code, tests and docs. It hit its usage limit (reset 19:41 local) at the very end of its test pass, after the application files were final, without writing its closing summary. No resume was possible.
- **Claude (session lead)** took over: reviewed the full diff, ran every check, and fixed what Codex left. Changes from Codex's draft: removed a stray duplicate block of `connections.*` keys that Codex inserted into the wrong (`settings.connections`) section of `en/` and `tr/common.json`; replaced the now false hint "Comment automation is not available yet" in the Connections reconnect hint; added an Inbox hint for "permission granted, flag still off" (`convo.commentsUnavailableEnableHint`, TR and EN) and changed the matching Inbox test. Code logic was accepted as written (see risk 2).

## What changed

### Per-account flag and capabilities
- New column `social_accounts.comment_automation_enabled boolean NOT NULL DEFAULT false` (migration 0059; table already tenant-scoped with RLS, no new table). The same migration adds `COMMENT_AUTOMATION_OFF` to the `inbound_events.ignore_reason` check constraint. Downgrade restores the old constraint (refuses if the new reason exists in history) and drops the column.
- `compute_capabilities(granted_scopes, stories_enabled, comment_automation_enabled=False)`: `comments_permission` = scope granted; `comment_read` and `comment_private_reply` = scope AND flag; `comment_reply` and `comment_moderate` stay false (public reply and moderation on real accounts remain out of scope and their provider methods still raise `*_NOT_VERIFIED`).
- Owner endpoint `PUT /api/v1/workspaces/{ws}/accounts/{account_id}/comment-automation` `{ "enabled": bool }`: owner only (403 otherwise), foreign IDs 404, mock account 409 (`real_account_required`), turning on needs status connected/degraded and the granted scope (409 `comments_permission_missing`), row-locked, recomputes capabilities, audit `account.comment_automation_changed` (from/to) in the same transaction, idempotent (no second audit row). `SocialAccountOut` gains `comment_automation_enabled`.
- OAuth callback: a fresh connect or reuse of a disconnected row resets the flag to false; a reconnect keeps it, and capabilities follow the scopes actually granted.
- Scope switch: `META_REQUEST_COMMENT_SCOPE` (default `true`); `false` requests only the original four scopes in the original order. `COMMENT_PRIVATE_REPLY_LIMIT_SCOPE` = `commenter` (default, strict) | `comment` (relaxed).

### Webhook and ingest
- `WebhookCodec(live_comments=True)` (Meta codec only; the mock keeps `synthetic_comments`) parses `entry[].changes[]` with `field == "comments"` into `comment` events whose `raw_item` is a `CommentEvent` with `schema = "provider-comment-v1"` (id, media id, root = parent or id, author = `from.id`, text, `version 1`, timestamp from `entry.time`, no username). Malformed items are dropped; a comments change no longer becomes an "other" event. Dedup key for provider comments is `ig:{account}:comment:{comment id}` (not a content hash, so a redelivery with a new `entry.time` is still one event).
- Ingest and processing: a meta account's comment is accepted only if the flag is on, status connected/degraded and `comments_permission` true; otherwise it is stored as `ignored` / `COMMENT_AUTOMATION_OFF` with an EMPTY payload (no comment text retained for accounts that did not opt in).
- `PublicMedia.ownership_state = "verified_provider"` for meta accounts (the signed webhook was delivered for our own account); one helper `media_ownership_ok` replaced every `verified_synthetic` check (mock accepts only `verified_synthetic`, meta only `verified_provider`). The real provider additionally re-reads media owner before sending.

### Real provider and executor
- `MetaInstagramProvider.read_comment` and `send_private_reply` are real (comment read, media owner check, window check against Meta's comment timestamp, then `POST /{ig-user-id}/messages` with `recipient.comment_id`, marked ambiguous). `find_private_reply` has no remote readback and returns `None`, so an ambiguous send stays `outcome_unknown` and is never resent. Shared code moved up from `SyntheticMetaCommentProvider`, whose tests still pass.
- `operations/private_reply.py` now uses the account's own provider kind; a meta account needs `meta` enabled, status connected/degraded, `comment_private_reply`, the flag and the scope, else terminal `CAPABILITY_MISSING` (also when the owner turns the flag off during pending work). Write-ahead operation, one attempt, approval/grant recheck and `eligibility()` recheck unchanged.

### Deterministic rules (meta accounts only; mock unchanged)
`app/comments/private_reply_rules.py` (pure) plus `real_refusal` in `comments/private_reply.py`, checked at proposal, in the pre-dispatch `eligibility()` recheck, in the executor and (window) in the provider.

| Reason code | Rule |
|---|---|
| `PRIVATE_REPLY_WINDOW_EXPIRED` | age strictly below 7 days minus 10 minutes (`META_PRIVATE_REPLY_WINDOW`); future or missing timestamp refused. The provider surfaces `PRIVATE_REPLY_EXPIRED` from Meta's own timestamp. |
| `PRIVATE_REPLY_COMMENT_ALREADY_USED` | one per comment (unique `private_reply_opportunities(account, comment)`) |
| `PRIVATE_REPLY_COMMENTER_LIMIT` | one per commenter per account, ever (**assumed-strict**); counts reserved (not expired), succeeded, outcome_unknown; failed and cancelled do not count; relaxable with `COMMENT_PRIVATE_REPLY_LIMIT_SCOPE=comment` |
| `PRIVATE_REPLY_COMMENTER_UNKNOWN` | comment without author id |
| `PRIVATE_REPLY_NOT_TOP_LEVEL` | any comment with a parent (eligibility of replies undocumented) |

Draft, claim validator and approval are the existing agent path (`comment.private_reply` tool, `{{fact:key}}`, `ask` by default, automatic only with a real owner delegation grant); no new draft path.

### Frontend
Connections card: for a real account with `comments_permission`, an owner-only switch "Comment-to-DM (private replies)" / "Yorumdan DM'ye (ozel yanitlar)" with state and explanation (one reply per customer, approval by default, 7 days); non-owners see read-only state; the Session 01 reconnect prompt stays when the permission is missing. Inbox comments pane lifts when `comment_read` or `comment_private_reply` is true (tested); otherwise it shows the reconnect hint, or the new "turn it on in Settings" hint when only the flag is missing. `openapi.json` patched narrowly (+82 lines), `schema.d.ts` regenerated (+63 lines).

### Live probe harness
`backend/tests/contract/test_meta_comments_live.py` (marker `meta_comments_live`, registered in `pyproject.toml`; never runs in CI, skipped without credentials; `ci.yml` already blanks `META_LIVE_*`). Probes: `subscribed_apps` readback, comment timestamp/owner read, one private reply (needs `META_LIVE_COMMENT_EFFECT=private_reply` and `META_LIVE_COMMENT_SEND=YES_SEND_REAL_MESSAGE`), repeat to the same comment, second comment by the same commenter (`META_LIVE_COMMENT_ID_SAME_COMMENTER`, plus `META_LIVE_COMMENT_LIMIT_PROBES`), recipient id hash. Optional `META_LIVE_PROBE_RECORD` writes a closed allow-list of sanitized fields (HTTP status, error code/subcode, booleans, counts, hashed recipient id; never token, text, username). Offline safety tests: `tests/unit/integrations/test_meta_comments_live_safety.py`. The older `test_meta_live.py` public-effect probes stay disabled.

### Decisions on Session 01's open questions
1. **`subscribed_apps` for `comments`:** the codebase has no place for subscriptions (the messages subscription is manual too), and an automatic call would be an external effect needing a ledger operation type. Documented as a **manual rollout step** (POST and readback), the probe does the read-only readback. No code.
2. **Private-reply limit:** strict reading enforced (per commenter, ever, plus per comment, top-level only, window minus 10 minutes), with reason codes and a single env switch to relax.
3. **Scope request risk:** `META_REQUEST_COMMENT_SCOPE` (default on), documented in `environment-variables.md` and `.env.example`.

## Docs updated
`account-agent-rollout.md` (new rollout section with rule table, rollback, probe and evidence), `environment-variables.md`, `.env.example`, `integrations.md`, `platform-capabilities.md`, `meta-app-review-package.md` (4.3 reviewer steps), `pilot-onboarding-checklist.md`, `api-design.md`, `data-model.md`, `observability.md` (audit catalog), `mvp-scope.md` (Track A gate), plus the activity group and EN/TR activity strings for the new audit action.

## Files
**Created:** `backend/app/comments/ownership.py`, `backend/app/comments/private_reply_rules.py`, `backend/migrations/versions/20261117_0059_comment_automation.py`, `backend/tests/contract/test_meta_comments_live.py`, `backend/tests/integration/agent/test_meta_private_reply.py`, `backend/tests/integration/operations/test_comment_automation.py`, `backend/tests/isolation/test_comment_automation_isolation.py`, `backend/tests/unit/integrations/test_meta_comments_live_safety.py`, `backend/tests/unit/integrations/test_meta_comments_real.py`, this report.
**Changed (backend):** `activity/classify.py`, `activity/groups.py`, `api/router.py`, `comments/{actions,codec,manual,private_reply,service}.py`, `core/config.py`, `core/i18n/{en,tr}.json`, `inbox/{ingest,models,processing}.py`, `integrations/instagram/{base,meta,meta_comments,models,oauth,registry,webhook_format}.py`, `operations/{accounts_router,manual_comments,oauth_service,private_reply,schemas}.py`, `pyproject.toml`, `.env.example`, tests `integration/integrations/test_oauth.py`, `integration/operations/test_accounts.py`, `unit/integrations/test_meta_comments.py`, `unit/integrations/test_oauth_client.py`.
**Changed (frontend):** `openapi.json`, `src/api/schema.d.ts`, `features/settings/{Connections.tsx,hooks.ts,connections.test.tsx,automation.test.tsx,settings.test.tsx}`, `features/inbox/{InboxWorkspace.tsx,inbox.test.tsx}`, `features/{agent/presentation.ts,content/messages.ts}`, `test/contentFixtures.ts`, `i18n/locales/{en,tr}/{agent,common,content,inbox}.json`.
Session 01 files remain as they were (the shared ones above carry both sessions' edits).

## Checks (in `WT`, DB `pivoris_p3s01_test`, `DEMO_TOOLS_ENABLED=true`)
- Backend: `ruff check` clean, `ruff format --check` (773 files) clean, `mypy app` (409 files) clean, `lint-imports` 23 contracts kept.
- Backend tests (`tests/unit tests/isolation tests/security tests/contract tests/integration/{integrations,operations,inbox}` and the agent comment, private-reply, tools, migration files, hardening and health tests): **2,964 passed, 18 skipped, 3 failed** (1,397 s).
  - `test_cors_allows_only_the_frontend_origin`: known environment failure from the baseline list (not rerun at HEAD in a separate tree; not allowed to touch other trees).
  - `test_cli_migration_status_head_only_and_check_config`: fails only because the exported `DEMO_TOOLS_ENABLED=true` conflicts with its `--production` config check; **passes (1 passed) with the variable unset**. Unrelated to this session.
  - `test_the_invite_token_is_never_logged_audited_notified_or_queued`: failed in the long run but **passes when run alone**; the invite flow is untouched here. Treated as an order or environment flake; not investigated further.
- Frontend: `npm.cmd run lint`, `typecheck`, `i18n:check` (2,643 keys), `build` clean; `npm.cmd test`: **58 files, 868 tests passed**.
- Not run: the full backend integration suite and Playwright E2E.

## Invariants
INV-01 foreign IDs 404 (new route, isolation test); no new tenant table (RLS unchanged). INV-02/04/16 private reply uses the existing validator, approval and policy grant; automatic needs a real owner grant, revoked grantor cancels (tested). INV-05/06/15 all sends go through the operations ledger, one attempt, ambiguous outcomes never resent; reads happen outside DB transactions in the worker. INV-09 real accounts are not simulated. INV-10 no token in payloads, logs or the API; probe records are allow-listed. INV-11 capabilities require scope AND flag. INV-12 flag changes audited in the same transaction. INV-19 `Clock` used for every window decision.

## Open questions and risks
1. All live behaviour is **pending**: whether `comments` is accepted for `subscribed_apps`, delivery to a Development-mode role account, authentic webhook payload keys, per-comment versus per-commenter limit, reply-to-reply eligibility, error codes, and whether `recipient_id` equals the later DM sender id.
2. For meta accounts a second proposal for a comment that already has an opportunity now raises `PRIVATE_REPLY_COMMENT_ALREADY_USED` instead of returning the existing action's result (the mock still returns the existing result). If the agent coordinator ever replays an unrecorded tool call, it would see a refusal instead of an idempotent answer; the checkpointed observation path should prevent this, but it was not exercised under a real replay.
3. The comment timestamp stored for a real comment comes from `entry.time` (delivery time), slightly later than creation; the 10-minute margin and the provider's re-read of Meta's own timestamp cover this.
4. The strict per-commenter rule blocks a returning customer from ever getting a second private reply; relax with `COMMENT_PRIVATE_REPLY_LIMIT_SCOPE=comment` only after the probe.
5. `.tmp/s02-final` (a git-ignored, permission-restricted folder created by Codex's sandbox) remains in the worktree and could not be removed.

## Handoff
Next live steps (user-driven): reconnect the dev-mode test account, turn the flag on, subscribe `comments` manually, run the read-only probes, then the opt-in send probes, record sanitized results via `META_LIVE_PROBE_RECORD`, and fill the "pending" items above in `platform-capabilities.md` section 1.8.

## Merge notes
Re-chain migration `0059` after Session 03's `0058`. Likely conflicts: `frontend/src/i18n/locales/*/common.json` and `content.json` (Session 03 brand strings), `docs/product/mvp-scope.md`, `frontend/openapi.json` and `schema.d.ts` (regenerate after merge), `backend/app/core/config.py`, `.env.example`, `docs/operations/environment-variables.md`.
