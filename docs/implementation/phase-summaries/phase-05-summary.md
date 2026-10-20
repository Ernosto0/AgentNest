# Phase 5 summary: Content and scheduling

**Status:** implemented and verified locally; **waiting for review** (per [roadmap.md §5](../roadmap.md)). Phase 6 has not been started.
**Scope reference:** [phase-05-content-and-scheduling.md](../phases/phase-05-content-and-scheduling.md). Plan and decisions: [phase-5-sessions/plan.md](../phase-5-sessions/plan.md) (tasks P5-00 … P5-10, decisions G1–G19), session briefs `s01` … `s14` in the same folder.
**Branch:** `main`, one commit per task or task group (list in §1), nothing pushed. Phase 4 was treated as *accepted with changes*: four of its review questions were decided by the owner and built first (P5-00).

## 1. What changed

| Session | Commit | Contents |
|---|---|---|
| (plan) | `672bef3` | Implementation plan, G1–G19, session briefs |
| 1 | `4378cb8` P5-00 Q2 | One `draft_reply` job per conversation (`draft_reply:{conversation_id}`), the new `RescheduleJob(run_at)` (the worker re-queues the same row and gives the attempt back), a newer inbound message is caught at the end of T3 |
| 1 | `3b1752e` P5-00 Q6 | `POST /social-accounts/{id}/reconnect` (mock only), audit `account.reconnected`, job `resume_account`, `queue.expedite`, "Yeniden bağlan (simülasyon)" on the connection screen |
| 2 | `01b908a` P5-00 Q3 | `effective_mode` returns the winning class; rules R13–R16 add the reason `CONTAINS_<CLASS>`; reason chip in the inbox |
| 2 | `db49318` P5-00 Q4 | `POST /automation-policies/review` stamps `automation_reviewed_at` once and audits `policy.reviewed`; `PUT` no longer stamps; button "Bu ayarları inceledim" |
| 2 | `6409663` P5-00 Q5 | `ReplyDraft.approval_state`, shown to people who cannot approve (who must approve and by when, or who decided, when, with the note) |
| 3 | `f552020` P5-01 | `MediaStorage` (local backend, `localmedia:` fetch reference), `MEDIA_*` settings and production check, migration `0008` `media_assets`, `media.ingest` (always a baseline sRGB JPEG without EXIF), `POST /media`, `GET /media/{id}/content`, `MEDIA_INVALID` / `MEDIA_TOO_LARGE`, sample images |
| 4 | `2fa9bad` P5-02 | Migration `0009` `content_items`, the pure transition table plus conditional audited `apply`, `create_draft` / `update` (versioning, claim validation, `fact_references`, approval and job cancellation), list/get/create/patch/validate routes, `queue.cancel_queued`, content ledger hooks |
| 5 | `a61878f` P5-05 | Migration `0010` `sim_containers` / `sim_published_media`, mock container lifecycle, publish, quota and failure modes (G18), migration `0011` capability names (G4), dev panel operations, `GET /dev/workspaces/{ws}/simulator/published` |
| 6 | `b7def52` P5-04 | Pure validation (G17), scheduling with DST handling (G13), quota forecast, canonical payload and hash, `submit` / `reapprove` / `cancel`, the `content_item` approval subject, notification kinds |
| 7 | `7a0b450` P5-06 | `operations/publish.execute_publish` (T1/T2/T3, quota read before T1, polling with an injected `Clock` and sleeper, retries on the same job row, auth → `on_hold`), `reconcile_publish`, `publish_content`, `reconcile_stuck_operations` extended, ledger hooks |
| 8 | `2546199` P5-07 | `ContentItemReferrers`: a fact change holds scheduled posts, returns pending ones to draft, marks drafts stale; old-string sweep; impact counts on the confirmation card |
| 9 | `cf5640e` P5-03a | `draft_content` task and prompt v1, fake tr/en, `generate_content` job (three phases, no transaction open during the model call), `POST /content-items/generate`, caption grounding resolution (§5, D-S9) |
| 9 | `9da1a50` P5-09 | `draft_content` evals: 26 tr/en cases, DB-free, hard INV-02 assertions |
| 10 | `4a30e8a` P5-03b | Commands `content.create_draft`, `content.cancel_scheduled` (confirmation `command.cancel_content`), `query.content_status`, `query.explain_failure`, the `ContentRef` resolver, interpreter prompt extended |
| 11 | `b067b06` P5-08a | Content frontend foundation: list with tabs, card, editor, media upload, status mapping (`content/status.ts`) |
| 12 | `ec6c8d1` P5-08b | Generate sheet, schedule sheet, failure detail, on-hold actions, cancel, approval body, notifications, command result links, dev panel additions |
| 13 | `fa811ee` P5-10a | Backend close-out: restart (AC-X5), concurrency (AC-F5), `@commits` crash test (AC-F4), isolation and simulation-flag tests, the AC map and mutation spot-checks ([ac-test-map.md](../phase-5-sessions/ac-test-map.md)) |
| 14 | P5-10b | E2E: `scenario-c` (fact change holds the scheduled post), `scenario-d`, `scenario-f`, shared helpers |
| 14 | P5-10c | Docs close-out (G1–G19 resolutions checked one by one, known doc issues fixed, local-development demos D, F, G) |
| 14 | P5-10d | This summary |

