# Feature Phase 1, Session 01: Test chat backend and scope update (F-02, part 1)

**Status:** Implemented and verified offline. Not committed (per the brief).
**Baseline commit:** `f1cc494` (`main`), plus the uncommitted work of this session.
**Migration head:** `0046` (`20261115_0046_assistant_test_chat.py`, down revision `0045`). **Session 03's push migration is now `0047`**; `sessions.md` is updated.

## 1. What was built

A real workspace, with or without a connected Instagram account, can send test customer messages and get the draft the assistant would produce, its decision, the reason and the facts used. Nothing is sent and nothing is counted anywhere.

### Design decision (deviation from the brief, with reasoning)

The brief suggested a sandbox *conversation* using `is_simulated = true`. A `conversations` row needs a `social_accounts` row (composite FK, unique per account), the unique "one active account per workspace" index leaves no room for a second sandbox account, and a real workspace may have no account at all (the onboarding step) or a Meta account (which the sandbox must never touch). So the sandbox is a **dedicated table, `assistant_test_turns`**, and not rows in `conversations`/`messages`/`reply_drafts`. The consequence is stronger than the brief asked for: nothing the real pipeline does after drafting (approval, `send_reply` job, operation, notification, attention count, customer memory, report row) is reachable, because none of that code ever reads this table. The drafting pipeline itself is the real one (shared facts, language choice, `drafting.make_plan`, claim validator, `reply_workflow.decide`).

"Extract the simulation path out of the dev-only router": `demo/simulator.py` was already a service module and only the mock-webhook path (`mock_account`, signed webhook, `sim_inbound_messages`) is tied to a mock account, so it cannot serve a real workspace. What is shared is the drafting logic, which I extracted from `inbox.context.prepare` into `gather_workspace_inputs()` (behaviour-preserving; `prepare` now calls it). The dev router and the simulator are unchanged. The new service does not import `app.demo` (import contract "demo is imported only by main and cli" stays kept) and does not read `DEMO_TOOLS_ENABLED` (tested with it off).

### Endpoints (all under `/api/v1/workspaces/{workspace_id}/assistant/test-chat`)

| Method & path | Result |
|---|---|
| `POST /messages` | `{text}` (1-500 chars) -> 202 `AssistantChatTurn`, `status: pending`. The turn id is the run id |
| `GET ` | `{items[], remaining_this_hour, remaining_today}`: the signed-in user's chat, oldest first. Poll until nothing is `pending` |
| `POST /reset` | `{cleared}` |

`AssistantChatTurn = {id, status, customer_text, created_at, completed_at, is_simulated: true, draft: null | {text, suggestion_text, decision, reasons[], facts_used[{key,label,display,verified_at}], language, intent, flags[]}}`. Permission: new `assistant.test` (owner and manager; staff 403; foreign workspace 404). A member sees and clears only their own chat. Draft generation stays asynchronous through the existing job queue: new job type `assistant_test_draft` (same three-phase handler, retries and backoff as `draft_reply`; no second mechanism).

### Files

New: `backend/app/inbox/sandbox.py` (service), `backend/app/inbox/sandbox_router.py`, `backend/migrations/versions/20261115_0046_assistant_test_chat.py`, `backend/tests/integration/inbox/test_assistant_test_chat.py` (33 tests).
Changed (backend): `app/inbox/models.py` (`AssistantTestTurn`), `app/inbox/context.py` (`gather_workspace_inputs`), `app/inbox/jobs.py` and `payloads.py` (job), `app/api/router.py`, `app/core/config.py` (`TEST_CHAT_MAX_MESSAGES_PER_HOUR`=20, `..._PER_DAY`=60), `app/core/errors.py` + `i18n/en.json` + `i18n/tr.json` (`TEST_CHAT_RATE_LIMITED`, 429), `app/core/db.py` (`CATEGORY_C_TABLES`), `app/identity/permissions.py`, `app/operations/send.py` (guard below), `tests/unit/identity/test_permissions.py`, `tests/unit/core/test_rls_policies.py` (53 -> 54 tables), `tests/integration/inbox/test_meta_registry_execution.py` (its helper marks rows non-simulated when it turns the account real, because of the new executor guard).
Changed (frontend, generated only): `frontend/openapi.json` (patched: only the 3 new paths and 6 new schemas inserted, 388 added lines, nothing else touched) and `frontend/src/api/schema.d.ts` (regenerated with `npm run gen:api`, 239 added lines). Session 02 can use them as they are.
Docs: `product/mvp-scope.md` (PWA/Web Push removed from Deferred; "Feature Phase 1" in-scope section with F-02, F-01, D-01), `implementation/roadmap.md` (feature-phase table linking to `sessions.md`), `features-phase-1.../sessions.md` (status, migration number), `architecture/api-design.md` (new §2.6a), `data-model.md`, `background-jobs.md`, `observability.md`, `security-and-privacy.md` (permission and privacy row), `operations/environment-variables.md`.

