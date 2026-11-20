# Feature Phase 2: merge of Sessions 04 to 07 into the main tree

The main tree already held Sessions 01 to 03 (uncommitted). Sessions 04 (story replies and mentions), 05 (approval-ladder suggestions), 06 (missed-customer report) and 07 (learning loop) were built in parallel worktrees from commit 20a0551, applied with `git apply --reject`, and the rejected hunks were then resolved by hand. This report records what conflicted and how it was resolved.

## Migration chain

`0047 -> 0048 -> 0049 (S01 transcripts) -> 0050 (S03 image descriptions) -> 0052 (S04 story-mention thank-you) -> 0053 (S05 delegation suggestions) -> 0055 (S07 fact save tokens)`. S06 has no migration. `uv run alembic heads` shows the single head `0055`. The test databases migrate from scratch in the fixtures (all shards ran on freshly migrated databases).

## Conflicts and resolutions

Backend:
- **`draft_reply` prompt.** S02 and S04 had each created a different `v3.md`. `v3.md` stays as S02's (transcript wording). New `v4.md` is `v3.md` plus S04's `<story_context>` rule line, placed where S04 had it relative to `v2.md`. `v2.md` and `v3.md` are kept. `DRAFT_REPLY.prompt_version` is `"v4"`. `tests/unit/ai/test_draft_reply_task.py` now expects `v4`, and `tests/unit/evals/test_eval_harness.py` allows `{"v1","v2","v3","v4"}`.
- **`ai/tasks/draft_reply.py`.** S02's `_line` transcript labelling and S04's `story_context` section (`data_section`), the `has_story_context` snapshot key and the story-title price lookup are all present. `DraftReplyInput` has both `DraftMessage.source` (S02) and `story_context` (S04).
- **`inbox/context.py`.** `DraftContext` has both `transcript_message_ids` and `story_context`, `story_mention`, `story_mention_template`. In `prepare()` the order is: pending-transcript check (`DraftSkip("transcript_pending")`, reschedules), then readings and workspace inputs, then the mention test (`stories.is_mention_only`) and story context. A plain story mention has no audio, so it never waits for a transcript; a mention beside a voice note, photo or text is not a plain mention.
- **`inbox/drafting.py`.** `_task_input` passes `story_context`. In `plan_with`, a story mention with a template goes to `_mention_plan` first (no model call); then `attachment_only`; then the model path. A transcript still sets `transcript_based` on the plan, which R18 turns into approval. `_mention_plan` is approval-required by default through the `reply.story_mention` class.
- **`inbox/views.py`, `router.py`, `schemas.py`.** `message_out(message, transcript, image_descriptions, story)` carries all three. `messages_out(session, ctx, conversation, messages)` is the one entry point (transcripts and descriptions in one query each, plus `_story_out`), used by `get_conversation`. `StoryOut` was added. `MessageOut.story` has a default of `None`, like `transcript` and `image_descriptions`, so existing fixtures without it still type-check (S04 had it required).
- **Evals.** `evals/loader.py` accepts both `transcript` and `story_context` input keys. The runner already carried both.
- **`core/db.py`.** `CATEGORY_C_TABLES` now holds `message_transcripts`, `message_image_descriptions`, `delegation_suggestions` and `fact_save_tokens`. `test_rls_policies.py` count: 56 -> 60 (56 + S01 + S03 + S05 + S07).
- **`api/router.py`.** `missed_reports_router` (S06) was imported but not included; now included after `reports_router`.
- **`notifications/catalog.py`.** `report.missed_customers_ready` (S06) added beside S05's `delegation_suggestion`. `delivery_policy.py`, `catalog.json` and the `ai.json` strings had both.
- **`demo/scripts/customer_messages.yaml`.** S04's `story_reply` and `story_mention` scripts appended after S02/S03's.
- **`pyproject.toml`.** Added S06's import-linter entries: `app.reporting.weekly_sources` and `app.reporting.missed_customers` in the reporting source modules, and `app.reporting.missed_router -> app.api.deps` in the two reporting contracts that list `app.reporting.router -> app.api.deps`. The D-01 line and S01's second openai ignore were already there.

