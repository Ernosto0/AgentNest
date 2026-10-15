# ADR-003: Python 3.12, FastAPI, synchronous SQLAlchemy 2.0, Pydantic v2, uv

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
The original spec proposes Python, FastAPI, Pydantic, SQLAlchemy and Alembic. The open choices are the Python version, sync vs async database access, and tooling. The founder's machine has Python 3.10/3.11 and `uv`.

## Alternatives
- **Python version:** 3.11 (installed) vs 3.12 (managed by uv) vs 3.13.
- **DB access style:** async SQLAlchemy (`asyncpg`) end-to-end vs sync SQLAlchemy with `psycopg` 3 and FastAPI's threadpool.
- **Package management:** pip + venv, Poetry, uv.

## Decision
- **Python 3.12**, installed and pinned through uv (`uv python install 3.12`, `requires-python = ">=3.12,<3.13"`).
- **FastAPI** with **synchronous** route handlers and **synchronous SQLAlchemy 2.0** (typed `Mapped[]` models) over **psycopg 3**.
- **Pydantic v2** for API schemas, LLM output schemas and settings (`pydantic-settings`).
- **Alembic** for migrations (autogenerate allowed, but every migration is reviewed by hand).
- **uv** for dependencies and running commands. **ruff** for lint and format, **mypy** (strict on `app/`) for types, **pytest** for tests.
- HTTP client for providers: **httpx** (sync).
- Money: `decimal.Decimal`. Never floats.
- Formatting of numbers, currencies and dates for rendering: **Babel**.

## Rationale
- Sync code is easier to reason about, test and debug for a solo developer, and avoids the class of async bugs (blocking calls in the event loop, session-per-task misuse). FastAPI runs sync handlers in a threadpool, which is sufficient for the expected load (tens of requests per second at most).
- Long operations (LLM, Meta API) run in the worker, not in HTTP handlers ([ADR-005](ADR-005-sync-api-vs-background-jobs.md)), so async I/O in the API gives little benefit.
- 3.12 is mature and supported by all chosen libraries. uv makes the version independent of the system Python.

## Trade-offs
- The threadpool limits concurrent in-flight requests (default ~40). That is acceptable at this scale, and connection pool size is aligned with it.
- Async-native libraries cannot be used directly in handlers without wrappers.

## Consequences
- DB session per request via a FastAPI dependency. Explicit `session.commit()` in services, never in repositories.
- Worker job handlers use the same sync session factory.
- `pyproject.toml` pins direct dependencies to compatible ranges. `uv.lock` is committed.

## Revisit when
- Measured API latency or throughput is limited by threadpool saturation.
- A feature needs long-lived connections in the API (WebSockets/SSE at scale). SSE with modest concurrency is still feasible with sync handlers plus a small async endpoint.
