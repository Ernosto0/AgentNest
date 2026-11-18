# Feature Phase 5, Session 06: video upload, validation and storage for Reels (Track B)

**Status:** Done offline (backend, tests, docs, minimal frontend, OpenAPI). Anything needing a real `ffprobe`/`ffmpeg`, Docker, Caddy or Meta is **pending** (see "Live items"). Nothing was committed.
**Baseline:** `1a58d41` plus the uncommitted work of Sessions 04 and 05. **Migration:** `0082`, `down_revision = "0081"`.
**Trigger:** see `s04-report.md` (Track B moved out of Deferred on 2026-11-18 at the owner's request; pilot demand evidence not yet recorded).
**Scope kept:** no `reel` content type, no publishing, no Reels UI, no player, no HTTP Range support (all Session 07). No transcoding.

## What was delivered

### Video prober (`backend/app/integrations/video/`)

- `base.py`: `VideoFacts` (frozen), the `VideoProber` protocol, `VideoProbeFailed(reason)` (a rejection) and `VideoProbeUnavailable` (retryable, never a rejection and never a silent accept).
- `mp4_boxes.py`: own bounded, seek-based ISO BMFF scanner (32/64-bit sizes, `size == 0`, at most 256 top-level boxes, 4096 nested boxes, depth 4, at most 32 MiB of `moov`, every size validated against the file). Gives major brand (`qt  ` = MOV; 3GP/3G2/M4A/MJ2 refused), `moov_first` and edit-list presence.
- `ffmpeg.py` (`FfmpegVideoProber`): argument lists only, no shell, `stdin=DEVNULL`, environment reduced to `PATH` and `LC_ALL=C`, private scratch directory, stdout/stderr to files (not pipes), `-protocol_whitelist file`, forced demuxer (`-f mov`, the ffmpeg 5.1 alias of the `mov,mp4,m4a,3gp,3g2,mj2` demuxer), wall-clock timeout with process-group kill, POSIX `setrlimit` (CPU, address space, file size, open files, no core), a process-wide `BoundedSemaphore` (`VIDEO_PROBE_MAX_CONCURRENCY`, 3 s wait, then retryable 503). Defensive JSON parsing (rotation swaps width and height, `0/0` frame rate falls back to `r_frame_rate`, `attached_pic` ignored, missing bitrate derived from size and duration, the worst audio stream decides). Thumbnail: one frame, `-map 0:V:0`, retry at 0 ms.
- `fake.py` (`FakeVideoProber`, test header `FAKEVIDEO1 {json}`) and `registry.py` (`VIDEO_PROBER=fake` is refused in production by the registry and by `check-config --production`).
- Settings (`core/config.py`, `.env.example`, `environment-variables.md`): `VIDEO_PROBER`, `VIDEO_FFPROBE_PATH`, `VIDEO_FFMPEG_PATH`, `VIDEO_PROBE_TIMEOUT_SECONDS`, `VIDEO_THUMBNAIL_TIMEOUT_SECONDS`, `VIDEO_PROBE_MAX_CONCURRENCY`, `MEDIA_MAX_VIDEO_BYTES`, `MEDIA_VIDEO_WORKSPACE_QUOTA_BYTES`, `MEDIA_SCRATCH_DIR`. New import-linter contract "Video adapters import only core".

### Pure rules (`backend/app/content/video.py`)

Named constants and a `VideoLimits` dataclass; `validate_video()` returns all issues (the first is primary) and warnings. 21 rejection codes, 3 non-blocking warnings (`EDIT_LIST_PRESENT`, `ASPECT_NOT_9_16`, `RESOLUTION_BELOW_RECOMMENDED`). Values and sources are in `docs/research/platform-capabilities.md` ("Reel video specification") and ADR-028: MP4/MOV, 3 s to 900 s, H.264/HEVC, one video stream, progressive 4:2:0, 23 to 60 fps (0.05 tolerance), displayed width at most 1920, both sides at least 64, aspect 0.1 to 10, at most 25 Mbps, optional AAC audio at most 48 kHz mono or stereo, `moov` before `mdat`, 300 000 000 bytes. Edit lists are a warning (`REJECT_EDIT_LISTS = False`), because iPhone/QuickTime files commonly have one; Meta's "no edit lists" text is therefore deliberately not enforced (unverified live).

### Data model (migration `0082`)

On `media_assets` (no new table, so RLS and the table counts are unchanged): `kind` (`image` default, `video`, `video_thumbnail`), `duration_ms`, `video_codec`, `audio_codec`, `frame_rate`, `bitrate_bps`, `container`, `video_warnings` (jsonb), `thumbnail_media_asset_id` with a composite FK `(workspace_id, thumbnail_media_asset_id)` to `media_assets(workspace_id, id)`; checks `ck_media_assets_kind` and `ck_media_assets_video_fields`; index `(workspace_id, kind)`. The downgrade raises while any non-image asset exists. Storage keys accept `mp4` and `mov`.

### Upload and ingest (`content/router.py`, `content/video_ingest.py`)

- `POST /workspaces/{id}/media/video` (`content.edit`, CSRF as for images; 201 `MediaAssetOut`). The image endpoint stays image-only. `GET /workspaces/{id}/media/{media_id}` returns metadata for every ready kind; `/content` serves every kind (404 for foreign or deleted).
- Order: auth, then header guards before any body byte (413 `VIDEO_TOO_LARGE` over 300 000 000 + 64 KiB or without a usable Content-Length, 409 `VIDEO_STORAGE_QUOTA_EXCEEDED`), then copy in 1 MiB chunks to a private 0600 temp file counting bytes and SHA-256 (abort at limit + 1), then probe, validate, thumbnail (re-encoded by `process_image` as baseline sRGB JPEG), storage `put` of video then thumbnail, then one transaction (quota re-checked under a workspace row lock, thumbnail row, video row, audit `media.uploaded`). Any failure after a `put` rolls back and deletes both objects. Rejections write `media.rejected` and leave no row and no object. No DB transaction is open during probing, storage I/O or previews.
- Video bytes are stored as uploaded (no transcoding, no metadata stripping; see limitations).
- Typed errors with TR and EN `what`/`next`: `VIDEO_INVALID` (422, `params.reason` and `params.reasons[{code,limit,actual}]`), `VIDEO_TOO_LARGE` (413), `VIDEO_STORAGE_QUOTA_EXCEEDED` (409), `VIDEO_PROBE_UNAVAILABLE` (503, retryable), `MEDIA_KIND_INVALID` (422). Per-reason texts under `content.media.videoReason.*` in the backend catalogs and the frontend locales.
- `S3MediaStorage.open` now streams (`_StreamingReader`) instead of buffering the object.

### Image-only callers

`media.get_asset(..., kind="image")` is the default, so a same-workspace video or thumbnail id used for `feed_image`/`story_image` media, carousel items, brand logo, template logo and the agent attach tool is refused (`MEDIA_KIND_INVALID` in the API, a typed refusal in the agent tool; foreign or unknown ids stay 404 and nothing is written). The service `_check`, carousel assets, template render records, story lookups, `media_deleted`, agent listings and counts, owner-task selection and the publish path (via `ordered_assets`) all filter `kind = 'image'`. Telegram ingest is image-only by construction (`media.ingest`).

### Retention (`content/media_cleanup.py`)

Videos follow the existing orphan (7 days) and published-only (90 days) rules; until Session 07 nothing references a video, so every uploaded video is orphan-eligible. A thumbnail is never eligible while its parent video is not deleted; it becomes eligible when the parent is deleted or missing and it is older than the orphan window. `run_media_cleanup` runs parents first, then thumbnails, in separate passes; both files are removed between transactions, and a crash between the two is finished by the next run (tested). The logo rule and the carousel-item reference (`content_item_media`) are respected.

### Deployment

Root `Dockerfile` backend stage installs Debian `ffmpeg` pinned by `ARG FFMPEG_DEBIAN_VERSION=7:5.1.9-0+deb12u1` (`--no-install-recommends`, lists cleaned, `dpkg-query` version check, before `USER agentnest`). `Caddyfile`: the 10 MB body limit now applies to everything except `/api/v1/workspaces/*/media/video`, which gets 310 MB. CI backend job installs `ffmpeg` so the real-binary test runs there. Docs: platform-capabilities (spec, sources, conflicts), ADR-028 (new) and the ADR-015 addendum, data-model, api-design, integrations, observability, security-and-privacy, deployment, runbook, local-development, environment-variables, troubleshooting, mvp-scope, pricing (derived, not measured storage cost).

### Frontend (minimal)

`mediaPreviewId()` helper (a video previews through its thumbnail, a thumbnail or unknown kind never enters the image-blob cache) used by the media preview paths, `video` and thumbnail fields in the media types, `content.media.videoReason.*` in both locales, `openapi.json` and `schema.d.ts` patched by hand. No upload UI, no player.

## Tests and checks (re-run by the reviewer, 2026-11-18)

Backend, from `backend/`:

- `uv run ruff check app tests evals migrations`: pass. `uv run ruff format --check app tests evals migrations`: pass (842 files). `uv run mypy app`: pass (441 files). `uv run lint-imports`: pass (25 contracts kept, 0 broken).
- `uv run pytest tests/unit tests/contract tests/security tests/isolation tests/integration/content tests/integration/operations -q -p no:cacheprovider`: **3035 passed, 20 skipped, 2 failed** (17 min). Both failures are environmental and known: `test_cli_migration_status_head_only_and_check_config` (the worktree `.env` sets `DEMO_TOOLS_ENABLED=true`) and `test_invite_secrets::...never_logged...` (passes, 2 passed, when run alone with `SENTRY_DSN=`). The 20 skips are live Meta/Telegram probes, one POSIX-rlimit test and the real-ffprobe test (no binaries here).
- After the reviewer's router change: `test_video_upload.py`, `test_video_isolation.py`, `test_video_agent_tools.py`, `test_media_upload.py`: 73 passed.
- Not run: the other `tests/integration` directories (full suite over an hour); the `alembic downgrade 0081 && upgrade head` CLI round trip (the worktree `.env` `DATABASE_URL` is not an `agentnest_p5b*` database); the round trip is covered by `test_video_media_migration.py` against the test DB.

Frontend, from `frontend/` (PowerShell): `npm.cmd run lint` pass; `npm.cmd run typecheck` pass; `npm.cmd test` 66 files, 925 tests passed; `npm.cmd run i18n:check` pass (2849 keys); `npm.cmd run build` pass.

New test files: `tests/unit/content/test_video_rules.py`, `tests/unit/integrations/{test_mp4_boxes,test_ffmpeg_prober,test_fake_video_prober}.py`, `tests/unit/core/test_video_config.py`, `tests/integration/content/{test_video_upload,test_video_agent_tools,test_video_media_migration,test_video_real_ffprobe}.py`, `tests/isolation/test_video_isolation.py`, `tests/helpers/videos.py`, frontend `mediaPreview.test.tsx`; extended: storage, packaging (pin, Caddy), RLS, media cleanup and upload tests.

## Review changes (made by the reviewer)

- Missing or invalid `Content-Length` (a chunked body) is now refused with 413 before the body is read. The specification said to rely on the byte counter, but Starlette spools the entire multipart body to disk before the endpoint runs, so a chunked upload would have bypassed the app limit entirely (only Caddy's 310 MB envelope would have stopped it). New test `test_chunked_body_without_content_length_is_refused_before_reading`; api-design and ADR-028 updated.
- The header guards (quota SELECT, commit, rejection audit) ran directly on the event loop in the `async` route; they now run in the thread pool (`_video_precheck`).

## Deviations and limitations

- **Edit lists are a warning, not a rejection** (decision, see above); closed GOP, audio bitrate and edit-list semantics are not checked.
- **Metadata is not stripped** from stored videos (QuickTime GPS such as `com.apple.quicktime.location.ISO6709` stays in the file). The file is private to workspace members; that Instagram removes location on publish is unverified. A lossless remux (`-c copy -map_metadata -1 -movflags +faststart`) would fix GPS, moov position and edit lists without transcoding; it is a recommended follow-up (not built).
- **Workspace purge deletes rows, not stored objects** (pre-existing for images, costlier for videos): follow-up.
- Aspect lower bound 0.1 (the stricter of Meta's conflicting 0.01 and 0.1). The 300 MB cap is decimal.
- A probe that exceeds the 1 MiB JSON cap, or a file whose `moov` exceeds 32 MiB, answers 503 (retryable) although a retry will never succeed; acceptable for a hostile file, noted for Session 07 hardening.
- `preexec_fn` is used for the rlimits (POSIX only); it is not thread-safe in the strict sense, which the standard library documents. A `process_group`/`prlimit` based approach is a possible hardening.
- The video route takes about twice the upload size in scratch disk per concurrent upload (Starlette spool plus our copy; the spool is in the system temp directory, our copy in `MEDIA_SCRATCH_DIR`).
- `VIDEO_TOO_LARGE`'s next-step text says 300 MB even if `MEDIA_MAX_VIDEO_BYTES` is changed.
- No HTTP Range support on `/content` (Session 07 player).

## Live items (pending, not verified)

- Real `ffprobe`/`ffmpeg` run: `test_video_real_ffprobe.py` skips locally and should run in CI (first CI run pending).
- Docker image build, the Debian pin `7:5.1.9-0+deb12u1` (read from packages.debian.org and the Debian security tracker by the session lead; not re-checked) and the image-size delta ("to be measured on the first build").
- `caddy validate` of the new matcher-scoped `request_body` blocks (`@video_upload`, `@other_uploads not path_regexp ...`).
- Whether Meta accepts an S3 presigned URL for a video container, the URL lifetime needed, edit-list acceptance, container processing times.
- Antigravity left ACL-locked scratch directories that cannot be removed from this session: `backend/var/s06-verification-{a,b,c,e,g}` (plus the S04/S05 `backend/.tmp/*` and `backend/.test-tmp/*`). All are git-ignored; delete from an elevated shell before committing.

## Merge notes

- Migration `0082` chains from `0081` (itself from `0080`, from `0061`); the orchestrator re-chains tracks. ADR number 028 as allotted to Track B.
- Shared files touched with appended or localized edits: `core/config.py`, `core/errors.py`, backend and frontend i18n catalogs, `openapi.json`, `schema.d.ts`, `.env.example`, `Dockerfile`, `Caddyfile`, `ci.yml`, `pyproject.toml` (one contract), `mvp-scope.md`, `platform-capabilities.md`, `data-model.md`, `pricing-and-unit-economics.md`, the ADR index.

## Questions

- Build the lossless remux (strip metadata, fix `moov` position and edit lists) so owners are not asked to re-export, or keep rejecting `MOOV_NOT_AT_FRONT`?
- Delete stored objects on workspace purge (images and videos)?
- Should edit lists become a rejection once Meta behaviour is verified live (one constant)?
- Is a 2 GiB per-workspace video quota and a 300 MB cap right for the pricing plans (plan-dependent quota)?
