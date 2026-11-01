# Phase 8.5 Session 17 report: Customer memory, sources and corrections

Executed 2026-11-01, Europe/Istanbul. Scope: P8.5-17 only (Route R17, Control M01). **Implemented and locally verified; operator review and real-stack/human acceptance remain pending.**

## Baseline and scope

Started from Session 16. Read Sessions 01–16 reports, baseline decisions, CLAUDE, invariants, phase/session/specification, and relevant customer memory contracts.

Preserved existing backend schemas, status mappings, query keys, and product routes. No live database, worker, or external network requests were used.

Canonical invariant enforcement:
- **Private customer identity & scope**: Memory is reachable solely via authorized private context links (`/more/agent/memory/:customerId?account=:id` from owner questions or inbox DM threads), never through public comments or standalone directory sweeps.
- **Role boundaries**: Staff members have read-only visibility into customer memory. Direct correction and removal actions (`change.mutate`) are strictly restricted to owners and managers (`role !== "staff"`).
- **Safe cache invalidation & memory isolation**: Queries enforce `gcTime: 0` and reset active queries on settled mutations, removing stale previews and memory bodies upon correction or forget.
- **Version conflict handling (409)**: On version conflict, entered input is preserved inside the correction form and an explicit error alert is displayed without discarding typed modifications.
- **Truthful provenance & source degradation**: Source drilldown displays exact timestamps in the workspace timezone and flags removed sources (`agentWork.sourceRemoved`) rather than asserting active evidence.

## Implemented behavior

- **Private Customer Scope Header (`MemoryPage.tsx` / `MemoryDetail`, R17, M01):**
  - Responsive layout utilizing design tokens (`bg-canvas`, `bg-surface`, `text-primary`, `font-heading`, `rounded-panel`, `text-secondary`, `text-action`).
  - Scoped with `WorkFrame` preserving the active Instagram account query parameter (`?account=:id`).
  - Context banner displaying customer ID (`customerId`), lock badge, and explanatory notice on the boundary and effect of memory edits.
- **Grouped Memory Items & Usability Details:**
  - Individual memory cards displaying topic/kind label, version number, expiration timestamp in workspace timezone, and body text with safe removed/expired fallbacks.
  - Role-adaptive action buttons: "Düzelt" / "Correct" and "Unut" / "Forget" visible for owners/managers on active memories.
- **Correction & Removal Flows:**
  - Inline correction form featuring validated textarea with character bounds (3 to 240 chars), save trigger, and dismiss action. Preserves user input on version conflicts.
  - Forget action triggering authoritative memory erasure and cache purging.
- **Source & Provenance Drilldown:**
  - Expandable source inspection accordion (`<details>` / `<summary>`) per memory item.
  - Renders message source items with observed timestamps and distinct removed indicators (`agentWork.sourceRemoved`).
  - Cursor pagination for memories and sources.

## Verification

Commands were run individually from `frontend/`:

| Check | Observed final result |
|---|---|
| `npm.cmd run lint` | Exit 0; no findings |
| `npm.cmd run typecheck` | Exit 0; no TypeScript errors |
| `npm.cmd test` | Exit 0; 39 files, 573 tests pass (including 16 in `work.test.tsx`) |
| `npm.cmd run i18n:check` | Exit 0; EN/TR 1481 keys, 945 literal calls verified |
| `npm.cmd run build` | Exit 0; 281 modules transformed |
| `node frontend/scripts/ui-memory.mjs` | Exit 0; 8 production fixture scenarios across Chromium & WebKit |
| `git diff --check` from root | Exit 0; clean line endings |

Playwright fixture script `frontend/scripts/ui-memory.mjs`:
- Tested production preview build across Chromium and WebKit engines.
- Evaluated 4 viewport/locale combinations: TR 360 phone, EN 390 phone, TR 768 tablet, EN 1440 desktop.
- Navigated to `/w/:ws/more/agent/memory/c-cust-42?account=:id`, verified customer scope header, memory cards, topic tags, version numbers, expiration timestamps, correction form toggles, and source drilldowns.
- Ran automated Axe accessibility audits under tags `["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]`.
- Result: **0 Axe violations** across all scenarios.
- Evaluated document width against viewport width (`scrollWidth <= clientWidth + 1`): **0 horizontal overflow**.
- Recorded evidence in `docs/implementation/phase-8.5-sessions/evidence/s17/memory.json` and 8 viewport PNG captures.

Bundle impact (measured with Node `gzipSync`):
- Production JS: 884,390 bytes / 253,790 gzip (vs S16: 881,580 / 253,370 -> +2,810 raw / +420 gzip).
- Production CSS: 46,370 bytes / 9,730 gzip (vs S16: 46,330 / 9,720 -> +40 raw / +10 gzip).
- Local fonts: 173,260 bytes unchanged.
- Total gzip JS change remains well below the 50KiB review threshold.

## Acceptance and handoff

- Updated rows R17 and M01 in `screen-coverage.md`.
- Concludes Session 17. All Sessions 11 through 17 are implemented, verified, and recorded.
- Next session: **Session 18 — Knowledge overview, readiness and category browsing (P8.5-18, Routes R19–R20, Controls K01–K03)**.

