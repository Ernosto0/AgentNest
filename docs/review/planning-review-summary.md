# Planning Review Summary

**Date:** 2026-10-15
**Scope:** Audit of [idea.md](../idea.md), external platform verification, architecture decisions, and the complete documentation system for implementation. No application code was written.

## 1. Most important issues found

The full list is in [gap-analysis.md](gap-analysis.md) (31 findings). These are the ones that most changed the plan:

1. **"Grounded in facts" had no mechanism (G-01, Critical).** Fixed by placeholder rendering of verified facts plus a deterministic claim validator. An LLM can no longer type a price into a customer reply without it being caught.
2. **No-duplicate guarantees were impossible as specified (G-02, Critical).** Instagram offers no idempotency keys. Fixed by a write-ahead operations ledger. Publishing reconciles through the media container status. Ambiguous DM sends are never auto-resent.
3. **Meta access is the critical external path (G-03, Critical).** Serving businesses you don't manage needs Advanced Access (App Review + Business Verification). Plan: assisted pilots via app tester roles under Standard Access (to verify), with App Review started early.
4. **Platform constraints missing from the design (G-04, G-06, G-07):** the 24-hour messaging window, no Story captions via the API, a public JPEG URL required for publishing, a 1000-byte DM limit. All are now explicit in the data model, policy, validation and UX.
5. **Approvals were not bound to what they approve (G-05, G-10).** They are now version- and payload-hash-bound, single-use and expiring. Fact changes put scheduled content on hold.
6. **Over-built infrastructure and agent design (G-08, G-09).** Redis/Celery are replaced by a PostgreSQL job queue with transactional enqueue. Eight agent-like components became four bounded, tool-less LLM tasks inside deterministic workflows.
7. **Prompt injection, tenancy and KVKK were named but not designed (G-11, G-12, G-13).** There is now an architectural containment design, composite-FK tenancy with an isolation test suite, and an engineering view of KVKK cross-border transfer obligations (legal review gate).

## 2. Major architecture decisions

20 ADRs in [decisions/](../architecture/decisions/README.md). The most consequential:

| Decision | ADR |
|---|---|
| Modular monolith: API + worker processes from one Python codebase | 001 |
| PostgreSQL as the only datastore; in-house `SKIP LOCKED` job queue with leases, dedup and transactional enqueue | 004, 006 |
| Every LLM call and external side effect runs in a job; HTTP does sync internal changes only | 005 |
| Four bounded LLM tasks with structured outputs and no tools; deterministic orchestration | 007 |
| Typed, versioned facts + candidates + `{{fact:key}}` placeholders + claim validator; no RAG in MVP | 008 |
| Own thin LLM interface; deterministic `fake` provider by default; `openai` first real adapter (changed from `anthropic` at Phase 3, see the ADR-009 amendment) | 009 |
| Instagram Login (no Facebook Page needed); stateful mock simulator sharing the real contract and webhook path | 010 |
| Write-ahead operations ledger with reconciliation | 011 |
| Owner channel abstraction; web first; Telegram provisional; WhatsApp never a hard dependency | 012 |
| Built-in session auth; shared-schema tenancy with composite FKs; RLS before production; no superuser | 013 |
| Deterministic policy engine (model output can only escalate); unified confirmation/authorisation approvals | 014 |
| License deliberately undecided; repo private and closed to contributions until decided | 019 (provisional) |

## 3. Documents created or modified

- **Modified:** none. `docs/idea.md` is preserved unchanged as the historical input.
- **Created:** 62 new Markdown files under `docs/` (alongside the unchanged `idea.md`), plus the root `CLAUDE.md`:
  - Root: `CLAUDE.md`
  - `docs/`: `README.md`, `invariants.md`, `glossary.md`
  - `docs/review/`: `gap-analysis.md`, `planning-review-summary.md`
  - `docs/product/`: `vision.md`, `personas-and-use-cases.md`, `requirements.md`, `user-journeys.md`, `mvp-scope.md`, `acceptance-criteria.md`
  - `docs/architecture/`: `system-overview.md`, `component-design.md`, `data-model.md`, `state-machines.md`, `workflows.md`, `api-design.md`, `agent-runtime.md`, `business-knowledge.md`, `integrations.md`, `background-jobs.md`, `security-and-privacy.md`, `observability.md`, `deployment.md`, `decisions/README.md`, `decisions/ADR-001` … `ADR-020`
  - `docs/implementation/`: `roadmap.md`, `task-breakdown.md`, `testing-strategy.md`, `phases/phase-01` … `phase-09`
  - `docs/operations/`: `local-development.md`, `environment-variables.md`, `troubleshooting.md`
  - `docs/research/`: `platform-capabilities.md`, `open-questions.md`

Structure deviations from the suggested layout, and why:
- Added `state-machines.md` and `workflows.md` as single sources for states and functional contracts, so that they are not scattered across documents.
- Merged "phase-06-integrations" into a gated Phase 7 and added Phases 8–9, because real Meta work depends on research results and on the local MVP.
- Added `invariants.md`, `glossary.md` and `review/`.

## 4. Validation performed (and not performed)