## 2. Contracts changed

- Schema: table `assistant_test_turns` (tenant, `workspace_id NOT NULL`, composite FK to `agent_runs`, RLS enabled and forced, policy `tenant_isolation_policy`, grants; `CHECK (is_simulated)`; `CHECK (status <> 'ready' OR decision IS NOT NULL)`). Listed in `CATEGORY_C_TABLES`.
- Endpoints, job type `assistant_test_draft`, permission `assistant.test`, error code `TEST_CHAT_RATE_LIMITED`, two env vars. All documented as listed above.

## 3. How each "Done when" item is met

| Item | Evidence (all in `tests/integration/inbox/test_assistant_test_chat.py` unless noted) |
|---|---|
| Role checks | `test_owner_and_manager_can_use_the_chat[owner/manager]`, `test_staff_cannot_use_the_chat` (403 on all three routes, no row written); `tests/unit/identity/test_permissions.py` |
| Isolation (foreign workspace 404) | `test_a_member_of_another_workspace_gets_404` (POST, GET, reset); the generic `tests/isolation` harness enumerates the new routes automatically and passed; `test_each_member_sees_only_their_own_chat`; RLS coverage test for the new table |
| No send, no operation | `test_nothing_is_sent_or_counted_in_a_workspace_with_a_connected_account`, `test_even_an_automatic_decision_sends_nothing` (forces decision `auto`; still no job other than `assistant_test_draft`, no operation, no sim-sent message), `test_the_turn_table_can_never_hold_a_real_row`. Row counts of conversations, messages, reply_drafts, approvals, operations, notifications, inbound_events, sim messages, customer identity/memory/sources and audit_logs, plus every non-test job, are identical before and after |
| Report exclusion | `compute_metrics` for the local day (all metrics, incl. `has_simulated_data`), `GET /home/attention`, `/approvals`, `/notifications` and `/conversations` are identical before and after (`test_nothing_is_sent_or_counted...`, `test_a_workspace_with_a_real_conversation_keeps_its_numbers`, which has a real draft and approval that stay counted). I did **not** edit `reporting/definitions.py` or `metrics.py`: they cannot see this table. I did not audit each metric's `is_simulated` filter individually; exclusion is structural and proven by the equality tests |
| Reset | `test_reset_clears_the_chat_and_its_content`, `..._only_clears_the_callers_chat`, `test_a_draft_that_arrives_after_a_reset_is_discarded`, `test_a_new_chat_starts_after_a_reset_without_the_old_messages` |
| Rate limit | hourly (with `Retry-After`, window slides), daily, per workspace not per member, reset gives nothing back, at most 3 drafts pending, old rows purged, another workspace unaffected, defaults sane (6 tests+) |
| Draft quality of content shown | price answer with `6.000 TL` and `facts_used` (key, label, display, `verified_at`); complaint -> `human_required` + `INTENT_COMPLAINT` + suggestion only; invented price -> `GROUNDING_FAILED`, no sendable text, marked suggestion; unverified price never quoted (`FACT_NOT_USABLE`); LLM down -> `human_required` `LLM_UNAVAILABLE`; works with demo tools off and with no connected account |
| Send executor / ledger refuse simulated -> real | New guard in `operations/send.py`: a simulated draft or conversation about to go through a non-mock account is cancelled (`SIMULATED_TO_REAL_ACCOUNT`) before any operation row, and `_get_or_create_operation` raises if reached. `test_the_send_executor_refuses_a_simulated_draft_for_a_real_account`. Note this is not "refuse every simulated conversation": simulated conversations legitimately send through the mock account in the demo. The sandbox itself never reaches the executor at all |

## 4. Checks run (exact)

Environment for every run: `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock DEMO_TOOLS_ENABLED=true`, `TEST_DATABASE_URL` pointing to my own database `pivoris_p1s01_test` (the repo `.env` sets `DEMO_TOOLS_ENABLED=false`, `LLM_PROVIDER=openai`, `INSTAGRAM_ENABLED_PROVIDERS=meta`, which makes the dev-route tests fail on this machine regardless of code; the first fast run without `DEMO_TOOLS_ENABLED=true` showed 2 extra failures for that reason only).

