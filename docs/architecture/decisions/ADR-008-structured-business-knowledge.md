# ADR-008: Structured, versioned business facts with placeholder rendering

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
Prices, opening hours, policies and promotions must never be invented, must be versioned and auditable, and must propagate to future replies and flag affected content when they change. Information arrives from several sources of different trustworthiness (owner, staff, pasted text, Instagram profile, websites) and can conflict. The LLM writes customer-facing text and could alter numbers.

## Alternatives
**Storage**
1. Free-text "business profile" document injected into prompts.
2. Vector store / RAG over documents.
3. **Typed fact records** in PostgreSQL (key, typed value, status, source, version history), plus separate candidate records for unconfirmed information.

**Grounding of generated text**
A. Prompt the model to "only use provided facts" and trust it.
B. Post-hoc check: compare numbers in the output with facts.
C. **Placeholders**: the model writes `{{fact:pricing.membership_monthly}}`, code renders the verified value, *and* a post-hoc validator rejects any critical-value pattern that did not come from a placeholder.

## Decision
- **Storage: option 3.** Full model in [business-knowledge.md](../business-knowledge.md) and [data-model.md](../data-model.md):
  - `business_facts`: current accepted value per `(workspace_id, key)`, typed (`money`, `weekly_hours`, `text`, `phone`, `address`, `url`, `boolean`, `enum`), `status` ∈ {`unverified`, `verified`, `archived`}, criticality, optional validity window.
  - `fact_versions`: **append-only** snapshot of the full value for every change, with source, actor and reason.
  - `fact_candidates`: proposed values from non-authoritative sources (staff proposals, extraction). These never change a fact without an authorised acceptance.
  - A **source-priority policy** decides whether a candidate is a harmless discrepancy or makes a fact *contested* (unusable for automation).
- **Grounding: option C.** LLM tasks receive verified facts with their keys and must reference critical values through placeholders. The **renderer** formats values per locale. The **claim validator** scans the final text for money, percentages, times, dates, weekdays with times, phone numbers, emails and URLs. Any match not produced by a placeholder fails validation (`GROUNDING_FAILED`).
- **No RAG/vector DB in MVP.** A small business has tens to low hundreds of facts (a few thousand tokens), so the relevant categories, or all verified facts, fit in the prompt.

## Rationale
- The LLM never has to "remember" or copy a number, so the most dangerous hallucination class becomes structurally impossible for values that pass through placeholders, and detectable for the rest.
- Typed values enable deterministic rendering (`7.000 ₺` vs `7,000 TRY`), deterministic validation and deterministic impact analysis.
- Version snapshots make history trivially reconstructable without replaying deltas.

## Trade-offs
- The validator will have false positives (e.g., "2 kişi", "10 dakika"). Mitigation: allow-listed patterns for non-commercial small quantities, configurable per locale. Validation failure routes to **approval**, not to silent sending, so false positives cost owner attention, not safety.
- The owner sees a fact UI with keys and types. Mitigation: owner-facing labels and category templates hide keys.
- Free-text facts (descriptions, FAQ answers, class timetable text) can be paraphrased by the LLM. Critical values inside them must still be placeholdered or the draft fails validation.

## Consequences
- Fact templates per business category (gym, Pilates studio) live in code as YAML and define expected keys, types, criticality and readiness requirements.
- Content and approved answers store `used_fact_refs` (fact ID + version), which powers impact analysis when facts change ([workflows.md §B](../workflows.md)).
- Rendered text is stored as rendered. Approvals cover the rendered text, never a template that could change later.

## Revisit when
- Workspaces regularly exceed ~300 facts, or long documents (menus, policies) must be quoted. Then add retrieval (Postgres full text or pgvector) for *non-critical* text facts only. Critical values remain typed facts.
