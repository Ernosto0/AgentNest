# Core UI/UX redesign verification

Date: 2026-11-07. Baseline: `2155931d4b25cec5508d22aa06d3044bf9960b16`. Scope is the core redesign requested for Today, Inbox, Approvals, Assistant, information questions and content editing. Secondary workflows inherit the shared visual system. No deployment, real message, real publication, commit or push is part of this change.

## Resulting experience

- Today puts blocking account issues and actionable work before request entry, upcoming posts and the daily summary. Current counts, capped previews and unavailable data remain distinct. Completed setup disappears; completed requirements within an incomplete setup are collapsed.
- Inbox keeps Messages, Comments and Questions together. Existing question/comment routes and notification targets remain valid. At 1200 px and above a 320 px list remains beside the selected record. Narrower layouts retain filters and list position when returning. Draft decisions are beside the reply workflow; manual composition opens separately. Export/erase remain owner-only and keep their confirmations.
- Contextual questions use the scoped agent-thread UUID. Contextual approvals reuse the queue summary and decision sheet with exact approval/action IDs. Public comment views mount no private messages, customer-memory or owner-question requests.
- Information answers offer “Save for future answers” with an internal stable UUID-based key. Reuse creates an unverified candidate; it does not approve an Instagram action or verify knowledge.
- Assistant has Overview, Voice, Permissions and History URLs. Requests come first. Every permission remains independently configurable; advanced limits and request sources start collapsed. Controller and permission changes retain explicit reviews.
- Content has a persistent approximate desktop preview and mobile Edit/Preview views. Local caption edits are visible immediately. The publishing account and existing content format are read-only: submission uses the workspace’s single active account, and published previews use the recorded account. Save, Review and Schedule are grouped; unsaved text blocks scheduling. Immutable content, media deletion, validation and timezone semantics are retained.
- Warm canvas, charcoal green navigation, sage assistant surfaces, local Inter/Manrope fonts and flatter working areas apply through shared components. Mobile destination search is in More; notifications remain in the header bell. The mobile header scrolls with the page so it cannot cover draft actions during keyboard use.

## Verification

| Check | Evidence |
|---|---|
| Frontend unit/integration tests | 601 passed, including explicit public/DM surface separation; final machine-readable summary in `checks/frontend-tests.json` |
| Backend owner-question API and continuation tests | 16 passed, including owner/manager/staff visibility, filtered pagination, same-account other thread, foreign account/workspace and invalid thread rejection |
| Real local API/worker browser check | 3 passed: mobile WebKit, mobile Chromium, desktop Chromium; goals, delegation review/application and controller transitions |
| Typecheck, lint, localization, build | Final results in `checks/`; localization covers English/Turkish |
| Production fixture browser matrix | `after/results.json`; Chromium and WebKit, EN/TR, 360, 390, 768, 1024, 1440 and 1920 px; core layout, axe, unclipped controls and runtime errors |
| Stateful fixture walkthroughs | Reply edit/approve; linked information answer and generated key; assistant request/progress; permission preview/application; save/review/schedule; explicit public moderation; expired drafts; dirty navigation; unavailable media; partial API failures; quiet/ready and account/publishing failure states |
| Short-screen keyboard/focus | 390×420 layout viewport; unsent text survives cancelled navigation; Tab reaches the manual-send control above phone navigation |
| Zoom/reflow | 720×450 layout viewport proxy for a 1440×900 window at 200% browser zoom; actual browser zoom and an actual phone remain human review items |

`before/results.json` records all four baseline suites passing in both browsers (32 scenarios). Baseline captures use the original fixture scripts; current captures use a unified core fixture. Fixture names/content differ, so these are structural and workflow comparisons, not identical-data pixel diffs.

Representative captures:

| Surface | Before | Current desktop | Current phone |
|---|---|---|---|
| Today | [Baseline captures](before/today/) | [EN 1440](after/chromium-en-1440-today.png) | [TR 390](after/chromium-tr-390-today.png) |
| Inbox | [Baseline captures](before/conversation/) | [EN 1440](after/chromium-en-1440-inbox.png) | [TR 390](after/chromium-tr-390-inbox.png) |
| Assistant | [Baseline captures](before/voice-delegation/) | [EN overview](after/chromium-en-1440-assistant.png) | [TR permissions](after/chromium-tr-390-assistant-permissions.png) |
| Content | [Baseline captures](before/content-detail/) | [EN editor](after/chromium-en-1440-content-edit.png) | [TR preview](after/chromium-tr-390-content-preview.png) |

## Environment and evidence boundaries

The baseline and visual browser runs use the production Vite bundle with intercepted APIs. All fixture mutations affect an in-memory fixture ledger. Browser versions and successful capture/check records are in `after/results.json`. The separate stack browser test uses the actual API, worker and a seeded disposable database with fake models and mock Instagram.

Docker Desktop could not start. Backend verification used an isolated local PostgreSQL 17 cluster bound to `127.0.0.1:55433`, with a new `agentnest_core_ui_test` database. The configured development/default database was not reseeded. The cluster is stopped after verification. The initial backend run exposed test-environment provider configuration and a fixture account uniqueness mistake; these were corrected before the complete 16-test selection was rerun successfully.

Only the optional owner-question `thread_id` query contract is changed; no migration is added. Generated OpenAPI/client diffs contain only that addition. A full runtime OpenAPI export also exposed two pre-existing Telegram webhook paths absent from the checked-in baseline; those unrelated paths were excluded from this scoped contract change.

The production JS bundle grows from 971.84 kB to 989.66 kB before gzip; the existing large-chunk warning remains. No new package, external font or runtime image service is introduced. Existing jsdom scroll/download-navigation notices are distinct from browser runtime errors and test failures.

Separate pricing-document changes in `docs/README.md` and `docs/product/pricing-and-unit-economics.md` appeared during final inspection. This task did not edit or stage them.

## Owner walkthrough

Implementation and automated verification precede owner review. Human sign-off has not been recorded. On Windows and an actual phone, review:

1. Open Today: pending work is immediately visible, and missing data never looks like zero.
2. Open a conversation: desktop retains its list; approve/edit a draft, and distinguish a queued result from verified delivery.
3. Answer a linked question and opt into reuse: no technical key is exposed, and knowledge still needs its existing review.
4. Inspect a public comment, its post context and a moderation confirmation without exposing private customer context.
5. Submit/follow an assistant request, inspect History, and review an individual permission change before applying it.
6. Prepare, save, review and schedule a post; inspect local edits in Preview, unavailable media and unsaved-change protection.
7. Check a short phone screen with its real keyboard, browser Back, language expansion and actual 200% browser zoom. Primary controls must remain reachable.

Real Instagram capability/delivery, real-model quality, owner sign-off and actual-device acceptance remain separate from these offline results. Broader historical Phase 8.5 acceptance is not asserted.
