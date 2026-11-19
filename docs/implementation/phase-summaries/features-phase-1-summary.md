# Feature Phase 1 Close-Out Summary: Before the First Pilot

- **Phase:** Feature Phase 1 (F-02 test chat, F-01 installable app and Web Push, D-01 visible "never invents a price" guarantee)
- **Specification:** [features-phase-1-before-first-pilot/sessions.md](../features-phase-1-before-first-pilot/sessions.md), source [pre-launch-feature-recommendations.md](../../review/pre-launch-feature-recommendations.md) §4 step 1
- **Sessions executed:** 01 to 05, each with a report in [features-phase-1-before-first-pilot/](../features-phase-1-before-first-pilot/) ([s01](../features-phase-1-before-first-pilot/s01-report.md), [s02](../features-phase-1-before-first-pilot/s02-report.md), [s03](../features-phase-1-before-first-pilot/s03-report.md), [s04](../features-phase-1-before-first-pilot/s04-report.md), [s05](../features-phase-1-before-first-pilot/s05-report.md))
- **Baseline Git commit:** `f1cc494` (`main`). **Nothing is committed**: all the work of the five sessions is uncommitted on `main` (see section 8, working-tree note).
- **Alembic migration head:** `20261116_0048_web_push_delivery.py` (revision `0048`). The next free migration is `0049`. Session 05 added no migration.
- **Status:** **Implemented and verified offline. Stopped for review.** Nothing was run against a real phone, a real push service, a real Telegram bot, a real Instagram account or the real model.
- **Date:** 2026-11-16

> [!NOTE] Current Status (Date: 2026-11-19)
> The code for this feature phase was subsequently committed to `main` (`e1c9f13`). Its functionality has been integrated, verified offline, and extended to Account Agent pilot readiness in Sessions 00–10 of the `answeres2.md` plan. The original historical test records and offline verification below are preserved intact. Remaining live provider verifications (live phone notifications, live Meta webhooks/publishing, live speech/vision APIs) are cataloged as pending live verification runbooks in Session 11 (`docs/implementation/account-agent-pilot-readiness/s11-report.md`).

---

## 1. Executive summary

The phase addresses the two biggest pilot risks: owners not trusting the assistant, and owners not seeing approvals (RK-03).

