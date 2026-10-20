# Phase 5 implementation plan: Content and scheduling

## Context
Phases 1–4 are on `main` (latest `a021ff9`, P4-13). The user treats Phase 4 as **accepted with changes**: four of its open review questions are now decided and are built first (P5-00 below). Phase 5 then delivers **workflow E** end to end against the mock provider:

image upload → content draft (manual or AI) → claim-validated submit with a version-bound approval → scheduling → deterministic publish worker (container semantics, ledger, reconcile, bounded retries with a deadline, `on_hold`) → cancel / re-approve → fact-change holds → content UI.

- Spec: `docs/implementation/phases/phase-05-content-and-scheduling.md`, plus its "Read first" list. Re-read `docs/invariants.md` first.
- Acceptance: AC-C4, AC-D1…D8, AC-F1…F7, AC-X5, INV-06 (exact `sim_published_media` counts), INV-18.

**Decisions already made by the user:**
- Work **directly on `main`**: one local commit per task (`P5-xx: …` with the Co-Authored-By line), nothing pushed. Normal dev/test databases and ports.
- **Phase 4 follow-ups**:
  - Q2: one draft key per conversation, plus a follow-up run.
  - Q3: keep the strictest-class rule and explain it with a reason chip.
  - Q4: an explicit review button.
  - Q5: staff see the approval state of their replies.
  - Q6: `resume_account` on reconnect.
- **Staff cannot "Publish now".** A submitter without `content.approve` must schedule ≥ now + 15 min (otherwise 422). Their pending approval expires at `scheduled_at`, as documented.

---

## 1. Module layout and dependency rules

```
backend/app/integrations/storage/{base.py, local.py, registry.py}   MediaStorage (ADR-015), key regex, no path traversal
backend/app/content/  models, media, transitions, validation, scheduling, service, generation, payload,
                      subject (approval callback), impact_handlers, hooks, router, jobs, schemas, views
backend/app/ai/       prompts/draft_content/v1.md, tasks/draft_content.py (+ DraftContentInput/ContentProposal in ai/schemas.py)
backend/app/commands/ resolver.py (ContentRef), executors/{content_create_draft, content_cancel, query_content_status, query_explain_failure}.py
backend/app/operations/ publish.py, reconcile.py (+ reconcile_publish), jobs.py (publish_content, reconcile_publish, resume_account)
backend/app/integrations/instagram/ mock.py (containers, publish, quota, media), models.py (SimContainer, SimPublishedMedia)
backend/migrations/versions/ 0008 media_assets · 0009 content_items (+ content_item FKs) · 0010 sim_containers/sim_published_media · 0011 mock capabilities data fix
backend/evals/draft_content/*.yaml
frontend/src/features/content/ ContentPage(Tabs), ContentCard, ContentEditor, MediaUpload, GenerateSheet, ScheduleSheet,
                               FailureDetail, OnHoldActions, ContentApprovalBody, hooks.ts, status.ts
frontend/e2e/ scenario-c.spec.ts (extend), scenario-d.spec.ts, scenario-f.spec.ts
```

**Import contracts** (appended to `backend/pyproject.toml`):
- `app.content` must not import `app.operations`, `app.commands` or `app.api`.
- `operations.publish` imports `content` (models, transitions).
- Content cancel and hold reach the ledger through `content/hooks.py`, a startup-registered hook, the same pattern as the approval callbacks and impact handlers.
- `app.integrations.storage` imports only `app.core`.
- `app.integrations.instagram.mock` may also import `app.integrations.storage` (G3).
- Add the new modules to the "services do not import the API layer" contract.
- `tests/unit/test_side_effect_calls.py` already covers `create_media_container`/`publish_container`.

`app/handlers.py` registers the new job modules: `content.jobs`, `content.subject`, `content.impact_handlers` and `operations` publish hooks.

**Dependencies:** add `pillow` and `python-multipart` (needed by FastAPI `UploadFile`).

---

## 2. Decisions for doc gaps
Each one is written into the named doc in the same change and listed as a deviation in the phase summary.