Run from `backend/` with `uv run` (Windows). `MEDIA_STORAGE_BACKEND=local` was also set for the last run (the repo `.env` sets `s3`, which made 6 publish and demo tests fail only on this machine).

| Command | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 3 files would be reformatted, none mine: `app/notifications/jobs.py`, `app/operations/calendar.py`, `tests/integration/test_hardening_integration_regressions.py` (not formatted at HEAD either). All files I created or changed are formatted |
| `uv run mypy app` | Success, no issues in 349 files (the ~5 older errors in `narrate_command_result.py` and `query_insights_summary.py` did not appear at this HEAD) |
| `uv run lint-imports` | 4 contracts BROKEN, all pre-existing and unrelated to inbox (INV-03 command reach via `notifications.jobs -> channels -> commands.narrator`, "approvals and notifications know no subject module", `reporting.home_router -> app.api.deps`, Telegram adapter AC-4 via `commands.service`). All other contracts KEPT, including "demo is imported only by main and cli" and "inbox uses only the webhook side" |
| `uv run alembic upgrade head` / `downgrade 0045` / `upgrade head` on a scratch database | clean both ways; after upgrade the table has RLS enabled and forced and policy `tenant_isolation_policy`; after downgrade the table is gone |
| `uv run pytest tests/integration/inbox/test_assistant_test_chat.py` | 33 passed |
| `uv run pytest tests/unit tests/isolation tests/security tests/contract` | 1850 passed, 13 skipped (live probes), 8 failed. 7 of the 8 fail identically at an untouched `HEAD` checkout (git worktree at `f1cc494`, same database and environment): `test_deployment_workflow_and_rollback::test_cli_migration_status_head_only_and_check_config` (expects head 0044), `test_telegram_commands_media::test_telegram_reporting_query_exact_matching_counts`, `test_delivery_policy::test_deliver_channel_notification_failure_records_error`, `test_activity_templates::test_every_action_the_code_writes_is_known_to_the_feed` (`auth.password_reset_throttled`), `test_import_rules::test_import_contracts_are_kept`, `test_workspace_isolation::test_the_same_requests_succeed_for_the_member_own_workspace` (`cancel-deletion` 404), `test_invite_secrets::test_the_invite_response_models_are_allow_lists` (extra `email`). The 8th, `test_invite_secrets::test_the_invite_token_is_never_logged_audited_notified_or_queued`, passes alone on my tree and at baseline; it reads captured log output and failed only in this full run (looks order-dependent; I did not investigate) |
| `uv run pytest tests/integration/inbox tests/integration/reporting tests/integration/demo tests/integration/operations tests/integration/policy tests/integration/notifications tests/integration/jobs tests/integration/ai tests/integration/identity` | 700 passed, 12 failed in the first run. Causes: (a) 2 `test_meta_registry_execution` tests were **caused by my send guard** (they flip a mock account to `meta` after a simulated draft was approved); I updated that test helper to mark the rows non-simulated, which is what a real account's rows are; (b) 8 demo and jobs tests failed only because `.env` has `MEDIA_STORAGE_BACKEND=s3`; (c) 2 invite tests (extra `email`) are the same pre-existing failure as above. Re-run of `test_meta_registry_execution`, `tests/integration/demo`, `jobs/test_concurrency.py`, `jobs/test_restart.py`, `identity/test_members_and_invites.py` and the new test file with `MEDIA_STORAGE_BACKEND=local`: 71 passed, 2 failed (only the pre-existing invite tests) |
| `npm.cmd run typecheck` (frontend) | passes with the regenerated `schema.d.ts`. Other frontend checks were not run (no frontend source changed) |

**Not run:** the full ~3,550-test suite; `tests/integration/agent`, `content`, `commands`, `knowledge`, `approvals`, `activity`, `retention`, `integrations`, `e2e`, `browser`. The integration directories I did run cover everything that calls `inbox.context.prepare`, the draft job, the send executor and reports. The agent and retention suites were not run although I touched `inbox.context` (a pure extract-function refactor) and added a table; the retention suite does not know the new table.

## 5. Invariant notes

