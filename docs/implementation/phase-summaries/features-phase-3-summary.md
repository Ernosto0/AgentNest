# Feature Phase 3 Close-Out Summary: After App Review

- **Phase:** Feature Phase 3 (F-05 comment-to-DM on real accounts, F-07 story and post template images)
- **Specification:** [features-phase-3-after-app-review/sessions.md](../features-phase-3-after-app-review/sessions.md), source [pre-launch-feature-recommendations.md](../../review/pre-launch-feature-recommendations.md) §4 step 3
- **Sessions executed:** 01 to 04 (Track A = 01 and 02, Track B = 03 and 04). Reports in [features-phase-3-after-app-review/](../features-phase-3-after-app-review/): [s01](../features-phase-3-after-app-review/s01-report.md), [s02](../features-phase-3-after-app-review/s02-report.md), [s03](../features-phase-3-after-app-review/s03-report.md), [s04](../features-phase-3-after-app-review/s04-report.md), [merge-report](../features-phase-3-after-app-review/merge-report.md).
- **Baseline Git commit:** `06c5d64` (`main`). **Nothing is committed**: all four sessions are uncommitted on `main` (see section 8).
- **Alembic migration head:** `20261117_0060_price_card_command.py` (revision `0060`). The next free migration is `0061`. Chain: `0057 (Feature Phase 2) -> 0058 (S03 template images) -> 0059 (S02 comment automation) -> 0060 (S04 price-card command)`. The session reports keep the numbers they were written with (S02 wrote `0059` on parent `0057`; S04 wrote `0060` on parent `0058`; S01 has no migration). `alembic heads` shows one head.
- **Status:** **Implemented and verified offline. Stopped for review.** Nothing was run against Meta, a real Instagram account, a real phone, or a real model. Everything that depends on those is in section 7 as pending.
- **Date:** 2026-11-17

---

## 1. Executive summary

Two independent tracks, built in parallel worktrees and merged by the orchestrator (see the merge report).

- **Track A, F-05 comment-to-DM on real accounts (Sessions 01 and 02).** Meta's comment documentation was read and R75-01 to R75-06 were answered or explicitly carried forward. The OAuth flow asks for `instagram_business_manage_comments`; existing accounts see a reconnect prompt. A real account gets comment capabilities only when the scope is granted **and** an owner turns on a per-account flag (default off). A comment "price?" can then produce a private reply with the verified answer through the existing draft, claim-validator, approval and delegation path, with Meta's 7-day and one-message limits enforced by deterministic reason codes. Live behaviour is untested; a skipped-by-default probe harness and a rollout runbook are the way to test it.
- **Track B, F-07 template images (Sessions 03 and 04).** Workspace brand settings (two colours, a logo) and a deterministic Pillow renderer for four templates (price, opening hours, services list, announcement) at story and feed sizes. Fact-backed fields hold fact keys; values are resolved from verified facts at render time and the versions used are recorded. In the content flow, a template picker with live preview sits next to Upload (editor, composer, Today story prompt), a rendered image's fact versions are linked to the content item so a price change holds it, "re-render with the new value" creates a new draft version that needs fresh approval, and a confirmed command ("make a price card for monthly membership") stages a draft and renders it in a job.

---

## 2. What changed, by feature

### 2.1 F-05 research, permission and capability (Session 01)
- `oauth.py`: `COMMENTS_SCOPE = "instagram_business_manage_comments"` is the fifth entry of `SCOPES` (indexes used elsewhere unchanged). `compute_capabilities` adds `comments_permission` (true iff the scope is in `granted_scopes`). The key is deliberately not named `comment_*`, so the permission alone never opens the Comments list. No migration; a missing key means "not granted".
- Connections shows a reconnect prompt for a real account without the permission (owner gets the existing reconnect button, others the owner-only text, mock accounts never see it) and lists "Comment permission" when granted. The Inbox "Comments are not available yet" pane uses a reconnect-specific hint.
- Research: `platform-capabilities.md` §1.8 holds the 2026-11-17 answers with Meta documentation URLs. Answered from the docs: scopes, access levels, webhook fields (`comments`, `live_comments`), the 7-day private-reply window and "one message to the commenter". Carried forward: authentic webhook payload keys, `subscribed_fields` acceptance, per-comment versus per-commenter limit, reply-to-reply eligibility, error codes, races, `recipient_id` identity. Nothing is "verified by test".
- `meta-app-review-package.md` (use-case text, rewritten Screencast 3, reviewer steps, checklist), `mvp-scope.md` (Track A subsection and gate), `pre-launch-problems.md` P-05 status, `integrations.md`, `pilot-onboarding-checklist.md`.