| # | Gap | Resolution | Doc |
|---|---|---|---|
| G1 | State machine misses transitions that workflows B/E require | Add `draft → cancelled`, `pending_approval → cancelled` (E step 7), `retry_scheduled → on_hold` (B 3.4), `publishing → on_hold (ACCOUNT_UNAVAILABLE)` (auth error during the attempt; the op → `failed ACCOUNT_NEEDS_REAUTH`) | state-machines §5 |
| G2 | Re-approve "same version" collides with the per-version job/ledger keys once an op exists | `on_hold` entry cancels the queued job and moves a `pending`/`retry_wait` op → `cancelled`. **Re-approve increments `version`**: `scheduled_at` is part of the approval payload, so it gets fresh `publish:{id}:v{n}` keys. Content is unchanged; full validation runs again, so a caption that still shows the old price fails and must be edited | state-machines §5, workflows §E |
| G3 | Mock must read the JPEG, but `integrations.instagram` imports only `core` | Local `public_fetch_url` returns `localmedia:{key}?exp=…`. The registry passes a `MediaStorage` to `MockInstagramProvider`. The mock checks the JPEG magic bytes. Meta still refuses the local backend (Phase 7) | integrations §3.3, ADR-015 note |
| G4 | Capability names: code has `content_publish`, docs have `publish_feed_image`/`publish_story_image` | `MOCK_CAPABILITIES = {messaging, publish_feed_image, publish_story_image}`. Migration 0011 rewrites existing mock rows; frontend capability labels follow | integrations §3.2 |
| G5 | Approval payload has `overlay_text`, the model has only `overlay_text_suggestions`; a story publishes no text | `overlay_text` = the suggestions list (binds what the approver saw). `ContainerSpec(STORIES, caption=None)`. Claim validation also covers the suggestions | workflows §E |
| G6 | Caption stored rendered vs template | `caption` stays the rendered text. Generation: `caption_template` → `render` → `caption`, with `fact_references` from the render result. Hashtags are appended by code at generation; the owner may delete them. Edits: plain text; references come from values matching verified facts (manual-reply matcher), and claim issues are **blocking at submit**, except a value that whole-token matches the current verified display of a fact: that is grounded (`matches_verified`), recorded as a reference and does not block (resolved in P5-03a; see workflows §E) | workflows §E, data-model §3.6 |
| G7 | Generate idempotency / `generation: running` | `content_items.client_request_id` with `unique (workspace_id, created_by_user_id, client_request_id)`. Generation creates `agent_runs(status=queued)` (Phase 3 D3 precedent) linked by `agent_run_id`; the response's `generation` is that run's status. An LLM failure leaves a manual draft (`generation: failed`, error code) | data-model §3.6, api-design §2.7 |
| G8 | External quota read vs "T1 lock" | Order: a read-only check → `get_publishing_quota` with no transaction open → T1 locks and re-checks everything. Exhausted → `retry_scheduled` at the oldest publish + 24 h, if before `execute_before`; else `failed (PUBLISH_DEADLINE_PASSED)` | workflows §E 6.1 |
| G9 | Polling under a `FrozenClock` | `execute_publish(..., sleep=time.sleep)`. The loop measures elapsed time with the `Clock`, and tests pass a sleeper that advances it. Poll every 10 s for up to 5 min with `heartbeat()` between polls and **no transaction open**, then enqueue `reconcile_publish` | background-jobs §3 |
| G10 | Retry mechanics with a running dedup key | Retries use `RetryableError(retry_after_seconds = max(backoff[1,5,15,30 min], retry_after))` on the same job row. Op `max_attempts=5` and `deadline_at=execute_before` govern provider attempts. Job `max_attempts=5`, with an `on_dead` failsafe → item `failed` | background-jobs §6 |
| G11 | `reconcile_stuck_operations` only scans `send_reply` | Extended to `publish_content`: `in_progress` > 15 min → `outcome_unknown` → `reconcile_publish` | background-jobs |
| G12 | Upload rules | Order: read ≤ limit+1 bytes (else 413 `MEDIA_TOO_LARGE`) → `Image.open`+`verify` → reopen → pixel cap (`MAX_IMAGE_PIXELS`, bomb warning = error) → `exif_transpose` → sRGB → **always** re-encode baseline JPEG q90 without EXIF (simplest guaranteed EXIF strip) → sha256 of the output. Rejected uploads store no row: 422 `MEDIA_INVALID` + audit `media.rejected`. The orphan `media_cleanup` job is deferred (limitation) | ADR-015 note, data-model |
| G13 | DST gaps/folds in schedule input | A nonexistent local time → item code `SCHEDULE_TIME_NONEXISTENT`; an ambiguous time → the earlier instant (`fold=0`), echoed back in `schedule_local` | workflows §E 4.1 |
| G14 | AC-C4 notification (`knowledge.fact_changed` skips the changer, Phase 3 D7) | New `content.on_hold` (attention) to `content.approve` holders including the changer; also used for `ACCOUNT_UNAVAILABLE`. Plus `content.published` (info) and `content.failed` (attention) | observability |
| G15 | Content tabs | Drafts = `draft`, `pending_approval` · Scheduled = `scheduled`, `publishing`, `retry_scheduled` · Published · Problems = `on_hold`, `failed`, `rejected`. `cancelled` is not listed | user-journeys §1 |
| G16 | `publish_max_delay` (ADR-014 names an env var) | Use the existing workspace setting `publish_max_delay_minutes` (360) | ADR-014 note |
| G17 | Submit item codes | `CONTENT_MEDIA_REQUIRED`, `MEDIA_NOT_READY`, `CAPTION_REQUIRED`, `CAPTION_TOO_LONG`, `CAPTION_NOT_ALLOWED`, `ASPECT_RATIO_OUT_OF_RANGE`, `CLAIM_VALIDATION_FAILED` (+issues), `SCHEDULE_IN_PAST`, `SCHEDULE_TOO_FAR`, `SCHEDULE_TIME_NONEXISTENT`, `SCHEDULE_TOO_SOON_FOR_APPROVAL` (staff, < 15 min), `ACCOUNT_NOT_CONNECTED`, `CAPABILITY_MISSING`, `PUBLISH_QUOTA_FORECAST_EXCEEDED`. Warnings (non-blocking): `STORY_ASPECT_NOT_9_16`, `OVERLAY_TOO_LONG` | observability §4 |
| G18 | Mock failure modes for publishing | `create_container`: `invalid_media` → `ProviderInvalidRequest(MEDIA_REJECTED)`. `container_status`: `invalid_media` → status `ERROR`. `publish`: `timeout_after_success` publishes, then raises `ProviderOutcomeUnknown`. `transient`, `rate_limited` and `auth_revoked` apply to all three | integrations §3.3 |
| G19 | Demo sample images | Commit `backend/app/demo/media/story-sample.png` (1080×1920) and `feed-sample.jpg` (1080×1350), generated once with Pillow. Used by the demo and the E2E specs | local-development §6 |

