# Phase 8.5 Session 24 report: Instagram connections, members and invitations

Executed 2026-11-01, Europe/Istanbul. Scope: P8.5-24 only (Routes R28–R29, Controls U02–U07). **Implemented and locally verified; operator review and real-stack/human acceptance remain pending.**

## Baseline and scope

Started from Session 23. Read Sessions 01–23 reports, baseline decisions, CLAUDE, invariants, phase/session/specification, and relevant OAuth, connection lifecycle, and membership management contracts.

Preserved existing backend schemas, status mappings, query keys, and product routes. No live database, worker, or external network requests were used.

Canonical invariant enforcement:
- **Owner-Only OAuth & Connection Management**: Initiating Meta or mock Instagram connection, reconnecting degraded/needs_reauth accounts, and disconnecting accounts are strictly restricted to workspace owners (`role === "owner"`). Staff members see read-only status and capability cards.
- **Defensive OAuth Callback Processing**: The `OAuthBanner` handles callback query parameters (`oauth=connected` or `oauth=error&code=...`), only permitting catalog error codes from `OAUTH_ERRORS` to select translated copy, and preserves unrelated URL parameters upon dismissal.
- **Safe Disconnection with Data-Erase Choice**: Disconnecting an account requires explicit confirmation via `BottomSheet`. The checkbox for erasing conversation history defaults to unchecked (`false`) and is always reset on cancel.
- **Roster Role Modifications & Last-Owner Invariant**: Only owners can modify roles or remove members. The backend invariant preventing removal of the last owner is surfaced via accessible error alerts without optimistic cache corruption.
- **One-Time Invite Generation & SVG QR Codes**: Invites are generated with explicit role assignment, producing one-time invite URLs with clipboard copy and pure SVG QR codes (`qrcode.toString({ type: "svg" })`) that operate without HTML5 canvas requirements.

## Implemented behavior

- **Instagram Connections (`Connections.tsx`, R28, U02–U04):**
  - Modernized with semantic design tokens (`bg-canvas`, `bg-surface`, `text-primary`, `font-heading`, `rounded-panel`, `text-secondary`, `border-border`).
  - `OAuthBanner` styled with semantic status badges and accessible alert roles.
  - `AccountStatusBadge` updated with semantic theme tokens (`connected`, `degraded`, `needs_reauth`, `disconnected`).
  - Account card displaying account handle, simulation badge, degraded timer notice, error message explanations, and granted capabilities.
  - Reconnect and disconnect buttons with owner-only access controls and busy state management.
  - Disconnect `BottomSheet` modal with conversation data deletion checkbox and danger confirmation button.
- **Members & Invites (`Members.tsx`, R29, U05–U07):**
  - Modernized with semantic design tokens and clean roster typography.
  - Members list with display names, email addresses, "You" indicator badge, and owner-only role dropdowns.
  - Member removal modal (`RemoveSheet`) with destructive action styling.
  - Invite generation flow (`InviteSheet`) with role selection, SVG QR rendering (with fallback empty-state avoiding browser warnings), and clipboard copy.
  - Pending invitations card with formatted expiration timestamps and instant revocation controls.

## Verification

Commands were run individually from `frontend/`:

| Check | Observed final result |
|---|---|
| `npm.cmd run lint` | Exit 0; no findings |
| `npm.cmd run typecheck` | Exit 0; no TypeScript errors |
| `npm.cmd test` | Exit 0; 41 files, 582 tests pass (including 35 in `connections.test.tsx` and `members.test.tsx`) |
| `npm.cmd run i18n:check` | Exit 0; EN/TR 1496 keys, 951 literal calls verified |
| `npm.cmd run build` | Exit 0; 281 modules transformed in 793ms |
| `node frontend/scripts/ui-connections.mjs` | Exit 0; 8 production fixture scenarios across Chromium & WebKit |
| `git diff --check` from root | Exit 0; clean line endings |

Playwright fixture script `frontend/scripts/ui-connections.mjs`:
- Tested production preview build across Chromium and WebKit engines.
- Evaluated 4 viewport/locale/role combinations: TR 360 phone (owner), EN 390 phone (owner), TR 768 tablet (manager), EN 1440 desktop (staff).
- Navigated to `/w/:ws/more/settings/connections` and `/w/:ws/more/settings/members`, verified account card status, capability pills, role dropdowns, and invite controls.
- Ran automated Axe accessibility audits under tags `["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]`.
- Result: **0 Axe violations** across all scenarios.
- Evaluated document width against viewport width (`scrollWidth <= clientWidth + 1`): **0 horizontal overflow**.
- Recorded evidence in `docs/implementation/phase-8.5-sessions/evidence/s24/connections-members.json` and 8 viewport PNG captures.

Bundle impact (measured with Node `gzipSync`):
- Production JS: 897,830 bytes / 253,676 gzip.
- Production CSS: 47,112 bytes / 9,694 gzip.