Frontend:
- **`openapi.json`.** The patched file was inconsistent (S07's `CandidateAccept` request body had landed on `GET conversations/{id}`; S06's `EstimateOut` was missing). It was replaced by the exporter's output (`uv run python -m app.cli export-openapi`), which has the same formatting and ordering as the committed file. It contains the paths and schemas of S02 to S07, and `MessageOut` has `transcript`, `image_descriptions` and `story`. `schema.d.ts` was regenerated with `npm run gen:api`.
- **`ConversationPage.tsx`.** Only the `StoryNote` import was missing; added. `TranscriptBlock` and `ImageDescriptionBlock` stay.
- **`inbox.json` (en, tr).** `convo.story.*` keys merged next to the transcript and image description keys. Both files are valid JSON and `i18n:check` passes.
- **`notifications/describe.ts`, `target.ts`.** `report.missed_customers_ready` added beside S05's `delegation_suggestion`.
- **`AgentPage.tsx`.** Both `DelegationSuggestionCard` (S05) and `LearnedThisMonth` (S07) render on the overview panel. `Dashboard.tsx` keeps S05's card.
- **`mockApi.ts`.** Serves `delegation-suggestions` (S05) and `learning/month` (S07). S06 added no background route: its report endpoints are mocked inside `missed.test.tsx`, and no other test hits them.

Docs:
- `api-design.md`, `integrations.md`, `workflows.md` (S04 story text merged into S02's transcript wording; step 2 now notes that a mention never waits for a transcript), `agent-runtime.md` (prompt `v4` described), `data-model.md` (`fact_save_tokens`), `observability.md` (S06's notification row and S05's `agent.delegation_suggestion_*` audit actions), `background-jobs.md` (S06's job: S06 had put a six-column row in the three-column scheduler table; it is now a short scheduler row plus the full job-catalog row), `mvp-scope.md` (D-02 row in the Feature Phase 2 table).
- A line-by-line check of every added line of each worktree diff against the main tree found nothing missing except the intended differences (migration revision ids, `v3` to `v4`, the RLS count, and the `MessageOut.story` default).

Clean-up: all `*.merge.rej` files deleted, no `*.orig` left. `s04` to `s07` reports are in this folder. Worktrees and the `backend/tmp-session05*` folders were not touched.

## Verification

Environment: `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN= OPENAI_API_KEY= PYTHONUTF8=1`, one test database per shard (`pivoris_p2merge_{a,b,c,d}_test`, `pivoris_p2merge_test`; the `_test` suffix is required by the test guard).

Backend static checks: `ruff check .` clean, `ruff format --check .` clean (729 files), `mypy app` clean (387 files), `lint-imports` 23 kept, 0 broken.

Backend tests (`uv run pytest -q`):

| Shard | Scope | Result |
|---|---|---|
| a | `tests/unit tests/isolation tests/security tests/contract` | 2166 passed, 13 skipped, 3 failed (see below) |
| b | `tests/integration/inbox` (`DEMO_TOOLS_ENABLED=true`) | 473 passed |
| c | `tests/integration/{agent,knowledge,policy,approvals,ai}` | 544 passed |
| d | the rest of `tests/integration` plus `tests/integration/test_*.py` (`DEMO_TOOLS_ENABLED=true`) | 1054 passed, 2 failed (known) |
| e | `tests/e2e` (`DEMO_TOOLS_ENABLED=true`) | 4 passed |

Failures, all explained:
- Shard a, `test_the_dev_job_listing_of_a_never_shows_the_jobs_of_b` and `test_the_simulator_listing_of_a_never_shows_what_b_published`: dev routes need `DEMO_TOOLS_ENABLED=true`. Re-run with it: `tests/isolation` and `tests/security/test_invite_secrets.py` all pass (66 passed).
- Shard a, `test_invite_secrets`: the known order-dependent test; it passes alone.
- Shard d: the two known environment failures, `test_cors_allows_only_the_frontend_origin` and `test_owner_creates_an_invite_with_a_one_time_link`.
- Side note: with `DEMO_TOOLS_ENABLED=true` set globally, `tests/unit/core/test_deployment_workflow_and_rollback.py::test_cli_migration_status_head_only_and_check_config` fails, because its production `check-config` rejects demo tools. It passes without the variable (7 passed), so it is not a merge issue.

Evals (`uv run python -m evals run --all`, fake provider): interpret_command 67/67, extract_fact_candidates 12/12, draft_reply 86/86 (includes `voice.yaml` and `stories.yaml`), draft_content 26/26, 0 hard failures.

Frontend (PowerShell, `frontend`): `npm.cmd run lint` clean, `typecheck` clean, `npm.cmd test` 55 files and 830 tests passed, `i18n:check` passed (2574 keys), `build` succeeded.

## Left open

- Nothing blocking. `docs/implementation/features-phase-2-during-pilots/sessions.md` and the Session 02 `voice_note` demo-script `expect` text ("not yet used for the draft") were not edited; the latter predates this merge and may be stale now that S02 drafts from transcripts.
- Nothing was committed, pushed or stashed.