---

## 3. Tasks (in order; run the task's tests after each, then commit)

**P5-00 Phase 4 follow-ups** (one commit each; each updates its doc and tests)
- **Q2 debounce.**
  - `draft_reply` key becomes `draft_reply:{conversation_id}`; `run_at` is not extended; the payload `message_id` becomes optional.
  - New `jobs` primitive `RescheduleJob(run_at)`: the worker re-queues the same row without consuming an attempt (`attempts − 1`).
  - At T3, if a newer inbound arrived during the run, the job discards its result and raises `RescheduleJob(now + debounce)`. Result: one job per conversation and nothing swallowed.
  - Update the other enqueue sites in `inbox/processing.py`, `service.py` and `impact.py`. Update background-jobs §2/§6, workflows §C and Phase 4 D8.
- **Q3 explain.** `policy/classes.effective_mode` also returns the winning class. When it differs from the intent's class, R13–R16 add a reason `CONTAINS_<CLASS>` (e.g. `CONTAINS_PRICING`: "Fiyat içeriyor, fiyat ayarı geçerli"). Reason catalog plus `convo.reason.*` in tr/en. Update workflows §C.1.
- **Q4 review.** New `POST /automation-policies/review` (`automation.manage`): stamps `automation_reviewed_at` once and audits `policy.reviewed`. `PUT` no longer stamps. The automation screen gets an "Bu ayarları inceledim" button while unreviewed. The seed still stamps directly. Update api-design §2.3.
- **Q5 staff state.** `ReplyDraft` gains `approval_state: {status, expires_at, decided_by_name, decided_at, decision_note} | null`, readable by anyone who may read the conversation. `DraftCard`, for users who cannot approve, shows pending (who must approve, the expiry) or approved/rejected/expired with the name and note. Update api-design §2.6.
- **Q6 resume.**
  - `operations/accounts.reconnect_mock(account_id)`: `needs_reauth → connected`, same external id, audit `account.reconnected`, enqueue `resume_account`.
  - Route `POST /social-accounts/{id}/reconnect` (mock only; `integrations.manage`).
  - `resume_account` re-enqueues or expedites `send_reply:{draft}` for queued drafts still in their window. It uses the new `jobs.queue.expedite(session, dedup_key, clock)` helper (sets `run_at=now` on a queued row).
  - It does **not** resume `on_hold` content (G.2).
  - UI: "Yeniden bağlan (simülasyon)" on the connection screen.
  - Update background-jobs (Phase 5, not 6), api-design §2.9 and the Phase 4 limitation.

