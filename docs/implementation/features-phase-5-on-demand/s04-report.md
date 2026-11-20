# Feature Phase 5, Session 04: carousel data model and validation (F-08, part 1)

**Status:** Done offline (backend, docs, OpenAPI). No UI (Session 05). Carousel publishing is **not** implemented: a due carousel is refused safely until Session 05.
**Baseline:** `1a58d41`. **Migration:** `0080`, `down_revision = "0061"`. Nothing committed.
**Trigger:** Track B moved out of Deferred in `mvp-scope.md` on 2026-11-18 at the owner's request to implement all Feature Phase 5 sessions. Pilot demand evidence is **not yet recorded**.

## What was delivered

- **Content type `feed_carousel`** with an ordered list of 2 to 10 images. A draft may hold 0 to 10 while it is being built; submit needs 2 to 10. `CAROUSEL_MIN_ITEMS = 2`, `CAROUSEL_MAX_ITEMS = 10` and `CAROUSEL_ASPECT_TOLERANCE = 0.02` are named constants in `content/validation.py` and are the only place to change the limits.
- **Migration `0080`** (`20261118_0080_feed_carousel.py`):
  - the `ck_content_items_content_type` check gains `feed_carousel`;
  - new table `content_item_media` with composite tenant FKs to `content_items` (`ON DELETE CASCADE`) and `media_assets`, `unique (content_item_id, position)` **deferrable initially deferred** (a reorder rewrites positions in one transaction), `unique (content_item_id, media_asset_id)`, `position >= 0 AND < 20`, `ENABLE` and `FORCE ROW LEVEL SECURITY`, `tenant_isolation_policy`, runtime-role grants (the 0055/0058 pattern);
  - backfill of capability `publish_feed_carousel` from `publish_feed_image` for all accounts (same Meta permission);
  - the downgrade refuses while any carousel exists.
  - `content_item_media` is added to `CATEGORY_C_TABLES` (64 tables).
- **Service and API** (`content/service.py`, `content/carousel.py`, `schemas.py`, `views.py`, `router.py`):
  - `media_asset_ids` (ordered list) on create and PATCH. PATCH replaces the whole list, which is how reorder, add and remove work. An unchanged list is a no-op.
  - Any change to the list or its order is a payload edit: version + 1, pending approval cancelled (`SUBJECT_EDITED`), queued job cancelled, item back to `draft`, claim validation and `fact_references` recomputed.
  - Wrong shape (`media_asset_id` on a carousel, a list on a single-image type, PATCH `null`) is 422 `CONTENT_MEDIA_SHAPE_INVALID`. More than 10 is 422 `CAROUSEL_TOO_MANY_ITEMS`, duplicates are 422 `CAROUSEL_DUPLICATE_MEDIA`. A foreign, unknown or non-ready asset is **404** and nothing is written.
  - `ContentItem.media_items` is `{media_asset_id, position, width, height, media_deleted}[]` (empty for other types). AI generation still accepts only `feed_image` and `story_image`.
