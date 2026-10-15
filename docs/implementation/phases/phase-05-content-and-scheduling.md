# Phase 5: Content and Scheduling

## Objective
Deliver workflow E end to end against the mock provider: image upload and validation, content drafts (manual and AI), claim-validated submission with version-bound approval and scheduling, a deterministic publish worker using container semantics, bounded retries with deadlines, reconciliation that prevents duplicates, cancellation, and fact-change holds.

## Read first
[workflows.md §E, §B step 3.4](../../architecture/workflows.md) · [state-machines.md §5, §6](../../architecture/state-machines.md) · [integrations.md §3.3, §3.6](../../architecture/integrations.md) · [agent-runtime.md §5](../../architecture/agent-runtime.md) · [data-model.md §3.6](../../architecture/data-model.md) · [api-design.md §2.7](../../architecture/api-design.md) · ADRs [011](../../architecture/decisions/ADR-011-external-operations-ledger.md), [015](../../architecture/decisions/ADR-015-media-storage.md) · [user-journeys.md J4](../../product/user-journeys.md)

## Scope
**In:** `MediaStorage` (local); `media_assets` + upload validation (Pillow); `content_items` + transitions; `draft_content` task + `generate_content` job + fake; content commands (`content.create_draft`, `content.cancel_scheduled`, `query.content_status`, `query.explain_failure`) with the content reference resolver; submission validation, schedule conversion, quota forecast, self-approval, staff pending approval; mock container lifecycle, publish and quota, plus publish failure modes; `publish_content`, `reconcile_publish`; retries, deadline and `on_hold` for account unavailability; cancel and re-approve; impact handlers for content; content UI.
**Out:** video and Reels, carousels, image generation, S3 storage (Phase 7), the real Meta adapter.

## Prerequisites
Phase 4 accepted.

## Files and modules expected to change
```
backend/app/integrations/storage/{base.py, local.py}
backend/app/content/{models.py, media.py, transitions.py, validation.py, scheduling.py, service.py, generation.py, router.py, jobs.py, schemas.py, impact_handlers.py}
backend/app/ai/{prompts/draft_content/v1.md, tasks/draft_content.py}
backend/app/commands/{resolver.py (ContentRef), executors/content.py}
backend/app/operations/{publish.py, reconcile.py}
backend/app/integrations/instagram/mock.py (containers, publish, quota, failure modes)
backend/evals/draft_content/*.yaml
frontend/src/features/content/{ContentTabs, ContentCard, ContentEditor, MediaUpload, GenerateSheet, ScheduleSheet, FailureDetail, OnHoldActions}.tsx
frontend/e2e/{scenario-c.spec.ts, scenario-d.spec.ts, scenario-f.spec.ts}
```

## Key interfaces and contracts
- `MediaStorage` ([ADR-015](../../architecture/decisions/ADR-015-media-storage.md)); `media.ingest(ctx, file, filename, content_type) -> MediaAsset`.
- `content.transitions.apply(item, event, **ctx)`: the only way to change status.
- `content.submit(ctx, item_id, schedule, self_approve, expected_version, actor)`.
- Approval payload for publishing: `{content_id, version, content_type, social_account_id, caption, overlay_text, media_asset_id, media_sha256, scheduled_at}`.
- `operations.execute_publish(content_id, version)`, `operations.reconcile(operation_id)`.
- Config added: `MEDIA_STORAGE_BACKEND` (`local`), `MEDIA_LOCAL_ROOT`, `MEDIA_MAX_IMAGE_BYTES`, `SIM_CONTAINER_DELAY_SECONDS` (default 2), `PUBLISH_DAILY_LIMIT` (default 50).

## Tasks (in order)

