# Background Jobs, Scheduling and Domain Events

**Purpose:** The job queue's semantics, the worker runtime, the scheduler, the catalog of job types with payload contracts, and how domain events are represented. Decision record: [ADR-006](decisions/ADR-006-postgres-job-queue.md).

## 1. Model

- **Domain tables are the source of truth** (content status, draft status, operation status). A job is only a *trigger* to act on that state.
- Every handler **re-reads and re-checks** domain state before acting. A duplicate, late or stale job therefore becomes a no-op.
- Jobs are enqueued **in the same transaction** as the state change that requires them (transactional outbox).

## 2. Enqueue API

```python
jobs.enqueue(
    session,
    job_type: str,                 # registered name
    payload: BaseModel,            # validated; IDs only, no secrets or message text
    *,
    workspace_id: UUID | None,
    run_at: datetime | None = None,   # default now (Clock)
    dedup_key: str | None = None,     # if a queued/running job has this key: no new row; returns existing
    priority: int = 100,
    max_attempts: int | None = None,  # default from handler registration
    correlation_id: UUID,
) -> UUID
```

`dedup_key` semantics: `INSERT … ON CONFLICT (dedup_key) WHERE status IN ('queued','running') DO NOTHING`, then select the existing row. For debounce (`draft_reply`), the existing queued job is kept (its `run_at` is **not** extended, so a stream of messages cannot postpone drafting forever).

## 3. Worker runtime

```
loop:
  if shutting_down: break
  job = claim_one()            # see below
  if not job: sleep(WORKER_POLL_INTERVAL_SECONDS); continue
  run(job)
```

**Claim** (one short transaction):
```sql
UPDATE jobs SET status='running', attempts=attempts+1, locked_by=:worker,
       lease_expires_at = now() + make_interval(secs => :lease)
WHERE id = (
  SELECT id FROM jobs
  WHERE (status='queued' AND run_at <= now())
     OR (status='running' AND lease_expires_at < now())     -- crashed worker recovery
  ORDER BY priority, run_at
  FOR UPDATE SKIP LOCKED
  LIMIT 1)
RETURNING *;
```
(The worker uses `Clock.now()` passed as a parameter instead of `now()`, so tests can control time.)

**Run:**
- Bind log context (`job_id`, `job_type`, `workspace_id`, `correlation_id`).
- Validate the payload with the registered model (failure → `dead`, `JOB_PAYLOAD_INVALID`).
- Call the handler with a fresh session factory and the clock. The handler manages its own transactions ([component-design.md §4](component-design.md)).
- Success → `status='succeeded'`, `finished_at`.
- `RetryableError` (or a typed retryable provider or LLM error) and `attempts < max_attempts` → `status='queued'`, `run_at = now + backoff(attempts)` (exponential with ±20 % jitter: 10 s, 60 s, 5 min, 15 min, 1 h by default; overridable per handler or by `retry_after`).
- Other exceptions or exhausted attempts → `status='dead'`, `last_error_code`/`detail`; the handler's `on_dead` hook updates domain state (e.g., draft `failed`, command `failed`) and notifies when user-relevant.
- **Lease** default 120 s (`JOB_LEASE_SECONDS`). Long handlers (publish polling) extend their lease by calling `heartbeat()`. A handler must **never** keep a DB transaction open across an external call.

**Concurrency:** `WORKER_CONCURRENCY` threads per process (default 2), each running the loop. Multiple worker processes are safe (SKIP LOCKED).

**Shutdown:** on SIGTERM/SIGINT, stop claiming and let the current jobs finish up to 30 s. Unfinished jobs are recovered through lease expiry.

**Restart survival ([INV-07](../invariants.md)):** all state is in Postgres. Nothing is scheduled in memory.

## 4. Scheduler (inside the worker)

Every 60 s, one scheduler tick (guarded by `pg_try_advisory_lock(<constant>)`, so only one worker process schedules) enqueues periodic jobs with deterministic dedup keys:

| Periodic job | Cadence | Dedup key |
|---|---|---|
| `expire_approvals` | every minute | `expire_approvals:{yyyy-mm-ddThh:mm}` |
| `generate_daily_report` | per workspace when local time ≥ `daily_report_hour` and no report job for today | `daily_report:{ws}:{local_date}` |
| `refresh_tokens` | daily 03:00 UTC (meta accounts) | `refresh_tokens:{date}` |
| `account_health_check` | every 5 min for `degraded` accounts | `health:{account}:{bucket5m}` |
| `promotion_expiry_notices` | daily per workspace at 09:00 local | `promo_expiry:{ws}:{date}` |
| `retention_cleanup` | daily 02:00 UTC | `retention:{date}` |
| `media_cleanup` | daily 02:30 UTC | `media_cleanup:{date}` |
| `sweep_abandoned_agent_runs` | every 10 min | `sweep_runs:{bucket10m}` |
| `reconcile_stuck_operations` | every 5 min (operations `in_progress` for > 15 min without a running job) | `reconcile_scan:{bucket5m}` |