### 2.2 F-05 comment-to-DM on real accounts (Session 02)
- **Flag and capabilities.** Migration `0059`: `social_accounts.comment_automation_enabled boolean NOT NULL DEFAULT false`, plus `COMMENT_AUTOMATION_OFF` in the `inbound_events.ignore_reason` CHECK. `comment_read` and `comment_private_reply` = scope AND flag; `comment_reply` and `comment_moderate` stay false on real accounts. Owner endpoint `PUT /workspaces/{ws}/accounts/{id}/comment-automation` (owner only, foreign ID 404, mock 409, needs connected/degraded and the scope, audit `account.comment_automation_changed`, idempotent). A fresh connect resets the flag; a reconnect keeps it. Switches: `META_REQUEST_COMMENT_SCOPE` (default true) and `COMMENT_PRIVATE_REPLY_LIMIT_SCOPE` (`commenter` default, `comment` relaxed).
- **Webhook and ingest.** `WebhookCodec(live_comments=True)` parses `changes[].field == "comments"` into `provider-comment-v1` events, dedup key `ig:{account}:comment:{id}`. A real account's comment is accepted only with flag, status and scope; otherwise it is stored `ignored` / `COMMENT_AUTOMATION_OFF` with an empty payload. Media ownership is `verified_provider` for signed own-account Meta webhooks (`media_ownership_ok` replaced every `verified_synthetic` check).
- **Real provider and executor.** `MetaInstagramProvider.read_comment` and `send_private_reply` are real (media owner check, window check against Meta's timestamp, `POST /{ig-user-id}/messages` with `recipient.comment_id`, marked ambiguous). There is no remote readback, so an ambiguous send stays `outcome_unknown` and is never resent. The executor uses the account's own provider kind and refuses with `CAPABILITY_MISSING` when the flag or scope goes away.
- **Deterministic rules** (`comments/private_reply_rules.py`, real accounts only): `PRIVATE_REPLY_WINDOW_EXPIRED` (7 days minus 10 minutes), `PRIVATE_REPLY_COMMENT_ALREADY_USED`, `PRIVATE_REPLY_COMMENTER_LIMIT` (one per commenter per account, ever; assumed-strict), `PRIVATE_REPLY_COMMENTER_UNKNOWN`, `PRIVATE_REPLY_NOT_TOP_LEVEL`. Checked at proposal, pre-dispatch and in the executor.
- **Draft and approval:** unchanged. `comment.private_reply` tool, `{{fact:key}}` placeholders, claim validator, `ask` by default, automatic only with a real owner delegation grant.
- **UI.** Owner-only switch "Comment-to-DM (private replies)" in Connections; Inbox pane lifts when `comment_read` or `comment_private_reply` is true, otherwise reconnect hint or "turn it on in Settings" hint.
- **Live probe harness** `tests/contract/test_meta_comments_live.py` (marker `meta_comments_live`, skipped without credentials and never run in CI; sends need `META_LIVE_COMMENT_SEND=YES_SEND_REAL_MESSAGE`; optional sanitized `META_LIVE_PROBE_RECORD`). Rollout runbook in `account-agent-rollout.md`.

### 2.3 F-07 brand settings and renderer (Session 03)
- **Brand.** Migration `0058`: table `workspace_brand_settings` (one row per workspace, `#rrggbb` CHECKs, nullable logo with composite FK to `media_assets`, RLS enabled and forced, registered in `CATEGORY_C_TABLES`, now 63 tables) and `media_assets.render_record` JSONB. `GET/PUT /workspaces/{id}/brand` (`settings.view` / new `brand.manage`, owner and manager), audit `brand.updated`, `BrandSection` in Settings (TR and EN). Media cleanup never deletes a workspace logo.
- **Renderer** `app/content/templates/`: `price_card`, `hours_card`, `services_list` (2 to 6 money facts), `announcement`, each in story 1080x1920 (text outside the top 250 px and bottom 340 px) and feed 1080x1350. Pillow only, bundled Noto Sans (SIL OFL 1.1, provenance in `fonts/SOURCE.md`), integer pixel math, wrapping, bounded shrink, ellipsis, WCAG-luminance text colour. `RENDERER_VERSION = "1"`.
- **Facts.** Only `usable_facts` (verified, live, in window, uncontested). A key that is not usable refuses the whole render (`TEMPLATE_FACT_NOT_USABLE`, 422); wrong value type is `TEMPLATE_FACT_TYPE_MISMATCH`. The announcement's free text goes through the claim validator (`TEMPLATE_TEXT_UNGROUNDED` for a price, time, phone, URL, discount word or large number); `{{fact:key}}` placeholders are allowed and their versions recorded.
- **Output** goes through `media.ingest_bytes` (size limit, baseline sRGB JPEG without EXIF, write-before-row, `media.uploaded`) plus a `render_record` and audit `media.template_rendered`. Routes (`content.edit`): `GET /content/templates`, `POST /content/template-images/preview` (stores nothing), `POST /content/template-images`.

### 2.4 F-07 template images in the content flow (Session 04)
- **Link and hold.** The render's fact references are merged into the item's `fact_references` on create, edit, submit, re-approve, generation and agent paths (the recorded version wins, so a stale image stays visible). `TEMPLATE_IMAGE_STALE` blocks submit and re-approve; an existing price-change impact handler holds the item.
- **Re-render.** `POST /content-items/{id}/template-image/rerender` creates a new asset and a new item version, draft again, approval cancelled; never auto-approved or published (audit `content.template_image_rerendered`). `ContentItemOut.template_image` carries template, format, fact versions, `stale`, `can_rerender`.
- **Hours rows** are built structurally (a comma in an exception note no longer splits a row).
- **Command** `content.make_price_card` (migration `0060` adds `command.make_price_card` to `ck_approvals_action`): the model names a fact key, never a price; confirmation card; the executor stages a draft plus a `render_template_image` job in the decision transaction, rendering and storage run later outside any transaction (audit `content.template_image_failed` on failure). `interpret_command` prompt `v3`, fake grammar, `evals/interpret_command/price_card.yaml`.
- **Frontend.** `TemplateImageSheet` (template and format pickers, verified-fact selects, announcement fields, debounced live preview, phone Fields/Preview toggle) with entry points in the editor, composer, Today story prompt and Today header; `TemplateImageNotice` (badge, out-of-date warning, "re-render with the new value", needs-approval-again); re-approve hidden while stale; command confirmation card and result messages; TR and EN strings.

---

## 3. Tests proving each acceptance criterion

| Criterion | Proof |
|---|---|
| S01: comment scope requested; capability follows the granted scope; nothing comment-related enabled by the permission alone | `tests/unit/integrations/test_oauth_client.py` (scope order and content, `compute_capabilities` with and without scope across story settings, all four `comment_*` false); `tests/integration/integrations/test_oauth.py` (reconnect callback records actual consent) |
| S01: existing connected accounts not broken | `tests/integration/operations/test_accounts.py` (legacy capabilities JSON serializes unchanged; DM send gate and content submit keep passing) |
| S01: reconnect prompt | `features/settings/connections.test.tsx`, `features/inbox/inbox.test.tsx` |
| S02: per-account flag default off; owner-only; mock refused; audit | `tests/integration/operations/test_comment_automation.py`, `tests/isolation/test_comment_automation_isolation.py` |
| S02: real webhook parsing, dedup, opt-out stores no text | `tests/unit/integrations/test_meta_comments.py`, `test_meta_comments_real.py`, inbox ingest tests |
| S02: private reply rules (window, one per comment, one per commenter, top-level only) and ambiguous send never resent | `tests/integration/agent/test_meta_private_reply.py`, `tests/unit/integrations/test_meta_comments_real.py` |
| S02: probe harness skipped without credentials, writes only allow-listed fields | `tests/unit/integrations/test_meta_comments_live_safety.py`; `tests/contract/test_meta_comments_live.py` shows as skipped |
| S03: brand API, validation, permission, 404 for foreign logo, RLS, logo survives cleanup | `tests/integration/content/test_template_images.py`, `tests/isolation/test_template_images_isolation.py`, `tests/unit/core/test_rls_policies.py`, `tests/unit/identity/test_permissions.py`, `features/settings/brand.test.tsx` |
| S03: every template and format renders at the right size; safe zones; Turkish glyphs; wrapping and truncation; goldens | `tests/unit/content/templates/test_cards.py` (with `goldens/`) |
| S03: missing, unverified, contested, expired or wrong-type fact refuses the render with no asset; ungrounded free text refused; placeholder version recorded | `tests/integration/content/test_template_images.py` |
| S04: render linked to the item; price change holds it; re-render needs approval again; stale image blocks submit | `tests/integration/content/test_template_image_flow.py`, `tests/unit/content/templates/test_link.py`, `tests/isolation/test_template_image_flow_isolation.py` |
| S04: price-card command (fact key only, confirmation, staged draft and job) | `tests/integration/commands/test_price_card_command.py`, `tests/unit/ai/test_fake_interpreter_price_card.py`, `evals/interpret_command/price_card.yaml` |
| S04: picker, preview, stale notice, command card | `features/content/templateImage.test.tsx`, `features/approvals/priceCard.test.tsx` |

Full check results: section 4.

---

## 4. Checks run

Environment: `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN= OPENAI_API_KEY= PYTHONUTF8=1 DEMO_TOOLS_ENABLED=true`. The whole backend suite ran as four parallel shards on four empty databases (`agentnest_p3m_{a,b,c,d}_test`, dropped afterwards). The shards shared one Postgres container and were slow (about 80 to 90 minutes for the integration shards, dominated by per-test `TRUNCATE` fsyncs), not hung.

| Check | Result |
|---|---|
| `uv run alembic heads` | single head `0060` |
| Migration `upgrade head`, `downgrade 0057`, `upgrade head` (shard DB) | pass (`0060`, `0057`, `0060`) |
| `ruff check .`, `ruff format --check .` | pass (799 files formatted) |
| `mypy app` | pass (422 source files) |
| `lint-imports` | 23 contracts kept, 0 broken |
| (a) `tests/unit tests/isolation tests/security tests/contract` | 2274 passed, 18 skipped, 2 failed (both known, see below) |
| (b) `tests/integration/{agent,commands,ai,approvals,integrations}` and `tests/integration/test_*.py` | 722 passed, 1 failed (`test_cors_allows_only_the_frontend_origin`, known) |
| (c) `tests/integration/{inbox,activity,demo,identity}` | 615 passed, 1 failed (`test_owner_creates_an_invite_with_a_one_time_link`, known) |
| (d) `tests/integration/{content,knowledge,jobs,notifications,operations,plans,policy,reporting,retention,waitlist}` | 924 passed |
| Total backend | 4535 passed, 18 skipped, 4 failed (all classified below; no `tests/e2e` run) |
| Evals, fake provider (`python -m evals run --all`) | interpret_command 84/84 (77 before plus 7 new price-card cases), extract_fact_candidates 12/12, draft_reply 86/86, draft_content 26/26; 0 hard failures |
| Frontend `npm.cmd run lint`, `typecheck`, `i18n:check`, `build` | pass (2717 keys, 1989 literal `t()` calls verified) |
| Frontend `npm.cmd test` | 61 files, 885 tests passed (baseline 833 at Feature Phase 2 close, 859 after S03, 864 after S01) |
| `frontend/openapi.json` against a fresh `export-openapi`; `schema.d.ts` against `npm run gen:api` | identical after the merge fix (the file had drifted by one enum, see the merge report) |

**Failures, all environmental or known, none caused by this phase:**
- `tests/unit/core/test_deployment_workflow_and_rollback.py::test_cli_migration_status_head_only_and_check_config`: fails only while `DEMO_TOOLS_ENABLED=true` is exported (it conflicts with the test's `--production` config check). Re-run with the variable unset: 7 passed in that file.
- `tests/security/test_invite_secrets.py::test_the_invite_token_is_never_logged_audited_notified_or_queued`: fails in the long shard (log capture is order-dependent) and passes alone with `DEMO_TOOLS_ENABLED=true`: 2 passed in that file. Same as the Feature Phase 2 Session 08 report.
- `test_cors_allows_only_the_frontend_origin`: the local `.env` allows another frontend origin (no `access-control-allow-origin` for `http://localhost:5173`). Baseline failure listed in the Feature Phase 2 close-out.
- `test_owner_creates_an_invite_with_a_one_time_link`: the local `.env` public URL is a `trycloudflare.com` address, so the invite link starts with `https://...trycloudflare.com` instead of `http://localhost:8000`. Baseline failure listed in the Feature Phase 2 close-out.

Not run: Playwright (`npm run e2e`), `tests/e2e`, anything against Meta, a real model, or a device. The comment live probes are collected and reported as skipped (all 18 skipped tests are in `tests/contract`: 5 new comment probes, 10 Meta probes, 3 Telegram probes).

---

## 5. Demo steps

All steps use the credential-free defaults (`LLM_PROVIDER=fake`, mock Instagram, `DEMO_TOOLS_ENABLED=true`) with the worker running and the demo data (`uv run python -m app.cli seed --reset`). Sign in as `owner@demo.local`.

1. **Brand (S03).** Settings, Workspace, Brand: pick two colours (or keep the defaults), optionally upload a logo, Save. A manager can do the same; staff see it read-only.
2. **Template image (S03, S04).** Content, new post (or the story prompt on Today): "Make an image from a template". Choose "Price card", pick a verified price fact, watch the live preview, choose story or feed, save. The draft has the picture attached and a "Made from a template" badge. Try "Opening hours" and "Announcement" (a price typed into the announcement text is refused; `{{fact:key}}` is accepted).
3. **Price change hold (S04).** Submit the item for approval or schedule it, then change that price fact. The item goes on hold with the out-of-date notice; "Re-render with the new value" creates a new version, which needs approval again.
4. **Command (S04).** On Today type "aylik uyelik icin fiyat karti yap" (or "make a price card for monthly membership"; the fake interpreter understands the ASCII spelling). The confirmation card shows the verified price; confirm. A draft appears and the worker renders the image (the draft page shows it after a reload).
5. **Comment automation, mock (S02).** The mock account still handles comments as before (Comments tab, simulated private replies). On a real account none of this is on by default; for the live procedure see [account-agent-rollout.md](../../operations/account-agent-rollout.md), section "Real-account comment-to-DM rollout".
6. **Connections (S01, S02).** With a real (non-mock) account in a test workspace, Connections shows the reconnect prompt when the permission is missing and, once granted, the owner switch "Comment-to-DM". (Not possible on the mock demo account by design; the tests cover it.)

---

## 6. Deviations from the briefs

1. **Close-out moved out of Session 04.** The Session 04 brief asked it to run all checks, write the phase summary and update the roadmap. Because Track B and Track A ran in parallel worktrees, the orchestrator did the merge and this close-out (merge review, full checks, summary, roadmap) after both tracks were applied. The S04 report is therefore a track report only.
2. **Codex and Sonnet split.** Codex (gpt-6.1-sol) wrote most of the code in S01 to S04, and hit its usage limit at the end of S02 and during S04. Claude took over each time: in S02 it reviewed the diff, removed a duplicate block of locale keys Codex put in the wrong section, and added the "permission granted, flag off" Inbox hint; in S04 it reviewed the backend diff and wrote the whole frontend itself. In S03 the reviewer added the missing Activity-feed entries for the new audit actions.
3. **Migration numbers.** Built as `0058`/`0059`/`0060` on different parents (see the header); re-chained to one line at merge. No migration content changed.
4. **S01, no migration.** The permission is derived from `granted_scopes` and a new key in the existing `capabilities` JSON.
5. **S02, `subscribed_apps` for `comments` is a manual rollout step**, not code: the codebase has no place for subscriptions (the messages subscription is manual too) and an automatic call would be an external effect needing a ledger operation type. The probe reads the subscription back.
6. **S02, strict private-reply limit enforced** (one per commenter per account, ever) because Meta's documentation is ambiguous; `COMMENT_PRIVATE_REPLY_LIMIT_SCOPE=comment` relaxes it.
7. **S02, mock path unchanged**, but for a real account a second proposal for the same comment is a refusal (`PRIVATE_REPLY_COMMENT_ALREADY_USED`) and not the existing action's result.
8. **S03, fonts are the full unmodified Noto Sans files** (about 1.1 MB), not a Latin subset, to keep the licence-clean originals.
9. **S03/S04, price disclosure policy not applied to price cards.** `policy.price_disclosure` is not consulted (a card is an owner-created post from a verified fact).
10. **Merge, OpenAPI drift fixed.** The checked-in `frontend/openapi.json` described the comment `schema` field as the single constant `synthetic-comment-v1`; a fresh export lists `["synthetic-comment-v1", "provider-comment-v1"]`. The file and `schema.d.ts` were regenerated (see the merge report).

---

## 7. Limitations and items waiting on a real account, provider or device

**Meta comments (all live items pending).**
- Nothing was run against Meta. The documentation was read through a summarising fetch tool; each page needs to be re-read before a rollout or an App Review submission.
- **`subscribed_apps` for `comments`:** whether `comments` is an accepted `subscribed_fields` value for this app (a 2026-10 check found `message_echoes` rejected) and the manual subscription step. **Pending.**
- **Webhook delivery to a Development-mode role account** and the authentic Instagram Login payload keys (`comment_id` versus `id`, `parent_id`, `from`). **Pending.**
- **Private-reply semantics:** per comment versus per commenter, eligibility of replies to replies, error codes, idempotency, and whether `recipient_id` equals the later messaging `sender.id`. Enforced strict until the probe says otherwise. **Pending.**
- **Scope in Live mode:** `SCOPES` now asks every connecting user for the comment scope; an unapproved permission may be refused or dropped for non-role users until Advanced Access. `META_REQUEST_COMMENT_SCOPE=false` is the switch. **Pending.**
- **App Review:** the permission request, screencasts (Screencast 3 must be recorded on the real flow, not the mock) and reviewer steps are prepared in `meta-app-review-package.md`; nothing was submitted. Public availability needs Advanced Access.
- The stored comment timestamp comes from `entry.time` (delivery), slightly later than creation; the 10-minute margin and the provider's re-read cover it. Public reply and moderation on real accounts stay off.
- The strict per-commenter rule blocks a returning customer from ever getting a second private reply.
- Other rows of the App Review package and Screencasts 1 and 2 still use Facebook Login names (pre-existing).

**Template images.**
- Exact pixel output is not asserted (FreeType and Pillow differ between Windows and Linux CI); tests use geometry, glyph presence and tolerant goldens. The cards have not been looked at on a real phone or posted to a real Instagram account.
- "This week's classes" is not structured data yet, so `services_list` uses 2 to 6 money facts.
- A command-staged draft shows no image until the render job runs, and the draft page does not poll.
- A replaced logo, and rendered cards never attached to an item, are deleted as orphans after `RETENTION_MEDIA_ORPHAN_DAYS`.
- Real-model behaviour of the new `content.make_price_card` interpretation (TR and EN phrasing) was not run; the evals ran with the fake model only.
- Playwright specs (`frontend/e2e`) were not run in this phase.

---

## 8. Open questions for the owner and working-tree note

1. Meta: confirm the live points in section 7 on a dev-mode test account (reconnect it, turn the flag on, subscribe `comments` manually, run the read-only probes, then the opt-in send probes) and record the sanitized results in `platform-capabilities.md` §1.8. Decide whether to put the fifth scope behind `META_REQUEST_COMMENT_SCOPE=false` until Advanced Access is granted.
2. Is the strict per-commenter private-reply rule acceptable until the probe results are in? (A returning customer never gets a second private reply.)
3. Should `policy.price_disclosure` apply to price cards? Should the 1.1 MB of fonts be subset to Latin (needs fontTools)?
4. Should the draft page poll while a command-staged render job is running? Should the hours card get a structured per-day builder as a next step?
5. If the agent coordinator ever replays an unrecorded private-reply tool call on a real account, it would see a refusal rather than an idempotent answer (S02 risk 2). The checkpointed observation path should prevent it but was not exercised under a real replay.
6. **Working tree.** Every change of Sessions 01 to 04 is uncommitted on `main`, on top of the also-uncommitted Feature Phase 2 work. The git worktrees `agentnest-p3/s01` and `agentnest-p3/s03` (outside the repo) and a git-ignored `.tmp` folder were left as they are. Suggested next step: review, then commit in logical pieces (one per session) before the next phase.
