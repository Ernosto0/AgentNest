# Feature Phase 5 (Track B) Close-Out Summary: Carousels and Reels (F-08)

- **Phase & Track:** Feature Phase 5, Track B — F-08 Carousels and Reels (Sessions 04 to 07)
- **Specification:** [features-phase-5-on-demand/sessions.md](../features-phase-5-on-demand/sessions.md), source [pre-launch-feature-recommendations.md](../../review/pre-launch-feature-recommendations.md) §3 F-08 and [ADR-028](../../architecture/decisions/ADR-028-video-media-probing-and-storage.md)
- **Sessions executed:** 04 to 07. Reports in [features-phase-5-on-demand/](../features-phase-5-on-demand/): [s04](../features-phase-5-on-demand/s04-report.md), [s05](../features-phase-5-on-demand/s05-report.md), [s06](../features-phase-5-on-demand/s06-report.md), [s07](../features-phase-5-on-demand/s07-report.md)
- **Baseline Git commit:** `1a58d41` (`main`). **Nothing is committed**: Sessions 04 to 07 are uncommitted in the merged Feature Phase 5 worktree. (The other tracks: Track A Sessions 01–03, Track C Sessions 08–09, Track D Sessions 10–11, Track E Session 12.)
- **Alembic migration head (Track B):** `0083` (`20261118_0083_reels.py`; chain `0071 -> 0080 -> 0081 -> 0082 -> 0083`, Track B allocation `0080–0089`).
- **Status:** **Implemented and verified offline. Stopped for review.** Nothing was run against live Instagram Graph API, live S3, a real LLM provider, or a physical mobile device.
- **Date:** 2026-11-18

---

## 1. Executive summary

Small-business owners can now prepare, approve, schedule, and publish **multi-image feed carousels** (`2–10` JPEG images) and **Instagram Reels** (`3–90 s` MP4/MOV video with custom cover or frame offset and feed-grid sharing) through the same safety architecture as single-image posts and stories:

- **Approval hash binding (INV-05):** For a carousel, the ordered tuple of child `media_asset_id`s and their `sha256` digests is hashed into `ContentApprovalPayload`. For a Reel, the video `sha256`, optional custom cover `media_asset_id` and `sha256`, `thumb_offset_ms`, `share_to_feed`, and `caption` are all bound into `ContentApprovalPayload`. Adding, removing, reordering, or replacing media, cover, offset, feed-sharing flag, or caption increments `version` and invalidates any existing approval.
- **Fact grounding and price-change holds (INV-02 / INV-13):** Carousel and Reel captions run through the claim validator (`validate_claims`), and template-rendered carousel slides contribute their `template_render.fact_versions` to `fact_references`, so a price change holds any scheduled or approved carousel or Reel (`on_hold`, `FACT_CHANGED`). Reel editors display an explicit disclosure that video and audio tracks themselves are not automatically fact-checked against Business Knowledge.
- **Crash-safe external operations ledger (INV-06 / INV-15):** Carousel publishing commits every created child container ID in `operations.provider_ref.children` and the parent `CAROUSEL` container ID before calling `media_publish`. Reel publishing creates the `REELS` container, commits `provider_ref` (`container_id`, `phase="processing"`) in T2, and hands status checks to the asynchronous `poll_reel_container` job (`RescheduleJob` along `15, 30, 60, 60, 120, 120, 180, 180, 300 s`, up to 30 min) without ever sleeping inside a worker thread.

---

## 2. What changed, by session

### 2.1 Session 04 — Carousel data model, validation, approval hash, and price-change hold
- **Migration `0080` (`20261118_0080_feed_carousel.py`):** Creates `content_item_media` (`id`, `workspace_id`, `content_item_id`, `media_asset_id`, `position`, `created_at`) with `ENABLE` + `FORCE ROW LEVEL SECURITY` (`tenant_isolation_policy`), composite tenant FKs (`ON DELETE CASCADE` to `content_items`, `ON DELETE NO ACTION` to `media_assets`), `DEFERRABLE INITIALLY DEFERRED` unique `(content_item_id, position)`, unique `(content_item_id, media_asset_id)`, check `0 <= position < 20`, and widens `ck_content_items_content_type` to include `'feed_carousel'`.
- **Domain rules (`content/carousel.py`, `validation.py`, `payload.py`, `service.py`):**
  - Drafts hold `0..10` ready JPEG images (`content_items.media_asset_id` is always `NULL` on `feed_carousel`); submission requires `2..10` (`CAROUSEL_MIN_ITEMS = 2`, `CAROUSEL_MAX_ITEMS = 10`).
  - Each slide obeys feed dimensions and aspect ratio (`4:5..1.91:1`) and must stay within `2%` (`CAROUSEL_ASPECT_TOLERANCE = 0.02`) of the first slide's aspect ratio (`CAROUSEL_MIXED_ASPECT_RATIO`).
  - Ordered `carousel_media_asset_ids` and `carousel_media_sha256s` join `ContentApprovalPayload`.
  - `replace_fact_references` unions caption-referenced facts with every template-rendered slide's `fact_versions`, so changing a fact holds the whole carousel.
  - `media_cleanup.py` protects child `content_item_media.media_asset_id` rows from orphan deletion and applies the 90-day post-publication retention rule.

