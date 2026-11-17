# Feature Phase 2, Session 08: Manage by chat, and phase close-out (D-04)

**Status:** Implemented and verified offline. Not committed, not pushed. Stopped for review. Nothing was run against a real model, phone, Instagram account or Telegram bot.
**Baseline:** `main` at `20a0551` plus the uncommitted Sessions 01 to 07 (left intact).
**Migration head:** `0056` (`20261117_0056_manage_by_chat.py`, `down_revision = "0055"`). The next free revision is `0057`.
**Who built what:** a Codex agent started this session and ran out of usage. Claude reviewed all of its work, kept it, and finished it. The changes Claude made to it are in section 7.

## 1. What was built

### Commands
- `content.reschedule` and `agent.pause_until` are in `commands/registry.py` (mutating, each with its `approval_action` and `approval_permission`), with `ContentReschedule`, `AgentPauseUntil` and `CommandTime` in `ai/schemas.py`. `CommandTime` is `{local_date: ISO | today | tomorrow | null, local_time: HH:MM | morning}`; `morning` is 09:00. Dates and times are resolved in the **workspace timezone** from the injected `Clock` (`ContentContext.now`), with DST handled by the existing `content.scheduling.local_to_utc` (a nonexistent time is refused, a repeated time takes the earlier instant). Past or equal instants (`SCHEDULE_IN_PAST`) and instants more than 60 days out (`SCHEDULE_TOO_FAR`) are refused before a card is shown.
- **Resolver** (`commands/manage.py`, called from `resolver.resolve`): `resolve_reschedule` finds the item by alias or by date, type and description, refuses with `REFERENCE_NOT_FOUND`, asks `command.clarify.which_content` when several match (the proposed time travels in the clarification state and is applied to the item the owner picks), and refuses `CONFLICT_STATE` for any state other than `pending_approval`, `scheduled`, `on_hold` or an item without a time. `resolve_pause` needs exactly one active or paused agent-controlled account in the workspace (`agent_snapshot`; the model supplies no account ID) and refuses with `CONFLICT_STATE` otherwise.
- **Confirmation card** (an `approvals` row, action `command.reschedule_content` needing `content.approve`, or `command.pause_agent` needing `agent.control`, i.e. the owner): reschedule summary `{label, old_formatted, new_formatted, timezone, content_id, is_simulated}`; pause summary `{resume_at, timezone, is_simulated}`. The authoritative UTC instants, the content version, the account's `config_version` and `controller_epoch` are in the hash-bound resolution, not the display text. Staff and managers are refused `FORBIDDEN` for the pause, staff for the reschedule.
- **`content_reschedule` executor** (runs as the person who decided, in one savepoint): locks the item; refuses `VERSION_CONFLICT` if the version or the old instant changed, `CONFLICT_STATE` if the state or workspace timezone changed, `VALIDATION_FAILED` if the target is no longer in the future; cancels the item's pending approval (`SUBJECT_EDITED`) and queued `publish_content` job; then runs the existing `edit` transition and `apply_submit` (media, grounding and quota validation again, self-approved by the confirming human, a new publish job). Any failure rolls the whole savepoint back, so the old schedule, version and job stay. Result `command.content_rescheduled {title, when}` plus a link.
- **`agent_pause_until` executor:** `agent/state.py::change_state` (extracted from the `POST /agent/pause` and `/resume` route code, so HTTP and the command share one implementation, one audit entry `agent.state_changed` and the controller clean-up) pauses the account, and in the same savepoint a durable `agent_resume_due` job is enqueued at the confirmed UTC instant with dedup key `agent_resume_due:{account}:{config_version}`. Result `command.agent_paused_until {when}`.
- **`agent_resume_due` job** (`agent/pause_jobs.py`, registered in `handlers.py`): payload `{account_id, config_version, controller_epoch, user_id, resume_at}`. If it runs early it reschedules itself; otherwise it locks the account and resumes only if the account is still `paused`, still agent-controlled and still at the same `config_version` and `controller_epoch`, and the confirming user is still an active owner. A manual resume, a manual or commanded newer pause, a config change or a lost owner makes it a no-op. A job from another workspace's context cannot touch the account (scoped lookup).
- **Migration `0056`:** extends the `approvals.action` CHECK with the two new actions (`ck_approvals_action`). The downgrade restores the old CHECK and refuses while rows with the new actions exist (history is not dropped). I ran `alembic upgrade head`, `downgrade 0055`, `upgrade head` on a test database: all three worked.
- **Interpreter** (`ai/tasks/interpret_command.py`, prompt `interpret_command/v2.md`, `prompt_version = "v2"`): the prompt adds both commands, a TR and an EN example each, the rule that a missing time is never guessed, and that a request to approve or publish as well stays `unsupported`. The fake interpreter has a `_interpret_management` grammar (pause/duraklat, move/taşı/ertele with a content noun, a clock time or "morning/sabah", tomorrow/today/ISO date) that runs after the unsupported-word check, so "pause ... and approve all replies" is `unsupported`.
- **Evals:** `evals/interpret_command/manage.yaml`, 10 hard cases (TR and EN reschedule, ambiguous, past, published, TR and EN pause, no agent account, past pause, pause plus approve). The harness (`evals/loader.py`, `runner.py`) accepts `agent` and per-case `content` inputs and the expectations `content_title`, `scheduled_at`, `resume_at`, `error_code`.

