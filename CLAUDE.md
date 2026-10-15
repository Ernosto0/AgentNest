# CLAUDE.md

Guidance for coding agents working in this repository.

## Project
AgentNest (working name): an Instagram operations assistant for small businesses (Turkish-first, mobile-first). It has an open-source core and a possible hosted SaaS. The full specification is in `docs/`. Start at `docs/README.md`.

## Current state
Planning is complete. Implementation follows `docs/implementation/roadmap.md`, phase by phase. **Check which phase is current** (latest phase summary or git log) before doing anything.

## How to work here
1. Before a phase: read `docs/invariants.md`, the phase document in `docs/implementation/phases/`, and every document in its "Read first" list.
2. Implement tasks in the listed order. Keep each change focused. Run the relevant tests after each task.
3. Do not invent architecture. If the docs are missing something or contradict each other, stop and raise it as a question in your summary. Do not guess.
4. Do not expand scope beyond the phase. Deferred features are listed in `docs/product/mvp-scope.md`.
5. If a contract changes (schema, endpoint, state, job type, env var), update the matching doc in the same change.
6. At the end of a phase: run all tests, write a phase summary (changes, tests proving each acceptance criterion, demo steps, deviations, limitations, questions), then **stop and wait for review**.

## Non-negotiables (details: `docs/invariants.md`)
- Workspace isolation on every query and route. Foreign IDs → 404.
- LLM output is a proposal: closed schemas, no tools, and model flags can only escalate decisions.
- Prices, hours, contacts, URLs and promotions come only from verified facts via `{{fact:key}}` placeholders, and are checked by the claim validator.
- External side effects only through the `operations` ledger; reconcile before any retry; never auto-resend an ambiguous DM.
- Approvals are explicit, version- and hash-bound, single-use and expiring. Free text never approves.
- Everything simulated is labelled `is_simulated` and shows a badge.
- Secrets never in the repo, logs, job payloads, API responses or the frontend.
- No external call inside a DB transaction. Time comes from the injected `Clock`.

## Stack and commands
- Backend: Python 3.12 (uv), FastAPI (sync), SQLAlchemy 2 + psycopg 3, Alembic, Pydantic v2, PostgreSQL 16 (Docker, port 5433). In-house Postgres job queue. **No Redis/Celery.**
- Frontend: React + TypeScript + Vite, TanStack Query, React Router, Tailwind, i18next (tr/en).
- Commands: `docs/operations/local-development.md`. Backend checks: `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest`. Frontend checks: `npm run lint && npm run typecheck && npm test && npm run i18n:check`.
- The developer machine is Windows. Keep commands cross-platform (no Makefile dependency, no bash-only scripts in required paths).

## Defaults that keep the demo credential-free
`LLM_PROVIDER=fake`, `INSTAGRAM_ENABLED_PROVIDERS=mock`, `MEDIA_STORAGE_BACKEND=local`, `DEMO_TOOLS_ENABLED=true` (development only).