- **Validation** (`content/validation.py`, pure): `CONTENT_MEDIA_REQUIRED` for 0 items, `CAROUSEL_TOO_FEW_ITEMS`, `CAROUSEL_TOO_MANY_ITEMS`, per-item `MEDIA_NOT_READY` and `ASPECT_RATIO_OUT_OF_RANGE` (field `media_asset_ids.{i}`), `CAROUSEL_MIXED_ASPECT_RATIO` (positions whose ratio differs from item 0 by more than 2 %), caption rules as `feed_image`, capability `publish_feed_carousel`. TR and EN texts added.
- **Approval hash (INV-16)**: `feed_image` and `story_image` payloads are unchanged (same keys, same hashes, so in-flight approvals are unaffected). A carousel payload carries `media_asset_id = null`, `media_sha256 = null` and `media_items = [{position, media_asset_id, sha256}, ...]` built from the DB rows in position order, so order is part of the hash. `subject.bound_payload_hash` recomputes it from the current rows: even a reorder done directly in the database makes the decision `APPROVAL_STALE` and the executor refuse.
- **Price-change hold**: `templates/link.item_render_references` unions the fact versions of every image of the item (single or carousel) and replaces `render_references` at all call sites (service create/update/submit/reapprove, generation, agent). The existing impact handler works from `fact_references`, so a carousel with a rendered price card goes `on_hold (FACT_CHANGED)` and a pending one returns to draft. `stale_template_keys` covers all images.
- **Media cleanup** treats an asset referenced only by `content_item_media` as referenced, with the same published-media retention.
- **Interim safety**: `operations/publish.py` refuses a due `feed_carousel` through the normal `_refuse` path with the interim unavailable-publish refusal (removed in Session 05) (item `failed`, no operation, no provider call; `TODO(Session 05)`). The quota read skips carousels. The Phase 7.5 agent tools refuse carousels (typed refusal and `APPROVAL_STALE` in the executor). The template render job ignores carousels.
- **Docs**: `data-model.md` (table, content type, count 64), `state-machines.md` §5 notes, `api-design.md`, `observability.md` (issue codes), `integrations.md` (capability, content types), `platform-capabilities.md` §1.6 (carousel research with sources), `mvp-scope.md`.
- **OpenAPI**: `frontend/openapi.json` patched by hand (`ContentType`, `media_items`, `media_asset_ids`); `schema.d.ts` regenerated. The only frontend source changes are type-only (`Exclude<ContentType, "feed_carousel">` where the generate flow and composer accept just the two single-image types).

## Meta rules (researched 2026-11-18)

Sources: https://developers.facebook.com/docs/instagram-platform/content-publishing and https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media

- Flow for Session 05: one child container per item (`is_carousel_item=true`), a `media_type=CAROUSEL` container with `children` and `caption`, then `media_publish`.
- **Item count conflicts.** Both Meta pages read on 2026-11-18 say **up to 20** ("Carousels are limited to 20 images, videos, or a mix of the two"; `children`: "up to 20 container IDs"). Earlier documentation and several third-party guides say 10, and the project brief says 2 to 10. The product cap stays at **10** (approved by the orchestrator), which is valid under both readings; raising it is one constant plus doc text.
- "Carousel images are all cropped based on the first image in the carousel (default 1:1)." Every image must also be 4:5 to 1.91:1. Meta does not say mixed ratios are rejected; Pivoris rejects them at submit to avoid a surprise crop.
- JPEG only (already guaranteed by `content/media.py`). Caption lives on the carousel container only (not supported on children). `alt_text` is supported on image children (not added here). `location_id` and `is_ai_generated` are not supported on children. A carousel counts as one post for the publishing limit. Reels cannot be carousel items.
- The same pages still disagree on the publish quota (100 vs 50 per 24 h); unchanged, the existing conservative 50 applies.

## Tests

- Unit: `tests/unit/content/test_validation.py` (carousel counts 0, 1, 2, 10, 11, not-ready, out-of-range, mixed and within-tolerance ratios, capability), `tests/unit/content/test_payload.py` (single-image payloads unchanged, ordered `media_items`, swap changes the hash), `test_rls_policies.py` (64 tables).
- Integration `tests/integration/content/test_carousel.py` (15 tests): ordering and no-op, limits, typed shape errors, mixed ratios block submit, edits (reorder, add, remove) invalidate a pending and an approved version, direct DB reorder is stale and gets a new hash on resubmit, executor refuses a reordered carousel, an old approval cannot execute, rendered price item joins the hold, cleanup keeps carousel files and removes true orphans, due carousel refuses without a provider call or operation, published carousel immutable, generation refuses carousels, reapprove binds a fresh order and version. `test_carousel_migration.py`: upgrade/downgrade round trip and the downgrade guard. Agent refusal in `test_agent_content_tools.py`.
- Isolation `tests/isolation/test_carousel_isolation.py` (5): foreign and mixed media ids are 404 with no partial create or patch, foreign carousel routes and listing, forced RLS and policy, fail-closed runtime role (no context, cross-tenant update and insert), composite FKs refuse a foreign item or asset.