### UI
- `features/approvals/ManagementSummary.tsx`: old and new local times with `ChangeSummary`, or the resume time, always with the timezone line; used by `ConfirmationCard` and `ApprovalDetailSheet`. Result messages and action labels in TR and EN (`ai.json`), `RESULT_MESSAGE_KEYS` and the narrator fallbacks (`core/narrator.py`) for `content_rescheduled`, `agent_paused_until`, `management_refused`.
- **Command box first on Today at phone width.** P-13 was **not** done (`docs/review/pre-launch-problems.md` had no status). Today now orders, below `lg`: account banners (`-order-2`), then the assistant panel (`-order-1`, with the command box first inside it), then waiting for you, today's numbers, upcoming content and the rest. Above `lg` every `order` is reset (`lg:order-none`), so the desktop layout is the DOM order as before. P-13's other asks (collapse or move the remaining sections) are still open, and I added a status line to P-13 saying so.

### Docs
`architecture/agent-runtime.md` (D-04 section), `api-design.md` (command contract extension), `data-model.md` (migration `0056`), `background-jobs.md` (`agent_resume_due`), `product/mvp-scope.md` (D-04 row, plus the F-04, D-03 and D-05 rows that were missing), `review/pre-launch-problems.md` (P-13 status), `implementation/roadmap.md`, `implementation/features-phase-2-during-pilots/sessions.md` (status line), and the phase summary.

## 2. New contracts

- **Commands:** `content.reschedule`, `agent.pause_until` (interpretation types; no new HTTP route, schema or env setting).
- **Approval actions:** `command.reschedule_content` (`content.approve`), `command.pause_agent` (`agent.control`). Migration `0056`.
- **Result keys:** `command.content_rescheduled {title, when}`, `command.agent_paused_until {when}`, `command.management_refused {reason}`.
- **Job:** `agent_resume_due` `{account_id, config_version, controller_epoch, user_id, resume_at}`, workspace-scoped, 3 attempts, dedup `agent_resume_due:{account_id}:{config_version}`.
- **Service:** `agent/state.py::change_state(db, clock, ctx, account_id, expected_config_version, target, *, repause=False)`. The HTTP routes call it with `repause=False` (a second pause is `CONFLICT_STATE`, as before); only the command passes `repause=True`.
- **Prompt:** `interpret_command` `v2` (`v1` kept).
- **Frontend:** no API schema change (`frontend/openapi.json` compared against a fresh `export-openapi`: identical).

## 3. Files

