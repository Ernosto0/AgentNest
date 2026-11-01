# Phase 8.5 Session 22 report: Activity feed, notification center and bell

Executed 2026-11-01, Europe/Istanbul. Scope: P8.5-22 only (Routes R25–R26, Controls E03–E04, S11). **Implemented and locally verified; operator review and real-stack/human acceptance remain pending.**

## Baseline and scope

Started from Session 21. Read Sessions 01–21 reports, baseline decisions, CLAUDE, invariants, phase/session/specification, and relevant audit log and notification catalog contracts.

Preserved existing backend schemas, status mappings, query keys, and product routes. No live database, worker, or external network requests were used.

Canonical invariant enforcement:
- **Local-Day Grouping on Workspace Clock**: Activity timeline groups entries by local day boundaries according to the workspace's configured timezone (`Europe/Istanbul` default), rendering friendly headers (`Today`, `Yesterday`, or localized date).
- **Safe Resource Links & Graceful Fallback**: Resource references in activity entries navigate directly to target entities (inbox conversation, content item) when a valid link exists, or render plain text labels when the resource is unlinked or foreign.
- **Authoritative Unread Transitions & Mark-All-Read**: Notification unread counts transition reliably upon marking all read or following a specific notification link. The notification bell and center share the authoritative unread count.
- **Defensive Target Recovery**: Every notification type in `catalog.json` (18 canonical types) maps to an authorized application route via `notificationTarget`, gracefully defaulting to parent index views when target parameters are missing or stale.
- **Restrained Live Regions & Polling Stability**: No noisy or repetitive live region announcements on background query polling.

## Implemented behavior

- **Activity Feed (`ActivityFeed.tsx`, R25, E03):**
  - Modernized with semantic design tokens (`bg-canvas`, `bg-surface`, `text-primary`, `font-heading`, `rounded-panel`, `text-secondary`, `border-border`).
  - Local-day grouped cards separating entries into chronological date blocks with uppercase headers (`Today`, `Yesterday`, or full localized date).
  - Activity type filter buttons (`ACTIVITY_GROUPS` plus `all`) with interactive active states.
  - Entry rows displaying action summary, simulation badge (`SimulatedBadge`), clickable or plain-text resource labels, and actor/timestamp provenance.
  - Cursor-based pagination with load more button and empty state handling.
- **Notification Center (`NotificationCenter.tsx`, R26, E04):**
  - Unread vs All filter button toggle.
  - Mark all as read button with pending mutation state disabling.
  - Polymorphic notification card with visual differentiation for unread items (`border-l-4 border-l-brand bg-brand/5`).
  - Severity styling with dedicated icons and labels (`info`, `attention`, `critical`).
  - Formatted workspace timezone timestamps and deep link navigation (`Aç` / `Open`).
- **Notification Bell (`NotificationBell.tsx`, S11):**
  - Redesigned with semantic tokens and touch target sizing (min 44px).
  - Unread badge counter with `9+` display for counts >= 10.
  - Accessible name containing visible label and exact unread count satisfying WCAG 2.5.3.
- **Target URL Mapper (`target.ts`):**
  - Defensively validates parameters and maps all 18 catalog types to inbox, content, knowledge, approvals, questions, reports, and settings.
- **Localization (`activity.json`, `ai.json`):**
  - Added `today` and `yesterday` keys in both Turkish and English namespaces.
  - Fixed legacy UTF-8 character encoding artifacts in Turkish strings.

## Verification

Commands were run individually from `frontend/`:

| Check | Observed final result |
|---|---|
| `npm.cmd run lint` | Exit 0; no findings |
| `npm.cmd run typecheck` | Exit 0; no TypeScript errors |
| `npm.cmd test` | Exit 0; 40 files, 578 tests pass (including 15 in `activity.test.tsx` and `notifications.test.tsx`) |
| `npm.cmd run i18n:check` | Exit 0; EN/TR 1485 keys, 951 literal calls verified |
| `npm.cmd run build` | Exit 0; 281 modules transformed in 650ms |
| `node frontend/scripts/ui-activity.mjs` | Exit 0; 8 production fixture scenarios across Chromium & WebKit |
| `git diff --check` from root | Exit 0; clean line endings |

Playwright fixture script `frontend/scripts/ui-activity.mjs`:
- Tested production preview build across Chromium and WebKit engines.
- Evaluated 4 viewport/locale/role combinations: TR 360 phone (owner), EN 390 phone (owner), TR 768 tablet (manager), EN 1440 desktop (staff).
- Navigated to `/w/:ws/more/activity` and `/w/:ws/more/notifications`, verified local-day grouped cards, filter buttons, unread counters, severity badges, and bell indicators.
- Ran automated Axe accessibility audits under tags `["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]`.
- Result: **0 Axe violations** across all scenarios.
- Evaluated document width against viewport width (`scrollWidth <= clientWidth + 1`): **0 horizontal overflow**.
- Recorded evidence in `docs/implementation/phase-8.5-sessions/evidence/s22/activity-notifications.json` and 8 viewport PNG captures.

Bundle impact (measured with Node `gzipSync`):
- Production JS: 891,371 bytes / 252,879 gzip.
- Production CSS: 46,250 bytes / 9,610 gzip.
