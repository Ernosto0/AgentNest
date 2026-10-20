# Session 3: Media storage and upload

**Plan:** `plan.md` §1 (module layout, import contracts, dependencies), §2 **G3, G12**, §3 **P5-01**. **Depends on:** session 2. **Commit:** `P5-01: …` (split into two commits if large: storage+settings, then upload API).

## Read first
`docs/architecture/decisions/ADR-015-media-storage.md`, `data-model.md` (media_assets), `api-design.md` (media endpoints), `integrations.md` §3.3, `environment-variables.md`, `backend/app/core/{config,errors}.py`, `backend/app/core/i18n/`.

## Build
- Add dependencies `pillow`, `python-multipart`.
- Settings: `MEDIA_STORAGE_BACKEND`, `MEDIA_LOCAL_ROOT`, `MEDIA_MAX_IMAGE_BYTES`, `MEDIA_PUBLIC_URL_TTL_SECONDS`. Production check: `local` refused when `meta` is enabled. Update `.env.example` and `environment-variables.md`.
- `app/integrations/storage/{base.py, local.py, registry.py}`: `MediaStorage` interface, key regex, no path traversal, key never derived from the filename. Local `public_fetch_url` returns `localmedia:{key}?exp=…` (G3). Import contract: `app.integrations.storage` imports only `app.core`.
- Migration **0008** `media_assets`.
- `content/media.ingest(ctx, file, filename, content_type)` in the G12 order: read ≤ limit+1 bytes (else 413 `MEDIA_TOO_LARGE`) → `Image.open` + `verify` → reopen → pixel cap (decompression-bomb warning = error) → `exif_transpose` → sRGB → always re-encode baseline JPEG q90 without EXIF → sha256 of the **output**. Rejected uploads store no row: 422 `MEDIA_INVALID` + audit `media.rejected`.
- `POST /media` (`content.edit`, multipart) and `GET /media/{id}/content` (authenticated stream, `X-Content-Type-Options: nosniff`, `Cache-Control: private`, correct content type).
- Error codes `MEDIA_INVALID` / `MEDIA_TOO_LARGE` with tr/en texts.
- Commit the demo sample images (G19): `backend/app/demo/media/story-sample.png` (1080×1920) and `feed-sample.jpg` (1080×1350), generated once with Pillow.
- Append the new import contracts to `pyproject.toml` (plan §1) as they become relevant; no `app.content` → `operations/commands/api` imports.

## Done when
- Tests: AC-D2 (PNG → `ready` JPEG, no EXIF; text file → `MEDIA_INVALID`); oversize → 413; decompression bomb rejected; storage key independent of filename and traversal-safe; workspace isolation (foreign media id → 404); content endpoint headers.
- Docs updated: ADR-015 note (G3), data-model, api-design, environment-variables, local-development (sample images).
- All backend checks green including `lint-imports`.
