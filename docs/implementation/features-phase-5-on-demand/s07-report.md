# Feature Phase 5 — Session 07 Report: Reels Publishing, Content Type, UI, and Track B Close-Out

- **Session:** 07 of 07 (Track B: F-08 Carousels and Reels; ends with Track B close-out)
- **Feature:** F-08 Reels (`0083` migration, `reel` content type, custom cover or `thumb_offset_ms`, `share_to_feed`, asynchronous `poll_reel_container` ledger publishing, React upload/scrubber/preview UI, Track B close-out)
- **Branch / worktree:** `C:\Users\ernos\pivoris-p5\b` (detached checkout at baseline commit `1a58d41`, `main`; uncommitted on top of Sessions 04, 05 and 06)
- **Migration head:** `20261118_0083_reels.py` (`0083`, `down_revision = "0082"`, track B range `0080–0089`)
- **Date:** 2026-11-18
- **Status:** Implemented and verified offline; stopped for review. All changes left uncommitted as instructed.

---

## 1. Summary of Changes

### 1.1 Migration `0083` and Database Models
- **`backend/migrations/versions/20261118_0083_reels.py`** (`0083`, `down_revision = "0082"`):
  - Widens `ck_content_items_type` to `('feed_image', 'story_image', 'feed_carousel', 'reel')`.
  - Adds `cover_media_asset_id UUID NULL`, `thumb_offset_ms INTEGER NULL`, and `share_to_feed BOOLEAN NULL` to `content_items`, with composite tenant FK `fk_content_items_cover_media_asset` on `(workspace_id, cover_media_asset_id) -> media_assets (workspace_id, id)` (`ON DELETE NO ACTION`, INV-01) and supporting index `ix_content_items_workspace_cover_media_asset`, plus check constraints `ck_content_items_thumb_offset_non_negative` (`thumb_offset_ms IS NULL OR thumb_offset_ms >= 0`) and `ck_content_items_cover_choice_exclusive` (`NOT (cover_media_asset_id IS NOT NULL AND thumb_offset_ms IS NOT NULL)`).
  - Widens `ck_sim_containers_media_type` to include `'REELS'` and adds `cover_url TEXT NULL`, `thumb_offset_ms INTEGER NULL`, `share_to_feed BOOLEAN NULL`, and `error_subcode TEXT NULL` to `sim_containers`.
  - Widens `ck_sim_failure_rules_operation` to include `'create_reel_container'`, widens `ck_sim_failure_rules_mode` to include `'slow_processing'` and `'processing_error'`, and adds `delay_s INTEGER NULL` and `error_subcode TEXT NULL` to `sim_failure_rules`.
  - Refuses downgrade cleanly (`RuntimeError`) when any `content_items` row has `content_type = 'reel'`, `cover_media_asset_id IS NOT NULL`, `thumb_offset_ms IS NOT NULL`, or `share_to_feed IS NOT NULL`, or when any `sim_containers` row has `media_type = 'REELS'`, or when any `sim_failure_rules` row uses the new operation/modes.
- **`backend/app/content/models.py` & `backend/app/integrations/instagram/models.py`**:
  - Updates `ContentItem`, `CONTENT_TYPES`, `SimContainer`, `SimFailureRule`, `SIM_CONTAINER_TYPES`, `SIM_FAILURE_OPERATIONS`, and `SIM_FAILURE_MODES` to match migration `0083`.

### 1.2 Content Rules, Validation, Payload Hashing, and Service Flow
- **`backend/app/content/validation.py` & `backend/app/content/video_limits.py`**:
  - Adds pure Reel submit validation (`_validate_reel_media`, `_validate_reel_cover`) and warning codes (`REEL_ASPECT_NOT_9_16`, `REEL_RESOLUTION_BELOW_RECOMMENDED`, `REEL_EDIT_LIST_PRESENT`).
  - Enforces that a `reel` item has a `ready` `kind="video"` primary `MediaAsset` passing `validate_video_Metadata`, has no carousel items, has no `overlay_text_suggestions`, and has at most one of `cover_media_asset_id` (a `ready` `kind="image"` asset within `4:5..9:16` aspect ratio and `<= 8 MB`) or `thumb_offset_ms` (`0 <= thumb_offset_ms < duration_ms`).
  - Validates the Reel caption through the existing claim validator (`validate_claims`) and records `fact_references` (`referrer_type = 'content_item'`), so a price change holds a scheduled or approved Reel with `FACT_CHANGED` (INV-02 / INV-13).
  - Requires account capability `publish_reel`.
