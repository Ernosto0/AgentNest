# ADR-004: PostgreSQL as the only datastore (no Redis in MVP)

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
The original spec proposes PostgreSQL, Redis (queueing and coordination) and optionally S3. The system needs persistent state, version history, a job queue that survives restarts, scheduled jobs, deduplication and audit logs. Budget and operational simplicity matter.

## Alternatives
1. PostgreSQL + Redis (+ Celery/RQ).
2. **PostgreSQL only** (jobs, locks, dedup, sessions in Postgres).
3. SQLite for local dev, PostgreSQL in production.

## Decision
Option 2. PostgreSQL **16** (any ≥ 15 is acceptable) is the single datastore in every environment: development, test, CI and production. Media binaries are not stored in Postgres ([ADR-015](ADR-015-media-storage.md)).

PostgreSQL features we rely on:
- `SELECT … FOR UPDATE SKIP LOCKED` for job claiming ([ADR-006](ADR-006-postgres-job-queue.md)).
- Partial unique indexes (e.g., one pending approval per subject, one active Instagram account per workspace).
- `INSERT … ON CONFLICT DO NOTHING` for deduplication.
- `JSONB` for typed-but-flexible payloads (fact values, raw webhooks, LLM outputs).
- Composite foreign keys for tenant integrity ([ADR-013](ADR-013-authentication-and-tenancy.md)).
- Row-Level Security as a later defence-in-depth layer.

## Rationale
- Removes a service and the **dual-write problem**: a state change and its follow-up job commit atomically.
- Restart survival comes for free: all queued and scheduled work is rows in tables.
- SQLite would diverge on exactly the features above (SKIP LOCKED, partial indexes, JSONB operators), so tests would not prove production behaviour.

## Trade-offs
- The local demo needs Docker (or a local Postgres install). Mitigation: a single `docker compose up -d postgres` command is documented, plus troubleshooting for Windows.
- Polling-based job claiming adds DB load. That is negligible at expected scale (one indexed query every 1–2 s per worker).
- No pub/sub. If needed, Postgres `LISTEN/NOTIFY` can wake workers without Redis.

## Consequences
- `docker-compose.yml` defines `postgres` (host port **5433** to avoid clashing with a native install), with a second database for tests.
- Integration tests run against real Postgres. Unit tests do not touch the DB.

## Revisit when
- Job throughput exceeds what one Postgres instance handles comfortably (thousands of jobs per minute), or rate limiting across many API replicas needs shared fast counters. At that point Redis is an *addition* behind the existing interfaces, not a rewrite.
