# Session 03 report: template image renderer (F-07, part 1)

**Status:** Implemented offline; all required checks pass (see section 6). Nothing live is involved. Nothing is committed.
**Baseline:** `06c5d64` (`main`). **Migration head after this session:** `0058` (`20261117_0058_template_images.py`, parent `0057`). Session 01 runs in parallel and may take `0059`; the orchestrator re-chains at merge.

## 1. Who built what

- **Codex (gpt-6.1-sol, medium)** wrote the code, tests, fonts, migration, docs and frontend from the reviewer's brief, and ran its own checks.
- **Reviewer (Claude)** read the whole diff, re-ran the checks, and fixed one gap: the new audit actions `media.template_rendered` and `brand.updated` were missing from the Activity feed (`app/activity/groups.py`, `activity.*` strings in `tr.json` and `en.json`), which made two tests in `tests/unit/test_activity_templates.py` fail. Everything else is Codex's draft unchanged.

## 2. What was built

- **Brand settings.** Table `workspace_brand_settings` (one row per workspace; `primary_color`, `accent_color` as lower-case `#rrggbb` with CHECKs; nullable `logo_media_asset_id` with a composite FK to `media_assets(workspace_id, id)`). RLS enabled and forced, tenant policy, role grants, registered in `CATEGORY_C_TABLES`. No row means the built-in default palette (`is_default: true`). `GET /workspaces/{id}/brand` (`settings.view`) and `PUT /workspaces/{id}/brand` (new permission `brand.manage`, owner and manager). A logo must be a ready asset of the same workspace (a foreign or unknown ID is 404). The update writes a `brand.updated` audit row in the same transaction. The `media_cleanup` job now never deletes an asset that is a workspace logo.
- **Settings UI.** `BrandSection` inside the Workspace section of Settings: two colour inputs (native picker plus hex field), logo upload (existing `MediaUpload`) and remove, save, success and error messages, read-only for roles without `brand.manage`. TR and EN strings.
- **Renderer** `backend/app/content/templates/` (`spec.py`, `layout.py`, `cards.py`, `service.py`, `router.py`, `fonts/`):
  - Templates `price_card`, `hours_card`, `services_list` (2 to 6 money facts; "this week's classes" is not structured yet), `announcement`, each in `story` 1080x1920 and `feed` 1080x1350. Story text stays out of the top 250 px and bottom 340 px.
  - Typed inputs: strict Pydantic discriminated union. Fact-backed fields hold fact keys, never values.
  - Pillow only, bundled Noto Sans Regular and Bold (SIL OFL 1.1, source URLs, version and SHA-256 in `fonts/SOURCE.md`, licence in `fonts/OFL.txt`), `Layout.BASIC`, integer pixel math, greedy wrap, bounded shrink, ellipsis truncation, a WCAG-luminance text colour rule. `RENDERER_VERSION = "1"`.
  - Facts come from `knowledge.service.usable_facts` (verified, live, in window, uncontested). Any key that is not usable refuses the whole render (`TEMPLATE_FACT_NOT_USABLE`, 422, with the keys); a wrong value type is `TEMPLATE_FACT_TYPE_MISMATCH` (422). The DB snapshot is committed before any Pillow or storage work.
  - INV-02 for the announcement's free text: the literal text (placeholders removed) and the rendered text are both run through the claim validator; a price, time, phone, URL, discount word or large number refuses the render with `TEMPLATE_TEXT_UNGROUNDED` and the field name. `{{fact:key}}` placeholders are allowed and their versions are recorded.
  - Output: PNG bytes go through the existing media path (`media.ingest_bytes`, which `ingest` now delegates to: size limit, `process_image` to a baseline sRGB JPEG without EXIF, write-before-row, `media.uploaded` audit) and the asset gets a `render_record`, plus a `media.template_rendered` audit row.
- **Routes** (all workspace-scoped, `content.edit`): `GET /content/templates` (catalog), `POST /content/template-images/preview` (returns the processed `image/jpeg`, stores nothing), `POST /content/template-images` (stores, returns the asset and `render_record`).
- **Render record** (`RenderRecord`, stored in new column `media_assets.render_record` JSONB): `renderer_version`, `template`, `format`, `language`, `facts: [{fact_id, key, version}]` (first-use order, unique), non-fact `inputs`, `brand` snapshot, `rendered_at` from `Clock`. `RenderRecord.fact_references()` returns `(fact_id, version)` pairs, the same shape as `Grounding.references`, so Session 04 can write them as `fact_references` on a content item and let `impact_handlers.py` hold the item on a price change.
- **Docs:** `mvp-scope.md` (template cards moved out of Deferred, AI image generation stays deferred, new Feature Phase 3 row), `api-design.md`, `data-model.md`, `observability.md` (audit catalog), `security-and-privacy.md` (RLS table list), `frontend/openapi.json` and `schema.d.ts`.

## 3. Files

Backend: `app/content/brand.py`, `app/content/templates/{__init__,cards,layout,router,service,spec}.py`, `app/content/templates/fonts/{NotoSans-Regular.ttf,NotoSans-Bold.ttf,OFL.txt,SOURCE.md}`, `app/content/{media,media_cleanup,models}.py`, `app/api/router.py`, `app/core/{db,errors}.py`, `app/core/i18n/{en,tr}.json`, `app/identity/permissions.py`, `app/activity/groups.py`, `migrations/versions/20261117_0058_template_images.py`.
Backend tests: `tests/unit/content/templates/{test_cards,samples,regen_goldens}.py` and 8 golden thumbnails (36 KB), `tests/integration/content/test_template_images.py`, `tests/isolation/test_template_images_isolation.py`, `tests/unit/core/test_rls_policies.py`, `tests/unit/identity/test_permissions.py`.
Frontend: `features/settings/{BrandSection.tsx,brand.test.tsx,WorkspaceSection.tsx,hooks.ts}`, `i18n/locales/{en,tr}/common.json`, `test/mockApi.ts`, `api/schema.d.ts`, `openapi.json`.
Docs: the five listed above plus this report.