- **`backend/app/content/payload.py` & `backend/app/content/subject.py`**:
  - Binds `media_sha256` (from the video asset), `cover_media_asset_id`, `cover_media_sha256` (from the custom cover asset), `thumb_offset_ms`, `share_to_feed` (`bool(item.share_to_feed) if item.share_to_feed is not None else True`), and `caption` into `ContentApprovalPayload` (`schema_version = 1`), so any change to video, cover, frame offset, feed-sharing flag, or caption changes `payload_hash` and invalidates prior approvals (INV-05).
- **`backend/app/content/service.py`, `schemas.py`, `views.py`, `router.py`, `media_cleanup.py`**:
  - Supports creating and patching `reel` drafts (defaulting `share_to_feed = True` on `reel` and rejecting `cover_media_asset_id`, `thumb_offset_ms`, and `share_to_feed` on non-reel types with `422 VALIDATION_ERROR`).
  - Rejects simultaneous `cover_media_asset_id` and `thumb_offset_ms` in the same PATCH (`REEL_COVER_CHOICE_CONFLICT`), clears the older cover option when the owner switches between a custom cover and a frame offset, and increments `version` only when a payload field actually changes.
  - Refuses `POST /content-items/generate`, `POST /content-items/{id}/regenerate`, `POST /content-items/from-template`, and `POST /content-items/{id}/rerender-template` for `reel` with `422 CONTENT_TYPE_NOT_SUPPORTED`.
  - Projects `cover_media_asset_id`, `cover_media_deleted`, `thumb_offset_ms`, `share_to_feed`, `video_duration_ms`, and `operation.processing` (`op.status == "in_progress" and op.provider_ref.get("phase") == "processing"`) on `ContentItemView`.
  - Protects referenced `cover_media_asset_id` rows from orphan deletion in `media_cleanup.py` and applies the same 90-day post-publication retention rule as primary media assets.

### 1.3 Provider Contract (`MetaInstagramProvider`, `MockInstagramProvider`, Capabilities)
- **`backend/app/integrations/instagram/base.py`, `meta.py`, `mock.py`, `oauth.py`, `operations/accounts.py`**:
  - Extends `ContainerSpec` with `media_type = "REELS"`, `video_url`, `cover_url`, `thumb_offset_ms`, and `share_to_feed`.
  - `MetaInstagramProvider.create_media_container`: sends `media_type="REELS"`, `video_url`, `share_to_feed` (`"true"` / `"false"`), optional `caption`, and at most one of `cover_url` or `thumb_offset_ms`; enforces HTTPS-only non-localhost URLs before calling Graph API; parses Meta processing subcodes from `status` payloads into `SUBCODE_<code>`.
  - `MockInstagramProvider`: creates `REELS` rows in `sim_containers` with configurable processing delay (`sim_reel_processing_seconds`, default `2`), supports `create_reel_container` failure rules plus `slow_processing` (`delay_s`) and `processing_error` (`error_subcode`), validates `localmedia:` video and cover assets, and produces deterministic `/reel/SIM.../` permalinks.
  - Grants `publish_reel: True` on connected mock accounts and on OAuth accounts when `instagram_business_content_publish` is granted.