- **F-02, test chat (Sessions 01 and 02).** An owner or manager can write to their own assistant as a customer, at the end of workspace setup and at any time from the Assistant page. The reply, the decision (`auto`, `approval_required`, `human_required`, `blocked`), a plain-language reason and the facts used come back, labelled SIMULATED. Nothing is sent and nothing counts in reports, the Home counts, approvals, notifications or customer memory.
- **F-01, installable app and push (Sessions 03 and 04).** The web app has a manifest, icons and a push-only service worker. Owners can opt in (per category: approvals, owner questions, failures) to phone notifications through a new `web_push` owner channel that uses the existing delivery ledger and quiet-hours policy. Payloads carry no customer text. A per-user device list and the iOS "Add to Home Screen" guide are included.
- **D-01, the visible guarantee (Session 05).** Next to every value of a drafted reply the app now shows which verified fact it came from and when that version was verified (inbox draft, approval detail, the account agent's approval, the test chat, the Telegram approval message). The mapping is built once on the server. The daily report and the Telegram summary gain two lines, "replies sent" and "unverified values sent", read from the claim validator's stored results for replies that were actually sent (never a constant; above zero it links to the records behind it).

---

## 2. What changed, by feature

### 2.1 F-02 test chat
- **Backend (S01):** service `app/inbox/sandbox.py`, routes `GET`, `POST /messages`, `POST /reset` under `/api/v1/workspaces/{id}/assistant/test-chat`, job `assistant_test_draft`, permission `assistant.test` (owner, manager), table `assistant_test_turns` (migration `0046`, RLS forced), rate limits (20 per hour, 60 per day per workspace), `TEST_CHAT_RATE_LIMITED`. The drafting inputs were extracted from `inbox.context.prepare` into `gather_workspace_inputs()`. A guard in `operations/send.py` refuses a simulated draft aimed at a non-mock account.
- **Frontend (S02):** the "Try your assistant" screen (`features/test-chat`), the shared `components/FactsUsed.tsx`, starter questions derived from verified facts, a last skippable step in `CreateWorkspaceWizard`, a button on the Assistant page, TR and EN strings.
- **Tests:** `tests/integration/inbox/test_assistant_test_chat.py` (33: roles, 404 for foreign workspaces, nothing sent or counted with row counts compared before and after, reset, rate limits, quality of the shown draft), RLS and permission unit tests, `src/features/test-chat/testChat.test.tsx` (16) and `wizard.test.tsx`.

### 2.2 F-01 installable app and Web Push
- **Installable app (S03):** `manifest.webmanifest`, icons (192, 512, maskable, Apple touch, favicon), `index.html` meta tags (P-17, partly), push-only `sw.js` (no cache, no fetch handler), registration in production builds or with `VITE_ENABLE_SW=true`, Caddy CSP `worker-src`/`manifest-src`.
- **Subscriptions (S03):** table `push_subscriptions` (migration `0047`, RLS forced, keys encrypted with the token key ring, unique per workspace, user and endpoint), `GET /config`, `GET`, `POST`, `DELETE` under `/push-subscriptions`, `WEB_PUSH_VAPID_PUBLIC_KEY`, `WEB_PUSH_VAPID_PRIVATE_KEY`, `WEB_PUSH_SUBJECT`, CLI `generate-vapid-keys`, dependency `pywebpush` 2.5.0.
- **Channel (S04):** `WebPushChannel` in `integrations/channels/web_push/` (registered lazily), SSRF allowlist plus public-IP check on every send, payload builder with fixed text and a same-origin link, `push_preferences` (migration `0048`) and `web_push` added to the delivery ledger's channel constraint, delivery through `deliver_channel_notification` (3 attempts), 404/410 revokes a device, three import-linter contracts, Settings card and a once-only prompt after the first approval, iOS guide.
- **Tests:** `test_push_subscriptions.py` (45), `test_push_subscriptions_isolation.py` (4), `test_web_push_settings.py` (7), `test_web_push_sender.py` (69), `test_web_push_payloads.py` (54), `test_web_push_channel.py` (33), `test_push_preferences.py` (6), `test_push_preferences_isolation.py` (4), `test_web_push_privacy.py` (2), import contract test, frontend `pwa.test.ts` (17) and `push.test.tsx` (18). Migration up and down verified on a scratch database; Chromium reported the production build as installable.

### 2.3 D-01 visible guarantee (this session)
- **One server-side mapping** (`app/knowledge/sources.py`): for each `{{fact:key}}` the draft rendered, the fact label (in the draft's language; Telegram uses the recipient's) and **when the rendered fact version was verified** (the `created_at` of that version's insert-only `fact_versions` row, which the service writes with the same clock value as `last_verified_at`). A price that changed after the draft was made does not make the draft look freshly verified. `null` means the history holds no verification of that version; it is never inferred.
- **API:** `ReplyDraft.rendered_facts[].verified_at` and a new deduplicated `ReplyDraft.facts_used[]` (`key`, `label`, `display`, `verified_at`); `GET /agent-actions/{id}` gets `facts_used` for `dm.send`. The test chat's `_facts_used` now calls the same helper (one implementation).
- **Web:** `FactsUsed` is shown under the draft text in the inbox `DraftCard`, in the reply approval detail (`ReplyApprovalBody`) and in the agent approval (`AgentApprovalBody`); the green value chip's pop-up now carries the date. The frontend maps nothing: it passes the server's list through.
- **Telegram approval message:** one line per fact under the proposed reply, `• 7.000 ₺ / ay — from: Monthly membership, verified 2026-11-03` (Turkish: `kaynak:`, `doğrulandı`); HTML-escaped, values clipped to 40 and labels to 60 characters, a 3,900-character budget (the API limit is 4,096) with "+N more".
- **Daily report:** metric `unverified_values_sent` (`definitions_version` 3). A reply counts when the claim-validator result stored with its draft lists an unmatched claim issue, or when an assistant-written draft was sent although its stored result says it did not pass. The report page shows a card with "replies sent" and "unverified values sent" at the top, both at zero too, linking to the drill-down when above zero. `get_daily_summary` and the Telegram "today's summary" carry the same two numbers.
- **Validator results are now stored for account-agent template replies** (`app/agent/dm.py` writes `{passed, issues, rendered}` into the draft; `validate_reply` returns the rendered spans). Before, only the legacy pipeline stored them.
- **Docs:** `workflows.md` §F.1 (metric definition, details), `api-design.md`, `integrations.md` §5.3, [demo-price-change-hold.md](../../operations/demo-price-change-hold.md) (the demo script).
- **Tests:** `tests/integration/inbox/test_fact_sources.py` (13), `tests/integration/reporting/test_unverified_values.py` (14), the scripted AC-E1 day now has 19 replies with a stored unverified value, `test_telegram_guarantee.py` (3), agent assertions in `test_dm.py` and `test_context_grounding.py`; frontend `inbox.test.tsx`, `approvals.test.tsx`, `reports.test.tsx`.

---

## 3. Demo steps

The full script, starting with the price-change hold, is [docs/operations/demo-price-change-hold.md](../../operations/demo-price-change-hold.md). In short: schedule a post that quotes the monthly price and let a simulated customer ask for it; change the price by command (`Aylık üyelik artık 7.000 TL`, confirm); show the post held (**Beklemede**, "Kullandığı işletme bilgisi değiştiği için beklemeye alındı.") and the reply draft redrafted with 7.000 ₺ and its source and date; open the approval; open the daily report card; try the practice chat; then, on a real phone, turn on notifications after the first approval. The script was written from the code paths and E2E specs and **not run as one sequence on a live stack**.

---

## 4. Checks run

Full detail, exact commands and per-failure attribution: [s05-report.md](../features-phase-1-before-first-pilot/s05-report.md) §3. Environment: `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN= DEMO_TOOLS_ENABLED=true`; the backend suite was run as six parallel shards on their own databases (all dropped afterwards).

| Check | Result |
|---|---|
| `ruff check .` | passes |
| `ruff format --check .` | 2 files (pre-existing, not touched) |
| `mypy app` | passes (360 files) |
| `lint-imports` | 19 kept, 4 broken (the same four as at `HEAD`); the web push contracts are kept |
| Backend tests, six shards (about 3,600 tests; everything except `tests/browser`, which has no tests) | 3,802 passed, 13 skipped, **35 failed or errored in total, all failing the same way at an untouched `HEAD` worktree or on the list below**; one failure caused by this phase (an old test that hard-coded the report definitions version) was fixed and passes |
| Frontend `lint` | 3 pre-existing `no-explicit-any` errors in `src/app/router.tsx` |
| Frontend `typecheck`, `i18n:check`, `build` | pass |
| Frontend `npm.cmd test` | 52 files, 785 tests passed |

**Failures that are not caused by this phase** (verified against an untouched `HEAD` worktree where not already known): isolation `cancel-deletion` 404; `test_cli_migration_status_head_only_and_check_config` hard-codes head `0044` (the head is now `0048`); the Telegram reporting test (and its e2e twin) and the delivery-policy unit test; the `auth.password_reset_throttled` activity template; 4 import-linter contracts (and the e2e test that runs them); invite responses carrying `email` (4 tests); `/meta` `calendar_providers`; a CORS test; `agent/test_calendar_agent.py` (4 failures, 1 error); `commands/{test_content_commands, test_explain_reply_failure, test_queries_failures_permissions}.py` (11); and four found in the full run that were not on the earlier list and also fail at `HEAD`: `retention/test_retention.py::test_more_than_1000_rows_are_removed_in_batches_of_1000`, `test_hardening_integration_regressions.py::test_serious5_...` and `::test_serious8_...`, `content/test_agent_content_tools.py::test_owner_task_loop_...`. `test_seed_refuses_to_run_in_production` fails only because the runs export `DEMO_TOOLS_ENABLED=true`. `ruff format --check` fails on two pre-existing files.

---

## 5. Deviations from the briefs

1. **S01, test chat storage.** The brief asked for a sandbox conversation using `is_simulated = true`. It uses a new table `assistant_test_turns` instead. A `conversations` row needs a `social_accounts` row, the unique "one active account per workspace" index leaves no room for a second sandbox account, and a real workspace may have no account at all or a real Meta account the sandbox must never touch. The consequence is stronger than the brief: nothing downstream (approval, send job, operation, notification, attention count, memory, report row) can ever see a test turn, because that code never reads the table.
2. **S02, wizard order.** The workspace is created at the end of step 3 as before and the try step runs after creation (the endpoints need a workspace); the progress bar shows 4 steps.
3. **S03, uniqueness** is per (workspace, user, endpoint) instead of per (user, endpoint): one browser has one subscription and one person can own several workspaces. S03's migration constraint naming was corrected by the orchestrator (`uq_assistant_test_turns_workspace_id_id` in `0046`).
4. **S04, delivery ledger split.** `dispatch_channel_notification` moved to `notifications/delivery_ledger.py` (re-exported from `notifications/jobs.py`) because importing the job module from `notify()` broke two more import contracts. Opt-in is per category (three), not per notification type (six).
5. **S05, "unverified values sent" counts replies, not values.** The drill-down lists records and a record can appear once per metric, so a reply that holds two unverified values counts once. The UI label for a nonzero count therefore says "Replies that contained unverified values". At zero the label is the briefed "Unverified values sent".
6. **S05, "exclude simulated data as every other metric does".** No report metric filters simulated rows out: each row carries `is_simulated` and the report shows a SIMULATED badge when any contributing row is simulated. The new metric follows that. The test chat is excluded because it writes none of these tables.
7. **S05, the verified date** is that of the fact version the draft rendered (derived from `fact_versions`), not the fact's current verification and not a stored per-draft date; no migration was needed.
8. **S05, agent drafts.** The account agent's template replies did not store a validator result or rendered spans; they do now (`app/agent/dm.py`, `app/agent/grounding.py`). Replies the agent writes without a template (calendar slot, owner's answer, customer clarification) are server-written and not claim-validated; they carry no result and are not judged by the new metric.

---

## 6. Limitations

**Test chat (F-02)**
- Uses the legacy drafting pipeline, **not** the Phase 7.5 account agent; an account on `controller_mode = agent` may answer differently.
- Never shows `blocked` for channel reasons (it assumes a healthy, connected account with an open window).
- Shares the daily LLM budget (500 calls per workspace) with real replies; the limits (20 an hour, 60 a day) are per workspace, not per member.
- In the wizard step (step 4) a new workspace has no facts, so most answers are "a person is needed"; product may want it moved after knowledge entry.
- Dates follow the app format ("Nov 3", "3 Kas"); starter questions are in the business language; the input is not sticky above the bottom navigation.
- **Never run against the real model** (`LLM_PROVIDER=openai`, `gpt-6-luna` not yet run live); every result used the deterministic fake provider.

**Installable app and push (F-01)**
- The maskable icon is the same pixels as `icon-512.png` (it needs a look on an Android adaptive-icon launcher). Key rotation does not re-encrypt push keys (`operations/key_rotation.py` covers social accounts only). P-17 is only partly closed (no `og:image`). The `Caddyfile` CSP change was never exercised.
- Subscribing still accepts any public `https` host (a device on a host outside the allowlist is revoked at its first send); the SSRF allowlist plus a public-IP check on every send leave a residual DNS-rebinding window, documented in `security-and-privacy.md`. `pywebpush` pulls in `aiohttp` (it imports it at load; our code never uses it).
- Quiet-hour pushes are not replayed in the morning; the notification stays in the app. Opt-in is per category. Partial success counts as delivered. A 429 `Retry-After` is not honoured (fixed backoff).
- **Important finding (S04), open question for the owner:** `dispatch_channel_notification` was never called from production `notify()`, so Telegram owner notifications through the ledger were not wired at all; only `web_push` is wired now. Telegram approval buttons therefore reach the owner only through whatever path existed before this phase. Decide whether Telegram should be wired the same way.

**Visible guarantee (D-01)**
- The metric reads the validator result **stored with the draft**. A draft whose validation retention erased (`{}`, `privacy_redacted`), a message with no draft, and a server-written agent reply carry no result and are in "replies sent" only; for a day first read after the text-retention window the number can read 0 because the evidence is gone. A saved report from before this metric does not show the guarantee card (it is not shown as zero).
- The fact labels in a draft are the facts' **current** labels (the draft does not snapshot them); only the verified date and the value are as rendered.
- Content posts (feed and story captions) are not covered: they match values by text rather than by placeholders, so there is no placeholder-to-fact record to show. The Telegram "content publication" approval message is unchanged.
- The Telegram daily summary is a reply to a question; the report is not pushed to Telegram on a schedule.
- No screenshots were taken for Session 05 (component tests with mocked data cover the rendering).

---

## 7. Items waiting on a real device or account

- **Android Chrome and iPhone (iOS 16.4+, from the Home Screen):** install, opt-in prompt after the first approval, a push arriving with no customer text, tapping it opens Approvals, quiet hours, revocation after sign-out. Steps: [s04-report.md](../features-phase-1-before-first-pilot/s04-report.md) §7. **Not done.**
- **Android adaptive-icon launcher:** the maskable icon.
- **Real push service** accepting a subscription and a send from this server (FCM, Mozilla, Apple), with real VAPID keys on an HTTPS deployment.
- **Real Telegram bot:** the approval message with the new source lines and the summary lines (tests use a fake client).
- **Real model (`gpt-6-luna`):** the test chat and drafting with real output; `LLM_PROVIDER=openai` was never run for this phase.
- **Real Instagram (Meta) account:** none of the phase's features was exercised against one; sends in tests go to the mock account.
- **Caddy:** the `Caddyfile` CSP and manifest header change has not been run.
- **Demo script:** one walk through [demo-price-change-hold.md](../../operations/demo-price-change-hold.md) on a live stack with the worker.

---

## 8. Open questions for the owner and working-tree note

1. Wire Telegram delivery through the ledger like `web_push`? (S04 finding above.)
2. Tighten `POST /push-subscriptions` to the push-service allowlist? (A one-line change plus test edits.)
3. Should "unverified values sent" count individual values rather than replies? (Needs a different drill-down.)
4. Should the test chat run the account agent in a dry-run mode when an account uses the agent controller, or at least say so in the UI?
5. Move the wizard's try step after knowledge entry?
6. **Working tree.** Mid-phase another session moved the working tree from `fix/ci-green` to `main`, so every change of Sessions 01 to 05 is uncommitted on `main`. `frontend/openapi.json` will probably conflict with `fix/ci-green` (commit `ba97bef` and later), which regenerated it; the phase's changes to it are additive patches (new paths and schemas only). `fix/ci-green` also fixed the three `no-explicit-any` lint errors in `src/app/router.tsx` that remain here.