## 4. Contracts

- Errors: `TEMPLATE_FACT_NOT_USABLE`, `TEMPLATE_FACT_TYPE_MISMATCH`, `TEMPLATE_TEXT_UNGROUNDED` (all 422, TR and EN messages). Upload errors (`MEDIA_INVALID`, `MEDIA_TOO_LARGE`) still apply to the rendered bytes.
- Audit actions: `brand.updated`, `media.template_rendered`.
- Permission: `brand.manage` (owner, manager).
- No new env var, job type, LLM call or Python dependency.

## 5. Determinism and test strategy

Exact pixel hashes are not asserted, because FreeType and Pillow can differ between CI (Linux) and Windows. The tests assert: output size and RGB mode for every template and format; byte-identical PNG on a second render in the same process; text-box geometry (inside the canvas, inside the story safe zones, clear of the logo box); wrapping and ellipsis truncation, and breaking of a very long word; glyph presence for every Turkish letter (ğ Ğ ı İ ş Ş ç Ç ö Ö ü Ü) and the TRY sign, and that İ and ı survive unfolded; and a tolerant mean-absolute-difference comparison against tiny checked-in grayscale golden thumbnails (regenerate with `tests/unit/content/templates/regen_goldens.py`). Integration tests cover a missing, unverified, contested, expired and wrong-type fact (no asset row, no stored object), ungrounded free text, a `{{fact:...}}` placeholder with its version recorded, a re-render after a price change recording the new version, the stored JPEG without EXIF and with `render_record`, preview storing nothing, brand defaults, set, validation, 403 and 404, the audit row, and a logo surviving `media_cleanup`. Isolation tests cover foreign workspace and foreign logo IDs and the RLS of the new table.

## 6. Checks (run in `s03`, test DB `pivoris_p3s03_test`)

| Check | Result |
|---|---|
| `ruff check .` and `ruff format --check .` | pass (779 files formatted) |
| `mypy app` | pass (414 files) |
| `lint-imports` | 23 contracts kept, 0 broken |
| `pytest tests/unit tests/isolation tests/security tests/contract tests/integration/content` (reviewer, before the activity fix) | 2,526 passed, 13 skipped, 5 failed |
| the 5 failures | 2 were the real activity-catalog gap, fixed (now pass). 3 (`test_phase6_isolation` dev job listing, `test_publishing_isolation` simulator listing, `test_invite_secrets`) need `DEMO_TOOLS_ENABLED=true`, which the shell did not set; with it they pass (12 passed). |
| after the fix: `tests/unit/test_activity_templates.py tests/unit/core`, new isolation, new integration and `tests/unit/content/templates` | 262 passed |
| Codex's own run | 494 backend tests passed (216 core, 278 content, isolation and media) |
| frontend `lint`, `typecheck`, `i18n:check` | pass (2,642 keys) |
| frontend `npm test` | 859 passed (59 files) |
| frontend `build` | pass |

I did not re-run `test_owner_creates_an_invite_with_a_one_time_link` and `test_cors_allows_only_the_frontend_origin` (known environment failures); they did not appear among the failures. The full integration suite was not run (per the session rules).

## 7. Invariant notes

INV-01: the new table has `workspace_id`, a composite FK to `media_assets`, forced RLS; foreign logo and workspace IDs are 404. INV-02: facts only through usable facts and `{{fact:key}}`; free text with critical values is refused. No external call in a transaction (the read snapshot is committed before Pillow and storage). Time only from `Clock`. Both languages are shipped. The rendered image is a normal media asset: simulated-provenance rules are unaffected because it is provider-neutral.

## 8. Open questions and handoff

- **Font size.** The two Noto Sans files are about 1.1 MB together (full glyph coverage, unmodified). They could be subset to Latin to about 100 KB with fontTools (not a dependency); left as is to keep the licence-clean unmodified files.
- **Hours rows** are built by splitting the formatted weekly-hours string on `", "` (at most 7 rows). A long exception note containing a comma could split oddly; a structured per-day builder is a possible Session 04 refinement.
- **Where the record lives.** The fact versions are stored on `media_assets.render_record`. Session 04 must copy them into the content item's `fact_references` when an image is attached, and re-render must create a new asset and a new item version that needs approval again.
- **Logo and cleanup.** A replaced logo becomes an ordinary orphan and is deleted after `RETENTION_MEDIA_ORPHAN_DAYS`. Rendered cards never attached to an item are deleted the same way.
- **Merge watch:** `app/core/db.py` (`CATEGORY_C_TABLES`), `tests/unit/core/test_rls_policies.py` (table count), `app/core/errors.py`, `app/core/i18n/{en,tr}.json`, `app/activity/groups.py`, `app/api/router.py`, `docs/product/mvp-scope.md`, `docs/architecture/{api-design,data-model,observability,security-and-privacy}.md`, `frontend/openapi.json`, `schema.d.ts`, the frontend locale files and the migration number.
- Session 04 owns the template picker, live preview in the content flow, the hold-on-price-change link and the "make a price card" command.