### 1.4 Asynchronous `poll_reel_container` Publishing and Crash/Restore Safety
- **`backend/app/operations/publish.py`, `jobs.py`, `payloads.py`, `content_ledger.py`, `backup_restore.py`**:
  - Splits Reel publishing across short transactions with **no in-process sleep** during video processing:
    1. **T1 (`_begin`)**: locks item, operation (`publish:{content_id}:v{version}`), and account; runs due-time approval, hash, fact, capability, and media checks; transitions `item -> publishing` and `op -> in_progress`; commits before any provider call (INV-15).
    2. **Container create + T2 (`_drive_reel` / `_store_reel_processing`)**: mints presigned/token video (and optional cover) fetch URLs outside any transaction, calls `provider.create_media_container`, then atomically commits `op.provider_ref = {"container_id": ..., "phase": "processing", "processing_started_at": ..., "polls": 0, "recreations": ...}` and enqueues `poll_reel_container` (`dedup_key = f"poll_reel:{op.id}"`) at `+15 s`, returning `PublishOutcome("processing")` immediately.
    3. **Polling (`poll_reel` / `poll_reel_container` job, `max_attempts = 8`)**: reads container status outside any transaction:
       - `IN_PROGRESS`: checks `REEL_PROCESSING_TIMEOUT` (30 min); if within budget, advances `polls`, refreshes `op.started_at` (so `reconcile_stuck_operations` only trips when polling stops for `> 15 min`), updates `op.next_attempt_at` along `REEL_POLL_SCHEDULE = (15, 30, 60, 60, 120, 120, 180, 180, 300)`, and raises `RescheduleJob(run_at)` without consuming a job attempt.
       - `FINISHED`: re-verifies lock and deadline in `_before_reel_publish`, calls `provider.publish_container` once, fetches permalink best-effort, and commits `published` / `succeeded` in **T3 (`_finish`)**.
       - `PUBLISHED`: finalises directly in `_finish` without calling `publish_container` again (INV-06).
       - `EXPIRED` or retryable `ERROR` (`SUBCODE_2207003`, `SUBCODE_2207032`, `SUBCODE_2207053`): forgets the failed container, increments `recreations` up to `MAX_CONTAINER_RECREATIONS = 2`, creates a replacement container, and reschedules polling; after 2 recreations fails with `PROVIDER_UNAVAILABLE`.
       - Non-retryable `ERROR`: fails immediately with `MEDIA_REJECTED` and preserves `last_error_detail`.
       - Transient status read errors: up to `REEL_MAX_READ_FAILURES = 5` consecutive read errors reschedule along the poll schedule (honouring `Retry-After`) without burning `op.attempts`; the 5th hands over to normal operation retry (`retry_wait` / `retry_scheduled`).
       - `on_dead` (`abandon_poll`) and `backup_restore.fence_inflight_operations`: fences `in_progress` operations to `outcome_unknown` and enqueues `reconcile_publish`.

### 1.5 Frontend Reel Composer, Editor, Scrubber, and Status UI
- **`frontend/src/features/content/ReelMedia.tsx`, `reel.ts`, `hooks.ts`, `ContentComposer.tsx`, `ContentEditor.tsx`, `ContentStatusPanel.tsx`, `ContentCard.tsx`, `ContentMedia.tsx`, `PostPreview.tsx`, `LibraryView.tsx`**:
  - Adds `"reel"` to the composer type selector, disabling AI draft generation and template creation when `"reel"` is selected while keeping "Blank draft" enabled with an explanatory note.
  - Adds `useUploadVideo` in `hooks.ts` over `uploadMediaVideoWithProgress` (`XMLHttpRequest` with `withCredentials = true`, upload progress events, and `AbortSignal` cancellation).
  - Builds `ReelMedia.tsx` with:
    - client-side `.mp4`/`.mov` type and `100 MB` size validation before opening the upload request;
    - determinate progress bar (`role="progressbar"`, `aria-valuemin/max/now`, percentage, and `n MB / m MB`), "Probing…" state at 100%, and a Cancel button;
    - `<video controls playsInline preload="metadata">` preview with `poster` from custom cover or server-extracted thumbnail and formatted duration badge;
    - non-blocking warning banner for `REEL_ASPECT_NOT_9_16`, `REEL_RESOLUTION_BELOW_RECOMMENDED`, and `REEL_EDIT_LIST_PRESENT`;
    - frame scrubber `<input type="range" step={100}>` over `0..maxOffsetMs` (`aria-valuetext` formatted as `0:07.3`) that seeks `video.currentTime` live and saves `thumb_offset_ms` on button click (sending no PATCH when unchanged), custom JPEG cover upload (`<= 8 MB`), and "Use first frame" reset;
    - `share_to_feed` switch (`role="switch"`) and explicit disclosure note (`role="note"`) that video and audio content are not automatically fact-checked against Business Knowledge.
  - Updates `ContentStatusPanel.tsx` to display the processing state (`"Instagram is processing this Reel…"` / `"Instagram bu reels videosunu işliyor…"` with next status-check timestamp) when `item.operation?.processing` is true.
  - Adds complete Turkish and English copy in `frontend/src/i18n/locales/{tr,en}/content.json` and backend `backend/app/core/i18n/{tr,en}.json`.