| Check | Result |
|---|---|
| Official Meta docs (Instagram overview, Business Login, messaging, webhooks, content publishing, media reference, data deletion), WhatsApp pricing, Telegram Bot API: fetched 2026-10-15 | Done. Findings with URLs and status in [platform-capabilities.md](../research/platform-capabilities.md) |
| WhatsApp AI-chatbot terms (Jan 2026) and KVKK transfer rules | **Secondary sources only.** Marked Conditional/Unverified |
| Live behaviour of Meta APIs (Standard Access testers, echoes, Story publishing, error codes) | **Not performed.** No Meta app exists yet. Listed as V-01…V-11 for research track R |
| Automated link check of all relative Markdown links | Done: 479 links, 0 broken |
| Cross-reference checks: every AC, INV, FR/NFR ID referenced is defined; job types used are in the catalog; error/reason codes catalogued; terminology (decision outcomes, states, approval `action` vs policy `action_class`) | Done; inconsistencies found were fixed (see below) |
| Mermaid diagrams rendered | **Not rendered.** Syntax reviewed by hand only |
| Application code, tests, tooling | None created, by design |

Inconsistencies found and fixed during cross-check: an approval-column name collided with the automation-policy concept; notification phase numbers disagreed; webhook signature verification would have required parsing before verifying (now separate mock and Meta webhook paths); "create content draft" was confirmation-gated, contradicting the UX journey; reason codes were missing from the catalog; the FR-017 phase was wrong; two Mermaid edges used doubtful syntax.

## 5. Critical risks and external dependencies

| Risk / dependency | Mitigation in plan |
|---|---|
| Meta App Review + Business Verification (timeline, rejection) | Research track R-6 starts now; Standard-Access tester pilots (V-01); demo mode stays valuable for sales |
| Real API behaviour differing from docs (echoes, stories, errors) | Capability flags; contract tests with recorded fixtures; Phase 7 re-plan step |
| Owners not opening a web app (no push channel in MVP) | OQ-01 decided from interviews; Phase 9; Web Push option |
| KVKK cross-border transfers (foreign hosting and LLM) | Gate 3 legal review; data minimisation; region-agnostic deployment |
| Turkish LLM quality and non-numeric hallucinations | Approval by default; eval sets with hard assertions; owner edits feed approved answers |
| Solo-founder bandwidth and scope creep | Strict phase scope, deferred list, gates, small tasks |

## 6. Unresolved questions (top items; full list in [open-questions.md](../research/open-questions.md))

- **OQ-01** Owner notification channel (Web Push vs Telegram vs WhatsApp). Decide from pilot interviews.
- **OQ-02** License (Apache-2.0 vs AGPL-3.0 vs other). Decide before going public.
- **OQ-03** Do Standard Access tester pilots work? Verify via V-01.
- **OQ-04** Hosting region and transfer basis. Needs legal review.
- **OQ-08** Default autonomy for pilots. Provisional: approval for everything.
- **OQ-09** Model per task and cost per workspace. Provisional: `gpt-6-luna` everywhere; measure other OpenAI tiers with evals.

None of these blocks Phases 1–6.

## 7. Recommended first implementation phase

**[Phase 1: Foundation](../implementation/phases/phase-01-foundation.md)**, starting with tasks P1-01 → P1-14. In parallel, the founder should start **research track R** (create the Meta app, test with their own professional account, start Business Verification) and the **pilot interviews** (R-7), because those answers gate Phases 7 and 9 and take calendar time.

## 8. Acceptance criteria for the planning work

| # | Criterion | Status |
|---|---|---|
| PC-1 | Every section of `idea.md` is mapped to its new location, and deliberate changes are listed with rationale | ✅ [requirements.md §3–4](../product/requirements.md), [gap-analysis.md](gap-analysis.md) |
| PC-2 | Every significant decision has an ADR with context, alternatives, choice, rationale, trade-offs, consequences and revisit conditions | ✅ 20 ADRs |
| PC-3 | Workflows A–G each define trigger, preconditions, inputs, steps, transitions, permissions, persistence, side effects, failure paths, idempotency and acceptance tests | ✅ [workflows.md](../architecture/workflows.md) |
| PC-4 | Every stateful entity has explicit states and allowed transitions | ✅ [state-machines.md](../architecture/state-machines.md) |
| PC-5 | Invariants (the 14 required plus 6 added) each name an enforcement mechanism and a proving test | ✅ [invariants.md](../invariants.md) |
| PC-6 | Phases 1–6 have objective, scope, prerequisites, files, interfaces, ordered tasks, tests, acceptance criteria, demo, risks and exclusions. Phases 7–9 are structured and explicitly gated for re-planning | ✅ [phases/](../implementation/phases/) |
| PC-7 | The local demo runs without credentials and is scripted end to end (seed, simulate, inspect, reset) | ✅ [local-development.md](../operations/local-development.md) (to be verified in P1-14 and P6-10) |
| PC-8 | Platform claims cite sources with dates; unverified items are listed with verification steps | ✅ [platform-capabilities.md](../research/platform-capabilities.md) |
| PC-9 | Open questions have impact, a provisional default, a deadline and an owner | ✅ [open-questions.md](../research/open-questions.md) |
| PC-10 | Internal links resolve; referenced IDs are defined; terminology matches the glossary | ✅ automated checks (§4) |
| PC-11 | Founder has reviewed and accepted (or amended) the ADRs, the MVP scope and the provisional defaults | ⏳ **Pending: human review** |

The planning work is complete when PC-11 is checked. After that, Phase 1 may begin.
