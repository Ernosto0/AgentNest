# Feature Phase 3, Session 01 report: close comment research and request the permission

**Status:** done (code, tests, research record, docs). Live evidence is **pending**: nothing was run against Meta, no app, token, test account or webhook was used, and nothing was submitted to App Review.
**Baseline:** `main` at `06c5d64` (detached worktree `pivoris-p3/s01`). Nothing committed or pushed.
**Migration head:** `0057`, unchanged. No migration was needed (the capability is derived from `granted_scopes` and a new key in the existing `capabilities` JSON; a missing key means "not granted").

## Who built what
- **Codex (gpt-6.1-sol, medium)** wrote the code and its tests: the new scope and capability, the Connections reconnect prompt, the Inbox hint, TR/EN strings, and the `integrations.md` and `pilot-onboarding-checklist.md` updates. It finished by itself (no usage-limit hit, no takeover needed).
- **Claude (session lead)** did the Meta documentation research and wrote the R75 register, the App Review package, `mvp-scope.md`, the P-05 status line and the Session 16 pointer; reviewed Codex's diff and ran all checks. Codex's draft was accepted without code changes (a review found no bug); the design decisions (key name, no `comment_*` enablement, no migration) were given in the brief.

## What changed

### Code
- `backend/app/integrations/instagram/oauth.py`: new `COMMENTS_SCOPE = "instagram_business_manage_comments"` appended as the fifth entry of `SCOPES` (indexes 1 and 2 used elsewhere are unchanged). `compute_capabilities` adds `comments_permission` (true iff the scope is in `granted_scopes`). The four `comment_read`, `comment_reply`, `comment_moderate` and `comment_private_reply` capabilities **stay false** even when the scope is granted.
- The key is named `comments_permission` (not `comment_*`) on purpose: the Inbox gate `useCommentsUnavailable` keys off `comment_*` flags, and the permission alone must not open the Comments list.
- Frontend: Connections card (`Connections.tsx`) shows "Reconnect with Instagram to grant comment permission. Comment automation is not available yet." for a real (`meta`) account that is not `disconnected` and lacks `comments_permission`; the owner gets the existing reconnect button (one button even in `needs_reauth`), non-owners see the existing owner-only text, mock accounts never see it. "What it can do" lists "Comment permission / Yorum izni" when granted. `InboxWorkspace.tsx`: the "Comments are not available yet" pane keeps the "Not yet" tab and uses a reconnect-specific hint when a real account lacks the permission. `presentation.ts` and `messages.ts` know the new key. Strings in `common`, `content`, `agent`, `inbox` (TR and EN).
- Existing connected accounts: untouched stored JSON, no backfill, messaging, publishing and insights keep working (test below). Reconnecting goes through the existing OAuth reconnect flow, which recomputes capabilities and `granted_scopes`.

### Docs
- `docs/research/platform-capabilities.md` section 1.8: replaced the open register with the 2026-11-17 answers (see below).
- `docs/operations/meta-app-review-package.md`: new warning block, a rewritten `instagram_business_manage_comments` row (Instagram Login scope, use-case description to paste, technical flow, data controls), Screencast 3 rewritten for the real flow (marked pending, not to be recorded on the mock), new section 4.3 reviewer test steps (pending Session 02), and a checklist item.
- `docs/product/mvp-scope.md`: removed the Deferred row "Real-account comment automation before capability acceptance"; added "Feature Phase 3, Track A" with F-05, its exclusions and its **gate** (scope granted, account capability flag on, delegation not off, live evidence recorded).
- `docs/review/pre-launch-problems.md`: P-05 status line (2026-11-17).
- `docs/architecture/integrations.md` section 3.2, `docs/operations/pilot-onboarding-checklist.md` (TR and EN scope list and comment notes), `docs/research/meta-comments-session16.md` (superseded-in-part pointer).

