# ADR-015: Media storage abstraction: local filesystem and S3-compatible

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
Owners upload images (later videos) for posts and Stories. Instagram fetches media from a **publicly accessible URL** at container-creation time and accepts only **JPEG** for images ([platform-capabilities.md §1.6](../../research/platform-capabilities.md)). The local demo must not need cloud storage. Uploaded files are untrusted input.

## Alternatives
1. Store binaries in PostgreSQL (`bytea`).
2. Local filesystem only.
3. **`MediaStorage` interface** with `local` and `s3` backends (S3-compatible: AWS S3, Cloudflare R2, MinIO, Backblaze B2, Hetzner Object Storage).

## Decision
Option 3.

```python
class MediaStorage(Protocol):
    def put(self, key: str, data: BinaryIO, content_type: str) -> None: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...
    def public_fetch_url(self, key: str, ttl_s: int) -> str: ...   # URL reachable by Meta
```

- `local` backend (development, demo, mock provider): files under `MEDIA_LOCAL_ROOT`. `public_fetch_url` returns an app URL that only the mock provider uses. The real Meta adapter **refuses** to run with the local backend unless `MEDIA_PUBLIC_BASE_URL` points to a public tunnel (development of Phase 7 only).
- `s3` backend: private bucket, **presigned GET URLs** with short TTL (default 1 h) for Meta fetches (TTL tolerance to verify, V-09). Owners view media through the authenticated API (`GET /media/{id}/content`), never through bucket URLs.
- Storage keys: `{workspace_id}/{yyyy}/{mm}/{media_id}.{ext}`. Never derived from user file names.

**Validation at upload (synchronous, deterministic):**
- Size limit (`MEDIA_MAX_IMAGE_BYTES`, default 8 MB, matching the Instagram image limit).
- Type detection by **content sniffing** (Pillow `Image.open` + `verify`), not by extension or the client's MIME type.
- Images: JPEG or PNG accepted. PNG (and JPEG with non-sRGB profile/EXIF orientation) is **re-encoded to baseline sRGB JPEG**, EXIF stripped (privacy: GPS). Dimensions recorded.
- Per-content-type checks at submission: feed image aspect ratio 4:5 to 1.91:1; story 9:16 recommended (warning, not error).
- Decompression-bomb protection (Pillow `MAX_IMAGE_PIXELS`).
- Video: **not accepted in MVP** (needs ffprobe validation/transcoding; deferred).

**Lifecycle:** `media_assets.status` ∈ `uploaded` → `ready` | `rejected`; `deleted`. A daily cleanup job deletes orphaned assets (not referenced by any content item, older than 7 days) and assets of deleted workspaces.

## Rationale
- Postgres bytea bloats backups. A filesystem-only design cannot serve Meta in production.
- S3-compatible API keeps hosting vendor-neutral and cheap (R2 has no egress fees; MinIO for self-hosters).

## Trade-offs
- Presigned URL TTL must outlast Meta's fetch. Container polling happens within minutes, so a 1 h TTL leaves ample margin (to verify).
- Re-encoding changes the owner's file slightly (quality 90).

## Implementation notes (Phase 5)
- **Local fetch URL (G3).** The mock Instagram provider must read the JPEG, but `app.integrations.instagram` may import only `app.core`. The local backend therefore returns an opaque reference, `localmedia:{key}?exp=<unix seconds>`, from `public_fetch_url` (expiry = injected `Clock` + `MEDIA_PUBLIC_URL_TTL_SECONDS`). The registry hands a `MediaStorage` to `MockInstagramProvider`, which resolves the reference through it and checks the JPEG magic bytes. It is not a network URL and Meta cannot use it: the Meta adapter (Phase 7) still refuses the local backend, and the production configuration check refuses `MEDIA_STORAGE_BACKEND=local` when `meta` is enabled. `app.integrations.storage` imports only `app.core`; `app.integrations.instagram.mock` may also import it.
- **Upload order (G12).** Read at most `limit + 1` bytes (more: 413 `MEDIA_TOO_LARGE`) → `Image.open` (only JPEG and PNG are sniffed) + `verify` → reopen → pixel cap of 36 000 000 (a Pillow decompression-bomb warning is treated as an error) → `exif_transpose` → convert to sRGB (transparency is flattened onto white) → **always** re-encode a baseline JPEG, quality 90, with no EXIF, ICC or other metadata (the simplest guaranteed removal of GPS data) → `sha256` over the **output**. A rejected upload stores no row and no object: 422 `MEDIA_INVALID` (reason in `params.reason`: `EMPTY_FILE`, `NOT_AN_IMAGE`, `CORRUPT_IMAGE`, `TOO_MANY_PIXELS`) plus a `media.rejected` audit entry (a too-large upload is audited the same way with reason `TOO_LARGE`). The object is written before the row, so a committed asset always has its bytes.
- **Keys** are built by `build_key(workspace_id, media_id, now)` and every backend checks them against one strict regex before touching storage.
- **Limitation.** The orphan `media_cleanup` job is deferred (`mvp-scope.md`): assets that no content item references are kept.

## Consequences
- `app/integrations/storage/{base.py, local.py, registry.py}` (`s3.py` in Phase 7), `app/content/media.py` (validation).
- Pillow is a backend dependency from Phase 5. `boto3` is added only when the `s3` backend is implemented (Phase 7).

## Revisit when
- Video/Reels support is added: introduce ffprobe validation and possibly a transcoding worker queue.