Backend, new: `app/commands/manage.py`, `app/commands/executors/{agent_pause_until,content_reschedule}.py`, `app/agent/{state,pause_jobs}.py` (`state.py` is the extracted pause/resume service; `pause_jobs.py` the resume job), `app/ai/prompts/interpret_command/v2.md`, `migrations/versions/20261117_0056_manage_by_chat.py`, `evals/interpret_command/manage.yaml`, `tests/integration/commands/test_manage_by_chat.py`, `tests/unit/commands/test_manage_times.py`.
Backend, changed: `app/ai/{schemas.py,tasks/interpret_command.py}`, `app/commands/{registry,resolver,service,content_refs}.py`, `app/agent/router.py` (routes delegate to `change_state`), `app/handlers.py`, `app/core/narrator.py`, `evals/{loader,runner}.py`, `tests/unit/commands/test_registry_and_transitions.py`, `tests/integration/commands/test_update_fact.py`.
Frontend, new: `src/features/approvals/{ManagementSummary.tsx,management.test.tsx}`. Changed: `features/commands/{ConfirmationCard.tsx,messages.ts,catalog.test.ts}`, `features/approvals/ApprovalDetailSheet.tsx`, `features/home/{AssistantPanel,Dashboard}.tsx`, `features/home/home.test.tsx` (+1 test), `i18n/locales/{en,tr}/ai.json`.
Docs: as above.

## 4. Checks (exact)

Environment for every backend run: `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN= OPENAI_API_KEY= PYTHONUTF8=1`, `TEST_DATABASE_URL` = the `.env` value with the database name `agentnest_p2s08_test` or `agentnest_p2s08_{a,b,c,d}_test` (parallel shards), run from `backend/` with `uv run pytest -q -p no:cacheprovider <paths>`.

| Check | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 737 files already formatted |
| `uv run mypy app` | Success, 392 source files |
| `uv run lint-imports` | 23 kept, 0 broken |
| `uv run python -m evals run --all` (fake) | interpret_command **77/77** (67 + the 10 new), extract_fact_candidates 12/12, draft_reply 86/86, draft_content 26/26, 0 hard failures |
| `alembic upgrade head`, `downgrade 0055`, `upgrade head` on the test DB | all three succeed; head `0056` |
| `export-openapi` against `frontend/openapi.json` | no difference |
| `tests/integration/commands tests/unit/commands` (first review run, DEMO true) | 226 passed |
| (a) `tests/unit tests/isolation tests/security tests/contract`, DEMO true | 2170 passed, 13 skipped, 2 failed: `test_cli_migration_status_head_only_and_check_config` (fails only with `DEMO_TOOLS_ENABLED=true`, known) and `test_invite_secrets` (order-dependent, known). Both pass without the flag / alone: 9 passed |
| (a) same, DEMO false (first run) | 2169 passed, 13 skipped, 3 failed: the two dev-route isolation tests (404 without demo tools; 12 passed with `DEMO_TOOLS_ENABLED=true` together with `test_invite_secrets`) and `test_invite_secrets` |
| (b) `tests/integration/inbox`, DEMO true | **473 passed** (an earlier run in parallel with my own ad-hoc runs on the same database had 3 setup errors; this is the clean full re-run) |
| (c) `tests/integration/{agent,knowledge,policy,approvals,ai}` | **544 passed** |
| (d) `tests/integration/{activity,commands,content,demo,identity,integrations,jobs,notifications,operations,reporting,retention}` + `tests/integration/test_*.py`, DEMO true | 1074 passed, 3 failed: `test_owner_creates_an_invite_with_a_one_time_link` and `test_cors_allows_only_the_frontend_origin` (known environment failures) and `test_manage_by_chat.py::test_old_timer_cannot_override_new_state_or_authority[manual_pause]`, a test of this session that relied on HTTP re-pause; fixed (section 7), file re-run: **21 passed** |
| (e) `tests/e2e`, DEMO true | 4 passed |
| Frontend `npm.cmd run lint` / `typecheck` / `i18n:check` / `build` | pass / pass / pass (en, tr, 2581 keys) / built |
| Frontend `npm.cmd test` (PowerShell) | **56 files, 833 tests passed** (Vitest ran normally) |

