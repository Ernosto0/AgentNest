# ADR-007: Deterministic workflows with bounded LLM tasks (no autonomous agents)

- **Status:** Superseded by ADR-024 for the Phase 7.5 account-agent path; retained for legacy bounded tasks
- **Date:** 2026-10-15

## Context
The original spec names eight components: Command Router, Business Knowledge Service, Conversation Agent, Content Agent, Operations Orchestrator, Execution Workers, Policy and Approval Service, Reporting Service. It also states the principle "use ordinary functions and deterministic services whenever possible". We need to decide where an LLM is genuinely required and what form its involvement takes.

## Where an LLM is genuinely needed

| Task | Why an LLM | Why not more than one call |
|---|---|---|
| Interpret an owner's natural-language instruction into a typed command | Open-ended Turkish/English phrasing, colloquial money and time expressions, references ("tomorrow's post") | The output is a single typed command or a clarification request. Reference resolution and execution are deterministic. |
| Classify a customer message and draft a reply | Intent and tone understanding, natural phrasing in the customer's language | The facts are supplied up front (small business, small fact set). No browsing or tool loop is needed. |
| Draft content (caption, story overlay text, concept) | Creative writing grounded in facts and brand voice | One proposal per request. The owner iterates by editing or asking again. |
| Extract fact candidates from pasted text | Unstructured to structured conversion | Single pass. Results are only *candidates* awaiting owner verification. |

**Not LLM tasks** (deterministic code): permission checks, policy decisions, approval handling, reference resolution, scheduling, publishing, sending, retries, reconciliation, reporting and counts, fact versioning, conflict detection, impact analysis, validation of claims, rendering of fact values, notification content.

## Alternatives
1. **Agentic orchestrator** with tool calling: an LLM plans multi-step operations and calls tools such as `update_fact` and `schedule_post`.
2. **Multiple specialised agents** collaborating (router agent → conversation agent → content agent).
3. **Bounded LLM tasks inside deterministic workflows**: each task is one model call with a closed output schema, no tools and no side effects. Deterministic code owns control flow and state.

## Decision
Option 3.
- Four LLM task types: `interpret_command`, `draft_reply`, `draft_content`, `extract_fact_candidates`. Contracts are in [agent-runtime.md](../agent-runtime.md).
- Each task is a pure function from (validated input context) to (validated structured proposal). It is executed inside a job, recorded in `agent_runs`, bounded by a timeout, a max-output-token limit and at most one repair retry for schema-invalid output.
- **No LLM tool calling** in the MVP. The LLM never calls `update_fact`. It *proposes* an `update_fact` command, which the application validates, confirms with the user, authorises and executes.
- The "Operations Orchestrator" from the original spec becomes **workflow code + state machines** ([state-machines.md](../state-machines.md), [workflows.md](../workflows.md)).
- The "Command Router" is the `interpret_command` task followed by the deterministic command registry.
- "Conversation Agent" and "Content Agent" become the `draft_reply` and `draft_content` tasks.

## Rationale
- The highest-risk operations (sending, publishing, changing prices) must be deterministic, auditable and permission-checked. An LLM in the control loop makes them neither.
- Single structured calls are cheap, fast, easy to evaluate with fixed datasets, and easy to replace with a deterministic fake for demos and tests.
- Prompt injection impact is bounded by design: a task with no tools can at worst produce a bad *proposal*, which then meets validators, policy and approval.

## Trade-offs
- Less "magical" multi-step autonomy. For example, "prepare and schedule a campaign for next week" becomes a draft that the owner approves and schedules, not an autonomous plan. That is a deliberate product choice (original spec §5: "not fully autonomous by default").
- Some requests need clarification round-trips instead of agentic exploration.

## Consequences
- `app/ai/` contains task definitions (input context builder, prompt template with version, output Pydantic schema, post-validator) and nothing that touches the DB or providers directly.
- Evaluation datasets are organised per task ([testing-strategy.md §6](../../implementation/testing-strategy.md)).

## Revisit when
- A validated user need requires multi-step reasoning over data that cannot be pre-fetched, for example cross-referencing many weeks of conversations. Even then, prefer read-only tools with deterministic execution, and keep side-effecting actions out of the LLM's tool set.
