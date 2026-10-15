# ADR-001: Modular monolith with a separate worker process

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
The product has several capability areas: knowledge, inbox, content, approvals, commands, reporting and integrations. The original spec proposes "separate frontend, API, and worker processes". The builder is a solo founder with a limited budget. The first milestone is a local demo, followed by a small number of assisted pilots. Expected load in the first year is tens of workspaces, each with tens to hundreds of messages per day.

## Alternatives
1. **Microservices** per capability (knowledge service, inbox service, publisher, …).
2. **Single process**: API and background work in the same process (e.g., FastAPI background tasks / in-process scheduler).
3. **Modular monolith, two process types from one codebase**: `api` (HTTP) and `worker` (jobs + scheduler), sharing modules and the database.

## Decision
Option 3. One Python package (`backend/app`) with internal modules ([component-design.md](../component-design.md)) deployed as two process types:
- `api`: FastAPI app, serves HTTP and webhooks. Does no long-running or external side-effect work inline (see [ADR-005](ADR-005-sync-api-vs-background-jobs.md)).
- `worker`: claims and runs jobs, runs the periodic scheduler loop.

The frontend is a separate static SPA build.

## Rationale
- Microservices would multiply deployment, observability and consistency work for no benefit at this scale. Cross-module workflows (fact change → content on hold → notification) are simpler and safer inside one database transaction.
- A single process would tie scheduled publishing to web-server lifecycles and make horizontal scaling of HTTP impossible without duplicating schedulers. It also makes webhook latency depend on LLM calls.
- Two process types from one codebase give isolation of failure domains (an LLM hang cannot stall webhook acknowledgement) at almost no extra complexity.

## Trade-offs
- Module boundaries are enforced by convention and tests, not by network boundaries, so they can erode. Mitigation: import rules ([component-design.md §3](../component-design.md)), checked by a lightweight import-linter test.
- Scaling is coarse-grained: scale API and worker replicas independently, but not individual modules.

## Consequences
- One `pyproject.toml`, one migration history, one test suite.
- Entry points: `app.main:create_app` (API) and `python -m app.worker` (worker).
- In local development the worker can run in a separate terminal. Tests call job handlers directly through a `run_due_jobs()` helper.

## Revisit when
- A module needs a different runtime or scaling profile, for example media transcoding with heavy CPU, which may become a separate worker *queue* before it becomes a separate service.
- Team size grows beyond ~5 engineers working in parallel on separate domains.
- A hosted multi-region deployment requires isolating integration egress.