Not run: `tests/browser` (no tests), Playwright (`npm run e2e`), anything against a real model, phone, Instagram or Telegram. The shards were run in parallel on a loaded machine, so two of my own ad-hoc runs briefly shared a database with a running shard; the three resulting setup errors in `test_voice_transcription.py` were a test-harness collision (the file passes alone: 31 passed, and the inbox shard was re-run in full: 473 passed).

## 5. Invariant notes

- **INV-03/04/16:** both commands are proposals; code resolves the target and the time, a human decision bound to the exact payload hash applies them, free text never decides, a customer message never reaches `CommandService`. A stale card (changed version, epoch or config version) cannot apply. Staff and managers cannot pause; staff cannot reschedule. The reschedule's self-approval is the confirming human's own decision (the card), not a model flag.
- **INV-07:** the resume is a row in `jobs`, survives a worker restart, and is fenced by version and epoch.
- **INV-12:** `agent.state_changed` is audited by the shared service in the decision transaction; the content path audits through the existing submit and transitions.
- **INV-18:** the confirmation card names old and new times and the timezone; "paused until" is shown with the automatic resume time, and the resume itself is a job, not a request success.
- **INV-19:** all relative dates ("tomorrow", "morning") use the workspace timezone and the injected `Clock`; tests cover Istanbul and New York across a DST change, a clock gap and a repeated hour.
- **INV-01:** foreign IDs: the resume job and the executors use workspace-scoped lookups; a foreign timer cannot resume an account (test).
- **No external call in a transaction:** none is made; both executors are DB-only.

## 6. Deviations, limitations and open questions

- **P-13 not done** (see section 1); only the command-box-first part was built, and the other P-13 asks stay open.
- **Pause re-pause:** the command may pause an already paused account (replacing the timer); HTTP still refuses. This is a deliberate asymmetry.
- **Real model language quality is pending**, as is every live eval. The fake interpreter is a regex grammar and proves the plumbing, not Turkish phrasing.
- Legacy-controlled accounts and workspaces with several agent accounts cannot be paused by chat (`CONFLICT_STATE`).
- No Playwright spec and no phone screenshot for the Today order; the order is asserted by a class-level component test.
- Open questions: should a pause command also accept legacy accounts? Should "until Monday" or "for 2 hours" be supported? Should a reschedule of an item that someone else already approved ask the approver again?

## 7. What changed from the Codex draft

Reviewed and kept: the registry entries, resolver, executors, `agent/state.py`, resume job, migration, prompt, evals, tests and docs. Fixed or changed by me:
1. `change_state` allowed pausing a paused account for **both** the command and the HTTP route, which silently changed `POST /agent/pause` (it used to return 409). It is now an explicit `repause=True` flag used only by the command; the docs and the `manual_pause` test were adjusted (the test now resumes first and asserts the HTTP route still returns 409 on a second pause).
2. `evals/interpret_command/manage.yaml`: the `pause_en` case had a malformed UUID (one digit too many).
3. `core/narrator.py`: one English string was 101 characters (ruff `E501`); shortened.
4. `Dashboard.tsx`: Codex put the whole assistant panel at `-order-1`, which pushed it above the account-blocking banners (re-auth, degraded). The banners now have `-order-2` (wrapped in one element that hides itself when empty), so the order is banners, assistant panel (command box first), then the rest. I kept Session 05's `DelegationSuggestionCard` insertion. Added a component test.
5. Docs: moved the D-04 scope note (it sat after the guardrails section of `mvp-scope.md`) into the Feature Phase 2 table and added the missing F-04, D-03 and D-05 rows; P-13 status line; roadmap and `sessions.md` status text made accurate.
6. Wrote this report and the phase summary.

## 8. Handoff

Review, then commit in logical pieces. Open items are in section 7 of the [phase summary](../phase-summaries/features-phase-2-summary.md); the first thing to do with a real key is the live eval run (`LLM_PROVIDER=openai uv run python -m evals run --all`), then a real voice note and photo on a pilot account, after the sub-processor notice.
