# Session 04: Model step and tool broker

**Task:** P7.5-04. **Status:** Planned. **Prerequisite:** Session 03.
Read the [common session rules](phase-7.5-sessions.md) and phase sections 4-6.

## Goal

Give the model a typed next-step/tool interface and a broker that can actually execute authorized calls and return observations.

## Read first

`app/integrations/llm/{base,fake,openai_provider}.py` as available in the current tree; `app/ai/{runner,runtime,prompt}.py`; finalized runtime/tool/import contracts; existing provider contract tests.

## Build

1. Add vendor-neutral step input/result types for tool call, wait, completion and handoff. Use server-issued references, tool-schema versions and bounded argument/result sizes. Customer-facing text must travel through a send tool.
2. Extend fake and real providers alongside existing bounded tasks. Inspect the installed SDK and current official provider documentation to select native tool calling or structured tool requests behind this contract. Preserve provider usage/error semantics and no hidden fake fallback.
3. Implement the registry/broker with read/internal/external action classifications, source permissions and visibility scopes. Construct workspace/account context on the server; validate tool names, aliases and arguments before dispatch.
4. Register scoped knowledge/thread reads and test handlers first; external tools can return a stable action/operation reference until their executors are wired. Unknown tools are structured failures, never dynamic Python/import execution.
5. Account for every call/repair in existing model-run evidence and cumulative budget. Redact tool responses/context snapshots by policy. Sanitize untrusted tool/document text as data; evidence references are not executable instructions.

## Verify and done when

Contract-test fake and fixture-backed real adapters for tool selection, results, completion, malformed calls, refusal, timeout and usage accounting. Broker tests reject foreign references, restricted public-to-private reads, undeclared tools, oversized payloads and customer attempts to change delegation. Preserve existing extraction/content task regressions. No real paid call is necessary for offline contract completion.

## Handoff

Write `s04-report.md` with the selected adapter mechanism, schemas, registry API, error taxonomy and scripted fake examples. Session 05 must be able to feed a tool result into the next model step. This is AC75-14/19/21 plumbing, not proof of autonomous conversation quality.
