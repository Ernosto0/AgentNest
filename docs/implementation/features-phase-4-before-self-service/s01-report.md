# Feature Phase 4, Session 01: import facts from the Instagram profile (F-09, part 1)

**Status:** Done offline (backend, frontend, docs). Live Instagram behaviour is **pending** (V-12).
**Baseline:** `e2fcc23`. **Migration head:** `0061` (`down_revision = "0060"`). Nothing committed.
**Who wrote what:** Codex (gpt-6.1-sol, two runs) wrote the backend, tests, backend docs and the frontend. The session agent (Sonnet 5.5) wrote the brief, reviewed the full diff, patched `frontend/openapi.json` and regenerated `schema.d.ts`, corrected status wording in the docs, ran the checks and wrote this report. No Codex usage limit was hit.

## What was delivered

- **Provider contract** (`integrations/instagram/base.py`, `meta.py`, `mock.py`): `get_profile_details` (bio, website, name, username) and `list_recent_captions(limit)` (id, caption, timestamp, permalink, media_type; newest first, limit 1 to 50, single page). Both are plain reads (not in the INV-15 list). Meta: `GET /{ig-id}?fields=username,name,biography,website` and `GET /{ig-id}/media?fields=id,caption,timestamp,permalink,media_type&limit=N`, strict response shapes, tolerant timestamps (`+0000` and `+00:00`). Mock: deterministic Turkish gym profile; captions are 5, 40 and 200 days before `Clock.now()`; scripted failure rules (operation `profile`) apply; process-local test override via `MockInstagramProvider.set_profile_fixture` / `clear_profile_fixtures`.
- **Migration `0061`**: nullable `fact_candidates.source_detail JSONB` with `CHECK (source_detail IS NULL OR jsonb_typeof(source_detail) = 'object')`. RLS on the table is unchanged (forced RLS already).
- **Source-agnostic pipeline** `backend/app/knowledge/imports.py` and the Instagram source `backend/app/knowledge/profile_import.py` (see the extension points below). Reuses `extract_fact_candidates` (task, `plan_candidates`, all excerpt, value and injection checks) unchanged.
- **Job** `import_instagram_profile` (payload `{run_id}` only, `max_attempts=2`, timeout 150 s, backoff 10/60 s, `on_dead` marks the run failed, dedup key `import_instagram_profile:{run_id}`). Provider reads and the model call run with no transaction open (short sessions: gather, prepare, store).
- **Triggers**: once after the first connection (`connect_mock` and the OAuth callback for a new connection or a reused disconnected row; keyed `first_connection:{social_account_id}`; a reconnect does not import; a failing trigger is isolated by a savepoint and never fails the connection) and `POST /workspaces/{id}/knowledge/imports/instagram`.
- **API**: `POST /workspaces/{workspace_id}/knowledge/imports/instagram` body `{client_request_id}`, `knowledge.edit`, 202, response `ExtractionOut` (unchanged). Poll with the existing `GET /knowledge/extractions/{run_id}`. 409 `CONFLICT_STATE` with `reason` `no_connected_account` / `account_not_ready`. `CandidateOut.source` = `{origin, posted_at, url, age_days, stale, simulated}`; `age_days` and `stale` (caption older than 90 days) are computed at read time from `Clock`; `url` only if `https://`.
- **Audit**: `knowledge.import_requested`, `knowledge.import_completed` (counts only: candidates, duplicates, stale, skipped_injection, segments); backend TR/EN activity labels added.
- **Frontend**: `InstagramImportButton` (self-contained, reusable; disabled with a hint when no connected account; working, done, none, failed, injection states), placed on the Suggestions header and in the Knowledge `TeachPanel`; candidate cards show origin (bio or "post on <date>"), "View post" link (https only, `rel="noopener noreferrer"`), a stale-price warning, and a "Simulated" chip. TR and EN strings under `knowledge.importInstagram.*` and `knowledge.suggestions.source.*`.
- **Docs**: `mvp-scope.md` (profile and website import moved out of Deferred; new "Feature Phase 4" F-09 row), `platform-capabilities.md` §1.9 and backlog item **V-12**, `api-design.md`, `background-jobs.md`, `data-model.md`, `agent-runtime.md`, `workflows.md`, `component-design.md`, `integrations.md`, `observability.md`, `security-and-privacy.md`, `sessions.md` status.

## Contracts