## 5. Handler rules (checklist for every handler)

1. Payload contains IDs; load everything else fresh.
2. Re-check the subject's state; return early (success) if there is nothing to do.
3. External calls happen **between** transactions, after the operation row is committed as `in_progress` ([ADR-011](decisions/ADR-011-external-operations-ledger.md)).
4. Classify errors: retryable vs permanent vs outcome-unknown.
5. Write audit entries and notifications in the same transaction as the state change.
6. Be idempotent under duplicate execution, including concurrent execution (row locks plus conditional updates).
7. Respect deadlines (`execute_before`, window end).
8. Propagate `correlation_id` to everything it creates.

## 6. Job catalog

| Job type | Payload | Enqueued by | Max attempts | Notes |
|---|---|---|---|---|
| `process_inbound_event` | `{event_id}` | webhook ingest | 3 | workflow C step 2 |
| `draft_reply` | `{conversation_id}` | inbound processing, fact change, manual "suggest reply" | 3 | dedup `draft_reply:{conversation_id}`, debounce `run_at = now + 8 s` |
| `send_reply` | `{reply_draft_id}` | approval decided / auto decision / owner reply / account resumed | 6 | retries only pre-acceptance errors; stops at the window end |
| `reconcile_send` | `{operation_id}` | send outcome unknown | 5 (every 2 min) | echo / lookup; then `OUTCOME_UNCONFIRMED` |
| `interpret_command` | `{command_id}` | command submit, clarification answer | 3 | |
| `generate_content` | `{content_id}` | `content.create_draft` | 3 | |
| `extract_fact_candidates` | `{extraction_run_id}` | paste & extract | 2 | |
| `publish_content` | `{content_id, version}` | content scheduled, retries | 5 | dedup `publish:{content_id}:v{version}`; `run_at = scheduled_at` |
| `reconcile_publish` | `{operation_id}` | publish outcome unknown, container still processing | 10 | container status check |
| `expire_approvals` | `{}` | scheduler | 1 | |
| `generate_daily_report` | `{workspace_id, local_date}` | scheduler, on demand | 3 | |
| `refresh_tokens` | `{}` (fans out `refresh_token` per account) | scheduler | 1 | |
| `refresh_token` | `{social_account_id}` | `refresh_tokens` | 3 | operation `refresh_token:{account}:{date}` |
| `account_health_check` | `{social_account_id}` | scheduler | 1 | |
| `resume_account` | `{social_account_id}` | reconnect / health restored | 3 | re-enqueue queued sends |
| `promotion_expiry_notices` | `{workspace_id, local_date}` | scheduler | 1 | |
| `retention_cleanup` | `{}` | scheduler | 1 | [security-and-privacy.md §8](security-and-privacy.md) |
| `media_cleanup` | `{}` | scheduler | 1 | |
| `sweep_abandoned_agent_runs` | `{}` | scheduler | 1 | |
| `reconcile_stuck_operations` | `{}` | scheduler | 1 | |
| `demo_emit_echo` | `{operation_id}` | mock send (simulated echo) | 1 | demo only |

## 7. Domain events

There is no separate event bus in the MVP. A "domain event" is represented by:
1. an **audit log entry** (the durable record; [observability.md §5](observability.md) lists the actions), and
2. any **jobs** or **notifications** created in the same transaction, and
3. in-process **callbacks** for cross-module reactions that must be atomic (e.g., `approvals` decided → subject module), registered at startup.

Key event flows:

| Event (audit action) | Synchronous reactions (same tx) | Asynchronous reactions (jobs) |
|---|---|---|
| `message.received` | supersede open draft; attention | `draft_reply` (debounced) |
| `reply_draft.created` (approval_required) | approval request, notification | — |
| `approval.approved` (reply.send) | draft `queued` | `send_reply` |
| `approval.approved` (content.publish) | content `scheduled` | `publish_content` at `scheduled_at` |
| `approval.approved` (command.*) | command execution, fact update, impact handling, notifications | `draft_reply` for superseded drafts |
| `fact.updated` | impact handling (drafts, content, answers) | redrafts |
| `operation.outcome_unknown` | subject → outcome_unknown / publishing | `reconcile_send` / `reconcile_publish` |
| `account.status_changed` (→ needs_reauth / degraded) | hold due content; notification | `account_health_check` (degraded) |
| `account.reconnected` | — | `resume_account` |

## 8. Testing hooks

- `jobs.run_due_jobs(clock, limit=100)`: claims and runs due jobs synchronously in the test thread until none are due. Used by integration tests and by the dev endpoint `POST /api/v1/dev/jobs/run-due`.
- `FrozenClock.advance(timedelta)`: combined with `run_due_jobs`, it simulates time passing (scheduled publishing, expiry, backoff, debounce).
- Concurrency test: two threads call `claim_one` on the same job; exactly one succeeds.
- Crash test: a handler raises after committing `in_progress`, the lease expires, and the job re-runs; the ledger prevents duplicate effects.
