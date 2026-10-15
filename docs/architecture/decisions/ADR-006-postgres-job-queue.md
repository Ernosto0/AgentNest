# ADR-006: PostgreSQL-backed job queue and scheduler

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
We need delayed jobs (publish at 19:00), retries with backoff, periodic jobs (daily reports, token refresh), deduplicated enqueueing (debounced reply drafting), survival across restarts, visibility of job state in the activity log, and deterministic tests with a controllable clock. [ADR-004](ADR-004-postgresql-only-datastore.md) excludes Redis.

## Alternatives
1. **Celery + Redis**: mature, but a broker dependency, a dual-write problem, and awkward deterministic testing.
2. **Existing Postgres-based Python queue library** (e.g., Procrastinate): mature features (scheduled jobs, periodic tasks, locks). Its own schema and conventions; workspace scoping and domain visibility sit outside our model; it is async-first.
3. **In-house job table** of about 300 lines: `jobs` table, claim with `FOR UPDATE SKIP LOCKED`, leases, retries, dedup keys, periodic scheduler.

## Decision
Option 3, with a deliberately small scope. Details in [background-jobs.md](../background-jobs.md):
- `jobs` table: `job_type`, `payload` (JSONB, validated by a Pydantic model per job type), `workspace_id` (nullable for system jobs), `status`, `run_at`, `attempts`, `max_attempts`, `lease_expires_at`, `locked_by`, `dedup_key` (unique among non-terminal jobs), `last_error_code`, `correlation_id`.
- Enqueue happens **inside the caller's transaction**, which acts as a transactional outbox.
- The worker claims due jobs, runs each handler in its own transaction scope, and records outcomes. Retryable errors reschedule with exponential backoff and jitter. Non-retryable or exhausted jobs become `dead`, and an audit/notification is emitted where relevant.
- An expired lease makes a `running` job claimable again, so **handlers must be idempotent** (that is also how they must be written anyway; see [ADR-011](ADR-011-external-operations-ledger.md)).
- A periodic scheduler inside the worker inserts recurring jobs every minute using deterministic dedup keys (e.g., `daily_report:{workspace_id}:{local_date}`).
- An injectable `Clock`. Tests use `FrozenClock` and call `run_due_jobs(clock)` synchronously.

## Rationale
- Transactional enqueue removes a whole class of consistency bugs.
- Domain needs are specific: workspace scoping, correlation IDs, debounce via dedup keys, and test-time determinism. These are easier to own than to adapt.
- The pattern (`SKIP LOCKED` + leases) is well known and small.

## Trade-offs
- We own the queue's bugs. Mitigation: a focused test suite (concurrency, lease expiry, dedup, backoff, restart) in Phase 1.
- No built-in monitoring UI. Mitigation: the activity view and a dev-only jobs page.
- Polling latency of about 1 s.

## Consequences
- The domain state (e.g., `content_items.status = scheduled`) is the source of truth for users. The job is only the trigger. Handlers re-read and re-check domain state before acting, so a stale or duplicate job is harmless.
- Separate from domain tables: no "scheduled_jobs" domain table as in the original spec. Users see content status, not job rows.

## Revisit when
- Job volume or latency requirements outgrow polling (see [ADR-004](ADR-004-postgresql-only-datastore.md)).
- The in-house queue accumulates bespoke features beyond its scope. At that point, evaluate migrating to a library behind the same `enqueue()`/handler interface.