---

## 2. Review Findings and Fixes Applied

During the Session 07 close-out review, three issues were identified and fixed:

1. **`reconcile_publish` lost `recreations` count and cap check when reconciling an `EXPIRED` or retryable-`ERROR` Reel container (`backend/app/operations/publish.py:1701-1715`, `backend/app/operations/publish.py:1062-1074`)**:
   - *Finding*: In `_conclude`, `if status_code not in ("FINISHED", "IN_PROGRESS"):` stripped `container_id` from `op.provider_ref` before building `reconciled_status` for a Reel whose container was `EXPIRED` or had a retryable processing subcode (`SUBCODE_2207003`, `SUBCODE_2207032`, `SUBCODE_2207053`). That caused `_drive_reel` to see `prepared.container_id is None` and create a replacement container without passing through `_reel_step`'s recreation counter or enforcing `MAX_CONTAINER_RECREATIONS` (`2`). In addition, when `_store_reel_processing` enqueued a fresh `poll_reel_container` job with `enqueue_poll=True`, any stale `queued` job with the same `dedup_key` kept its old `run_at`.
   - *Fix*: Updated `_conclude` in `backend/app/operations/publish.py` to check `reel_recreate` against `MAX_CONTAINER_RECREATIONS` (failing immediately with `PROVIDER_UNAVAILABLE` once `recreations >= MAX_CONTAINER_RECREATIONS`), preserve `container_id` on `op.provider_ref` for `is_reel` so `reconciled_status` flows into `_drive_reel -> _reel_step` (which increments `recreations` and replaces the container), and call `cancel_queued(session, f"poll_reel:{op.id}", env.clock)` before `enqueue(...)` in `_store_reel_processing`. Added integration test `test_reconcile_reel_retryable_error_increments_recreations_and_enforces_cap` in `backend/tests/integration/content/test_reel_publish.py`.
2. **`ReelMedia.tsx` range slider upper bound, `aria-valuetext`, byte progress display, and no-op PATCH guard (`frontend/src/features/content/ReelMedia.tsx:60-68, 134-169, 281-306, 329-346`)**:
   - *Finding*: (a) `maxDurationMs` allowed selecting `thumb_offset_ms == duration_ms`, whereas backend validation (`backend/app/content/validation.py:251`) enforces `0 <= offset < duration_ms` (strict `<`); (b) the frame scrubber `<input type="range">` was missing `aria-valuetext`; (c) `applyThumbOffset` and `toggleShareToFeed` sent a `PATCH` even when the value was unchanged; and (d) the upload progress status showed only the percentage without the `loaded / total` MB progress.
   - *Fix*: Clamped the scrubber maximum `maxOffsetMs` to `Math.max(0, rawDurationMs - 100)`, added `aria-valuetext={formatVideoTime(effectiveMs, true)}`, added early return guards in `applyThumbOffset` and `toggleShareToFeed` when the value is unchanged, and displayed `loaded MB / total MB` alongside the percentage during XHR video uploads. Added assertions in `frontend/src/features/content/reel.test.tsx`.