| Item | Value |
|---|---|
| Job type | `import_instagram_profile`, payload `ImportRunPayload{run_id}` |
| Run | `agent_runs` task `extract_fact_candidates`; `input_snapshot` = `{source, client_request_id, user_id, social_account_id, trigger, segments[], injection_flags[], captions_unavailable?, profile_website?, stored_at}`; **no imported text**; `agent_runs.output` is not stored (`store_output=False`) |
| Candidate source | `source_type = "instagram_profile"`, `source_excerpt` (verbatim snippet), `source_detail = {origin: "bio"\|"caption", posted_at, url, simulated}`, proposer = system actor `import.instagram_profile` |
| Settings / env vars | none added (`PROFILE_IMPORT_CAPTIONS = 12` and `STALE_CAPTION_DAYS = 90` are constants) |
| Run error codes | `ACCOUNT_NEEDS_REAUTH`, `CAPABILITY_MISSING`, `PROVIDER_UNAVAILABLE`, `PROVIDER_REJECTED`, `CONFLICT_STATE` |

## Behaviour rules (all tested)

- One candidate per fact key per import: bio first, then the newest caption.
- Deduplication before anything is created: skipped when equal to the verified fact (no `superseded` row either), when an equal **pending** candidate of any source exists, or when the owner already accepted or rejected the same value from `instagram_profile`. An unverified fact with an equal value does not block (accepting it verifies it, as for paste). A changed value supersedes the earlier pending import candidate through the existing `propose_candidate` rule.
- Injection: any bio or caption segment with `detect_injection` hits is dropped before the model sees it (checked on the whole segment, before truncation); flags surface as `injection_suspected`; the model section is the labelled untrusted section; `accept_items` still checks the excerpt and its line.
- Nothing is verified: only `fact_candidates` rows (status `pending`) are created; no facts are touched.
- Idempotency: first connection per account row (one run, one job), manual re-import per `client_request_id`, an in-progress run (queued or running, under 10 minutes old) is returned instead of a second one, a succeeded run is a no-op on redelivery.

## Extension points for Session 02 (website source)

1. **Add a gatherer**: `imports.GatherInput(session_factory, clock, workspace_id, snapshot) -> GatherResult(segments, notes, simulated)`. Do network work inside it with no transaction open (open short sessions yourself, close before the fetch). Raise `imports.ImportFailed(code)` for a final failure and `RetryableError` for a transient one.
2. **Add a job handler** like `profile_import.import_instagram_profile`: `@job_handler("import_website", imports.ImportRunPayload, ..., on_dead=imports.fail_run_if_open)` calling `imports.run_import(job, source_type="website", gather=...)`. `"website"` is already in `CANDIDATE_SOURCES` and the DB check constraint, so **no migration is needed** for the source value. Register the module in `app/handlers.py`.
3. **Request function**: copy `profile_import.request_instagram_import` (uses `imports.create_import_run`, `find_request`, `find_in_progress`, audits `knowledge.import_requested`, enqueues). Put the endpoint beside `POST /knowledge/imports/instagram` as `POST /knowledge/imports/website`; polling is the existing `GET /knowledge/extractions/{run_id}` (it works for any run of task `extract_fact_candidates`). Note `find_in_progress` is per `source` value.
4. **Segments**: origin `"website_page"` is already an allowed header label in `prepare_segments` (any other origin is relabelled `data`); `ImportSegment.url` carries the page URL (only `https://` is stored); `source_detail.origin` is free text, so the UI ignores unknown origins gracefully (add a label for `website_page` in `CandidateSource` in `SuggestionsPage.tsx` and `knowledge.suggestions.source.*`). Staleness only applies to origin `caption`.
5. **Prefill**: a bounded `http(s)` website from the profile is stored in the run snapshot as `profile_website` (not exposed by any API yet). Session 02 can read it from the latest `instagram_profile` import run, or expose it in a status response, to prefill the website step.
6. **Combined onboarding step**: use the reusable `InstagramImportButton` (props `variant`, `onDone`) and a new website counterpart; both end at the existing Suggestions review.
7. The SSRF-safe fetcher must run inside the gatherer; the pipeline already drops injected segments, caps text at 8000 characters (700 per segment) and keeps the evidence excerpt.

## Deviations and open questions