## R75-01 to R75-06: result
Sources were read on 2026-11-17 on `developers.facebook.com/documentation/instagram-platform/` (comment-moderation, private-replies, webhooks, webhooks/fields, webhooks/setup, webhooks/examples, reference/ig-comment, reference/ig-media/comments, app-review, reference/error-codes). The pages that were unreachable in October are readable now (the docs moved from `/docs/...` to `/documentation/...`; each page has a `.md` twin; index at `/documentation/instagram-platform/llms.txt`). They were read through a summarising fetch tool, so statements are "read in documentation", not verified by test, and each page should be re-read before a rollout or a submission. Full table with URLs: `platform-capabilities.md` section 1.8.

| Item | Outcome |
|---|---|
| R75-01 scopes, access, subscriptions | **Answered from docs.** Instagram Login uses `instagram_business_basic` + `instagram_business_manage_comments` (private replies list no messaging permission in that column; we hold `manage_messages` anyway). Advanced Access plus App Review is needed for businesses we do not own or manage; Standard Access covers owned accounts and pilot role users. Fields `comments` and `live_comments`; per-account `POST /{ig-id}/subscribed_apps`; app must be Live; setup page says Advanced Access is required for these notifications. **Carried forward:** actual `permissions` returned after consent, Development-mode delivery for role users, whether `comments` is an allowed `subscribed_fields` value for this app (a 2026-10 live check found `message_echoes` rejected), and the missing `subscribed_apps` call for comments in our code. |
| R75-02 event shapes, pagination, ownership | **Partly answered.** Webhook `value` has `id`, `from`, `text`, `media`; `parent_id` for replies (the documented example with `comment_id` is the Unified Login one). `/comments`: top-level only, newest first, max 50, owner token. **Carried forward:** authentic Instagram Login payload keys, edit and delete events, native moderator changes, cursor pagination. |
| R75-03 reply/hide/delete semantics | **Partly answered.** Reply returns `{id}`; hide (`?hide=`) and delete return `{success:true}`; owner's own comments always display; live comments unsupported; `hidden` is readable. **Carried forward:** already-deleted/hidden behaviour, errors, reconcile after an unknown outcome. |
| R75-04 private reply limits | **Partly answered.** 7 days (Live: during the broadcast), "only one message can be sent to the commenter", response `recipient_id` + `message_id`, Inbox or Requests delivery. **Carried forward:** per comment versus per commenter, eligibility of replies to replies, errors, idempotency or readback. |
| R75-05 DM eligibility after reply, identity | **Partly answered.** Follow-ups only after the recipient responds, within 24 h. **Carried forward:** whether `recipient_id` equals the later messaging `sender.id` and the commenter ID. No name matching. |
| R75-06 quotas, errors, races, revoked grants | **Carried forward in full.** Docs give no numbers, no comment error codes, no race semantics. |

Capabilities remain off in code until Session 02 and its live probe; no item is "verified by test" (no dev-mode account was available).

