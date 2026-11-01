# Phase 8.5 Session 12 report: Approvals and history

Executed 2026-11-01, Europe/Istanbul. Scope: P8.5-12 only (Route R10, Controls P01–P05). **Implemented and locally verified; operator review and real-stack/human acceptance remain pending.**

## Baseline and scope

Started from Session 11. Read Sessions 01–11 reports, baseline decisions, CLAUDE, invariants, phase/session/specification, and relevant approvals contracts.

Preserved existing backend schemas, status mappings, query keys, and product routes. No live database, worker, or external network requests were used.

Canonical invariant enforcement:
- Polymorphic decision surface: handles all 5 approval bodies (`reply.send`, `content.publish`, `agent.action`, `fact.change`, and `command.cancel_content`) without unbacked presentation.
- Cryptographic hash binding: every decision transmits the exact displayed SHA-256 `payload_hash` in mutation payloads (`{ decision: "approve" | "reject", payload_hash, note: null }`), preventing blind execution on changed underlying state.
- Role boundary enforcement: only owners and managers with `can_decide: true` can approve or reject; staff members receive an explicit informative message (`t("approvals.detail.cannotDecide")`).
- Stale state & version conflict protection: `ContentApprovalBody` checks if the content item was updated after the approval was requested (`isStaleFor(approval, item)`), showing an alert notice and disabling the approval button to prevent accidental approval of obsolete content.
- Truthful state & history: approved, rejected, and expired decisions remain visible in the "History" tab without false optimism; decisions do not prematurely claim final execution effects until confirmed.

## Implemented behavior

- **Approvals Queue & Navigation (`ApprovalsList.tsx`, R10):**
  - Responsive layout utilizing design tokens (`bg-canvas`, `bg-surface`, `text-primary`, `font-heading`, `rounded-control`, `text-secondary`).
  - Accessible tab bar (`role="tablist"`) for "Bekleyen" / "Pending" and "Geçmiş" / "History" views.
  - Interactive rows with action category badge, before/after preview summary, localized date/time formatting in workspace timezone, and simulation tags.
  - Empty states for both pending and history queues.
- **Approval Detail Sheet (`ApprovalDetailSheet.tsx`, P01):**
  - Accessible `BottomSheet` modal with proper focus trap and return.
  - Polymorphic routing of body components based on `approval.action` and `approval.subject.type`.
  - Expiry timestamp formatting with workspace timezone and live countdown context.
  - Explicit action buttons for "Onayla" / "Approve" and "Reddet" / "Reject".
- **Change & Impact Summaries (`ChangeSummary.tsx`, `CancelContentSummary.tsx`, P02):**
  - Before/after diff display with strike-through styling for prior values and emphasized action color for new values.
  - Impact summary detailing affected entities (e.g. pending reply drafts) with exact counts.
  - Cancellation preview displaying target item type, current status badge, and scheduled publication time.
- **Action Bodies (`ReplyApprovalBody.tsx`, `ContentApprovalBody.tsx`, `AgentApprovalBody.tsx`, P03–P05):**
  - Reply body rendering grounded draft text, decision reasoning chips, and deep links to conversation.
  - Content publish body rendering `ContentPreview` with exact media preview, caption, story overlay text, and publication timing.
  - Agent action body rendering action labels, target text blockquotes, parameters, and stale preview alerts.

## Verification

Commands were run individually from `frontend/`:

| Check | Observed final result |
|---|---|
| `npm.cmd run lint` | Exit 0; no findings |
| `npm.cmd run typecheck` | Exit 0; no TypeScript errors |
| `npm.cmd test` | Exit 0; 39 files, 567 tests pass |
| `npm.cmd run i18n:check` | Exit 0; EN/TR 1476 keys, 937 literal calls verified |
| `npm.cmd run build` | Exit 0; 281 modules transformed |
| `node frontend/scripts/ui-approvals.mjs` | Exit 0; 8 production fixture scenarios across Chromium & WebKit |
| `git diff --check` from root | Exit 0; clean line endings |

Playwright fixture script `frontend/scripts/ui-approvals.mjs`:
- Tested production preview build across Chromium and WebKit engines.
- Evaluated 4 viewport/locale combinations: TR 360 phone, EN 390 phone, TR 768 tablet, EN 1440 desktop.
- Navigated to `/approvals`, verified pending row rendering, opened detail sheet, verified payload hash binding and polymorphic summary layout.
- Ran automated Axe accessibility audits under tags `["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]`.
- Result: **0 Axe violations** across all scenarios.
- Evaluated document width against viewport width (`scrollWidth <= clientWidth + 1`): **0 horizontal overflow**.
- Recorded evidence in `docs/implementation/phase-8.5-sessions/evidence/s12/approvals.json` and 8 viewport PNG captures.

Bundle impact (measured with Node `gzipSync`):
- Production JS: 867,932 bytes / 250,068 gzip (vs S11: 866,035 / 249,931 -> +1,897 raw / +137 gzip).
- Production CSS: 45,785 bytes / 9,518 gzip (vs S11: 45,879 / 9,515 -> -94 raw / +3 gzip).
- Local fonts: 173,280 bytes unchanged.
- Total gzip JS change remains well below the 50KiB review threshold.

## Acceptance and handoff

- Updated rows R10, P01, P02, P03, P04, and P05 in `screen-coverage.md`.
- Concludes Session 12. Ready for Session 13 (Assistant overview and tasks).