## Checks

Backend, from `backend/`:
- `uv run ruff check app tests evals migrations` pass; `uv run ruff format --check app tests evals migrations` pass (821 files); `uv run mypy app` pass (433 files); `uv run lint-imports` pass (24 contracts kept). (Plain `ruff check .` also walks the locked scratch directory `backend/.tmp/`, see Limitations.)
- `uv run pytest tests/unit tests/contract tests/security tests/isolation`: 2441 passed, 18 skipped (live probes), 2 deselected (invite-secret test, run separately). Three tests failed in the first run only because the worktree `.env` then had demo tools off and a Sentry DSN (`test_phase6_isolation` dev job listing, `test_publishing_isolation` simulator listing, `test_invite_secrets`). After the orchestrator normalised `.env`, those three files pass (12 passed). The integration run above used `DEMO_TOOLS_ENABLED=true SENTRY_DSN=` explicitly.
- `uv run pytest tests/integration/content tests/integration/operations tests/integration/approvals tests/integration/knowledge tests/integration/agent tests/integration/integrations tests/integration/commands`: 1181 passed, 1 failed (40 min). The one failure was a defect in the new `test_carousel_migration.py` (a `:true` inside a `text()` literal was parsed as a bind parameter); fixed with `CAST(... AS jsonb)`, and the file then passes (1 passed). After that fix, `test_carousel.py`, `test_carousel_isolation.py` and `test_rls_policies.py` were re-run together: 39 passed. Not run: the other `tests/integration` directories (the full suite takes over an hour).

Frontend, from `frontend/` (PowerShell): `npm.cmd run lint` pass; `npm.cmd run typecheck` pass; `npm.cmd run i18n:check` pass (2762 keys); `npm.cmd test` 913 passed; `npm.cmd run build` pass.

## Deviations and limitations

- The product cap is 10 although Meta currently documents 20 (see above).
- Mixed aspect ratio is a product rule (Meta crops, it does not reject); tolerance 2 %.
- No per-item caption or alt text (Instagram has no per-item caption; alt text can be added in Session 05 as migration `0081`).
- Real Meta carousel publishing is untested and unimplemented: the capability `publish_feed_carousel` is derived from the same scope as feed images (**unverified live**).
- `template_image` state in the API stays null for carousels.
- The agent cannot create, submit or schedule carousels; AI generation of carousel copy is out of scope.
- Codex left permission-locked scratch directories under `backend/.tmp/` (`baseline`, `carousel-run2`, `checks-main`, `verify-integration`, `verify-main`, each with a protected `.pytest_cache`). They could not be deleted from this session. `.gitignore` only ignores `/.tmp/` at the repo root, so they show as untracked and make `ruff check .` crash; delete them manually (for example from an elevated shell, or after taking ownership) before committing.

## Merge notes

- Migration IDs: `0080` chains from `0061`; the orchestrator re-chains when merging tracks.
- `tests/unit/core/test_rls_policies.py` hard-codes the Category C table count (now 64). Every track that adds a tenant table edits that number, `CATEGORY_C_TABLES` and the `data-model.md` sentence; reconcile them at merge.
- `backend/app/core/errors.py`, both i18n JSON files, `frontend/openapi.json`, `schema.d.ts`, `data-model.md` and `mvp-scope.md` were edited by appending or inserting localized lines.

## Questions

- Raise the cap to Meta's current 20? (One constant, then docs.)
- Should carousels be hidden from the UI and API until Session 05 ships publishing? Today they can be created, validated and approved, and a due one fails with the interim unavailable-publish refusal (removed in Session 05).