### 2.2 Session 05 — Carousel publishing through the operations ledger and carousel UI
- **Migration `0081` (`20261118_0081_carousel_simulator.py`):** Widens `sim_containers.media_type` to include `'CAROUSEL'`, makes `sim_containers.media_url` nullable, adds `is_carousel_item BOOLEAN NOT NULL DEFAULT false` and `children JSONB NULL` to `sim_containers`, and widens `sim_failure_rules.operation` to include `'create_carousel_item'` and `'create_carousel_container'`.
- **Provider & ledger (`integrations/instagram/{base,meta,mock}.py`, `operations/publish.py`):**
  - `ContainerSpec` supports `is_carousel_item=True` on `IMAGE` child containers and `media_type="CAROUSEL"` with `children: tuple[str, ...]`.
  - `_drive_carousel` creates missing child containers one by one (committing each child ID in `op.provider_ref["children"]` immediately), polls children within a shared 5-minute budget, creates and commits the parent `CAROUSEL` container, polls it to `FINISHED`, and calls `publish_container` once.
  - `reconcile_publish` checks the parent container first (`PUBLISHED` finalises without re-publishing; `FINISHED` publishes once; `EXPIRED` or no parent reuses surviving children stored in `provider_ref.children`).
- **Frontend (`CarouselMedia.tsx`, `carousel.ts`, `ContentEditor.tsx`, `PostPreview.tsx`, `ContentCard.tsx`):**
  - Multi-file upload queue, keyboard-accessible slide reordering (`Move left` / `Move right`), removal, template-slide insertion ("Add price card"), slide switcher in `PostPreview`, and `1/N` count badge on library cards.

### 2.3 Session 06 — Video upload, ffprobe/ffmpeg validation, private storage, and thumbnail extraction
- **ADR-028 & Migration `0082` (`20261118_0082_video_media.py`):**
  - Records [ADR-028](../../architecture/decisions/ADR-028-video-media-probing-and-storage.md): stream-to-temp before probe, subprocess `ffprobe`/`ffmpeg` with argument arrays (`shell=False`), no server-side transcoding, Range-enabled private streaming, and signed capability URLs for local Meta fetches.
  - Adds `duration_ms INTEGER NULL`, `video_codec TEXT NULL`, `audio_codec TEXT NULL`, `frame_rate NUMERIC(7,3) NULL`, `bitrate_bps BIGINT NULL`, `container TEXT NULL`, `thumbnail_media_asset_id UUID NULL`, and `video_warnings JSONB NULL` to `media_assets`, plus `ck_media_assets_kind` (`'image', 'video', 'video_thumbnail'`), `ck_media_assets_video_fields`, and composite FK `(workspace_id, thumbnail_media_asset_id)` to `media_assets(workspace_id, id)`.
- **Video adapter & storage (`integrations/video/`, `integrations/storage/`, `content/media.py`, `content/video_limits.py`):**
  - Enforces import-linter contract `Video adapters import only core` (`app.integrations.video` -> `app.core` only).
  - Validates ISO BMFF (`ftyp` box at offset 4 with MP4/QuickTime brands), single video stream (`h264`/`hevc`, progressive, `1..60 fps`, `<= 1920 px` width, `<= 25 Mbps`, non-rotated `3:16..16:9`), optional audio (`aac`, `1..2` channels, `<= 320 kbps`), and duration `3,000..90,000 ms`, plus non-blocking warnings (`ASPECT_NOT_9_16`, `RESOLUTION_BELOW_RECOMMENDED`, `EDIT_LIST_PRESENT`).
  - Extracts a deterministic baseline sRGB JPEG thumbnail (`1080x1920` max) stored under `{workspace_id}/{asset_id}.thumb.jpg` and cleaned up together with the video.
  - Adds `POST /media/video`, `GET /media/{id}/thumbnail`, `GET /media/{id}/content` (HTTP `206 Partial Content` for `Range: bytes=start-end`), and public HMAC-SHA256 signed capability URL `GET /api/v1/public/media/{token}` for local storage mode.

