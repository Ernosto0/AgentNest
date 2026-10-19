# Phase 3: AI Runtime, Commands and Approvals Core

## Objective
Introduce the bounded LLM runtime (fake and OpenAI providers), fact placeholder rendering and the claim validator, the generic approval mechanism, basic notifications, and the natural-language command system. Deliver the complete fact-update workflow (B) and paste-and-extract onboarding. Set up the eval harness.

## Read first
[agent-runtime.md](../../architecture/agent-runtime.md) · [workflows.md §B, §D](../../architecture/workflows.md) · [state-machines.md §1, §3](../../architecture/state-machines.md) · [business-knowledge.md §6–8](../../architecture/business-knowledge.md) · [data-model.md §3.3–3.4](../../architecture/data-model.md) · [api-design.md §2.3–2.5](../../architecture/api-design.md) · ADRs [007](../../architecture/decisions/ADR-007-deterministic-workflows-bounded-llm-tasks.md), [008](../../architecture/decisions/ADR-008-structured-business-knowledge.md), [009](../../architecture/decisions/ADR-009-llm-provider-abstraction.md), [014](../../architecture/decisions/ADR-014-approval-and-policy-model.md) · [testing-strategy.md §6](../testing-strategy.md) · [user-journeys.md J3](../../product/user-journeys.md)

## Scope
**In:** `integrations/llm` (protocol, fake, openai); `ai` (task runner, prompt templates v1, `agent_runs`, task definitions for `interpret_command` and `extract_fact_candidates`); renderer and claim validator; `approvals` (model, service, decision API, expiry sweep job, decided-callbacks registry); `notifications` (model, create, list, read; the web bell); `commands` (model, submit, interpret job, resolver, clarification, confirmation via approvals, executors for `query.fact`, `query.pending_approvals`, `query.activity_summary` (basic: counts available so far), `knowledge.update_fact`, `knowledge.update_brand_voice`, `unsupported`); `fact_references` + impact framework (handler registry; this phase handles no referrers yet except its own tests); extraction endpoint and job; eval harness with initial datasets.
**Out:** `draft_reply` and `draft_content` tasks (Phases 4–5), content references in commands (Phase 5), Telegram.

## Prerequisites
Phase 2 accepted.

## Files and modules expected to change
```
backend/app/integrations/llm/{base.py, fake.py, openai_provider.py, errors.py}
backend/app/ai/{models.py, runner.py, prompts/{interpret_command,extract_fact_candidates}/v1.md, tasks/{interpret_command.py, extract_fact_candidates.py}, injection.py, schemas.py}
backend/app/knowledge/{render.py, claims.py, impact.py, extraction.py}, knowledge/models.py (fact_references)
backend/app/approvals/{models.py, service.py, callbacks.py, jobs.py, router.py, schemas.py}
backend/app/notifications/{models.py, service.py, router.py}
backend/app/commands/{models.py, registry.py, service.py, resolver.py, executors/*.py, jobs.py, router.py, schemas.py}
backend/evals/{__main__.py, runner.py, fixtures/demo_gym.yaml, interpret_command/*.yaml, extract_fact_candidates/*.yaml}
backend/migrations/versions/<rev>_ai_commands_approvals.py
frontend/src/features/commands/{CommandBar, CommandResultCard, ConfirmationCard, ClarificationChips}.tsx
frontend/src/features/approvals/{ApprovalsList, ApprovalDetailSheet}.tsx
frontend/src/features/notifications/NotificationBell.tsx
frontend/src/features/knowledge/PasteExtractSheet.tsx
```