**P5-01 Media.**
- Settings: `MEDIA_STORAGE_BACKEND`, `MEDIA_LOCAL_ROOT`, `MEDIA_MAX_IMAGE_BYTES`, `MEDIA_PUBLIC_URL_TTL_SECONDS`. Production check: `local` is refused when `meta` is enabled.
- `storage/local.py`.
- Migration 0008 `media_assets`.
- `content/media.ingest(ctx, file, filename, content_type)` (G12).
- `POST /media` (`content.edit`, multipart) and `GET /media/{id}/content`: an authenticated stream with `nosniff`, `Cache-Control: private` and the correct content type.
- Error codes `MEDIA_INVALID` / `MEDIA_TOO_LARGE` with tr/en texts.
- Tests: AC-D2 (PNG → `ready` JPEG with no EXIF; a text file → `MEDIA_INVALID`), oversize → 413, decompression bomb, storage key never derived from the filename, isolation.

**P5-02 Content model and transitions.**
- Migration 0009 `content_items`: data-model §3.6 plus `client_request_id`; composite FKs to the account, media and approval; index `(workspace_id, status, scheduled_at)`; FK `approvals → operations` is already there.
- `content/transitions.apply(item, event, **ctx)`: the §5 table plus G1. A conditional update on the expected status; audits each transition; anything else → `CONFLICT_STATE`.
- `service.create_draft` / `update`:
  - `expected_version` → `VERSION_CONFLICT`.
  - Any payload change → version+1, re-validate, replace `fact_references`.
  - From `pending_approval`/`scheduled`/`on_hold`/`rejected`/`failed` → `draft` + `cancel_for_subject(SUBJECT_EDITED)` + cancel the queued job (new `jobs.queue.cancel_queued(session, dedup_key)`).
  - `published` → 409.
- CRUD routes: list with tab filters, get, create, patch, validate.
- Tests: unit tests for all allowed and the key forbidden transitions; published is immutable (INV-17); AC-D6 edit-after-approval.

**P5-03 Generation and content commands.**
- `draft_content` `TaskDefinition`:
  - schema per agent-runtime §5;
  - post-validator: structure, ≤ 10 hashtags, every `commercial_claims` item maps to a used fact key;
  - prompt v1 with facts and brand voice as data sections, the objective as owner data.
- tr/en fake keyed on objective keywords (deneme/trial → `{{fact:promotion.trial_session}}` overlay; fiyat/üyelik → caption with `{{fact:pricing.membership_monthly}}`).
- `generate_content` job, three phases (the model call has no transaction open):
  - render → claim validation (issues stored inline, not a hard stop) → `fact_references`;
  - `content.generated` audit;
  - re-check the item is still `draft` at the generated version before saving.