### 2.4 Session 07 — Reels publishing, `reel` content type, Reel UI, and Track B close-out
- **Migration `0083` (`20261118_0083_reels.py`):** Widens `ck_content_items_content_type` to include `'reel'`, adds `cover_media_asset_id` (with composite tenant FK), `thumb_offset_ms`, and `share_to_feed` (with mutual-exclusivity and non-negative checks) to `content_items`, and adds `REELS` container and failure-injection columns/constraints to `sim_containers` and `sim_failure_rules`.
- **Content & approval binding (`content/validation.py`, `payload.py`, `service.py`, `views.py`):**
  - Validates primary `kind="video"` asset, optional custom JPEG cover (`cover_media_asset_id`, `4:5..9:16`, `<= 8 MB`) or `thumb_offset_ms` (`0 <= offset < duration_ms`), caption claim grounding, and account capability `publish_reel`.
  - Binds video `sha256`, cover ID & `sha256`, `thumb_offset_ms`, `share_to_feed`, and `caption` into `ContentApprovalPayload`.
  - Refuses AI generation and template rendering for `reel` (`422 CONTENT_TYPE_NOT_SUPPORTED`).
- **Asynchronous Reel publishing (`operations/publish.py`, `jobs.py`, `backup_restore.py`):**
  - `execute_publish` creates the `REELS` container, commits `phase="processing"` in T2, and enqueues `poll_reel_container` (`max_attempts = 8`, `dedup_key = f"poll_reel:{op.id}"`) without sleeping.
  - `poll_reel_container` reschedules along `REEL_POLL_SCHEDULE` (`15, 30, 60, 60, 120, 120, 180, 180, 300 s`) via `RescheduleJob` until `REEL_PROCESSING_TIMEOUT` (30 min), recreates up to `MAX_CONTAINER_RECREATIONS = 2` times on `EXPIRED` or retryable subcodes (`2207003`, `2207032`, `2207053`), tolerates up to 4 status read errors before operation retry, publishes once on `FINISHED`, and fences to `outcome_unknown` + `reconcile_publish` on worker death or backup restore.
- **Frontend (`ReelMedia.tsx`, `reel.ts`, `ContentComposer.tsx`, `ContentStatusPanel.tsx`):**
  - Reel composer option (blank draft only), XHR video upload with determinate progress (`%` and `MB / MB`) and cancel, `<video>` player with Range streaming and poster preview, frame scrubber (`step=100`, `aria-valuetext`, no-op PATCH guard), custom JPEG cover upload, `share_to_feed` toggle, fact-check disclosure note, and `"Instagram is processing this Reel…"` status panel.

---

## 3. Tests proving each acceptance criterion