INV-01 (tenant column, composite FK, RLS forced, 404 on foreign ids, per-user visibility), INV-02 (draft comes from the real placeholder renderer and claim validator; facts shown come from the validator's record), INV-04 (the model is still only a proposal; the decision is the policy engine's), INV-09 (`is_simulated` always true by a check constraint, in every response; the executor guard), INV-15 (no provider call from the sandbox; `inbox` still does not import the mock/meta adapters), INV-20 (works without demo tools; no `app.demo` import). Time comes from the injected `Clock`; no external call inside a transaction (the model is called between the two transactions, as in `draft_reply`).
Not done on purpose: no audit-log rows for test messages (they would show in the activity feed, and the content is the owner's own test text); the LLM runs are still recorded in `agent_runs` (they appear in system health and count against the daily budget).

## 6. Limitations and open questions

1. **Legacy pipeline only.** The test chat shows the legacy drafting pipeline (decision, reasons, facts). If an account runs the Phase 7.5 agent (`controller_mode = agent`), real DMs are answered by the agent, whose behaviour the test chat does not reproduce. Default is `legacy`. Decide whether Session 02 should say so in the UI or whether a later session should run the agent in a dry-run mode.
2. **The channel is assumed healthy** (account connected, messaging allowed, window open). The decision therefore never shows `blocked` for connection reasons; it can still be `blocked` only if policy says so. The decision does reflect the real automation policy and readiness (for example `READINESS_NOT_READY`), so a fresh workspace will mostly see `approval_required`.
3. **Shared LLM budget.** Test messages count against `LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY` (500), so heavy use could push real replies to a human. The test chat limit (60 a day, 20 an hour, plus one repair call each) bounds this to roughly a quarter of the budget.
4. **Retention.** Test turns are deleted 2 days after creation, but only when that workspace sends another test message (and with the workspace). An idle workspace keeps its last test text (scrubbed if reset). I did not touch `retention/cleanup.py` because its counts feed an audit entry whose shape tests assert; add a rule there if that is not acceptable.
5. The rate limit is per workspace, so two members share it. Per-user limits were not added.
6. Real-model behaviour was not run (`LLM_PROVIDER=openai`, `gpt-6-luna` not yet run live per the project notes). All results above use the deterministic fake provider and scripted proposals.
7. Frontend client strings for `TEST_CHAT_RATE_LIMITED` and for the reason codes are Session 02's work. The backend i18n catalogs (tr, en) have the error text.

## 7. Working-tree notes

- During the session the shared tree changed under me: the branch went from `fix/ci-green` to `main` at `f1cc494` (reflog: `reset: moving to HEAD`), and the uncommitted `frontend/src/app/router.tsx` change and some format-only edits by another session disappeared from `git status`. I did not cause that (I never ran stash/reset/checkout on tracked files except `git checkout frontend/openapi.json`, my own file, to redo my patch), and I did not touch `router.tsx`. If that router change mattered it needs to be recovered from whoever made the reset.
- I ran `ruff format` only on files I created or edited. `ruff format --check .` reports 3 files that are not mine and not formatted at HEAD: `app/notifications/jobs.py`, `app/operations/calendar.py`, `tests/integration/test_hardening_integration_regressions.py`.
- A temporary git worktree at HEAD was used to get a baseline of failing tests and has been removed. The temporary databases `pivoris_p1s01_test` and `pivoris_p1s01_mig` are dropped at the end.

## 8. Handoff to Session 02

- Use `frontend/openapi.json` / `src/api/schema.d.ts` types `AssistantChatOut`, `AssistantChatTurnOut`, `AssistantChatDraftOut`, `FactUsedOut`, `AssistantChatMessageIn`, `AssistantChatResetOut`.
- Poll `GET` every 1 to 2 seconds while any turn is `pending` (a draft takes the debounce-free job time: about a second with the fake model, a few seconds with a real one; up to about 3 minutes only when the provider is retrying). Show the `is_simulated` badge on every turn.
- Handle 429 `TEST_CHAT_RATE_LIMITED` (`Retry-After` header, `params.retry_after`) and show `remaining_*`.
- Reason codes to explain in plain words: `POLICY_REQUIRES_APPROVAL`, `AUTOMATION_OFF`, `READINESS_NOT_READY`, `INTENT_*`, `FLAG_*`, `ESCALATION_KEYWORD`, `MODEL_REQUESTED_HUMAN`, `FACT_NOT_USABLE`, `GROUNDING_FAILED`, `LANGUAGE_UNSUPPORTED`, `ATTACHMENT_ONLY` (not reachable in the chat), `LLM_UNAVAILABLE`, `LLM_BUDGET_EXCEEDED`, `INJECTION_SUSPECTED`.
- `draft.text` is null when a person must answer; show `suggestion_text` (it may contain the markers ⟦ ⟧ around unverified values) only as "wording to start from".
- Next migration number is `0047`.
