# Session 04 report: model step and tool broker

**Status:** Offline complete, operator reviewed. The typed model/tool path is implemented
and fixture-tested. No agent conversation, external effect handler, model quality or live
platform result is claimed.

## Baseline and preserved work

- Started from `main` at `b5cdee1` after the operator reviewed the uncommitted Sessions 01–03
  contracts, migrations and reports. Their files and the separate blocked Session 08 audit were
  preserved. No commit, push, deployment, paid model call or live account action occurred.
- The Session 02 migration already permits `agent_runs.task = account_agent_step` and has a
  nullable composite FK from `agent_runs` to `agent_steps`; this session adds no migration.

## Implementation and transport decision

- `LLMProvider.generate_step(LLMStepRequest)` now returns a typed tool, wait, completion or
  handoff proposal with usage, model identity and a bounded operational explanation. A tool
  request carries a registered name, schema version and closed Pydantic argument schema; prior
  observations carry call/result pairs. The legacy `generate_structured` contract is unchanged.
- The OpenAI adapter uses native Responses function calls (`tools`, `tool_choice=required`,
  `parallel_tool_calls=false`, `store=false`, `max_retries=0`) and accepts exactly one call.
  `agent_decide` is the explicit wait/complete/handoff control function. The adapter rejects
  malformed, multiple, empty, incomplete and overlarge calls, maps refusals and HTTP failures
  to the existing typed error taxonomy, and records available usage. The strict schema converter
  is application-owned. The installed SDK was OpenAI 3.31.0; the official
  [function-calling guide](https://developers.openai.com/api/docs/guides/function-calling)
  was reachable and read on 2026-10-26. Fixture transport tests use an HTTP stub, not an API key.
- The fake provider has a scriptable step queue and a safe unscripted handoff. It does not
  silently stand in for an unavailable real provider.
- `ToolBroker` registers versioned capability classes (`public_read`, `private_read`,
  `internal_write`, `external_effect`), validates exact names, schema version, closed arguments,
  byte bounds, source/surface permission and persisted workspace/account/thread scope before a
  handler runs. Built-in `knowledge.read` and `thread.read` return bounded results; private DM
  reads are unavailable to public-comment contexts. No effect tool or provider side effect is
  registered by this session. Later effect handlers must use the Session 03 delegation service
  and operation ledger; a model tool call is never authority.
- `run_step` links an `AgentRun` to the durable `AgentStep` and commits redacted evidence before
  the provider call. It uses the existing provider error semantics, allows one schema repair,
  reserves that repair before the second call under a workspace lock, and records repair count
  and available token usage. Run snapshots/output contain only counts, names and decision kind,
  never prompt or private tool bodies. The provider call occurs with no DB transaction open.

## Verification

Environment: Python 3.12, OpenAI SDK 3.31.0, local PostgreSQL test database, deterministic
fake and HTTP fixture transport. No paid or live call.

| Command | Result |
|---|---|
| `uv run pytest tests/unit/integrations/test_openai_steps.py tests/unit/integrations/test_openai_provider.py tests/unit/integrations/test_fake_provider.py tests/integration/agent/test_tools.py tests/integration/agent/test_step_runner.py tests/integration/ai/test_runner.py -q --tb=short` | 46 passed. Covers tool/result continuation, strict request body, control decision, malformed/multiple/refused/incomplete calls, 429 classification, tenant/visibility/argument checks, repair reservation and redacted run evidence, plus legacy providers/runner. |
| Focused `uv run ruff check` on Session 04 files and tests | Passed. |
| `uv run mypy app evals` | Passed: 264 source files. |
| `uv run lint-imports` | Passed: 19 contracts, 0 broken. |

The focused verification does not imply the full backend suite, real-model quality or an agent
end-to-end workflow passed. AC75-14/19/21 have foundational transport and broker evidence only.

## Session 05 handoff and remaining boundaries

- Call `build_default_broker().available(context)` to obtain filtered `LLMToolDefinition`s;
  send those through `LLMStepRequest` and call `run_step` only for a claimed `model_pending`
  `AgentStep`. `ToolBroker.dispatch` returns `ToolResult.observation()`, which can be placed in
  `LLMToolObservation` with the model `call_id` for a later step. The coordinator must commit
  before model/tool network work, revalidate cursor/epoch/policy/deletion generation after the
  call, and never dispatch a stale result.
- A model `wait_for` is only a proposal; verify a matching persisted owner question, approval,
  operation or scheduled task before transitioning to a wait. A public context never gains
  private reads through tool arguments or a shared identity string.
- The current `knowledge.read` calls existing `usable_facts()` then slices the list. Session 06
  owns bounded database retrieval, relevant source/version selection and stronger public-only
  context construction. Session 07 registers the DM effect tool and links exact action intent,
  authorization and the existing send ledger. No Session 04 test is evidence of those effects.
- `run_step` reserves initial/repair call slots for the new path, while legacy `run_task` still
  has its older non-atomic daily check. Session 05 must unify the workspace quota and persist
  cumulative goal/activation step, token and tool-call reservations. A provider transport error
  before a usage-bearing response may leave token totals unknown, but the call/run and status
  remain recorded.
