# Feature Phase 5, Session 05: carousel publishing and UI (F-08, part 2)

**Status:** Done offline (backend, UI, docs, OpenAPI). Live Meta acceptance is **pending** (no live calls were made).
**Baseline:** `1a58d41` plus Session 04's uncommitted work. **Migration:** `0081`, `down_revision = "0080"`. Nothing committed.
**Trigger:** see `s04-report.md` (Track B moved out of Deferred on 2026-11-18 at the owner's request; pilot demand evidence not yet recorded).

## What was delivered

### Publishing through the operations ledger (`operations/publish.py`)

- The `CAROUSEL_PUBLISH_NOT_AVAILABLE` refusal is gone. A due `feed_carousel` follows the normal `_begin` checks (approval, hash over the ordered media, capability `publish_feed_carousel`, circuit, deadline, quota) and then `_drive_carousel`. The single-image path is unchanged (same calls, same operation key `publish:{content_id}:v{version}`).
- Flow: one child container per item in position order (`is_carousel_item=true`, no caption), poll each child to `FINISHED`, the carousel container (`media_type=CAROUSEL`, `children`, caption), poll it, then `media_publish` on the carousel container only.
- **Persisted state** in `operations.provider_ref`: `children: [{media_asset_id, container_id}]` (keyed by asset id, never by index; written after every created child) and `container_id` (the carousel container; the same key single images use, so `reconcile_publish`, `abandon_*` and the stuck sweep work unchanged). Image URLs and tokens never enter the ledger.
- **Resume, reconcile first.** On every attempt and every reconciliation continuation: the stored carousel container is read first (`PUBLISHED` finishes with no publish call and without touching children; `FINISHED` publishes; `IN_PROGRESS` is polled; `ERROR` fails `MEDIA_REJECTED`; `EXPIRED` drops only the carousel id). Then each stored child is read (`FINISHED` kept, `EXPIRED` or not found recreated alone, `ERROR` fails `MEDIA_REJECTED`, `PUBLISHED` fails `PROVIDER_REJECTED`) and only missing children are created. Nothing that exists and is usable is recreated.
- **No duplicate publish.** `media_publish` is called only for a carousel container read as `FINISHED` in the same run. An ambiguous publish answer (`ProviderOutcomeUnknown`, an unexpected exception, `CONTAINER_PUBLISHED`/`NOT_READY`/`EXPIRED`) goes to `mark_unknown` and reconciliation reads the carousel container (`PUBLISHED` is a success, `FINISHED` proves nothing went out). A crash after `media_publish` and before the record is settled by the stored container's `PUBLISHED` status. An ambiguous create (a lost answer) only leaves an unpublished orphan container, as for single images.
- Polling: one shared 5-minute budget for all children, a fresh 5 minutes for the carousel container; the container-recreation cap (2) is per run across all containers; the job lease is raised to cover both budgets (`PUBLISH_LEASE_SECONDS`). No transaction is open during any provider call, sleep or heartbeat (the test harness asserts it on every call).
- **Quota: one post per carousel.** The pre-flight quota read now runs for carousels (after validating approval hash and media); children are never counted; the mock records one published-media row per carousel.
- **Single-image behaviour tightened slightly:** an unknown container status code now fails `PROVIDER_REJECTED` instead of looping until the poll timeout.
- Insights: a published carousel is skipped by the media-snapshot capture and `get_media_insights` raises a typed `MEDIA_INSIGHTS_NOT_SUPPORTED` for carousels (album metrics are outside the verified contract). No fake metrics.
- S04 safety pieces were adjusted, not lost: the ordered-media approval hash and `APPROVAL_STALE` on a reorder, the fact-change hold, the agent refusals and the media-retention treatment are untouched; only the publish refusal was replaced by the real flow.

### Providers

- `ContainerSpec` gained `is_carousel_item`, `children` and media type `CAROUSEL`, with shape validation (child: image URL and no caption; carousel: 2 to 20 children and no URL).
- **Mock:** carousel containers validate that every child exists for the same account, is a carousel item, is `FINISHED` and not already part of a published carousel (`CHILD_NOT_FOUND`, `CHILD_EXPIRED`, `CHILD_NOT_READY`, `TOO_FEW_CHILDREN`, `TOO_MANY_CHILDREN`); a bare child cannot be published (`CONTAINER_NOT_PUBLISHABLE`). Injectable failures per step: new operations `create_carousel_item` and `create_carousel_container` (plus the existing `container_status` and `publish`), with a new `skip_first` on a rule to fail the Nth call; exposed (optional) in the dev failure-rule API and the dev panel.
- **Migration `0081`** (simulator tables only): `media_type` check gains `CAROUSEL`, `sim_containers.is_carousel_item` and `children` (jsonb), `media_url` nullable, the operation check gains the two new operations, `sim_failure_rules.skip_first`. Full downgrade.
- **Meta:** `POST /<IG_ID>/media` with `image_url` + `is_carousel_item=true` per child; with `media_type=CAROUSEL`, comma-joined `children` and `caption` for the carousel; `media_publish` with `creation_id` of the carousel container (still marked ambiguous). Source (read 2026-11-18): https://developers.facebook.com/docs/instagram-platform/content-publishing. Not exercised live.

### UI (TR + EN, 360 px)

- The composer offers Carousel (blank draft only; AI generation and templates are disabled for it).
- New `CarouselMedia` editor: multi-select upload (sequential, per-file state, stops at 10), ordered thumbnails, remove, **drag to reorder** and **Move up / Move down buttons** (aria-labelled with the position, polite live region), one PATCH of `media_asset_ids` per change with `expectedVersion`, nothing sent for an unchanged order. Pure logic in `carousel.ts` (`move`, `remove`, `append`, `sameOrder`, message mapping).
- Preview: first image with a stepper ("2 / 5"), one caption; cards and library show the first image plus an image-count badge. Caption hint: the caption belongs to the whole carousel, no per-image captions.
- Validation messages in TR and EN for the carousel and per-item codes.

## Tests and checks

New and extended tests:

- `tests/integration/content/test_carousel_publish.py` (happy path and order, quota once, failure and resume at each step including a middle child, lost answers on child and carousel creation, ambiguous publish both ways, invalid and `ERROR` child, crash after each committed id, expired child or carousel, shared poll budget, recreation cap, media deleted at due time, a published child rejected) and `test_carousel_publish_crash_commits.py` (the same crash points with real commits).
- `tests/integration/content/test_carousel_migration.py` (0081 round trip), `tests/isolation/test_carousel_isolation.py` (publish cannot reach a foreign carousel or asset), contract cases for the mock, Meta request-body unit tests, `ContainerSpec` shape tests.
- Frontend `carousel.test.tsx` (reorder, remove, append cap, Move up/down PATCH with the right `expectedVersion`, disabled first and last, multi-select upload order and cap, no PATCH for an unchanged order, message rendering).

## Checks

Backend, from `backend/` (`DEMO_TOOLS_ENABLED=true SENTRY_DSN=`):
- `uv run ruff check app tests evals migrations` pass; `uv run ruff format --check app tests evals migrations` pass; `uv run mypy app` pass; `uv run lint-imports` pass (24 contracts kept).
- `uv run pytest tests/integration/content tests/integration/operations`: 452 passed (10 min).
- `uv run pytest tests/unit tests/contract tests/security tests/isolation`: 2455 passed, 18 skipped (live probes), 2 failed. Both failures are environmental: `test_invite_secrets` passes (2 passed) with `SENTRY_DSN=` set (the worktree `.env` has a Sentry DSN, same as in S04), and `test_cli_migration_status_head_only_and_check_config` fails only because the worktree `.env` sets `DEMO_TOOLS_ENABLED=true`, which `check-config --production` rejects (not related to this change).
- Not run: the other `tests/integration` directories (full suite over an hour).

Frontend, from `frontend/` (PowerShell): `npm.cmd run lint` pass; `npm.cmd run typecheck` pass; `npm.cmd test` 923 passed; `npm.cmd run i18n:check` pass (2790 keys); `npm.cmd run build` pass.

## Deviations and limitations

- Meta currently documents up to 20 carousel items; the product cap stays 10 (decision).
- No per-image alt text (decision); mixed aspect ratio is a product rule.
- Drag reorder is not unit-tested (jsdom); the button path is.
- Carousel insights are not supported (skipped, no fake data).
- `get_container_status` on Meta does not return the media id for `PUBLISHED`; the permalink for a reconciled carousel is therefore fetched only when the id is known (same as single images).
- Live Meta publishing of carousels is unverified; the capability `publish_feed_carousel` shares the scope of `publish_feed_image`.
- Codex left an ACL-locked `backend/.test-tmp/` (and the S04 `backend/.tmp/*` directories); delete from an elevated shell before committing. `ruff` must be run on `app tests evals migrations`.

## Merge notes

- Migration IDs: `0081` chains from `0080` (itself from `0061`); the orchestrator re-chains tracks.
- Shared files touched with appended or localized edits: `core/errors.py`, i18n catalogs, `openapi.json`, `schema.d.ts`, `data-model.md`, `integrations.md`, `state-machines.md`, `workflows.md`, `mvp-scope.md`, `platform-capabilities.md`.

## Questions

- Raise the cap to Meta's 20? (One constant plus docs.)
- Should the Meta provider also read the media id for a `PUBLISHED` container once Meta documents the field?