- `POST /content-items/generate` (G7).
- Commands:
  - `InterpretCommandInput.content_catalog` with aliases `C1..Cn`: the next 14 days plus recent failures.
  - ContentRef resolver: alias → else filter by local date (workspace timezone), type and status; 0 matches → `REFERENCE_NOT_FOUND`; more than 1 → clarification with title and time options.
  - Executors:
    - `content.create_draft`: no confirmation; `interpreting → executing` shortcut.
    - `content.cancel_scheduled`: confirmation approval `command.cancel_content` with payload `{content_id, content_version}`; generalise `Confirm` beyond `fact_id`; permission `content.approve` checked against the human; execution as the decider.
    - `query.content_status`.
    - `query.explain_failure`: `latest_failure` or a ref, explained from the error catalog with links.
  - Fake interpreter grammar for the demo phrases.
- Tests: AC-D1 (`test_generate.py`), resolver ambiguity and not-found cases, cancel via command.

**P5-04 Submission.**
- `content/validation.py` (G17, pure, unit-tested).
- `scheduling.py`: `zoneinfo`; now − 1 min ≤ t ≤ now + 60 days; G13; staff ≥ now + 15 min.
- Quota forecast: no rolling 24 h window around `t` may exceed `PUBLISH_DAILY_LIMIT`.
- `payload.py`: canonical payload (phase doc shape + G5) → `payload_hash`.
- `service.submit(ctx, item_id, schedule, self_approve, expected_version, actor)`:
  - With `content.approve` + `self_approve` → `record_policy_grant(self_approved=True)` → `scheduled`.
  - Staff → `approvals.request(authorization, content.publish, required content.approve, expires_at=scheduled_at)` → `pending_approval`.
  - `self_approve` without the permission → 403.
  - On `scheduled`: set `execute_before = scheduled_at + publish_max_delay_minutes`; copy `is_simulated` from the account; enqueue `publish_content` with `run_at=scheduled_at` and dedup `publish:{id}:v{version}`.
- `content/subject.py` callbacks:
  - approve → `scheduled` + enqueue;
  - reject → `rejected` (note);
  - expire → `draft (APPROVAL_EXPIRED)` + notify the requester.
- Routes `submit`, `cancel` (G1/E7; `publishing` → 409; op cancel via hook), `reapprove` (G2).
- Tests:
  - AC-D3 (`unit/content/test_validation.py`);
  - AC-D4 (19:00 Istanbul → 16:00 UTC, approval bound to version and hash, job `run_at`);
  - AC-D7 (`test_cancel.py`), AC-D8 (`test_staff_submit.py`);
  - DST tests (Europe/Istanbul and Europe/Lisbon);
  - payload hash stability; stale hash → 409.

**P5-05 Mock publishing.**
- Migration 0010: `sim_containers` and `sim_published_media` (`unique(container_id)`).
- Mock methods:
  - `create_media_container`: JPEG via storage (G3); `IN_PROGRESS`, `ready_at = now + SIM_CONTAINER_DELAY_SECONDS`, `expires_at = now + 24 h`.
  - `get_container_status`.
  - `publish_container`: requires `FINISHED`; a duplicate is a DB error → `ProviderInvalidRequest`.
  - `get_media`: permalink `https://instagram.example/sim/{id}`.
  - `get_publishing_quota`: last 24 h, limit `PUBLISH_DAILY_LIMIT`.
  - Failure modes per G18.
- Migration 0011 (G4).
- Contract tests: replace the `NotImplementedError` assertions with the lifecycle, double publish, expiry and each failure mode.
- Dev panel failure-rule operations gain `create_container`, `container_status` and `publish`. Read-only `GET /dev/workspaces/{ws}/simulator/published` for the "exactly one post" demo.

**P5-06 Publish executor.** `operations/publish.execute_publish(session_factory, clock, settings, workspace_id, content_id, version, *, provider=None, sleep=time.sleep)`, per workflows §E step 6 and G8–G10:
1. **T1:** lock the item; wrong status or version → no-op (and cancel the waiting op).
   - Due-time checks: workspace active; `assert_executable`; payload hash; account `connected` + capability; otherwise → `on_hold (ACCOUNT_UNAVAILABLE)` + notify.
   - `> execute_before` → `failed (PUBLISH_DEADLINE_PASSED)`.
   - Get or create op `publish:{id}:v{n}` (`ON CONFLICT DO NOTHING` + `FOR UPDATE`). `succeeded` → repair to `published`.
   - Op `in_progress`, item `publishing`. Commit.