3. **Documentation alignment (`docs/architecture/background-jobs.md:132`, `docs/product/mvp-scope.md:88-90`, `docs/architecture/observability.md:131`, `docs/architecture/data-model.md:531,550`)**:
   - *Finding*: `background-jobs.md` listed `poll_reel_container` max attempts as `5` instead of `8` (matching `backend/app/operations/jobs.py:229`); `mvp-scope.md` line 90 still said `"Reels publishing, content type and UI remain Session 07"` while line 95 marked Sessions 06 & 07 implemented; `observability.md` §4.2 omitted `publish_reel` from `CAPABILITY_MISSING`; and `data-model.md` §3.6/§3.7 omitted `(workspace_id, cover_media_asset_id)` from the `content_items` composite FK list and the Reel `provider_ref` keys from `operations`.
   - *Fix*: Updated all four files to match the implemented contracts.

---

## 3. Acceptance Criteria Verification

| Criterion | Status | Proving Tests |
|---|---|---|
| Migration `0083` applies cleanly, enforces check constraints & composite tenant FK on `cover_media_asset_id`, and refuses downgrade when Reel rows exist | Pass | `tests/integration/content/test_reel_migration.py` |
| Creating and patching `reel` items (`media_asset_id`, `cover_media_asset_id`, `thumb_offset_ms`, `share_to_feed`), mutual exclusivity of cover image and frame offset, non-reel rejection, version increment only on payload changes | Pass | `tests/integration/content/test_reel.py`, `tests/unit/content/test_payload.py`, `tests/unit/content/test_validation.py` |
| Approval payload hash binds video `sha256`, cover ID & `sha256`, `thumb_offset_ms`, `share_to_feed`, and `caption`; any mutation invalidates approval; caption fact change puts scheduled Reel `on_hold (FACT_CHANGED)` | Pass | `tests/integration/content/test_reel.py`, `tests/unit/content/test_payload.py` |
| AI generation, regeneration, template creation, and template re-render refuse `reel` with `422 CONTENT_TYPE_NOT_SUPPORTED`; agent draft tool excludes `reel` | Pass | `tests/integration/content/test_reel.py` |
| `execute_publish` creates `REELS` container, commits T2 (`phase="processing"`, `container_id`) and enqueues `poll_reel_container` without sleeping in-process | Pass | `tests/integration/content/test_reel_publish.py`, `tests/integration/content/test_reel_publish_crash_commits.py` |
| `poll_reel_container` follows `REEL_POLL_SCHEDULE` via `RescheduleJob`, publishes once on `FINISHED`, finalises without re-publishing on `PUBLISHED`, recreates up to 2 times on `EXPIRED` / retryable subcodes, fails on permanent `ERROR` or `REEL_PROCESSING_TIMEOUT` (30 min), and tolerates up to 4 read failures before operation retry | Pass | `tests/unit/operations/test_reel_poll_schedule.py`, `tests/integration/content/test_reel_publish.py` |
| Crash safety (after create before T2, after T2 before first poll, after `publish_container` before T3), concurrent poll idempotency, and restore/reconcile recreation cap enforcement | Pass | `tests/integration/content/test_reel_publish_crash_commits.py`, `tests/integration/content/test_reel_publish.py` |
| `MetaInstagramProvider` and `MockInstagramProvider` contract parity for `REELS` (`video_url`, `cover_url` vs `thumb_offset_ms`, `share_to_feed`, processing subcodes, HTTPS validation) | Pass | `tests/unit/integrations/test_meta_provider.py`, `tests/contract/test_instagram_provider_contract.py` |
| Tenant isolation (cross-workspace video or cover asset rejected; cross-workspace endpoints return `404`) and orphan/retention cleanup protection for `cover_media_asset_id` | Pass | `tests/isolation/test_reel_isolation.py`, `tests/integration/content/test_reel.py` |
| Frontend Reel composer, XHR video upload progress/cancel, `<video>` player & frame scrubber (`aria-valuetext`, no-op PATCH guard), custom JPEG cover upload, `share_to_feed` toggle, fact-check disclosure, processing status panel, and TR/EN i18n parity | Pass | `frontend/src/features/content/reel.test.tsx` |

---

## 4. Test & Static Check Results