Schema: migrations `0008` (media_assets), `0009` (content_items and its foreign keys), `0010` (sim_containers, sim_published_media), `0011` (mock capability names data fix). New dependencies: `pillow`, `python-multipart`. New job types: `generate_content`, `publish_content`, `reconcile_publish`, `resume_account`. Import contracts: 16 kept (`content` does not import `operations`/`commands`/`api`; `integrations.storage` imports only `core`; the content submit rules are pure).

## 2. Test results

| Check | Result |
|---|---|
| `ruff check` / `ruff format --check` / `mypy app evals` | clean (379 files formatted, 211 source files) |
| `lint-imports` | 16 contracts kept, 0 broken |
| Evals (`--all --provider fake --strict`) | `interpret_command` 61/61, `extract_fact_candidates` 12/12, `draft_reply` 61/61, `draft_content` 26/26; 0 hard failures |
| Backend `pytest` | **2176 passed** in 16 min 40 s (the machine was also running the frontend tests, the evals and the real-time demo walk; session 13's quiet run took 6 min) |
| Frontend lint / typecheck / i18n check | clean (920 keys, tr + en) |
| Frontend `npm test` | **392 passed** (23 files) |
| OpenAPI drift (regenerate `openapi.json` and `schema.d.ts`, `git diff --exit-code`) | no difference |
| E2E (3 projects) | **90 passed** in 19.2 min on mobile-webkit, mobile-chromium and desktop-chromium (30 tests each: Phase 1, scenarios A, B, C including the new fact-change test, D, F). Playwright WebKit, not a real iPhone |

## 3. Acceptance criteria

Paths are relative to `backend/`; the complete map (every test per criterion, with notes) is [ac-test-map.md](../phase-5-sessions/ac-test-map.md).

| # | Criterion | Evidence |
|---|---|---|
| AC-C4 | A price change by command holds the scheduled post (`on_hold`, job and operation cancelled, the approved approval stays approved but authorises nothing), `content.on_hold` reaches every approver including the changer; a pending post goes back to draft with its approval cancelled; a published post is unchanged | `tests/integration/content/test_fact_impact.py::test_ac_c4_a_price_change_by_command_holds_the_scheduled_post`, `::test_the_author_who_cannot_approve_is_told_too`, `::test_an_item_waiting_for_approval_goes_back_to_a_draft_and_its_approval_is_cancelled`, `::test_published_and_publishing_items_are_untouched`; E2E `scenario-c` "fact change holds the scheduled post (AC-C4)" |
| AC-D1 | "Deneme dersi için bir story hazırla" creates a story draft with overlay suggestions, references and no caption | `tests/integration/content/test_generate.py::test_ac_d1_…`, `::test_a_story_is_generated_without_a_caption`; `tests/integration/commands/test_content_commands.py`; evals `draft_content`; E2E `scenario-d` D1/D2/D4 |
| AC-D2 | A PNG becomes a `ready` JPEG without EXIF; a text file is `MEDIA_INVALID` | `tests/integration/content/test_media_upload.py::test_a_png_becomes_a_ready_jpeg_without_exif`, `::test_exif_and_gps_in_a_jpeg_never_reach_the_stored_file`, `::test_a_text_file_is_rejected_whatever_its_name_and_type`; E2E uploads `story-sample.png` / `feed-sample.jpg` |
| AC-D3 | A story without media fails with `CONTENT_MEDIA_REQUIRED` | `tests/unit/content/test_validation.py::test_ac_d3_…`; `tests/integration/content/test_schedule.py::test_the_dry_run_lists_every_submit_rule_and_changes_nothing` |
| AC-D4 | 19:00 Istanbul is 16:00 UTC; the approval is bound to version and payload hash; the job has `run_at = scheduled_at` | `tests/integration/content/test_schedule.py::test_ac_d4_…`; E2E D1/D2/D4 (+2 minutes shows *Zamanlandı*) |
| AC-D5 | Past `scheduled_at`, running due jobs publishes the item once with a simulated media id | `tests/integration/content/test_publish.py::test_ac_d5_…`; E2E D5 (*Yayınlandı* + *SİMÜLASYON*, one simulator row) |
| AC-D6 | Editing a scheduled item returns it to draft, voids the approval; the old job is a no-op | `test_schedule.py::test_ac_d6_…`, `test_edit_after_approval.py::…`, `test_publish.py::test_a_job_of_an_old_version_publishes_nothing_after_an_edit`, `::test_a_job_of_an_old_version_publishes_nothing_while_a_newer_version_is_scheduled` (added in session 13); E2E D6 |
| AC-D7 | Cancelling a scheduled item cancels it and its job | `tests/integration/content/test_cancel.py::test_ac_d7_…`; `test_publish.py::test_an_item_that_is_no_longer_scheduled_is_not_published` |
| AC-D8 | A staff submission is a pending authorisation; only owner or manager approves; staff never get "Hemen yayınla" | `tests/integration/content/test_staff_submit.py::test_ac_d8_…`, `::test_only_owner_and_manager_can_approve`; E2E D8 (two tests: *Onay bekliyor*, then the owner approves and it reads *Zamanlandı*) |
| AC-F1 | `transient ×2`: retries with backoff, published once on the third attempt | `tests/integration/content/test_publish_retry.py::test_ac_f1_…` |
| AC-F2 | `transient` always: `failed` (`PROVIDER_UNAVAILABLE`) after the attempts, with a notification | `test_publish_retry.py::test_ac_f2_…` |
| AC-F3 | A timeout after the publish is reconciled to `published` with no second post | `tests/integration/content/test_publish_reconcile.py::test_ac_f3_…` |
| AC-F4 | A worker killed between container and publish publishes once, using the stored container id | `tests/integration/content/test_publish_crash_commits.py::test_ac_f4_commits_…` (real commits), `test_publish_reconcile.py::test_ac_f4_…` |
| AC-F5 | The same publish run twice concurrently yields one publication | `tests/integration/jobs/test_concurrency.py::test_ac_f5_…` (two threads, a barrier, 5 rounds; and two workers) |
| AC-F6 | `MEDIA_REJECTED` is not retried | `tests/integration/content/test_publish_permanent.py::test_ac_f6_…`; E2E F6 |
| AC-F7 | The UI shows *Başarısız* with the cause and the next step; a retry shows the next attempt time | E2E `scenario-f` F6 (*Başarısız*, "Instagram görseli işleyemedi.", "Düzenle ve yeniden gönder") and F7 (*Tekrar denenecek HH:MM* on the badge, the detail and the list card); backend support `test_publish_retry.py::test_the_retry_is_visible_in_the_api_with_its_next_attempt_time` |
| AC-X5 | A queued and a scheduled job (and a publish) survive a worker restart | `tests/integration/jobs/test_restart.py::test_ac_x5_a_scheduled_publish_survives_a_worker_restart`, `::test_a_publish_job_whose_worker_died_after_claiming_it_is_published_once_by_the_next`, `::test_a_new_worker_instance_picks_up_queued_and_scheduled_jobs` |
| INV-06 | Duplicate jobs or events cause one remote effect (exact `sim_published_media` counts) | `test_concurrency.py`, `test_publish_crash_commits.py`, `test_publish_reconcile.py`, `test_publish.py::test_running_the_same_publish_again_publishes_nothing_more`; every publish test asserts the count; E2E D5 and the demo (§4) check the simulator list |
| INV-18 | "Published" is shown only for a `published` item; scheduled, publishing, checking, retrying and failed read differently | `frontend/src/features/content/status.test.tsx` (badge table), `crosscutting.test.tsx`; E2E D1 (nothing reads *Yayınlandı* while scheduled), D5, F6, F7 |
| AC-X1 / AC-X2 | Isolation of the new routes; everything simulated is flagged | `tests/isolation/test_content_isolation.py`, `test_media_isolation.py`, `test_publishing_isolation.py`; `tests/integration/test_simulation_flag.py`; E2E badges (*SİMÜLASYON* on cards, details, permalink and the dev list) |

**Mutation spot-checks (session 13, all reverted).** Dropping the container-id commit (T2) turned both AC-F4 tests red; allowing a publish without `FINISHED` and treating `IN_PROGRESS` as `FINISHED` each turned the contract/polling tests red; dropping the `workspace_id` filter from `get_item` and `list_items` turned the content isolation tests red. Skipping the T1 version check **survived** the existing suite and was closed by a new test (`test_a_job_of_an_old_version_publishes_nothing_while_a_newer_version_is_scheduled`). Details: the table at the end of ac-test-map.md.

## 4. Demo steps

Verified on a fresh seed with the API, the worker and the Vite dev server (a throw-away Playwright script walked the steps in real time on desktop Chromium; it was not committed). The same flows are asserted, without the long waits, by the E2E specs.

1. `docker compose up -d postgres`; `cd backend`; `uv run alembic upgrade head`; `uv run python -m app.cli seed --reset`; start the API, **the worker** and `npm run dev`. Sign in as `owner@demo.local`, open *Gölkent Fitness & Pilates*.
2. **Story.** Home: "Deneme dersi için bir story hazırla" → "İçeriği aç" → the draft shows the overlay suggestion ("İlk deneme seansı ücretsiz, rezervasyon gerekir.") and the note that the text belongs on the picture → upload `story-sample.png` → **Zamanla** +2 minutes → **Onayla ve zamanla**. Observed: *Taslak* → *Zamanlandı* → (at the minute) *Yayınlanıyor* → 12 s later *Yayınlandı* with *SİMÜLASYON* and the simulated permalink.
3. **Price post and price change.** İçerik → Taslak iste ("Aylık üyelik fiyatı hakkında bir gönderi") → the caption holds "6.000 ₺ / ay" → upload `feed-sample.jpg` → schedule +3 hours → *Zamanlandı*. Home: "Aylık üyelik artık 7.000 TL" → the card shows 6.000 → 7.000 and "Etkilenecek öğeler: İçerik: 1 adet" → Onayla. İçerik → Sorunlar: the post is *Beklemede* with "Kullandığı işletme bilgisi değiştiği için beklemeye alındı." and **Olduğu gibi yeniden onayla**.
4. **Retries.** Dev panel → operation *publish*, error *transient*, **Sonraki çağrı için ekle** twice → a post published with **Hemen yayınla**. Observed: *Yayınlanıyor* → *Tekrar denenecek 22:24* → *Tekrar denenecek 22:29* (1 and 5 minutes later) → *Yayınlandı* after 6 minutes 14 s. Dev panel → "Simülatörde yayınlananlar" lists that post **once** (the list had 2 rows in total because step 2 had already published the story; one row per published post).
5. **Phase 4 follow-ups.** Dev panel → rule *send → auth_revoked*, price question (Ayşe), Onayla ve gönder → the reply stays queued (*Birazdan gönderilecek*) → More → Otomasyon ve Instagram → **Yeniden bağlan (simülasyon)** → the reply is *Gönderildi* without approving it again. After clearing the review stamp in the database, the automation screen shows **Bu ayarları inceledim** and pressing it shows "Bu ayarları gözden geçirdiniz." A pending reply, opened as `staff@demo.local`, reads "Bu yanıtı bir sahip ya da yönetici onaylamalı. Son onay zamanı: …".

**Steps that did not behave as the plan or docs wrote them**
- The `CONTAINS_PRICING` chip did **not** appear in the demo: the fake model labels every price question as `pricing`, which is the class that decides, so there is nothing to explain (the chip is absent by design in that case). It needs a model that labels a reply as another class while it quotes a price; that is proven with a scripted model in `tests/integration/inbox/test_reply_workflow.py::test_a_price_question_the_model_labels_hours_still_follows_the_pricing_policy` and `tests/unit/policy/test_reply_rules.py`. It cannot be shown with `LLM_PROVIDER=fake`.
- The plan and `local-development.md` §6 G spoke of a Home banner after the revoked token. There is none in Phase 5: Home is still a basic placeholder (the Home dashboard and banners are P6-04/P6-05). The state is visible on the connection screen ("yeniden bağlanmalı") and in the bell. `local-development.md` §6 was corrected.
- "transient ×2" is two clicks of the dev panel button (each rule is for the next call only, `remaining: 1`); documented in §6 F.
- The "Dev → Simulator: 1 row" check is one row **per post**; it reads 2 rows after demo step 2 has published the story.

## 5. Deviations from the docs and plan (and why)

### 5.1 Planning-time decisions G1–G19 (written into the named docs in the sessions that built them; checked one by one in P5-10c)

| # | Deviation / resolution | Recorded in |
|---|---|---|
| G1 | State table gains `draft → cancelled`, `pending_approval → cancelled`, `retry_scheduled → on_hold`, `publishing → on_hold (ACCOUNT_UNAVAILABLE)` | state-machines §5 |
| G2 | Re-approval **increments `version`** (fresh `publish:{id}:v{n}` keys); `on_hold` entry cancels the queued job and a waiting operation | state-machines §5, workflows §E |
| G3 | Local `public_fetch_url` is an opaque `localmedia:{key}?exp=…` reference; the registry passes a `MediaStorage` to the mock, which checks the JPEG magic bytes | integrations §3.3, ADR-015 |
| G4 | Capability names `publish_feed_image` / `publish_story_image`; migration 0011 rewrites existing mock rows | integrations §3.2 |
| G5 | Approval payload `overlay_text` = the overlay suggestions; a story publishes no text (`ContainerSpec(STORIES, caption=None)`) | workflows §E |
| G6 | `caption` is the rendered text; generation renders `caption_template`; hashtags are appended by code | workflows §E, data-model §3.6 |
| G7 | `client_request_id` + `agent_runs(queued)` for generation; failure leaves a manual draft | data-model §3.6, api-design §2.7 |
| G8 | Quota read with no transaction open before T1, then T1 re-checks | workflows §E 6.1 |
| G9 | Publish polling measured with the injected `Clock` and a sleeper (10 s, up to 5 min, `heartbeat()`); the explicit sentence was missing from `background-jobs.md` and was added in P5-10c | workflows §E, background-jobs |
| G10 | Retries on the same job row via `RetryableError(retry_after_seconds)`; operation `max_attempts=5`, `deadline_at`; `on_dead` failsafe | background-jobs |
| G11 | `reconcile_stuck_operations` extended to `publish_content` | background-jobs |
| G12 | Upload order and always-re-encode; no row for a rejected upload; orphan `media_cleanup` deferred | ADR-015, data-model |
| G13 | DST gap → `SCHEDULE_TIME_NONEXISTENT`; fold → the earlier instant | workflows §E |
| G14 | New `content.on_hold` / `content.published` / `content.failed`; `content.on_hold` also reaches the author of a fact change | observability |
| G15 | Tabs: Drafts, Scheduled, Published, Problems; `cancelled` in none | user-journeys §1 (sharpened in P5-10c) |
| G16 | `publish_max_delay_minutes` workspace setting (default 360 at the time; 1440 since Q3), not an env var; the ADR-014 note was missing and was added in P5-10c | ADR-014, workflows §E |
| G17 | Submit item codes and warnings | observability §4 |
| G18 | Mock publishing failure modes | integrations §3.3 |
| G19 | Sample images `story-sample.png`, `feed-sample.jpg` | local-development §6 |

### 5.2 P5-00 (Phase 4 follow-ups)

| # | Deviation | Notes |
|---|---|---|
| P0-1 | `suggest-reply` keeps its own job key `draft_reply:{conversation_id}:requested` | It carries a flag; the plan said one key per conversation. Phase 4 D8 is marked as superseded |
| P0-2 | A fact-change or release redraft now waits the debounce window instead of running at once | One consistent rule for every enqueue site |
| P0-3 | The audit action of a reconnect is `account.reconnected` (optional `audit_action` on `transition_account`); the other account audit names stay `social_account.<status>` | The audit-name convention is now documented (observability §4) |
| P0-4 | Residual window: a customer message stored after the T3 commit but before the worker marks the job succeeded waits for its next trigger; the stored draft is closed by that message (`NEW_INBOUND`) | Recorded in the Phase 4 summary D8 |
| P0-5 | Reconnect does not clear permanent failure rules; it accepts only `needs_reauth` (anything else is 409 `CONFLICT_STATE`) | Clearing rules is Phase 6 (P6-05) |
| P0-6 | `auto` mode can still be saved before the review button is pressed (readiness stays below ready; rule R15 keeps approval) | Saving is no longer the review |
| P0-7 | `approval_state.status` may read `pending` after `expires_at` until the expiry sweep runs; a reply approved by policy shows no decider name | Display only |

### 5.3 Deviations found while building (by session)

| # | Deviation | Notes |
|---|---|---|
| S3-1 | Pixel cap 36 000 000 (constant, ADR-015); `meta` with `MEDIA_STORAGE_BACKEND=local` is refused in production, and `s3` is not buildable before Phase 7 | |
| S3-2 | `media_assets.status` only ever holds `ready` (the check constraint allows `uploaded`, `rejected`, `deleted`) | Rejected uploads store no row (G12) |
| S3-3 | Starlette buffers the multipart body before the size check; the 413 is raised after reading | |
| S3-4 | The `media_cleanup` job is deferred | Phase 6 retention scope |
| S4-1 | Editing an approved, scheduled item leaves its approval `approved` (an approval never leaves that state) but stale; AC-D6 asserts stale + job cancelled | Approval machine untouched |
| S4-2 | `/validate` was a claim-only dry run, widened in S6 to every submit rule; an edit clears `scheduled_at` and the hold fields; the list takes `tab` | |
| S5-1 | Only `IN_PROGRESS`, `ERROR`, `PUBLISHED` are stored in `sim_containers`; `FINISHED` / `EXPIRED` are derived from `ready_at` / `expires_at` and the clock | data-model §3.6 |
| S5-2 | The mock rejects a story caption (`CAPTION_NOT_ALLOWED`) and enforces the 24 h quota | |
| S5-3 | `timeout_after_success` was meant for send and publish only; the mock **also** honours it for `create_container` (the container exists, the answer is lost) and turns it into a transient error for `container_status`. The executor treats an unknown outcome there as a failed attempt. integrations §3.3 now says so (found in P5-10c) | No visible effect: a retry creates another container |
| S6-1 | `social_account_id` is set at submit from the workspace's connected account | |
| S6-2 | Claim issues carry `fact_key`; new issue `PLACEHOLDER_UNRENDERED` | |
| S6-3 | The 15-minute lead applies to any submission that waits for an approver, not only to staff | |
| S6-4 | The quota forecast counts `scheduled`, `publishing`, `retry_scheduled` and `published` items | |
| S6-5 | Re-approval needs `content.approve`; **cancel needs `content.approve`**, so staff could not withdraw their own pending submission (per workflows §E step 7) | RESOLVED by Q1 (§7): staff may now cancel their own pending submission |
| S7-1 | An overdue deadline goes `scheduled → publishing → failed` inside T1 (no direct edge) | |
| S7-2 | `ContainerStatus` gained an optional `media_id` (for the permalink after a reconcile) | OPEN QUESTION Q2 |
| S7-3 | The quota-retry time is derived from the account's own published items (falls back to now + 1 h); a quota deferral raises `RescheduleJob` and spends no attempt | |
| S7-4 | With the former 6 h default of `publish_max_delay_minutes`, an exhausted quota mostly ended in `failed (PUBLISH_DEADLINE_PASSED)` | RESOLVED by Q3 (§7): the default is 24 h |
| S7-5 | A dead `publish_content` job with the item `in_progress` becomes `outcome_unknown` → reconcile, never a blind failure | |
| S7-6 | Reconcile does not call `handle_auth_error` when its own read fails with an auth error | |
| S8-1 | No `content.on_hold` for `pending_approval → draft` (counted in the impact result instead) | observability |
| S8-2 | The old-string sweep is guarded: whole token, only money, hours, phone, email, address and URL values, at least 4 characters; `publishing` is untouched | |
| S9-1 | Caption grounding: a value that whole-token matches the **current** verified display of a fact is grounded (`matches_verified`), recorded in `fact_references`, and does not block; invented, stale (old price) and rounded values still block. Submit and re-approve replace `fact_references`. `ücretsiz` / `free` is grounded only with a verified promotion fact | workflows §E (this resolves G6) |
| S9-2 | `commercial_claims` is `list[{claim, fact_key?}]` | agent-runtime §5 |
| S9-3 | Generated text is saved through the `edit` transition (version 1 → 2) | |
| S9-4 | The matching is by value, not meaning: `07:00` typed for Saturday is grounded if it appears in the verified hours | Limitation |
| S9-5 | `generation.status` reads `running` until the text is saved; a discarded generation still reads `succeeded` | |
| S9-6 | Phase 4's reply path still uses the loose manual-reply matcher; `tests/integration/ai/test_runner.py` now installs its stand-in per test | |
| S10-1 | A cancel command whose item changed after the confirmation fails with `VERSION_CONFLICT` / `CONFLICT_STATE` and the decision stands (not an HTTP 409 with a rollback); staff are refused at request time | workflows §B.1 (not §A) |
| S10-2 | Interpreter prompt v1 was extended in place; `client_request_id` of a command execution is `command:{id}` | |
| S11-1 | New `StatusBadge` keys; `FactChip` generalised; the caption limit 2200 mirrors the backend `CAPTION_MAX_CHARS` (V-05 unverified) | |
| S12-1 | The generate sheet shows the active account read-only and offers a blank manual draft; "Zamanla" is disabled while there are unsaved changes; the dev panel has only the failure-rule operations and the published list | |
| S12-2 | Editing a `rejected` / `failed` item with only a title or note change cannot be resubmitted: submit needs `draft`, and such an edit did not change the payload | RESOLVED by Q4 (§7): any edit of such an item is a new version and a draft |
| S12-3 | Staff see the full status panel (including the approval expiry) when their item is `pending_approval` | OPEN QUESTION Q5 |
| S13-1 | Media assets and simulator containers carry no `is_simulated` column; the item, approval, operation, notification and audit rows and the API responses do, and are tested | OPEN QUESTION Q6 |
| S13-2 | Mutation (c) initially survived; a test was added | |
| S13-3 | Under mutation (a) one reconcile test appeared to hang; not investigated | OPEN QUESTION Q7 |
| S14-1 | Doc fixes: acceptance-criteria file name (`test_media_upload.py`), the `/validate` body note (the server accepts no body; the generated type marks `self_approve` required, so the client sends `{self_approve:false}`), the account audit-name convention (`social_account.<status>` in code, `account.reconnected` for the reconnect; docs said `account.*`), ADR-014 (G16) and background-jobs (G9) notes, component-design, user-journeys, local-development demos | |
| S14-2 | E2E drives the long paths through the dev "run due jobs" API and does not wait for the 1 and 5 minute retries or the reconcile check; those are proven by the integration tests | Plan §3 P5-10 |

## 6. Known limitations

- **No real Instagram.** The Story API behaviour is unverified (V-03; stories stay behind `publish_story_image`), as is the 2200-character caption limit (V-05) and the 50 posts per 24 h limit (OQ-18/V-04). The Meta adapter and S3 storage are Phase 7; production with `meta` needs `MEDIA_STORAGE_BACKEND=s3`, which cannot be built yet.
- No `media_cleanup` job: orphan files stay under `MEDIA_LOCAL_ROOT` (delete the folder to start clean).
- Starlette buffers a multipart upload before the size check (see S3-3).
- Grounding of a typed caption is by value, not meaning (S9-4); Phase 4's reply path keeps the looser matcher.
- Held posts are never resumed automatically (neither after a reconnect nor after a fact change): the owner re-approves (G2).
- The Home dashboard, banners, the circuit breaker, `degraded`, clearing the `auth_revoked` rule on reconnect and the retention jobs remain Phase 6.
- The CONTAINS_PRICING chip cannot be produced with the fake model (§4).
- Publishing takes about ten seconds even in the demo: the executor polls the container every 10 s.
- Only desktop Chromium was used for the real-time demo walk; the E2E suite runs all three projects (§2). The real iOS Safari, a LAN phone test and GitHub CI have still not run.
- No video, Reels, carousels, image generation or hashtag research (out of scope).

## 7. Open questions for review

Each one needs a decision from the owner; none blocks the next phase.

- **Q1 (S6-5) RESOLVED (owner decision, follow-up commit "Q1"):** Staff can withdraw (cancel) their **own pending submission**. The cancel route now admits any member and the service decides (`content.service.may_cancel`): owners and managers keep their rights; anyone else may cancel only a `pending_approval` item they created or whose current approval they requested, and its pending approval is cancelled (`SUBJECT_CANCELLED`). Their own draft, scheduled or held items and other people's items stay `403`. `ContentItem` gained `can_cancel` (so the UI shows Cancel only when it will work). Docs: workflows §E step 7, api-design §2.7, security matrix. Tests: `test_cancel.py` (withdraw own, created-by, someone else's, other statuses, owners/managers unchanged) and Vitest in `flows.test.tsx`.
- **Q2 (S7-2) OPEN QUESTION:** `ContainerStatus.media_id` is optional and set by the mock when the container is `PUBLISHED`; reconcile uses it to fetch the permalink. Can the Phase 7 Meta adapter supply the media id from the container status?
- **Q3 (S7-4) RESOLVED (owner decision, commit "Q3"):** The default `publish_max_delay_minutes` is now 1440 (24 h), which is also the top of the validation range (1 to 1440). Docs: ADR-014 note, workflows §E, data-model, user-journeys, plan G16. Tests that assumed 360 were updated; the ones about a short deadline set it explicitly (`Publishing.set_max_delay`); a new test covers the default and the range. A workspace created earlier keeps the value stored in its settings (the default is written at creation): change it with `PATCH /workspaces/{id}`.
- **Q4 (S12-2) RESOLVED (owner decision, commit "Q4"):** Any edit of a `rejected` or `failed` item, a title or note only included, now uses the existing `edit` transition: `version + 1`, back to `draft`. The next submission therefore has a new approval and a new `publish:{id}:v{n}` job key (INV-16); a title or note on other statuses is still saved in place, an edit that changes nothing is a no-op, and `published` stays immutable (INV-17). No new state or edge. Docs: state-machines §5, api-design §2.7, workflows §E step 2. Tests: `test_resubmit.py` and Vitest ("Düzenle ve yeniden gönder" after a title-only edit, for `failed` and `rejected`). No frontend code change was needed: the PATCH answer is a draft, which the page already schedules.
- **Q5 (S12-3) OPEN QUESTION:** Staff see the full status panel (expiry time of the approval) for their pending item. Fine?
- **Q6 (S13-1) OPEN QUESTION:** Media assets and the simulator containers have no `is_simulated` column (the content item that uses them has). Was a schema change meant, or is the item's flag enough?
- **Q7 (S13-3) OPEN QUESTION:** Under mutation (a) (the T2 commit dropped) one reconcile test appeared to hang in session 13; it was not investigated. Do you want it investigated (a hang instead of a failure would be a testing hazard)? The unmutated full suite ran to the end without any hang in this session.
- **Q8 (S9-4) OPEN QUESTION:** Typed values are grounded by value, not meaning (`07:00` typed for Saturday passes if it appears in the verified hours). Accept for the MVP?
- **Q9 (S5-3) OPEN QUESTION:** The mock honours `timeout_after_success` on `create_container` although the plan defined it for send and publish only. Keep (documented now) or remove it from the mock?
- **Q10 (carried over) RESOLVED for the model ID (owner decision, commit "Q10"):** OpenAI's official docs (developers.openai.com models, pricing and `gpt-6-luna` pages, read 2026-10-21) list `gpt-6-luna` as the cheapest GPT-6 model ($0.10 / $0.50 per 1M tokens; the others are `gpt-6.1-sol` and `gpt-6-astra`), with model ID and only snapshot `gpt-6-luna`, the Responses API and `structured_outputs`. It is what config, `.env.example` and the docs already used, so no value changed; the "unverified" wording was replaced and the memory note updated. `LLM_PROVIDER=fake` stays the default; no key was used and no paid call was made, so the adapter is **still not proven against the real API**. Open detail: the model page lists reasoning effort `none`, `low`, `medium`, `high`, `xhigh`, `max`, while the config accepts `minimal | low | medium | high`; the default `low` is valid, but check before choosing another value.
