# Phase 8.5 Session 07 report: Inbox list and desktop workspace

Executed 2026-11-01, Europe/Istanbul. Scope: P8.5-07 only. **Implemented and locally verified; operator review and real-stack/human acceptance remain pending.**

## Baseline and scope

Started from `main@cf9ce4a` + Session 06. Read Sessions 01–06 reports, baseline decisions, CLAUDE, invariants, phase/session/specification, current roadmap, and relevant inbox contracts.

Preserved existing backend schemas, status mappings, query keys, and product routes. No live database, worker, or external network requests were used. Focused phone routes were retained while introducing the desktop list/detail structure without duplicating conversation mutation logic.

## Implemented behavior

- **Desktop List/Detail Workspace (`InboxPage.tsx`, R06):**
  - Introduces a responsive split workspace on desktop (`lg:flex` 1024px+), positioning the conversation list on the left pane (`w-full lg:w-[380px] xl:w-[420px] lg:shrink-0`) and a calm selection placeholder on the right pane with clear guidance (`t("convo.selectConversation")`).
  - Retains focused single-view layout on phone (< 1024px) routing directly to `/w/:id/inbox/:conversationId`.
- **Conversation List & Filters (`ConversationList.tsx`, I01):**
  - Canonical filters (`any`, `needs_approval`, `needs_human`, `failed`) implemented with accessible `role="tablist"` and `role="tab"` buttons with `aria-selected` state.
  - Filter selection is synchronized with `URLSearchParams` (`?attention=...`) so back/forward browser navigation and external deep links preserve the active filter view.
  - Selected row state (`activeId` matching conversation) with highlighted styling (`bg-indigo-50/90 ring-2 ring-indigo-600 shadow-xs`) and `aria-current="true"`.
  - Customer identity hierarchy: circular initials avatar derived from customer handle or customer number, customer name/handle with overflow handling, and truncated last message preview.
  - Clear attention badges (`data-testid="attention-chip"`), human takeover indicator (`t("convo.handledByYou")`), 24h reply window countdown timer (`<WindowTimer />`), and simulation badge (`<SimulatedBadge />`).
  - Empty and error fallbacks using semantic `<EmptyState>` and `<ErrorMessage>` components.

## Verification

Commands were run individually from `frontend/`:

| Check | Observed final result |
|---|---|
| `npm.cmd run lint` | Exit 0; no findings |
| `npm.cmd run typecheck` | Exit 0; no TypeScript errors |
| `npm.cmd test` | Exit 0; 39 files, 566 tests pass |
| `npm.cmd run i18n:check` | Exit 0; EN/TR 1471 keys, 925 literal calls verified |
| `npm.cmd run build` | Exit 0; 280 modules transformed |
| `node scripts/ui-inbox.mjs` | Exit 0; 8 production fixture scenarios across Chromium & WebKit |
| `git diff --check` from root | Exit 0; clean line endings |

Unit test additions:
- Added filter tab switching test asserting query URL parameter propagation in `inbox.test.tsx`.
- Added long customer name wrapping and error handling test in `inbox.test.tsx`.

Playwright fixture script `frontend/scripts/ui-inbox.mjs`:
- Tested production build against preview server across Chromium and WebKit.
- Evaluated 4 viewport/locale combinations: TR 360 phone, EN 390 phone, TR 768 tablet, EN 1440 desktop.
- Evaluated desktop list/detail structure (placeholder panel visibility at 1440px).
- Ran automated Axe accessibility scans under tags `["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]`.
- Result: **0 Axe violations** across all scenarios.
- Evaluated document width against viewport width (`scrollWidth === innerWidth`): **0 horizontal overflow**.
- Recorded evidence in `docs/implementation/phase-8.5-sessions/evidence/s07/inbox.json` and 8 viewport PNG captures.

Bundle impact (measured with Node `gzipSync`):
- Production JS: 857,876 bytes / 248,189 gzip (vs S06: 855,510 / 247,519 -> +2,366 raw / +670 gzip).
- Production CSS: 42,897 bytes / 9,110 gzip (vs S06: 40,657 / 8,896 -> +2,240 raw / +214 gzip).
- Local fonts: 173,280 bytes unchanged.
- Total gzip JS change is well below the 50KiB review threshold.

## Acceptance and handoff

- Updated R06 and I01 in `screen-coverage.md`.
- Ready for Session 08 (Conversation, grounded drafts and composer).

