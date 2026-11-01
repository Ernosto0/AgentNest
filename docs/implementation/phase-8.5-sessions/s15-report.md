# Phase 8.5 Session 15 report: Owner questions

Executed 2026-11-01, Europe/Istanbul. Scope: P8.5-15 only (Routes R13 & R14, Controls Q01–Q02). **Implemented and locally verified; operator review and real-stack/human acceptance remain pending.**

## Baseline and scope

Started from Session 14. Read Sessions 01–14 reports, baseline decisions, CLAUDE, invariants, phase/session/specification, and relevant owner questions contracts.

Preserved existing backend schemas, status mappings, query keys, and product routes. No live database, worker, or external network requests were used.

Canonical invariant enforcement:
- Information-only boundary: answering an owner question provides business context and knowledge; it never approves a pending reply or schedules an operation (`t("agentWork.informationOnly")`).
- Role boundaries & proposal separation: owners and managers provide authoritative answers (`kind: "answer"`, `submitAnswer`); staff members submit suggestions (`kind: "proposal"`, `proposeAnswer`). Staff never see or trigger reusable knowledge candidate controls.
- Reusable knowledge opt-in & validation: only answers to customer-facing questions (`visibility === "customer_reply"`) by owners/managers can be saved as knowledge candidates. Keys strictly validate pattern `^[a-z][a-z0-9_]{0,60}$`.
- Version conflict & idempotency protection: mutation payload enforces `expected_version` binding with `client_request_id` (`newRequestId()`). On version conflicts (409), user input is strictly preserved in the textarea to prevent data loss.
- Expiration and lifecycle truthfulness: expired questions cannot be answered and render an explicit status badge; answered questions link to the recorded history list.

## Implemented behavior

- **Questions Queue (`QuestionsPage.tsx` / `QuestionList.tsx`, R13, Q01):**
  - Responsive layout utilizing design tokens (`bg-canvas`, `bg-surface`, `text-primary`, `font-heading`, `rounded-control`, `text-secondary`, `text-action`).
  - Account query filter preserving selected Instagram account in navigation.
  - Question cards displaying question text with redacted/removed safe fallback, `WorkState` status badges (`pending`, `answered`, `expired`, `redacted`), and localized expiration time in workspace timezone.
  - Empty state notice and cursor pagination.
- **Question Detail (`QuestionPage.tsx` / `QuestionDetail.tsx`, R14, Q02):**
  - Prominent information disclosure alert box.
  - Question detail card rendering full customer question, state badge, visibility label, deadline timestamp, and customer memory deep link (`/more/agent/memory/:customerId`).
  - Role-adaptive answer composer:
    - Textarea with character limits (500 with reuse, 700 standard).
    - Reusable knowledge checkbox toggle and validated key field.
    - Submit button: "Bilgi yanıtını kaydet" / "Save information answer" for owners/managers, "Öneriyi kaydet" / "Save proposal" for staff.
    - Idempotent request ID and expected version binding.
    - Preservation of typed input on error.
  - Answer history card with chronological prior entries, author role badges, proposal tags, candidate markers, pagination, and direct links to `/approvals`.

## Verification

Commands were run individually from `frontend/`:

| Check | Observed final result |
|---|---|
| `npm.cmd run lint` | Exit 0; no findings |
| `npm.cmd run typecheck` | Exit 0; no TypeScript errors |
| `npm.cmd test` | Exit 0; 39 files, 567 tests pass |
| `npm.cmd run i18n:check` | Exit 0; EN/TR 1476 keys, 936 literal calls verified |
| `npm.cmd run build` | Exit 0; 281 modules transformed |
| `node frontend/scripts/ui-questions.mjs` | Exit 0; 8 production fixture scenarios across Chromium & WebKit |
| `git diff --check` from root | Exit 0; clean line endings |

Playwright fixture script `frontend/scripts/ui-questions.mjs`:
- Tested production preview build across Chromium and WebKit engines.
- Evaluated 4 viewport/locale combinations: TR 360 phone, EN 390 phone, TR 768 tablet, EN 1440 desktop.
- Navigated to `/w/:ws/more/agent/questions?account=:id`, verified account switcher, question queue item, status badge, and expiration countdown.
- Navigated to `/w/:ws/more/agent/questions/q-test-1?account=:id`, verified information disclosure, question detail card, customer memory link, answer composer, knowledge candidate reuse checkbox and key input, and answer history list.
- Ran automated Axe accessibility audits under tags `["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]`.
- Result: **0 Axe violations** across all scenarios.
- Evaluated document width against viewport width (`scrollWidth <= clientWidth + 1`): **0 horizontal overflow**.
- Recorded evidence in `docs/implementation/phase-8.5-sessions/evidence/s15/questions.json` and 16 viewport PNG captures.

Bundle impact (measured with Node `gzipSync`):
- Production JS: 877,090 bytes / 252,960 gzip (vs S14: 874,340 / 252,680 -> +2,750 raw / +280 gzip).
- Production CSS: 46,130 bytes / 9,670 gzip (vs S14: 46,130 / 9,670 -> unchanged).
- Local fonts: 173,280 bytes unchanged.
- Total gzip JS change remains well below the 50KiB review threshold.

## Acceptance and handoff

- Updated rows R13, R14, Q01, and Q02 in `screen-coverage.md`.
- Concludes Session 15. All Sessions 11 through 15 are implemented, verified, and recorded.

