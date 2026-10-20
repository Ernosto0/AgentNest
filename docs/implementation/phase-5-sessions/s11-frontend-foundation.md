# Session 11: Frontend foundation (types, routes, list, card, editor, upload)

**Plan:** `plan.md` §3 **P5-08 (part 1)**. **Depends on:** session 10 (stable OpenAPI). **Commit:** `P5-08a: …`.

## Read first
`component-design.md`, `user-journeys.md` J4, `frontend/src/` structure (an existing feature such as `features/inbox` as template: hooks, `mockApi` in tests, `StatusBadge`, `SimulatedBadge`, `FactChip`), `app/router.tsx`, `app/app.test.tsx`, i18n setup and `i18n:check`, `docs/product/` copy conventions (Turkish-first, mobile-first).

## Build
- Regenerate `openapi.json` / `schema.d.ts` (backend dump script per local-development); extend `api/types.ts`.
- `i18n/index.ts`: new `content.json` (tr/en); **move `content.title` into it** (shallow merge).
- Routes `content` and `content/:id` replace the placeholder (update `app.test.tsx:111`).
- `ContentPage` with tabs (G15): Drafts = draft + pending_approval; Scheduled = scheduled + publishing + retry_scheduled; Published; Problems = on_hold + failed + rejected. `cancelled` hidden.
- `ContentCard` with `StatusBadge` + `SimulatedBadge`.
- `content/status.ts` status mapping: `publishing` + op `outcome_unknown` → "Kontrol ediliyor"; `retry_scheduled` → "Tekrar denenecek {{time}}"; **only `published` → "Yayınlandı"** (INV-18).
- `ContentEditor`: feed (caption + counter); story (overlay suggestions + note "metin görselin üzerinde olmalı"); inline validation issues and fact chips (reuse `FactChip`); sends `expected_version`; handles `VERSION_CONFLICT` (409) by reloading with a message.
- `MediaUpload`: upload, preview via `/media/{id}/content` (authenticated fetch, blob URL), warnings, error mapping for `MEDIA_INVALID` / `MEDIA_TOO_LARGE`.
- `hooks.ts` (TanStack Query) for list/get/create/patch/validate/upload.

## Done when
- Vitest per component with `mockApi`: INV-18 badge table (every status → label, "Yayınlandı" only for `published`), `expected_version` sent, 409 handling, tab membership, upload error states.
- `npm run lint ; npm run typecheck ; npm test ; npm run i18n:check` green; OpenAPI drift check clean.
