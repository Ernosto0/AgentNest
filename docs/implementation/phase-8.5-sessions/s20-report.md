# Phase 8.5 Session 20 report: Approved-answer library

Executed 2026-11-01, Europe/Istanbul. Scope: P8.5-20 only (Route R22, Control K19). **Implemented and locally verified; operator review and real-stack/human acceptance remain pending.**

## Baseline and scope

Started from Session 19. Read Sessions 01–19 reports, baseline decisions, CLAUDE, invariants, phase/session/specification, and relevant knowledge library contracts.

Preserved existing backend schemas, status mappings, query keys, and product routes. No live database, worker, or external network requests were used.

Canonical invariant enforcement:
- **Template Placeholder Grounding**: Approved answers require values to be dynamically referenced via `{{fact:category.key}}` placeholders rather than hardcoded literals. The server rejects literal prices/times (`LITERAL_VALUE`), and the UI renders grounded template code blocks with clear visual differentiation.
- **Review Requirement Awareness**: Answers marked with `needs_review` display an explicit attention badge and warning so operators know when underlying fact modifications require reviewing template answers.
- **Role boundaries**: Only owners and managers can create new approved answers or archive existing ones (`role === "owner" || role === "manager"`). Staff members see an explanatory guidance banner (`answers.staffNote`) with creation forms and archive controls hidden.
- **Save-As-Answer from Inbox**: Preserves integration with sent conversation messages in `ConversationPage.tsx`, allowing owners/managers to convert successful replies into reusable templates without manual copy-paste.

## Implemented behavior

- **Approved Answers Library (`ApprovedAnswers.tsx`, R22, K19):**
  - Modernized with semantic design tokens (`bg-canvas`, `bg-surface`, `text-primary`, `font-heading`, `rounded-panel`, `text-secondary`, `border-border`).
  - Overview return link (`← t("answers.back")`) navigating to `/w/:ws/more/knowledge`.
  - Intent category pills (`pricing`, `hours`, `faq`, `location_contact`, etc.) and language badges (`TR`, `EN`).
  - Formatted template renderer (`renderTemplatePlaceholders`) highlighting dynamic `{{fact:...}}` tags in distinct code blocks.
  - State indicator for answers requiring review (`answers.needsReview`).
  - Empty state fallback (`EmptyState`) when no approved answers exist.
- **Creation Form (Owners/Managers):**
  - Structured fields for title, customer question example, answer template with placeholder helper hint, topic/intent select, and language select.
  - Dedicated `label` and `input`/`textarea` association using semantic IDs and `aria-describedby`.
  - Literal value error notification (`t("answers.literalValue")`) with accessible alert role.
  - Archive action trigger with busy state disabling.
- **Inbox Integration (`ConversationPage.tsx`):**
  - Updated inline "Save as answer" action on sent messages with semantic theme tokens and focus styles.

## Verification

Commands were run individually from `frontend/`:

| Check | Observed final result |
|---|---|
| `npm.cmd run lint` | Exit 0; no findings |
| `npm.cmd run typecheck` | Exit 0; no TypeScript errors |
| `npm.cmd test` | Exit 0; 40 files, 578 tests pass (including 5 in `approvedAnswers.test.tsx`) |
| `npm.cmd run i18n:check` | Exit 0; EN/TR 1483 keys, 950 literal calls verified |
| `npm.cmd run build` | Exit 0; 281 modules transformed in 828ms |
| `node frontend/scripts/ui-approved-answers.mjs` | Exit 0; 8 production fixture scenarios across Chromium & WebKit |
| `git diff --check` from root | Exit 0; clean line endings |

Playwright fixture script `frontend/scripts/ui-approved-answers.mjs`:
- Tested production preview build across Chromium and WebKit engines.
- Evaluated 4 viewport/locale/role combinations: TR 360 phone (owner), EN 390 phone (owner), TR 768 tablet (manager), EN 1440 desktop (staff).
- Navigated to `/w/:ws/more/knowledge/answers`, verified header, back link, approved answer cards, topic badges, placeholder highlights, and creation form visibility according to roles.
- Ran automated Axe accessibility audits under tags `["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]`.
- Result: **0 Axe violations** across all scenarios.
- Evaluated document width against viewport width (`scrollWidth <= clientWidth + 1`): **0 horizontal overflow**.
- Recorded evidence in `docs/implementation/phase-8.5-sessions/evidence/s20/approved-answers.json` and 8 viewport PNG captures.

Bundle impact (measured with Node `gzipSync`):
- Production JS: 888,860 bytes / 254,490 gzip.
- Production CSS: 46,330 bytes / 9,720 gzip.