2. Create the container if there is no `provider_ref.container_id` → **T2** commit the id.
3. Poll (G9): `ERROR` → `failed (MEDIA_REJECTED)`; `EXPIRED` → clear the id and go back to step 2; `PUBLISHED` → step 5.
4. `publish_container`. Outcome unknown → op `outcome_unknown` + `reconcile_publish` at +1 min, which re-reads the container (`FINISHED` → `outcome_unknown → in_progress` + publish again; `PUBLISHED` → succeed).
5. **T3:** `get_media` (best effort) → op `succeeded`, item `published` + `content.published` notification and audit; `health.record_success`.
6. Errors (G.1 mapping):
   - transient/rate limited → `retry_wait`/`retry_scheduled` (G10);
   - permanent → `failed` immediately;
   - auth → `health.handle_auth_error` + item `on_hold` (G1);
   - permission → `failed (CAPABILITY_MISSING)`.

Also in this task: register the content hooks, extend `reconcile_stuck_operations` (G11), and the jobs `publish_content` (5) and `reconcile_publish` (10).

Tests: AC-D5, AC-F1…F6 (named files per acceptance-criteria.md), quota exhaustion → `retry_scheduled`, deadline passed → `failed`, `auth_revoked` at due time → `on_hold`, cancel during `publishing` → 409. Every test asserts the `sim_published_media` count (INV-06).

**P5-07 Content impact handlers.** `content/impact_handlers.py` `ContentItemReferrers` (count + apply_change):
- `scheduled`/`retry_scheduled` → `on_hold (FACT_CHANGED)` + approval cancelled + job and op cancelled + `content.on_hold`;
- `pending_approval` → `draft` (`hold_reason=FACT_CHANGED`, approval cancelled);
- `draft` → `validation.stale = true`.
- Sweep: items in those states whose caption or overlay contains the **old display string** are treated as referencing, even without a `fact_references` row.
- `published` is untouched.
- Impact counts feed the command confirmation card.
- Tests: AC-C4 (`test_fact_impact.py`).

**P5-08 Frontend** (`content.json` tr/en; move `content.title` into it because of the shallow merge).
- Routes `content`, `content/:id` replace the placeholder (update `app.test.tsx:111`).
- Tabs (G15).
- `ContentCard`: `StatusBadge` + `SimulatedBadge`.
- `ContentEditor`:
  - feed: caption with a counter;
  - story: overlay suggestions + the "metin görselin üzerinde olmalı" note;
  - inline validation issues and fact chips (reuse `FactChip`).
- `MediaUpload`: preview via `/media/{id}/content`, warnings.
- `GenerateSheet`.
- `ScheduleSheet`:
  - local date and time with "İstanbul saati";
  - "Hemen yayınla" only for approvers;
  - an exact summary;
  - "Onayla ve zamanla" vs "Onaya gönder".
- Status mapping in `content/status.ts`:
  - `publishing` + op `outcome_unknown` → "Kontrol ediliyor";
  - `retry_scheduled` → "Tekrar denenecek {{time}}";
  - only `published` → "Yayınlandı" (INV-18).
- `FailureDetail`: error catalog what/next.
- `OnHoldActions`: edit / re-approve / cancel.
- Simulated permalink with a badge.
- Other files touched:
  - `ContentApprovalBody` in `ApprovalDetailSheet` for `content.publish`;
  - notifications `describe.ts` for `content.*`;
  - Dev panel operations;
  - command result links to content.
- Regenerate `openapi.json` / `schema.d.ts`.
- Vitest per component using `mockApi`: the INV-18 badge table, `expected_version` sent, no "now" for staff, 409 handling.

**P5-09 Evals.**
- `evals/draft_content/*.yaml`, ≥ 15 tr/en cases: backed and unbacked promotions, price mentions, story overlay length, `do_not_share`, invented discount.
- `loader.TASKS` + `EVALUATORS["draft_content"]`, DB-free: task → render → claims.
- Hard assertions: 0 ungrounded critical values in passing captions; unbacked claims flagged; a story has no caption.