| Criterion | Proving tests |
|---|---|
| S04: migration `0080` schema, RLS, deferred position uniqueness, and downgrade guard | `tests/integration/content/test_carousel_migration.py` |
| S04: carousel creation, `2..10` image limit, `2%` shared aspect ratio, order binding into approval hash, template slide fact-change hold, orphan/retention cleanup | `tests/integration/content/test_carousel.py`, `tests/unit/content/test_validation.py`, `tests/unit/content/test_payload.py` |
| S04: tenant isolation on `content_item_media` and carousel endpoints | `tests/isolation/test_carousel_isolation.py` |
| S05: migration `0081` simulator schema and downgrade guard | `tests/integration/content/test_carousel_migration.py` |
| S05: carousel ledger publishing (per-child commits, parent commit, single `publish_container`, crash recovery, child/parent expiration recreation cap, quota/rate-limit/auth handling) | `tests/integration/content/test_carousel_publish.py`, `tests/integration/content/test_carousel_publish_crash_commits.py` |
| S05: Meta and Mock provider contract for `is_carousel_item` and `CAROUSEL` containers | `tests/unit/integrations/test_meta_provider.py`, `tests/contract/test_instagram_provider_contract.py` |
| S05: frontend carousel uploader, reordering, preview slide switcher, library count badge, TR/EN i18n | `frontend/src/features/content/carousel.test.tsx` |
| S06: migration `0082` video columns/constraints and downgrade guard | `tests/integration/content/test_video_media_migration.py` |
| S06: ISO BMFF signature check, pure `validate_video_metadata` rules, subprocess `ffprobe`/`ffmpeg` argument safety & output caps | `tests/unit/content/test_video_rules.py`, `tests/unit/integrations/test_ffmpeg_prober.py`, `tests/unit/integrations/test_fake_video_prober.py` |
| S06: `POST /media/video`, thumbnail extraction, HTTP `206` Range streaming, signed public fetch token & SSRF/path-traversal resistance, cleanup of video + thumbnail | `tests/integration/content/test_video_upload.py`, `tests/unit/integrations/test_media_storage.py`, `tests/isolation/test_video_isolation.py` |
| S07: migration `0083` schema, constraints, composite FK, and downgrade guard | `tests/integration/content/test_reel_migration.py` |
| S07: `reel` CRUD, cover vs `thumb_offset_ms` exclusivity, `share_to_feed`, approval payload hash binding, caption fact-change hold, AI/template refusal (`422 CONTENT_TYPE_NOT_SUPPORTED`), cover cleanup protection | `tests/integration/content/test_reel.py`, `tests/unit/content/test_payload.py`, `tests/unit/content/test_validation.py` |
| S07: non-blocking `execute_publish` -> `poll_reel_container` lifecycle, `REEL_POLL_SCHEDULE`, retryable subcodes & recreation cap, read-failure tolerance, `REEL_PROCESSING_TIMEOUT`, crash/restore safety, concurrent poll idempotency | `tests/unit/operations/test_reel_poll_schedule.py`, `tests/integration/content/test_reel_publish.py`, `tests/integration/content/test_reel_publish_crash_commits.py` |
| S07: Meta and Mock provider contract for `REELS` (`video_url`, `cover_url`, `thumb_offset`, `share_to_feed`, subcodes) and tenant isolation | `tests/unit/integrations/test_meta_provider.py`, `tests/contract/test_instagram_provider_contract.py`, `tests/isolation/test_reel_isolation.py` |
| S07: frontend Reel composer, XHR upload progress/cancel, `<video>` scrubber, cover upload, `share_to_feed`, disclosure note, processing status panel, TR/EN i18n | `frontend/src/features/content/reel.test.tsx` |

---

## 4. Verification results at Track B close-out

| Check | Result |
|---|---|
| `ruff check app tests evals migrations` | Pass (`All checks passed!`) |
| `ruff format --check app tests evals migrations` | Pass (`849 files already formatted`) |
| `mypy app` | Pass (`Success: no issues found in 442 source files`) |
| `lint-imports` | Pass (`25 kept, 0 broken`, including `Video adapters import only core`) |
| Backend `pytest` (`unit`, `contract`, `security`, `isolation`, `integration/content`, `integration/operations`) | `3092 passed, 20 skipped, 1 known baseline env failure` (`test_cli_migration_status_head_only_and_check_config` with `DEMO_TOOLS_ENABLED=true`; `0` Track B failures) |
| Frontend `lint`, `typecheck`, `i18n:check` (`2896 keys`), `build` | Pass (`0` errors, `388` modules transformed) |
| Frontend `npm.cmd test` | Pass (`67` test files, `939` tests passed, `0` failed) |

---

## 5. Deviations, limitations, and live items pending

1. **No server-side video transcoding (by design, ADR-028):** Non-conforming videos (unsupported codec, container, frame rate, bitrate, duration, or rotation) are rejected at upload with actionable TR/EN error messages rather than transcoded on the server.
2. **No automatic fact-checking of video frames or audio tracks:** Only the text caption of a Reel is checked against Business Knowledge (`validate_claims`), and the Reel editor displays a persistent disclosure note explaining this boundary.
3. **Live Meta Graph API verification pending (Gate 2 / Phase 7 live checklist):**
   - Live carousel publishing (`is_carousel_item=true` children + `media_type=CAROUSEL` parent + `media_publish`) against a real Instagram Professional account under Instagram Login (`graph.instagram.com`).
   - Live Reel publishing (`media_type=REELS` with presigned S3 `video_url` and `cover_url`, `thumb_offset` in milliseconds, `share_to_feed`, and real container transcoding status polling) against a real Instagram Professional account.
4. **Host dependency:** Production and staging images running `VIDEO_PROBE_BACKEND=ffprobe` (or `auto`) must provide `ffmpeg` and `ffprobe` on `PATH`.
5. **Working tree:** All changes from Sessions 04 to 07 are uncommitted in this worktree for coordinator review and merge.
