# Phase 8.5 Session 19 report: Typed fact editors, extraction, suggestions & history

Executed 2026-11-01, Europe/Istanbul. Scope: P8.5-19 only (Routes R20–R21, Controls K04–K18). **Implemented and locally verified; operator review and real-stack/human acceptance remain pending.**

## Baseline and scope

Started from Session 18. Read Sessions 01–18 reports, baseline decisions, CLAUDE, invariants, phase/session/specification, and relevant knowledge contracts.

Preserved existing backend schemas, status mappings, query keys, and product routes. No live database, worker, or external network requests were used.

Canonical invariant enforcement:
- **11 Typed Editors**: Fully supported and modernized with semantic design tokens: `money`, `weekly_hours`, `text`, `localized_text`, `phone`, `email`, `address`, `url`, `boolean`, `enum`, and `string_list`.
- **Role boundaries**: Staff members editing or creating facts have their submissions routed as candidates/suggestions (`202 Accepted`) rather than directly modifying verified facts; only owners and managers can verify or resolve candidates.
- **Input preservation on conflict (409)**: On version conflict or API failure, entered inputs inside `FactEditorSheet` and `PasteExtractSheet` are strictly retained without discarding typed modifications.
- **Immutable version history**: Fact revisions are displayed as immutable chronological versions with exact timestamps formatted in the workspace timezone, change kinds, actor attribution, and revision reasons.
- **Truthful suggestions triage**: Suggestions screen exposes candidate relationships (`contest`, `discrepancy`, `new`), proposed vs current values, source excerpts, and prompt-injection safety notices.

## Implemented behavior

- **Fact Editor Sheet (`FactEditorSheet.tsx`, R20, K04):**
  - Modernized with semantic design tokens (`bg-surface`, `text-primary`, `text-secondary`, `rounded-card`, `border-border`, `bg-attention-subtle`).
  - Supports both creation of named/pattern facts and version-tracked updates of existing facts.
  - Validity date range inputs (`valid_from`, `valid_until`) and revision reason tracking.
  - Displays field-level error messages mapped from API error payloads.
- **All 11 Typed Editors (`editors/`, K05–K15):**
  - `MoneyEditor`: Amount parsing with Turkish/English decimal conventions, ambiguous notation disambiguation selector, unit dropdown, and localized condition textareas.
  - `HoursEditor`: Weekday toggle chips (`mon`..`sun`) with pill styling, time range inputs with add/remove controls, and date-specific exception overrides with closed toggles.
  - `SimpleEditors`:
    - `TextEditor`: Multiline textarea with draft retention.
    - `LocalizedTextEditor`: Bilingual language tab switcher (TR/EN) with emptiness indicators and per-locale editing.
    - `PhoneEditor`: E.164 parsing, tel input mode, and real-time validity feedback.
    - `EmailEditor`: RFC-compliant email pattern validation.
    - `AddressEditor`: Structured multi-line address, district, city, and maps URL inputs.
    - `UrlEditor`: Validated web URL input.
    - `BooleanEditor`: True/False radio group with semantic legend and keyboard support.
    - `EnumEditor`: Controlled select element with localized enum values.
    - `StringListEditor`: Textarea with line-delimited items and automatic pruning.
- **Paste & Extract Sheet (`PasteExtractSheet.tsx`, R19/R21, K16):**
  - Textarea with 8,000 character limit and live counter.
  - In-flight progress spinner, error alert with input preservation on failure.
  - Success summary showing created candidate count with direct link to Suggestions, and injection warning.
- **Suggestions Triage Page (`SuggestionsPage.tsx`, R21, K17):**
  - Back link navigation to Knowledge Overview.
  - Pending suggestion list with candidate relation explainers (`contest`, `discrepancy`, `new`).
  - Source excerpt blockquotes with provenance attribution.
  - Accept and Reject actions with role-gated visibility and loading states.
- **History Sheet (`HistorySheet.tsx`, R20, K18):**
  - Bottom sheet showing version audit trail.
  - Version number, created date/time in workspace timezone, change kind, actor name, and revision notes.

## Verification

Commands were run individually from `frontend/`:

| Check | Observed final result |
|---|---|
| `npm.cmd run lint` | Exit 0; no findings |
| `npm.cmd run typecheck` | Exit 0; no TypeScript errors |
| `npm.cmd test` | Exit 0; 39 files, 573 tests pass (including 125 across knowledge test suites) |
| `npm.cmd run i18n:check` | Exit 0; EN/TR 1481 keys, 945 literal calls verified |
| `npm.cmd run build` | Exit 0; 281 modules transformed in 843ms |
| `node frontend/scripts/ui-fact-editors.mjs` | Exit 0; 8 production fixture scenarios across Chromium & WebKit |
| `git diff --check` from root | Exit 0; clean line endings |

Playwright fixture script `frontend/scripts/ui-fact-editors.mjs`:
- Tested production preview build across Chromium and WebKit engines.
- Evaluated 4 viewport/locale/role combinations: TR 360 phone (owner), EN 390 phone (owner), TR 768 tablet (manager), EN 1440 desktop (staff).
- Navigated to `/w/:ws/more/knowledge/pricing`, opened `FactEditorSheet` for typed editing, verified role-dependent save/suggest buttons, checked overflow, ran Axe audit (0 violations).
- Opened `HistorySheet`, verified version history list, ran Axe audit (0 violations).
- Navigated to `/w/:ws/more/knowledge/suggestions`, verified candidate cards, excerpt quotes, and accept/reject controls, ran Axe audit (0 violations).
- Evaluated document width against viewport width (`scrollWidth <= clientWidth + 1`): **0 horizontal overflow**.
- Recorded evidence in `docs/implementation/phase-8.5-sessions/evidence/s19/fact-editors.json` and 8 viewport PNG captures.

Bundle impact (measured with Node `gzipSync`):
- Production JS: 885,750 bytes / 254,090 gzip.
- Production CSS: 46,410 bytes / 9,730 gzip.
