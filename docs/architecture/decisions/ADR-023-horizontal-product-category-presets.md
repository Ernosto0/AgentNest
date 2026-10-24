# ADR-023: Horizontal product with optional category presets

- **Status:** Accepted
- **Date:** 2026-10-24
- **Supersedes:** the "fact templates per business category (gym, Pilates studio)" consequence of [ADR-008](ADR-008-structured-business-knowledge.md). Everything else in ADR-008 stands.

## Context
The original idea ([idea.md §3.1](../../idea.md)) started with gyms and Pilates studios. That beachhead leaked into the product itself:
- The workspace category allowed only `gym`, `pilates_studio` or `other`, and the wizard selected `gym` by default.
- Services, prices and promotions existed only in the gym/Pilates templates. An `other` business had no checklist slot for what it sells or what it costs.
- The deterministic fake LLM (demo, CI, evals) recognised `pilates|reformer|fitness`, preferred `pricing.membership_monthly` and always added `#fitness` hashtags.
- Both demo workspaces, the eval fixtures and the landing page were fitness businesses.

The product decision is now: **any small business that talks to customers on Instagram is a target customer.**

## Alternatives
1. Keep the fitness beachhead and add more verticals one by one, each with its own template and fake logic.
2. Remove business categories entirely.
3. **A business-agnostic core** (services, prices, promotions, FAQ for every business) plus **optional category presets** that only add suggestions.

## Decision
Option 3.
- `workspaces.business_category` ∈ {`beauty_wellness`, `food_beverage`, `retail`, `fitness`, `health_clinic`, `education`, `hospitality`, `services`, `other`}. Existing `gym` and `pilates_studio` rows migrate to `fitness`.
- `knowledge/templates/common.yaml` is the complete core every workspace gets. It now includes `service.*` (ready, ≥ 1), `pricing.*` (owner-named prices; ready, ≥ 1 when prices are shared) and `promotion.*`.
- `knowledge/templates/presets/<category>.yaml` is optional. A preset may add **suggested fixed keys** (for example `pricing.membership_monthly` for fitness), and `hashtags{tr,en}` used by content drafting. A preset must not add readiness requirements, so readiness is identical for every category.
- Logic outside the templates (fake LLM, prompts, simulator scripts) must not name a sector-specific key or word. It works from the workspace's own facts and labels, and from the preset's hashtags.
- The demo seeds three sectors: a Turkish gym (`golkent-fitness`), a Turkish beauty salon (`nilufer-guzellik`) and an English café (`harbor-cafe`).

## Rationale
- Readiness and grounding never depended on the sector, only the key names did. Owner-named `pricing.*` facts keep the same typed, verified and placeholdered guarantees (INV-02).
- Presets keep onboarding fast for common sectors without making any sector special in code.
- A multi-sector demo and multi-sector evals show that drafting is not overfitted to one vertical.

## Trade-offs
- Staff can only propose fixed template keys (business-knowledge.md §5). In categories without a preset, prices are pattern keys, so staff cannot propose them; the owner or a manager enters them. This is acceptable for the MVP.
- Merging `gym` and `pilates_studio` into `fitness` loses the distinction for existing rows. Only demo and local data existed.

## Consequences
- The `business_category` check constraint changes (migration `0018`).
- [business-knowledge.md §3](../business-knowledge.md) describes the core and presets. Readiness `price_policy` is satisfied by any usable `pricing.*` fact when prices are shared.
- Eval fixtures exist per sector; regressions in one sector are visible separately.

## Revisit when
- A sector needs structured data the core cannot express (e.g., restaurant menus with many items, hotel room availability). Then add typed structures for that sector behind a preset, not in the core.