| Check | Command | Result |
|---|---|---|
| Ruff lint | `uv run ruff check app tests evals migrations` | Pass (`All checks passed!`) |
| Ruff format | `uv run ruff format --check app tests evals migrations` | Pass (`849 files already formatted`) |
| Mypy | `uv run mypy app` | Pass (`Success: no issues found in 442 source files`) |
| Import linter | `uv run lint-imports` | Pass (`25 kept, 0 broken`) |
| Backend unit tests | `pytest tests/unit -q -p no:cacheprovider` | `2301 passed, 1 skipped, 1 known env failure` (`test_cli_migration_status_head_only_and_check_config`, `.env` `DEMO_TOOLS_ENABLED=true`) |
| Backend contract, security & isolation tests | `pytest tests/contract tests/security tests/isolation -q -p no:cacheprovider` | Pass (`261 passed, 18 skipped, 0 failed`) |
| Backend content & operations integration tests | `pytest tests/integration/content tests/integration/operations -q -p no:cacheprovider` | Pass (`530 passed, 1 skipped, 0 failed`) |
| Frontend ESLint | `npm.cmd run lint` | Pass (0 errors, 0 warnings) |
| Frontend TypeScript | `npm.cmd run typecheck` | Pass (0 errors) |
| Frontend i18n check | `npm.cmd run i18n:check` | Pass (`2896 keys`, `2075 literal t() calls verified`) |
| Frontend Vite build | `npm.cmd run build` | Pass (`388 modules transformed`, built in `1.79s`) |
| Frontend Vitest suite | `npm.cmd test` | Pass (`67 test files, 939 tests passed, 0 failed`) |

---

## 5. Manual Demo Steps (Simulated Mode)

With the API, worker (`uv run python -m app.worker`), and frontend (`npm.cmd run dev`) running in simulated mode (`INSTAGRAM_ENABLED_PROVIDERS=mock`, `MEDIA_STORAGE_BACKEND=local`, `DEMO_TOOLS_ENABLED=true`):

1. **Create a Reel draft:** Open **Content** → **New draft**, select **Reels / Reel** (note that AI generation and template cards are disabled with an explanation), enter a title, and click **Blank draft**.
2. **Upload a video:** Choose an `.mp4` or `.mov` clip (`3–90 s`, H.264/HEVC). Observe the determinate upload progress bar (`%` and `MB / MB`), the `"Probing…"` transition at 100%, the inline `<video>` preview with duration badge, and any non-blocking aspect-ratio or resolution advisories.
3. **Choose a cover and feed-grid preference:** Drag the frame scrubber slider to seek the `<video>` preview and click **Use this frame** (or upload a custom JPEG cover via **Upload JPEG cover**, or reset with **Use first frame**). Toggle **Also share to profile feed** as desired.
4. **Caption grounding and submission:** Write a caption quoting a verified gym price (or a mismatched price to see the claim validator block submission, while the disclosure note explains that video/audio tracks are not automatically fact-checked). Submit and approve the Reel.
5. **Asynchronous container processing and publish:** Observe the status panel display **"Instagram is processing this Reel…"** with the next status-check timestamp while `poll_reel_container` polls the simulated `REELS` container, followed by automatic transition to **Published** with a simulated `/reel/SIM.../` permalink. Use the dev failure simulator (`create_reel_container`, `slow_processing`, or `processing_error`) to observe container recreation or timeout handling.

---

## 6. Deviations, Limitations, and Live Items Pending

- **No deviations** from the Session 07 specification after the review fixes in §2.
- **Live Meta Reels verification pending (Gate 2 / Phase 7 live checklist):**
  - Real `POST /{ig-user-id}/media` with `media_type=REELS`, presigned S3 `video_url` and `cover_url`, `thumb_offset` in milliseconds, and `share_to_feed` against a founder/tester Instagram Professional account under Instagram Login (`graph.instagram.com`).
  - Empirical measurement of Meta's real-world Reel transcoding latency distribution and error subcode payload shapes on `GET /{ig-container-id}?fields=status,status_code`.
- **Host dependency for deployment:** `ffmpeg` and `ffprobe` must be installed on the API and worker hosts (or container image) whenever `VIDEO_PROBE_BACKEND=ffprobe` (or `auto` in non-test environments) is active.