## Key interfaces and contracts
- `LLMProvider.generate_structured(...)` ([ADR-009](../../architecture/decisions/ADR-009-llm-provider-abstraction.md)). `FakeLLMProvider.queue(task, output | Exception)`.
- `ai.run_task(ctx, task, input, correlation_id) -> TaskOutcome{status, output, agent_run_id, error_code}`.
- `render(template, usable_facts, locale) -> RenderResult{text, used, spans, errors}`; `validate_claims(text, render_result, locale, *, allow_suffix_span=None) -> ClaimReport{passed, issues[]}`.
- `approvals.request / decide / cancel_for_subject / assert_executable`. `callbacks.register(subject_type, on_decided)`.
- `CommandInterpretation` union ([agent-runtime.md §3](../../architecture/agent-runtime.md)). Registry entries: `{type, mutating, required_permission, params_model, executor, confirmation_summary_builder}`.
- `knowledge.analyze_impact(ctx, fact_id) -> ImpactReport` with a pluggable `ReferrerHandler` registry (`count`, `apply_change`).
- Tables: `agent_runs`, `approvals`, `notifications`, `owner_commands`, `fact_references`.
- Config added: `LLM_PROVIDER`, `LLM_MODEL_DEFAULT`, `LLM_MODEL_<TASK>`, `OPENAI_API_KEY`, `LLM_REASONING_EFFORT`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY`. The production check refuses `fake`.

## Tasks (in order)

| ID | Task | Details | Size |
|---|---|---|---|
| P3-01 | LLM integration | Protocol, result and error types; `FakeLLMProvider` (dispatch per task to deterministic implementations + scripting queue); `OpenAIProvider` using the official SDK (Responses API, strict structured outputs from Pydantic, `store=false`, no tools), timeouts, usage capture, error mapping. Unit tests use the fake only. The OpenAI adapter is tested with a stubbed HTTP transport (no network). | M |
| P3-02 | Task runner and agent runs | `agent_runs` model; runner with budget check, prompt loading by version, run record committed before the call, validation + one repair, error classification for job retries; sweeper job for abandoned runs; redaction of input snapshots. | M |
| P3-03 | Renderer and claim validator | Placeholder parsing; rendering by type and locale with spans; validator patterns tr/en ([business-knowledge.md §7](../../architecture/business-knowledge.md)) with allow-lists; byte-length check helper. ≥ 60 unit cases. | M |
| P3-04 | Approvals and notifications | Models + migration; service with all guards and conditional updates; callback registry; `expire_approvals` periodic job; API (list, detail with `can_decide`, decision); notifications model, service with dedup, list/read API; `approval.requested` notifications. | L |
| P3-05 | Command intake and interpretation | `owner_commands` model; submit API (client_request_id idempotency; 202); `interpret_command` job → task → post-processing (catalog validation, value re-parse, clarification building) → read-only execution or confirmation approval; clarification answer API; cancel; expiry handled by the approvals sweep plus a command-specific check. Fake implementation covers the demo phrases in tr and en. | L |
| P3-06 | Executors | `query.fact` (rendered), `query.pending_approvals`, `query.activity_summary` (counts from `audit_logs` and commands for now, marked "basic"), `knowledge.update_fact` (version check, owner/manager vs staff), `knowledge.update_brand_voice`, `unsupported` with localised suggestions. Results as `{message_key, params, links}`. | M |
| P3-07 | Impact framework | `fact_references` table and helpers; `analyze_impact` used for confirmation summaries; `apply_change` called in the update transaction (no handlers yet besides tests); fact-change notification. | S |
| P3-08 | Extraction | `extract_fact_candidates` task, prompt v1, fake regex implementation; verbatim-excerpt filter; endpoint + run status; candidates created with `pasted_text` source. | M |
| P3-09 | Eval harness | Runner CLI, YAML loader, metrics, hard assertions, Markdown/JSON report; datasets: `interpret_command` (≥ 30 cases incl. "approve", "publish now", "send message" → unsupported), `extract_fact_candidates` (≥ 10 incl. injection text). CI step with `fake`. | M |
| P3-10 | Frontend | Command bar on Home (sticky above the tab bar on mobile); command polling; result card; clarification chips; confirmation card (old → new values, impact counts, confirm/cancel with payload hash); approvals list and detail sheet (generic rendering by `action`); notification bell; paste-and-extract sheet in the knowledge screens; "Offline demo AI" indicator from `/api/v1/meta`. | L |
| P3-11 | Tests | See below. | M |

## Tests to add
- **Unit:** validator patterns; renderer; approval guard logic (pure parts); command registry schema; value re-parse disagreement → clarification; injection heuristic patterns.
- **Integration:** AC-C1, AC-C2, AC-C6, AC-C7, AC-A6; approval decide: wrong hash, double decision, expired, foreign workspace, missing permission; staff update → contest candidate; LLM failure paths (queued exception → retry → failed; invalid output → repair → failed); budget exceeded; the command interpreter never yields an executable "approve" (scripted fake returns a non-registry type → `unsupported`).
- **Eval:** fake datasets pass hard assertions.
- **E2E:** command → confirmation → fact updated, visible in knowledge with history (mobile).

## Acceptance criteria
- AC-A6, AC-C1, AC-C2, AC-C6 and AC-C7 pass. AC-C3–C5 are deferred to Phases 4–5 where referrers exist.
- INV-04 test: no command type can approve, publish or send. The decision API only accepts explicit approval IDs and payload hashes.
- With `LLM_PROVIDER=openai` and a key set, the same demo commands work manually (manual check; not in CI).
- `agent_runs` rows exist for every task execution, with tokens (real provider) and `is_fake` (fake).

## Demo scenario
On Home, type "Aylık üyelik artık 7.000 TL" → *Anlıyorum…* → confirmation card "6.000 ₺ → 7.000 ₺" → Onayla → Business knowledge shows the new version with source "komut". Type "fiyat artık 7000" → clarification chips (monthly / 3 months / reformer 8). Type "gönderiyi şimdi yayınla" → "This is not something I can do yet" with a pointer to Content. Paste a bio with prices → suggestions appear with excerpts.

## Known risks
- The fake interpreter's grammar may be too narrow for exploratory demos. Mitigation: the documented demo phrases, plus the real provider option.
- Approval callback complexity. Mitigation: callbacks run in the same transaction, with tests for rollback on callback failure.

## Explicitly excluded
Reply drafting, content, Instagram, the Telegram channel, LLM tool use.