| ID | Task | Details | Size |
|---|---|---|---|
| P5-01 | Media | Storage interface + local backend; `media_assets` model; upload endpoint (multipart; size limit; Pillow sniff + verify; pixel limit; PNG→JPEG sRGB; EXIF strip; dimensions; sha256); authenticated content endpoint with `nosniff`. | M |
| P5-02 | Content model and transitions | Migration; transition table exactly per [state-machines.md §5](../../architecture/state-machines.md); version increments on payload edits; edit cancels approvals; CRUD API. | M |
| P5-03 | Generation and content commands | `draft_content` task + prompt v1 + fake; `generate_content` job; validation results stored; `fact_references`; ContentRef resolver (alias, date in the workspace timezone, type, status; clarification on ambiguity); executors for the four content commands. | L |
| P5-04 | Submission | Validation rules (type, media, aspect ratio, caption length, claim validation pass, schedule window, capability, quota forecast); schedule conversion via `zoneinfo`; self-approve vs pending approval; callbacks (approve → scheduled + enqueue; reject; expire → draft `APPROVAL_EXPIRED`); notifications. | M |
| P5-05 | Mock publishing | Containers (`IN_PROGRESS` → `FINISHED` after the delay, `EXPIRED` after 24 h, `PUBLISHED`), publish with `unique(container_id)`, quota, failure modes (`transient`, `rate_limited`, `invalid_media`, `auth_revoked`, `timeout_after_success`) for `create_container`, `container_status` and `publish`. Contract tests. | M |
| P5-06 | Publish executor | `execute_publish` per [workflows.md §E step 6](../../architecture/workflows.md): due checks, ledger, container creation committed, polling with heartbeat, publish, `outcome_unknown` → `reconcile_publish`, retry backoff within `execute_before`, permanent failures, `on_hold` for account unavailability, quota exhaustion, success notifications. Cancel and re-approve endpoints. | L |
| P5-07 | Content impact handlers | Fact change → scheduled/retry → `on_hold`; pending → draft; drafts → stale validation; re-validation sweep with old-value string matching. | S |
| P5-08 | Frontend | Content tabs (Drafts, Scheduled, Published, Problems); editor for feed (caption) and story (overlay suggestions, explanation that text must be in the image); media upload with preview and warnings; generate sheet; validation issues inline; schedule sheet (date and time in the workspace timezone, "Publish now"); status badges incl. "next attempt at"; failure detail from the error catalog; on-hold actions (edit / re-approve / cancel); simulated permalink with badge. | L |
| P5-09 | Evals | `draft_content` dataset (≥ 15 cases): promotions backed or unbacked, price mentions, story overlay length. | S |
| P5-10 | Tests | See below. | M |

## Tests to add
- **Unit:** transitions (all allowed + key forbidden ones); validation rules; schedule conversion (Europe/Istanbul and Europe/Lisbon across a DST change); payload hash stability.
- **Integration:** AC-D1…D8, AC-F1…F6, AC-C4, AC-X5 (scheduled publish survives a worker restart), quota exhaustion → `retry_scheduled`, deadline passed → `failed`, `auth_revoked` at due time → `on_hold`, cancel during `publishing` → 409, published items immutable.
- **Crash test (`@commits`):** raise after the container ID commit → re-run publishes once.
- **E2E:** `scenario-c.spec.ts` (complete: fact change holds the scheduled post), `scenario-d.spec.ts`, `scenario-f.spec.ts` (failure rule via the dev API; dev "run due jobs").

## Acceptance criteria
- AC-C4, AC-D1…D8 and AC-F1…F7 pass.
- INV-06: in all publish tests, `sim_published_media` contains exactly the expected number of rows.
- INV-18: no UI state shows "Yayınlandı" before the operation is `succeeded`.

## Demo scenario
Command "Deneme dersi için bir story hazırla" → draft with overlay suggestions and the note about text in the image → upload a PNG (converted) → Approve & schedule for 2 minutes from now → *Zamanlandı* → (wait, or dev "run due jobs" after the time) → *Yayınlanıyor* → *Yayınlandı · SİMÜLASYON*. Schedule another post containing the price → change the price by command → the post moves to *Beklemede: fiyat değişti*. Set the failure rule "transient ×2" → publish → retries shown → published once.

## Known risks
- Real Story API behaviour is unverified (V-03). Story support stays behind the `publish_story_image` capability.
- Polling with heartbeat inside a job must not hold DB transactions open. Verified by code review checklist and tests.

## Explicitly excluded
Video and Reels, carousels, hashtag research, image generation, S3, real Meta.
