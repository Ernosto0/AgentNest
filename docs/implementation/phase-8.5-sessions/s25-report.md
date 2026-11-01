# Phase 8.5 Session 25 report: Operational health, developer tools and fallbacks

Executed 2026-11-01, Europe/Istanbul. Scope: P8.5-25 only (Routes R30–R31, R33, Controls U08–U10). **Implemented and locally verified; operator review and real-stack/human acceptance remain pending.**

## Baseline and scope

Started from Session 24. Read Sessions 01–24 reports, baseline decisions, CLAUDE, invariants, phase/session/specification, and relevant health, developer tooling, and fallback error handling contracts.

Preserved existing backend schemas, status mappings, query keys, and product routes. No live database, worker, or external network requests were used.

Canonical invariant enforcement:
- **Operational Health Diagnostics & Scope Gating**: System health dashboard is restricted to owners and managers (`role === "owner" || role === "manager"`). It provides diagnostics across connected Instagram accounts, operations, asynchronous background workers/jobs, incoming webhooks, and AI execution/token telemetry.
- **Truthful Absence vs Zero**: System health faithfully distinguishes between missing, zero, and unavailable values (e.g. `jobs.oldest_queued_age_seconds === null` indicates empty queue, distinct from 0 seconds).
- **Developer Tooling Flag Guarding**: Developer panel is accessible only when `demo_tools_enabled` is true on the server metadata endpoint (`GET /api/v1/meta`). In production mode or when demo tools are disabled, the route is barred and hidden from navigation menus.
- **Controlled Failure Simulation & Reset Safety**: Developer panel provides simulation triggers for customer messages, configurable failure rules across API operations, background job execution, and a destructive reset flow. The reset modal requires deliberate confirmation, replaces the demo workspace with a fresh ID, and invalidates cached data.
- **Robust 404 & Loading Fallbacks**: Both global and workspace-scoped non-existent routes resolve cleanly to `NotFoundPage`, offering a graceful return link to workspace selection with no confusing HTTP 403 authorization leaks.

## Implemented behavior

- **System Health Screen (`SystemHealth.tsx`, R30, U08):**
  - Modernized with semantic design tokens (`bg-canvas`, `bg-surface`, `text-primary`, `font-heading`, `rounded-panel`, `text-secondary`, `border-border`).
  - Refresh button with busy state and workspace clock generation timestamp.
  - Accounts section displaying status pills, degraded notices, connection expiration dates, and quick management links.
  - Operations section showing counts by operation type and status, alongside the latest failure log with decrypted error codes and simulation badges.
  - Background jobs card reporting queued jobs, oldest job age in human units (seconds, minutes, hours), and dead jobs over 24 hours.
  - Webhooks telemetry card displaying received, ignored, failed, and signature failure statistics with security guidance hints.
  - AI runs card summarizing execution counts by task/status, total runs, failure rate percentage, input/output token units, cost in USD, and monthly budget utilization.
- **Developer Panel (`DevPanel.tsx`, R31, U09–U10):**
  - Customer simulation card dispatching predefined multi-lingual mock conversations.
  - Failure rule injection card with operation and mode selectors.
  - Published media simulator log with auto-refresh and simulated badges.
  - Background job runner and health-check diagnostic triggers.
  - Destructive demo reset flow with `BottomSheet` confirmation.
- **Fallback Screens (`NotFoundPage.tsx`, `FullScreenStatus.tsx`, R33):**
  - Responsive empty state with clear guidance and styled navigation back button.

## Verification

Commands were run individually from `frontend/`:

| Check | Observed final result |
|---|---|
| `npm.cmd run lint` | Exit 0; no findings |
| `npm.cmd run typecheck` | Exit 0; no TypeScript errors |
| `npm.cmd test` | Exit 0; 41 files, 582 tests pass (including 12 in `systemHealth.test.tsx` and `dev.test.tsx`) |
| `npm.cmd run i18n:check` | Exit 0; EN/TR 1496 keys, 963 literal calls verified |
| `npm.cmd run build` | Exit 0; 281 modules transformed in 590ms |
| `node frontend/scripts/ui-health-dev.mjs` | Exit 0; 8 production fixture scenarios across Chromium & WebKit |
| `git diff --check` from root | Exit 0; clean line endings |

Playwright fixture script `frontend/scripts/ui-health-dev.mjs`:
- Tested production preview build across Chromium and WebKit engines.
- Evaluated 4 viewport/locale/role combinations: TR 360 phone (owner), EN 390 phone (owner), TR 768 tablet (manager), EN 1440 desktop (owner).
- Navigated to `/w/:ws/more/settings/system-health`, `/w/:ws/more/dev`, and non-existent fallback route `/w/:ws/non-existent-page`.
- Verified health metric cards, simulator script controls, failure injection selects, and 404 heading resolution.
- Ran automated Axe accessibility audits under tags `["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]`.
- Result: **0 Axe violations** across all scenarios.
- Evaluated document width against viewport width (`scrollWidth <= clientWidth + 1`): **0 horizontal overflow**.
- Recorded evidence in `docs/implementation/phase-8.5-sessions/evidence/s25/health-dev.json` and 8 viewport PNG captures.

Bundle impact (measured with Node `gzipSync`):
- Production JS: 900,043 bytes / 253,837 gzip.
- Production CSS: 47,277 bytes / 9,711 gzip.
