# Feature Phase 1, Session 05: Visible guarantee and phase close-out (D-01)

**Status:** Implemented and verified offline (backend and frontend tests, sharded full backend run, baseline comparison). Not committed. Stopped for review.
**Baseline:** `main` at `f1cc494` plus the uncommitted Sessions 01 to 04 in the tree (the tree was moved from `fix/ci-green` to `main` by another session during the phase).
**Migration head:** `0048` (unchanged). The next free migration is `0049`. No migration was needed: the validator results were already stored with the draft, and the fact's verification date is derived from the insert-only `fact_versions`.
**Real device or account:** nothing in this session needs one, and nothing was tested on one. Telegram was tested with a fake client.

## 1. What was built

### Fact source beside every placeholder-derived value (server-provided mapping)
- **`app/knowledge/sources.py` (new, one implementation).** `fact_sources(session, workspace_id, rendered, language)` turns the validator's stored record of a draft (`reply_drafts.validation["rendered"]`: key, fact id, version, span, display) into `FactSource(key, label, display, version, verified_at)`; `unique_sources` lists each fact once; `span_records` is the stored form (now shared by `inbox/drafting.py` and the agent). `app/inbox/sandbox.py::_facts_used` (Session 01) now calls it instead of its own code.
- **Verified date = the date of the fact version the draft rendered.** It is the `created_at` of the newest verifying `fact_versions` row (`created`, `value_changed` or `verified` with status `verified`) at or before the rendered version; the service writes that row with the same `clock.now()` as `business_facts.last_verified_at`. So a draft rendered last week keeps last week's date after the price changed, and `fact_versions` is insert-only (INV-17). If the history has no verifying row for that version the date is `null` ("verification date unknown"); it is never guessed. I did not store a date on the draft (no migration).
- **API.** `RenderedFactOut.verified_at` (per placeholder span) and a new `ReplyDraftOut.facts_used: [{key, label, display, verified_at}]` (deduplicated by fact; schema `FactSourceOut`). `GET /…/agent-actions/{id}` gets `facts_used` for `dm.send` (the account agent's approval). Every reply-draft route goes through `inbox/views.draft_out`, so the conversation view, the open draft, recent drafts and `GET /reply-drafts/{id}` (which the approval detail uses) all have it. Labels use the draft's language (as before); a foreign workspace's fact id is never looked up (tested).
- **Web.** The shared `FactsUsed` component (Session 02) is shown under the draft text in `DraftCard` (inbox), in `ReplyApprovalBody` (approval detail) and `AgentApprovalBody`; it receives the server's list unchanged. The green value chip's pop-up now says "Source: Monthly membership, verified 3 Nov" when the date is known. `formatVerifiedDate` moved to `components/formatVerifiedDate.ts` (a react-refresh lint warning otherwise). Approval **list** rows show only the action summary (no reply text), so there is nothing to annotate there; the detail sheet is where the reply text appears.
- **Telegram approval message** (`integrations/channels/telegram/adapter.py`): under "Proposed Reply", a block with one compact line per fact: `• <b>6.000 ₺ / ay</b> — from: Monthly membership, verified 2026-01-15` (`kaynak:` and `doğrulandı` for a Turkish recipient; label language follows the recipient). Day in the workspace timezone (recipient timezone). All database text is `html.escape`d, a value is clipped to 40 characters, a label to 60, and lines that would pass a 3,900-character budget (limit 4,096; the markup counts, so it is conservative) are replaced by "+N more". Customer data rules are unchanged. Content-publication approval messages are unchanged (see limitations).
- **Account-agent drafts now carry the validator result.** Before, only the legacy pipeline stored `validation.rendered`/`issues`/`passed`; an agent template reply stored none, so its source would not show and the report could not judge it. `validate_reply` now returns the rendered span records (`GroundedReply.rendered`, `claims_checked`), and `agent/dm.py` stores `{passed: true, issues: [], rendered}` in the draft for template replies. Server-written replies (calendar slot, owner's answer, customer clarification) are not claim-validated and store nothing new.

### "Replies sent" and "unverified values sent" in the daily report and the Telegram summary
- **New metric `unverified_values_sent`** (`reporting/definitions.py`, `definitions_version` `"2"` to `"3"`, inbox key so staff see it too). Row set = the `replies_sent` message rows joined to their draft where **the stored claim-validator result** has a claim issue (`MONEY`, `PERCENT`, `DISCOUNT_WORD`, `TIME`, `DATE`, `PHONE`, `EMAIL`, `URL`, `NUMBER`) that is not marked `matches_verified`, via `jsonb_path_exists` on `reply_drafts.validation`; **or** the draft is assistant-written (`ai`, `approved_answer`) and its stored `passed` is `false`. It is read from what was stored when the draft was made or edited; nothing is recomputed and nothing is a constant (tests change the stored result and watch the number follow).
- **Counts replies, not values**, because a drill-down row is a record and a record can be in a metric once. A reply with two unverified values counts once. A person's own text with a value that equals a verified one is not counted. `TOO_LONG` and render errors are not claims.
- **Not judged** (in `replies_sent` only): a message with no draft, a draft whose validation retention erased (`{}` or `privacy_redacted`), a server-written agent reply.
- **Simulated data:** no metric filters simulated rows out; each row carries `is_simulated` and the report shows the SIMULATED badge when any contributing row is simulated. The new metric does the same. The test chat is excluded because it writes none of these tables.
- **Old reports:** a saved report from before version 3 does not contain the key; it is served without it, its drill-down for the key is 404, and the UI shows no guarantee card (never "0").
- **Report page:** a card "Never an invented number" (`Uydurma bilgi yok`) at the top shows "Replies sent" and "Unverified values sent", both even at zero (green zero, no link). Above zero the label becomes "Replies that contained unverified values", the number is red and links to the existing drill-down route (`more/reports/:date/unverified_values_sent`, the `MetricItems` screen), with a short instruction. Both metrics are left out of the section rows when the card is shown.
- **Telegram summary:** `get_daily_summary` has `unverified_values_sent` (`None` when the report predates the metric); the "Bugünkü özet / Today's summary" reply ends with "Replies sent" and "Replies with unverified values sent" (both at zero too); the "how many DMs" variant is unchanged.
- **Docs:** `architecture/workflows.md` §F.1 (definition, version 3, details), `architecture/api-design.md` (draft fields, fact sources, metric), `architecture/integrations.md` §5.3 (Telegram), new `operations/demo-price-change-hold.md`.

### Demo script
`docs/operations/demo-price-change-hold.md`: set up, schedule a post that quotes the monthly price and create a reply draft from a simulated customer, change the price by command (`Aylık üyelik artık 7.000 TL`), show the held post and the re-drafted reply with its source and new date, the approval, the report card (and how to make the count nonzero), the practice chat, and web push opt-in. Phrases, button labels and routes were checked against `frontend/e2e/scenario-b/c.spec.ts`, the Turkish catalogs, `app/inbox/impact.py`, `app/content/impact_handlers.py`, `app/cli.py`. **It was not run end to end on a live stack**; the script says so.

### Close-out
`s05-report.md` (this file), `phase-summaries/features-phase-1-summary.md`, `roadmap.md` (Feature Phase 1 row), `sessions.md` (status).

## 2. Files changed (Session 05 only)

Backend, new: `app/knowledge/sources.py`, `tests/integration/inbox/test_fact_sources.py` (13), `tests/integration/reporting/test_unverified_values.py` (13), `tests/unit/integrations/channels/test_telegram_guarantee.py` (3).
Backend, changed: `app/inbox/{schemas,views,sandbox,drafting}.py`, `app/agent/{dm,grounding,work_views}.py`, `app/integrations/channels/telegram/{adapter,handlers}.py`, `app/reporting/{definitions,service}.py`, `app/core/i18n/{en,tr}.json`; tests `tests/helpers/reporting.py` (the scripted day now has 9 AI and 10 owner replies with a stored unverified value, so `unverified_values_sent` is 19, a value no other legacy metric has), `tests/integration/reporting/{test_daily_report,test_report_api,test_report_service}.py` (registry 25 keys, version 3), `tests/integration/agent/{test_dm,test_context_grounding,test_work_views}.py`.
Frontend, new: `src/components/formatVerifiedDate.ts`. Changed: `openapi.json` and `src/api/schema.d.ts` (additive: schemas `FactSourceOut`, `RenderedFactOut.verified_at`, `ReplyDraftOut.facts_used`, `ExactActionPreview.facts_used`; patience diff of `openapi.json` shows one changed line, a comma), `components/FactsUsed.tsx`, `features/inbox/{DraftCard,DraftParts}.tsx`, `features/approvals/{ReplyApprovalBody,AgentApprovalBody}.tsx`, `features/reports/DailyReport.tsx`, `i18n/locales/{en,tr}/{inbox,reports}.json`, tests `inbox.test.tsx` (+2), `approvals.test.tsx` (+1), `reports.test.tsx` (+3).
Docs: listed above.
A mistake I made and reverted: I ran `ruff format` over `app` and `tests`, which reformatted the two known unformatted files (`app/operations/calendar.py`, `tests/integration/test_hardening_integration_regressions.py`); I restored both with `git checkout -- <file>` after confirming their diff was formatting only.

## 3. Checks (exact)

Environment for every backend run: `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN= DEMO_TOOLS_ENABLED=true`, `TEST_DATABASE_URL` = the `.env` value with the database name swapped. Six databases `pivoris_p1s05_{1..6}_test` ran as parallel shards, one more for dev runs and one for the baseline worktree; **all eight were dropped** (verified: none left).

| Command (from `backend/` unless noted) | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 2 files would be reformatted, the two known pre-existing ones (`app/operations/calendar.py`, `tests/integration/test_hardening_integration_regressions.py`) |
| `uv run mypy app` | Success, 360 files |
| `uv run lint-imports` | 19 kept, 4 broken: the same four as at `HEAD` (INV-03 command reach, "approvals and notifications know no subject module", `reporting.home_router -> api.deps`, Telegram AC-4 via `commands.service`). The three web-push contracts and the knowledge contracts are kept |
| Shard 1: `tests/unit tests/contract tests/security tests/isolation` | 1992 passed, 13 skipped, **8 failed** |
| Shard 2: `tests/integration/inbox` | **336 passed** |
| Shard 3: `tests/integration/agent tests/integration/jobs` | 351 passed, **5 failed, 1 error** (one of the failures was mine, fixed, see below) |
| Shard 4: `tests/integration/commands approvals notifications operations` | 296 passed, **11 failed** |
| Shard 5: `tests/integration/reporting content knowledge policy activity` | 559 passed, **1 failed** |
| Shard 6: `tests/integration/{identity,ai,demo,integrations,retention}`, `tests/integration/test_*.py`, `tests/e2e` | 268 passed, **10 failed** |
| After the fix: `tests/integration/agent/test_work_views.py` | 8 passed |
| Earlier focused run: `tests/integration/reporting tests/unit/reporting tests/integration/inbox/test_fact_sources.py` | 146 + 13 passed (the one failure in that run was a wrong assertion in my own new test, fixed) |

**One failure was caused by this session and is fixed:** `tests/integration/agent/test_work_views.py::test_old_snapshot_never_gains_new_metric_keys` asserted `DEFINITIONS_VERSION == "2"`. It now asserts `"3"` and also asserts the old snapshot does not gain `unverified_values_sent`. It passes. Three reporting tests asserting version `"2"` and the registry size were updated before the runs.

**Every other failure is pre-existing; attribution:**
- On the orchestrator's list: `test_cli_migration_status_head_only_and_check_config` (hard-coded head `0044`); `test_telegram_reporting_query_exact_matching_counts` and e2e `test_ac2_telegram_daily_summary_matches_web_report` (both look for `<b>N</b>` in a message that has `<b>Toplam Gelen:</b> N`; the same failure text with and without my change); `test_deliver_channel_notification_failure_records_error`; `test_every_action_the_code_writes_is_known_to_the_feed` (`auth.password_reset_throttled`); `test_import_contracts_are_kept` and e2e `test_ac4_core_architectural_isolation_import_linter` (the 4 contracts); the 2 `test_invite_secrets` and 2 `test_members_and_invites` tests (invite `email`); isolation `cancel-deletion` 404; `test_meta_exposes_only_public_configuration`; `test_cors_allows_only_the_frontend_origin`; 5 of shard 3 are `agent/test_calendar_agent.py` (4 failures + 1 error; the other failed test of shard 3 was mine, above); shard 4's 11 are `commands/{test_content_commands, test_explain_reply_failure, test_queries_failures_permissions}.py`.
- **Not on the list, confirmed at the untouched `HEAD` worktree** (`scratchpad/baseline`, its own database, same environment) where they fail identically: `integration/retention/test_retention.py::test_more_than_1000_rows_are_removed_in_batches_of_1000` (21 sessions opened instead of 15), `integration/test_hardening_integration_regressions.py::test_serious5_pending_approval_holds_slot_and_db_rejects_overlap` and `::test_serious8_telegram_messages_not_swallowed_and_target_replied_question`, `integration/content/test_agent_content_tools.py::test_owner_task_loop_prepares_schedules_waits_for_verified_publish_then_completes` (`KeyError: 'content_id'`). For these four I ran only the failing tests at baseline, not their whole files.
- `integration/test_seed.py::test_seed_refuses_to_run_in_production` fails because I export `DEMO_TOOLS_ENABLED=true` (the config refuses it in production); it fails the same at baseline with the same environment.
- The 11 shard-4 failures were compared by running the three files at baseline: the identical 11 tests fail there (55 passed).

Skipped: `tests/browser` (it holds one fixture module, no tests) and the frontend `scripts/ui-*.mjs` browser scripts. `tests/e2e` (Python, offline) ran inside shard 6.

Frontend (from `frontend/`; Vitest from PowerShell):

| Command | Result |
|---|---|
| `npm.cmd run lint` | 3 errors, the pre-existing `no-explicit-any` in `src/app/router.tsx` (lines 9, 13, 22; fixed on `fix/ci-green`); no warning from my files |
| `npm.cmd run typecheck` | passes |
| `npm.cmd test` | 52 files, **785 tests passed** (779 before; 6 new) |
| `npm.cmd run i18n:check` | passes (2435 keys, 1777 literal `t()` calls) |
| `npm.cmd run build` | built OK (existing Rollup `INEFFECTIVE_DYNAMIC_IMPORT` warnings only) |

## 4. Invariants

INV-01 (every query workspace-scoped; the foreign-fact test; no new table); INV-02 (every value shown comes from the validator's record; the guarantee number is read from stored validator results; nothing here lets an unverified value through, it only reports one); INV-08 (the metric is a SQL row set over persisted records, with a drill-down that equals the count, no model involved); INV-09 (simulated rows flagged, badge unchanged); INV-10 (no secret in the new responses or in Telegram text); INV-17 (the date is derived from the insert-only version history, never rewritten); INV-19 (dates in the workspace timezone in the web and Telegram views). No external call inside a transaction was added.

## 5. Deviations, open questions

1. **"Unverified values sent" counts replies**, not values (drill-down rows are unique per record). The UI says "Replies that contained unverified values" when nonzero. Change it only with a different row model.
2. **"Exclude simulated data as every other metric does"** does not match the code: no metric excludes simulated rows; they are flagged. I followed the code.
3. **Account-agent drafts were changed** (`agent/dm.py`, `agent/grounding.py`) to store the validator result; this goes beyond the brief but is needed for the guarantee to cover agent replies. It is a stored-JSON addition on drafts only; the agent suite shows no new failure.
4. **Labels are current, dates are as rendered.** The draft does not snapshot the fact label; the label shown is the fact's current one in the draft's language. The value shown is the one rendered (the text), and the date is that version's.
5. **Content posts are not covered** (captions are matched by text, not by placeholders, so there is no stored mapping), and the Telegram approval for a content publication is unchanged.
6. **Retention can erase the evidence.** For a day first generated after the text retention window, the validator results are gone and the number reads 0 (it cannot read "unknown"). Scheduled generation runs daily, so a normal day is stored long before. Say if you want an "evidence missing" state.
7. The demo script was not run live (see section 1). No screenshots this session.
8. Open items carried from earlier sessions are in the phase summary (Telegram delivery wiring question, push subscribe allowlist, real-device checks).
