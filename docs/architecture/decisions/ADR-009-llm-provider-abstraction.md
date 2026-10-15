# ADR-009: Thin LLM provider abstraction with structured outputs and a deterministic fake

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
Business logic must not couple to one LLM vendor. The local demo and the test suite must work **without paid credentials**. Outputs must be machine-validated. Costs must be observable.

## Alternatives
1. Call one vendor SDK directly from task code.
2. Use a multi-provider framework (LangChain, LiteLLM).
3. **Own a thin interface** (one method) with small provider adapters.

## Decision
Option 3.

```python
class LLMProvider(Protocol):
    name: str
    def generate_structured(
        self,
        *,
        task: str,                    # e.g. "draft_reply"
        model: str,
        system: str,                  # trusted instructions (prompt template, versioned)
        messages: list[LLMMessage],   # untrusted data is wrapped and labelled here
        output_schema: type[BaseModel],
        max_output_tokens: int,
        timeout_s: float,
    ) -> LLMResult: ...               # parsed model instance + usage + raw text + provider metadata
```

Adapters:
- **`fake`** (default for development, demo and CI): deterministic, rule-based (keyword/regex) implementations of each task in Turkish and English, producing schema-valid outputs. It can be scripted per test case. The UI labels it "Offline demo AI".
- **`anthropic`** (first real adapter): uses the Messages API with **structured outputs** (`output_config.format` with a JSON schema derived from the Pydantic model). No tools. Default model `claude-opus-5-5`, configurable globally and per task (`LLM_MODEL_<TASK>`).
- An `openai_compatible` adapter (which would also cover local models such as Ollama) is possible later and not required for MVP.

Cross-cutting behaviour, implemented once in the **task runner**, not in adapters:
- Output is **always** re-validated with Pydantic, even if the provider guarantees the schema. One repair attempt is allowed: the validation errors are sent back once. Then the task fails with `LLM_OUTPUT_INVALID`.
- Timeouts (default 30 s), max output tokens per task, and job-level retries for transient provider errors (429/5xx/timeouts) with backoff.
- Per-workspace daily call budget (`LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY`). When exceeded, tasks fail with `LLM_BUDGET_EXCEEDED`, which routes to a human.
- Every call recorded in `agent_runs` (task, provider, model, prompt version, token usage, latency, outcome; redacted input snapshot).
- **No silent fallback** from a real provider to `fake` in production. Failure routes the work to a human with a visible reason.

## Rationale
- One method is enough because all tasks are single structured calls ([ADR-007](ADR-007-deterministic-workflows-bounded-llm-tasks.md)).
- Frameworks add large dependency surfaces and abstractions we do not use (chains, agents, memory).
- A deterministic fake makes invariants testable and the demo free.

## Trade-offs
- Adding a provider means writing an adapter (~150 lines).
- Provider-specific features (prompt caching, citations) are used only inside adapters, behind the same interface.

## Consequences
- `app/integrations/llm/` holds adapters. `app/ai/` holds tasks. Tasks never import a vendor SDK.
- Prompt templates are versioned files (`app/ai/prompts/<task>/v<N>.md`). The version is stored in `agent_runs.prompt_version`, so eval results can be attributed to a version.
- Prompt caching: system prompt and fact context are placed first and kept stable per workspace, so adapters can apply provider caching.

## Revisit when
- A task genuinely needs tool use or multi-turn interaction ([ADR-007](ADR-007-deterministic-workflows-bounded-llm-tasks.md) revisit conditions).
- Self-hosters ask for local models. Then add the `openai_compatible` adapter.
