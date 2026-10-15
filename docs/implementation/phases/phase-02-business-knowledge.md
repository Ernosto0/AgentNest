# Phase 2: Business Knowledge

## Objective
Implement typed, versioned, verifiable business facts with candidates, conflict rules, category templates and readiness. Add the owner-facing knowledge screens and a workspace creation wizard. Seed realistic fictional facts for the demo workspaces.

## Read first
[business-knowledge.md](../../architecture/business-knowledge.md) · [workflows.md §A](../../architecture/workflows.md) · [state-machines.md §2](../../architecture/state-machines.md) · [data-model.md §3.3](../../architecture/data-model.md) · [api-design.md §2.3](../../architecture/api-design.md) · [ADR-008](../../architecture/decisions/ADR-008-structured-business-knowledge.md) · [ADR-016](../../architecture/decisions/ADR-016-localization.md) · [user-journeys.md J1](../../product/user-journeys.md)

## Scope
**In:** value types (validation, locale-aware parsing, rendering with Babel); templates (common, gym, pilates_studio); `business_facts`, `fact_versions`, `fact_candidates`; FactService (create, update, verify, archive, restore, usable_facts); candidate relations (`new`, `same`, `discrepancy`, `contest`) and resolution; readiness; knowledge API; knowledge UI; workspace creation wizard; demo fact seed.
**Out:** extraction from pasted text (Phase 3), placeholder rendering and the claim validator (Phase 3), approved answers (Phase 4), impact analysis (Phase 3), automation review screen (the `automation_reviewed_at` flag is set via the settings endpoint for now; the screen comes in Phase 4).

## Prerequisites
Phase 1 accepted.

## Files and modules expected to change
```
backend/app/knowledge/{models.py, values.py, parsing.py, formatting.py, templates/{common,gym,pilates_studio}.yaml, templates.py, service.py, candidates.py, readiness.py, repository.py, schemas.py, router.py}
backend/migrations/versions/<rev>_knowledge.py
backend/app/demo/data/{facts_golkent_fitness.yaml, facts_harbor_pilates.yaml}, backend/app/demo/seed.py
backend/app/core/i18n/{tr,en}.json (labels, errors)
backend/tests/unit/knowledge/…, backend/tests/integration/knowledge/…
frontend/src/features/knowledge/… (FactList, FactEditor per type, VerifyButton, HistorySheet, SuggestionsList, ReadinessChecklist)
frontend/src/features/workspaces/CreateWorkspaceWizard.tsx
frontend/src/features/home/ReadinessCard.tsx
frontend/e2e/scenario-a.spec.ts (A1–A5)
```

## Key interfaces and contracts
- Value Pydantic models per `value_type` ([business-knowledge.md §2](../../architecture/business-knowledge.md)).
- `parse_money(text, locale, default_currency) -> Money | ParseAmbiguity`. Turkish: `7.000` = 7000, `7.000,50` = 7000.50, `7 bin` = 7000, suffixes `TL`, `₺`, `TRY`. English: `7,000` = 7000, `7.5` = 7.50. Ambiguous cases return alternatives.
- `format_fact(fact, locale) -> str` (Babel). Whole TRY amounts without decimals: `6.000 ₺`.
- `FactService`: `create`, `update(ctx, fact_id, value, expected_version, actor, source_type, reason)`, `verify`, `archive`, `restore`, `usable_facts(ctx, categories=None, on_date=None)`, `propose_candidate(...)`, `accept_candidate`, `reject_candidate`.
- Staff edits route to `propose_candidate(staff_proposal)` automatically, and the API responds 202 with the candidate.
- `readiness(ctx) -> Readiness{level, requirements[]}` per [workflows.md §A step 7](../../architecture/workflows.md). The account-connected requirement reports `not_connected` until Phase 4.

## Tasks (in order)

| ID | Task | Details | Size |
|---|---|---|---|
| P2-01 | Value types, parsing, formatting | Pydantic value models; parsers (money tr/en, phone to E.164 for TR numbers, weekly hours editor format); Babel formatting; Turkish case-folding helper for matching. Extensive unit tests. | M |
| P2-02 | Templates | YAML schema + loader + validation at startup (unique keys, valid types). Common, gym and Pilates templates per [business-knowledge.md §3](../../architecture/business-knowledge.md). | S |
| P2-03 | Schema | Migration for `business_facts`, `fact_versions`, `fact_candidates` with composite FKs, partial unique key index and checks. | S |
| P2-04 | FactService | Versioning (snapshot per change), optimistic concurrency, verification rules by permission, archive/restore, validity windows (workspace-local dates), `usable_facts`. Audit for every change. | M |
| P2-05 | Candidates | Relation computation; `same` auto-superseded; accept → `update` with `candidate_accepted`; reject; recompute relations after fact changes; `contest` makes the fact unusable. | M |
| P2-06 | Readiness | Computation + `GET /readiness`; `settings.automation_reviewed_at` via the workspace PATCH (temporary). | S |
| P2-07 | Knowledge API | Endpoints per [api-design.md §2.3](../../architecture/api-design.md) except extraction and approved answers. Responses include `display` (rendered in the user's UI locale) and `usable`. | M |
| P2-08 | Demo seed | Facts for `golkent-fitness` and `harbor-pilates` per [business-knowledge.md §10](../../architecture/business-knowledge.md), including the unverified student price and a pending discrepancy candidate. `seed --reset` re-creates them. | S |
| P2-09 | Knowledge UI | Category list with status chips; editors for money (amount + unit + conditions), weekly hours (day ranges + exceptions), text, localised text (tr/en tabs), phone, address, enum, boolean; verify; archive; history sheet; Suggestions list (accept/reject, with the source excerpt and a relation explanation); readiness checklist card on Home with deep links. | L |
| P2-10 | Workspace creation wizard | Name → category → market/locale/timezone/currency (defaults by market) → lands on the knowledge checklist. | M |
| P2-11 | Tests | See below. | M |

## Tests to add
- **Unit:** parsers (≥ 30 tr/en money cases including ambiguity), formatting (`6.000 ₺`, `€1,200`), weekly hours rendering, relation computation, usability (verified, archived, validity window in the workspace timezone, contested), readiness levels.
- **Integration:** create/update/verify/archive with versions and audit (AC-A3); staff edit becomes a candidate and returns 403 for verify (AC-A4); optimistic concurrency 409; accept/reject flows; discrepancy keeps the fact usable; contest makes it unusable; readiness (AC-A5); isolation for all new routes (harness).
- **E2E:** `scenario-a.spec.ts` A1, A2 and verify flow, on mobile and desktop.

## Acceptance criteria
- AC-A1, AC-A2, AC-A3, AC-A4, AC-A5 pass.
- Every fact change produces exactly one new `fact_versions` row and one audit entry. Previous versions are unchanged (INV-17).
- Seeded demo gym readiness is `ready_for_drafts` (account not yet connected).
- All new UI strings in tr and en. Money is displayed in locale format.

## Demo scenario
Log in as owner → More → Business knowledge → see categories; the student price is marked *Doğrulanmamış* (unverified) → verify it → see history → Suggestions shows "Bio says 5.500 ₺, verified price is 6.000 ₺" → reject → Home readiness checklist shows remaining items. Log in as staff → edit the monthly price → it appears as a suggestion for the owner, and the fact shows "contested".

## Known risks
- Parser edge cases in Turkish formats. Mitigation: confirmations are always shown for command-based updates in Phase 3; editors show formatted previews.

## Explicitly excluded
LLM features, placeholders, approved answers, Instagram, content, website or profile import.
