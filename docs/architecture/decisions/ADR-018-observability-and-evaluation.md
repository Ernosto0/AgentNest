# ADR-018: Structured logs, correlation IDs, error catalog, versioned AI evals

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
A solo founder must be able to answer "what happened to this customer's message?" or "why didn't this post publish?" in minutes, both locally and on a single production VM, without an expensive observability stack. AI behaviour must be measurable across prompt and model changes.

## Decision

### Logs and correlation
- **structlog**, JSON in production, pretty console in development.
- Context fields bound automatically: `request_id` (per HTTP request), `correlation_id` (propagated from the trigger across jobs: inbound webhook → draft → approval → send), `workspace_id`, `job_id`, `job_type`, `operation_id`, `agent_run_id`, `user_id` (never email).
- `correlation_id` is stored on `jobs`, `operations`, `agent_runs`, `audit_logs` and `inbound_events`, so one ID reconstructs a full flow from the database even if logs have rotated.

### Error catalog
- Stable, documented error codes (e.g., `MESSAGING_WINDOW_CLOSED`, `ACCOUNT_NEEDS_REAUTH`, `OUTCOME_UNCONFIRMED`) in one module (`app/core/errors.py`), each with: HTTP status (if API-facing), retryable flag, user-facing i18n key with "what happened" and "what you can do". Catalog in [observability.md §4](../observability.md).
- User-visible statuses and errors are rendered from codes, never from raw exception text.

### Metrics and traces
- MVP: no metrics backend. Operational counters are derived from database tables (jobs by status, operations by outcome, agent runs by outcome and cost). A dev/owner-facing "System health" panel queries them.
- OpenTelemetry tracing is **deferred**. Correlation IDs are designed to map onto trace IDs later.
- Optional error tracking (Sentry-compatible DSN) from Phase 8, off by default.

### AI evaluation
- Versioned YAML datasets in `backend/evals/<task>/` (customer messages, owner commands, injection attempts, content requests) with expected labels and **hard assertions** (must escalate, must not contain an unrendered money value, must produce `unsupported`).
- Runner `uv run python -m evals run --task draft_reply --provider fake|anthropic` outputs a JSON + Markdown report (accuracy per label, invariant violations, tokens, cost estimate) under `backend/evals/reports/`.
- CI runs evals against the **fake** provider (pipeline correctness). Real-provider evals run manually or on demand with a cost cap, and results are committed as baselines when prompts or models change.

## Alternatives considered
- Full Prometheus/Grafana/Loki/Tempo stack: too heavy for a single VM and a solo founder at this stage.
- LLM observability SaaS: possible later. `agent_runs` covers MVP needs and keeps data in our control (privacy).

## Consequences
- Phase 1 delivers logging setup, request IDs, the error catalog skeleton and the audit log.
- Phase 3 delivers `agent_runs` and the eval runner.

## Revisit when
- More than one production VM, or more than ~50 active workspaces: add OpenTelemetry and a hosted log or trace backend.