**P5-10 Tests and close-out.**
- AC-X5 publish case in `integration/jobs/test_restart.py`.
- AC-F5 in `integration/jobs/test_concurrency.py` (two threads → one publication).
- `@commits` crash test: raise right after the T2 container-id commit → re-run → exactly one publication using the stored id.
- Isolation `foreign_ids` + content and media IDs; AC-X2 additions to `test_simulation_flag.py`.
- E2E:
  - `scenario-c.spec.ts`: add "fact change holds the scheduled post"; keep the existing tests.
  - `scenario-d.spec.ts`: story command → upload the PNG → schedule +2 min shows *Zamanlandı · time*; "Hemen yayınla" → *Yayınlandı · SİMÜLASYON*; edit after approval → *Taslak*; staff → *Onay bekliyor*.
  - `scenario-f.spec.ts`: failure rule via the dev API; `publish invalid_media` → *Başarısız* + cause + "Düzenle ve yeniden gönder"; `publish transient ×1` → "Tekrar denenecek HH:MM" (AC-F7).
  - The slow retry and reconcile paths are proven by the integration tests, not by waiting minutes in E2E.
- Docs: every doc named in §2, plus component-design, environment-variables, `.env.example` and local-development (demos D, F and the reconnect step of G).
- Phase summary `docs/implementation/phase-summaries/phase-05-summary.md`: changes, tests per AC, demo steps, deviations (G1–G19 + P5-00), limitations, questions. Then **stop for review**.

---

## 4. Shared files touched (append-only where possible)
- Backend: `app/handlers.py`, `app/main.py`, `app/api/router.py`, `core/{config,errors}.py`, `core/i18n/{en,tr}.json`, `jobs/{queue,worker}.py` (`RescheduleJob`, `cancel_queued`, `expedite`), `operations/{jobs,accounts,accounts_router}.py`, `integrations/instagram/{mock,models,registry}.py`, `commands/{registry,resolver,service,transitions}.py`, `ai/schemas.py`, `inbox/{processing,jobs,service,impact,views}.py`, `policy/{classes,rules_reply,router,service}.py`, `demo/dev_router.py`, `evals/{loader,runner}.py`, `pyproject.toml`, `tests/isolation/conftest.py`, contract tests.
- Frontend: `app/router.tsx`, `i18n/index.ts`, `api/types.ts`, `ApprovalDetailSheet.tsx`, `notifications/describe.ts`, `DevPanel.tsx`, `AutomationSettings.tsx`, inbox `DraftCard.tsx`, the connection screen, `app.test.tsx`.
- CI: `.github/workflows/ci.yml` (`draft_content` evals are already covered by `--all`).

## 5. Verification
- After each task:
  ```
  uv run ruff check . ; uv run ruff format --check . ; uv run mypy app evals ; uv run lint-imports ; uv run pytest <task tests>
  ```
- End of phase:
  - full `uv run pytest`;
  - `uv run python -m evals run --all --provider fake --strict` (0 hard failures);
  - `npm run lint ; npm run typecheck ; npm test ; npm run i18n:check`;
  - the OpenAPI drift check (regenerate, then `git diff --exit-code`);
  - `npm run e2e` (all specs, 3 projects).
- Mutation spot-checks, each reverted afterwards; each must turn a named test red:
  - drop the container-id commit before publish (crash test);
  - allow publish without `FINISHED`;
  - skip the version check in T1 (AC-D6);
  - drop the `workspace_id` filter in the content repository.
- Manual demo (phase doc), on a fresh seed with API + worker + `npm run dev`:
  1. "Deneme dersi için bir story hazırla" → overlay suggestions + note → upload `story-sample.png` (converted) → Onayla ve zamanla +2 min → *Zamanlandı* → *Yayınlanıyor* → *Yayınlandı · SİMÜLASYON*.
  2. A feed post with the price, scheduled → "Aylık üyelik artık 7.000 TL" → confirm → *Beklemede: fiyat değişti*.
  3. Failure rule `publish transient ×2` → publish → retries shown (1 and 5 min) → published once (Dev → Simulator: 1 row).
  4. Phase 4 follow-ups: an `auth_revoked` send → reconnect (simulation) → the queued reply is sent; the review button; the `CONTAINS_PRICING` chip; the staff approval state.