- **Contact fields**: the IG User reference lists no email, phone or address "contact button" fields, so none are read; phone and e-mail come only from the bio and captions text. Recorded as Unavailable in `platform-capabilities.md` §1.9.
- **`caption` with Instagram Login** is documented as "Facebook Login only" in the IG Media field table while other pages suggest otherwise: **Unverified / contradictory (V-12)**. The job degrades to a profile-only import (`captions_unavailable` in the snapshot) if the media read is rejected. The permission and sort order of `GET /{id}/media` under Instagram Login are also Unverified.
- Website is not a model segment (no template fact key takes a URL); it is only kept as prefill metadata.
- Mock profile overrides are process-local (tests only); the dev stack always uses the default fixture. The default fixture's old caption price is suppressed in practice by the bio value for the same key (tests use caption-only fixtures to prove the 90-day warning).
- The repo has no viewer role (owner, manager, staff); an unsupported read-only role is denied at the service layer in tests.
- Open: whether a re-import should also supersede pending candidates whose key no longer appears in the profile (today they stay until the owner decides).

## Pending live (do not claim)

V-12: real `biography` and `website` reads, `caption` presence under Instagram Login, `/media` ordering, `limit` and `@` handling, with fixtures recorded from the founder's test account. Until then the feature is verified against the mock and synthetic Meta responses only.

## Checks

Backend, from `backend/` with `PYTHONUTF8=1`:
- `uv run ruff check .` pass; `uv run ruff format --check .` pass (803 files); `uv run mypy app` pass (424 files); `uv run lint-imports` pass (23 contracts kept).
- Codex ran `uv run pytest tests/unit tests/contract`: 2200 passed, 18 skipped (explicit live probes); and `tests/integration/knowledge tests/integration/operations tests/integration/integrations tests/integration/jobs tests/integration/ai tests/integration/activity tests/isolation tests/security`: 418 passed (process env `DEMO_TOOLS_ENABLED=true`, `SENTRY_DSN=''`; the worktree `.env` has demo tools off, which makes an existing dev-route health test return 404 by configuration, not because of this change).
- Session agent re-ran `tests/integration/knowledge/test_profile_import.py tests/unit/knowledge/test_imports.py tests/isolation/test_knowledge_isolation.py`: 26 passed. Other users of mock-account connection: `tests/integration/agent/test_calendar_agent.py`, `test_hardening_integration_regressions.py`, `test_seed.py`, `test_simulation_flag.py`, `test_health_and_errors.py`, `demo/` (with `DEMO_TOOLS_ENABLED=true SENTRY_DSN=`): 62 passed, 1 failed. The failure is `test_health_and_errors.py::test_cors_allows_only_the_frontend_origin` (CORS preflight returns 400): environment configuration of the worktree (the files `app/main.py` and `app/core/config.py` are untouched by this session); it was not re-run on the baseline commit. A broader run of the remaining `tests/integration` directories was attempted but two overlapping pytest processes shared the test DB, so it was stopped and not counted; the directories that connect a mock account are the ones listed above.
- New tests: `tests/integration/knowledge/test_profile_import.py` (19: first-connection trigger, evidence and source detail, no facts, stale warning at read time, dedup in five forms, idempotency, reconnect no-op, injection, auth failure, captions fallback, empty import without LLM, staff stays pending, no open transaction around provider/model calls, foreign account refused, trigger failure isolation, DB check constraint, retries then dead), `tests/unit/knowledge/test_imports.py`, provider tests in `test_meta_provider.py` and `test_instagram_provider_contract.py`, OAuth connect/reconnect assertions in `test_oauth.py`, import isolation in `test_knowledge_isolation.py`.

Frontend, from `frontend/` (PowerShell): `npm.cmd run lint` pass; `npm.cmd run typecheck` pass; `npm.cmd run i18n:check` pass (2732 keys); `npm.cmd test` **897 passed (62 files)**; `npm.cmd run build` pass. New tests in `src/features/knowledge/instagramImport.test.tsx`.

## Merge notes

- `frontend/openapi.json` was patched, not regenerated: path `/api/v1/workspaces/{workspace_id}/knowledge/imports/instagram` added, schemas `CandidateSourceOut` and `ImportRequest` added, `CandidateOut` changed; `frontend/src/api/schema.d.ts` regenerated with `npm run gen:api`.
- `backend/.pytest-tmp/` (created by Codex with `--basetemp`) is ACL-locked and could not be deleted from this session; it is not part of the diff and must be removed by hand in the worktree.
- `backend/pyproject.toml`: two modules added to the "no API import" contract list; expect a trivial conflict if another session edits that list.
- Docs touched by many sessions (`mvp-scope.md`, `platform-capabilities.md` backlog, `api-design.md`, `background-jobs.md`, `sessions.md` status line) may conflict textually.