## Tests and checks (all run in `WT`, DB `pivoris_p3s01_test`)
- Backend unit: `SCOPES` order and content, the authorize URL carries the scope, `compute_capabilities` with and without the scope across both story settings (`comments_permission` true/false, all four `comment_*` false, messaging and publishing unchanged), updated full-dict assertion.
- Backend integration: OAuth reconnect callback records the actual consent (scope returned or not, from `connected` and `needs_reauth`), stores `granted_scopes`, keeps `comment_*` false; an account with legacy capabilities (no key) serializes through the API unchanged; legacy and `comments_permission` true/false/absent accounts keep passing the DM send gate and content submit validation.
- Frontend: reconnect prompt for connected, degraded and needs_reauth real accounts (one button, correct reconnect request body), not shown with the permission, for mock accounts or disconnected ones, non-owner sees owner-only text; Inbox hint with permission undefined, false and true.
- Results:
  - `uv run ruff check .`, `ruff format --check .`, `mypy app`, `lint-imports` (23 contracts kept): clean.
  - `pytest tests/unit tests/isolation tests/security tests/contract tests/integration/integrations tests/integration/operations/test_accounts.py`: **2,295 passed, 13 skipped, 4 failed** (357 s). The 4 failures (`test_the_dev_job_listing_of_a_never_shows_the_jobs_of_b`, `test_the_simulator_listing_of_a_never_shows_what_b_published`, `test_the_invite_token_is_never_logged_audited_notified_or_queued`, `test_the_dev_route_runs_the_health_check_now`) are environmental: the copied `.env` has `DEMO_TOOLS_ENABLED` off, so `/api/v1/dev/*` returns 404. With `DEMO_TOOLS_ENABLED=true` exported all four pass (4 passed). They touch no code of this session. I did not run them at HEAD in a separate tree (not allowed to touch other trees).
  - Frontend: `npm.cmd run lint`, `typecheck`, `i18n:check` (2,636 keys), `build`: clean; `npm.cmd test`: **58 files, 864 tests passed**.
- Not run: the full backend integration suite, Playwright E2E.

## Invariants
INV-11 respected: capabilities follow the granted scope and nothing comment-related is enabled; INV-10: no token or secret fields added, API still returns the whitelisted `capabilities` map; INV-14: mock demo unchanged. No new tenant table, no external call, no clock use.

## Open questions and risks
1. **Live-mode scope risk.** `SCOPES` now asks every connecting user for the comment scope. For role users (pilots, Standard Access) that works by Meta's docs; for a Live app serving non-role users, an unapproved permission may be refused or dropped at the consent screen until Advanced Access is granted. Not testable here. If this proves a problem before approval, put the fifth scope behind a config switch.
2. The `subscribed_apps` call for `comments` is not made anywhere in the code (a manual step for messages so far). Session 02 must add or document it.
3. Private-reply count rule (per comment or per commenter) is ambiguous in the docs; Session 02 should enforce the stricter reading until the live probe says otherwise.
4. The package's other permission rows and Screencasts 1 and 2 still use Facebook Login names (pre-existing, noted in the package).
5. Meta documentation was read through a summarising fetch tool; re-read the pages before submitting.

## Handoff to Session 02
Needs a dev-mode test account with the scope granted (reconnect it from Settings), then: per-account flag (default off), `comments` webhook subscription, the real adapter in `meta_comments.py`, deterministic 7-day/one-message enforcement with reason codes, the live probe that records the carried-forward items, and a rollout section. When Session 02 turns on `comment_*` flags, the Inbox "unavailable" pane will lift automatically (it keys off those flags).

## Merge notes
Shared files likely to conflict with parallel Session 03: `docs/product/mvp-scope.md` (this session edits section 3's end and one Deferred row; Session 03 edits the "image generation" Deferred row and adds its own subsection) and possibly `frontend/src/i18n/locales/*/common.json`, `content.json` (Settings brand strings). No migration, so no revision conflict.

## Files
Changed (25): `backend/app/integrations/instagram/oauth.py`; `backend/tests/unit/integrations/test_oauth_client.py`, `backend/tests/integration/integrations/test_oauth.py`, `backend/tests/integration/operations/test_accounts.py`; `frontend/src/features/settings/Connections.tsx`, `settings/connections.test.tsx`, `inbox/InboxWorkspace.tsx`, `inbox/inbox.test.tsx`, `content/messages.ts`, `agent/presentation.ts`; `frontend/src/i18n/locales/{en,tr}/{agent,common,content,inbox}.json`; `docs/architecture/integrations.md`, `docs/operations/meta-app-review-package.md`, `docs/operations/pilot-onboarding-checklist.md`, `docs/product/mvp-scope.md`, `docs/research/platform-capabilities.md`, `docs/research/meta-comments-session16.md`, `docs/review/pre-launch-problems.md`. Created: this report.
