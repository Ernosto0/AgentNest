# ADR-021: Simulation provenance belongs to provider results

- **Status:** Accepted by owner, 2026-10-24
- **Date:** 2026-10-24
- **Scope:** Clarifies INV-09; does not change production mock restrictions.

## Context

Phase 5 Q6 and Phase 6 Gate 1 identified two records without `is_simulated`:
reusable uploads (`media_assets`) and internal mock-provider `sim_*` tables.
An upload can exist before account selection and can later serve either provider.
Assigning mock provenance from the workspace or storage backend would mislabel it.
Draft-stage content likewise has no provider result until an account is selected.

## Decision

Keep INV-09's requirement that simulated operations are never presented as real.
Require provider-derived provenance on every exposed result of a mock operation:
messages, account-bound drafts/content, operations, notifications, report evidence
and the audit entries of those operations. Every such result needs its simulation badge.

Reusable uploads and their upload/rejection/retention audit events are provider-neutral:
they neither claim publication nor sending. Internal `sim_*` records are simulator
implementation state, accessible only through development tooling, rather than
customer-facing operation results. They do not need a redundant flag. Storage choice
and `workspace.is_demo` never establish provider provenance. Meta results stay real
even in a demo workspace. A neutral upload never makes a later mock result real.

INV-09 enforcement wording: "Provider-result `is_simulated` is derived from
`social_accounts.provider_kind = 'mock'` and copied to all resulting domain/evidence
rows; the UI badges every simulated result. Provider-neutral reusable uploads and
their lifecycle audits, and internal development-only `sim_*` state, are excluded.
Unbound drafts acquire provider provenance when bound to an account. Production
refuses mock accounts outside explicitly permitted demo workspaces."

## Alternatives and consequences

- Adding a boolean to reusable uploads would require an arbitrary provider choice or
  could prevent reuse across providers; it would not describe the bytes truthfully.
- Adding a constant flag to `sim_*` adds no protection beyond the provider boundary.
- This clarification permits no missing flag or badge on a mock send/publication.
  Existing simulation propagation, isolation, production settings and E2E tests remain
  required. See `backend/tests/integration/test_simulation_flag.py` and
  `frontend/src/features/settings/connections.test.tsx`.

## Revisit

Revisit if media generation itself becomes a simulated provider operation, or internal
simulator objects are exposed through ordinary customer APIs.
