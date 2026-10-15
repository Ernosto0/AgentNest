# ADR-005: What runs in the request vs in background jobs

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
Some operations are fast and internal (edit a fact). Some call LLMs (seconds to tens of seconds, may fail). Some call Meta (external side effects, rate limits, outages). Webhooks must be acknowledged promptly. Users on mobile networks need responsive feedback.

## Alternatives
1. Do everything inline in HTTP handlers with timeouts.
2. Do everything in jobs, with the API only enqueuing.
3. **Rule-based split** (below).

## Decision
**In the HTTP request (synchronous):**
- Reads.
- Internal state changes that need no LLM and no external call: edit or verify a fact, decide an approval, cancel scheduled content, take over a conversation, change settings.
- Deterministic validation (claim validator, schedule validation, media validation of uploaded files ≤ the image size limit).
- **Enqueuing** jobs, in the same transaction as the state change.

**In background jobs (asynchronous):**
- **Every LLM call** (command interpretation, reply drafting, content drafting, fact extraction).
- **Every external side effect or external read** (Instagram send/publish/fetch, token refresh, Telegram sends).
- Processing of inbound webhooks (the webhook handler only verifies, stores and enqueues).
- Scheduled and periodic work (publishing at time T, daily reports, retention cleanup, approval expiry sweep).

**Client pattern for async work:** the API returns `202 Accepted` with the resource ID and its status (e.g., an `owner_command` in `interpreting`). The frontend polls `GET` on that resource until it reaches a terminal or waiting state. With the `fake` LLM provider the job completes in about one worker poll interval, so the demo still feels instant.

## Rationale
- Isolates user-facing latency and webhook acknowledgement from slow or failing dependencies.
- Gives every LLM and external call the same retry, timeout, tracing and audit treatment.
- One uniform pattern across channels: a Telegram command and a web command both become `owner_commands` processed by the same job.

## Trade-offs
- Polling adds UI latency of up to the worker poll interval plus the frontend poll interval. Mitigation: worker poll interval 1 s in development; the frontend polls at 1 s while a command is pending and backs off afterwards.
- More states for the UI to render (`interpreting`, `generating`). These are designed in [user-journeys.md](../../product/user-journeys.md).

## Consequences
- HTTP handlers must never import provider clients directly. Enforced by import rules ([component-design.md §3](../component-design.md)).
- Every async resource has a `status` field and a terminal-state contract ([state-machines.md](../state-machines.md)).

## Revisit when
- UX research shows that polling latency hurts. Add SSE for push without changing the job model.
