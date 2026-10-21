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

`dedup_key` semantics: `INSERT … ON CONFLICT (dedup_key) WHERE status IN ('queued','running') DO NOTHING`, then select the existing row. For debounce (`draft_reply`), the existing queued job is kept (its `run_at` is **not** extended, so a stream of messages cannot postpone drafting forever). A job that is already *running* also owns the key, so a trigger that arrives meanwhile is a no-op: the running handler is responsible for noticing it (`RescheduleJob`, §3).

Implementation notes (Phase 1): `enqueue` also takes `clock` (default `SystemClock`; used for the default `run_at`) and never commits. It raises `ValueError` for an unregistered job type, `TypeError` if `payload` is not an instance of the handler's payload model, and `ValueError` if the payload contains a key named `text`, `message`, `message_text`, `body`, `caption`, `token`, `password` or `secret` (payloads carry IDs only).

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
- `RescheduleJob(run_at)` → `status='queued'`, `run_at`, `attempts − 1` (see the implementation notes).
- `RetryableError` (or a typed retryable provider or LLM error) and `attempts < max_attempts` → `status='queued'`, `run_at = now + backoff(attempts)` (exponential with ±20 % jitter: 10 s, 60 s, 5 min, 15 min, 1 h by default; overridable per handler or by `retry_after`).
- Other exceptions or exhausted attempts → `status='dead'`, `last_error_code`/`detail`; the handler's `on_dead` hook updates domain state (e.g., draft `failed`, command `failed`) and notifies when user-relevant.
- **Lease** default 120 s (`JOB_LEASE_SECONDS`). Long handlers (publish polling) extend their lease by calling `heartbeat()`. The publish poll (G9, workflows.md §E step 6) measures elapsed time with the injected `Clock` and waits through an injected sleeper (`execute_publish(..., sleep=time.sleep)`), so tests under a `FrozenClock` pass a sleeper that advances the clock instead of waiting; it polls every 10 s for up to 5 minutes with no transaction open. A handler must **never** keep a DB transaction open across an external call.

Implementation notes (Phase 1):
- **Fencing.** Every outcome update (`succeeded`, retry, `dead`) and every heartbeat is conditional: `UPDATE jobs … WHERE id = :id AND status = 'running' AND locked_by = :worker AND attempts = :n`. An execution that lost its lease (another worker reclaimed the job after expiry) updates nothing, logs `job_lease_lost` and leaves the outcome to the new owner. `heartbeat()` raises `JobLeaseLost` in that case, which aborts the handler without finalising.
- **Dead-letter causes.** Unregistered job type or invalid payload → `dead`, `JOB_PAYLOAD_INVALID` (the detail names fields and error types, never values, and the handler's `on_dead` is not called because there is no valid payload). A job reclaimed after more lease expiries than `max_attempts` (the handler keeps crashing) → `dead`, `INTERNAL_ERROR`, without running again. Any unexpected exception → `dead` immediately, `INTERNAL_ERROR` (no retry: only `RetryableError` retries). An `AppError` → `dead` with its own code. `last_error_detail` is truncated to 500 characters and values after `token|secret|password|authorization|api_key|cookie` are redacted. A failing `on_dead` hook is logged and does not change the `dead` state.
- **`timeout`** in `@job_handler(…, timeout=…)` is the lease (seconds) taken for that job type when it is longer than `JOB_LEASE_SECONDS`. Python threads cannot be killed, so it is not a hard execution limit.
- **(Phase 5) `RescheduleJob(run_at)`** (`jobs/registry.py`): a handler that has nothing wrong but must run again later raises it. The worker re-queues the **same row** at `run_at` with `attempts − 1` (the claim's increment is given back, so the retry budget is only spent on failures), records no error code, and logs `job_rescheduled`. Whatever the handler committed stays committed. The outcome is `rescheduled`; like the others it is a fenced update, so a lost lease changes nothing.
- **(Phase 5) `queue.expedite(session, dedup_key, clock)`**: sets `run_at = now` on a *queued* job with that key whose `run_at` is still in the future (returns whether one moved); a running, finished or already-due job is left alone. It runs in the caller's transaction and never commits (used by `resume_account`).
- **(Phase 5) `queue.cancel_queued(session, dedup_key, clock=None)`**: sets a *queued* job with that key to `cancelled` (with `finished_at` when a clock is given) and returns whether one was cancelled. A running job is left alone (it re-checks the domain state when it runs), and so is a finished one. The dedup key is free again afterwards. It runs in the caller's transaction and never commits (used when an edit, a cancel or a hold takes the publish job of a content version out of play).
- `RetryableError(code, detail, retry_after_seconds=…)` lives in `core/errors.py`. `retry_after_seconds` overrides the backoff schedule.
- **Shutdown** uses one shared 30 s deadline for all worker threads (not 30 s per thread).

**Concurrency:** `WORKER_CONCURRENCY` threads per process (default 2), each running the loop. Multiple worker processes are safe (SKIP LOCKED).

**Shutdown:** on SIGTERM/SIGINT, stop claiming and let the current jobs finish up to 30 s. Unfinished jobs are recovered through lease expiry.

**Restart survival ([INV-07](../invariants.md)):** all state is in Postgres. Nothing is scheduled in memory.

## 4. Scheduler (inside the worker)

Every 60 s, one scheduler tick (guarded by `pg_try_advisory_xact_lock(<constant>)` held for the tick's transaction, so only one worker process schedules; a process that does not get the lock skips the tick) enqueues periodic jobs with deterministic dedup keys. Periodic functions are registered with `register_periodic(fn(session, clock) -> int)` in `jobs/scheduler.py`; each runs in its own savepoint so one failing function cannot block the others. **No periodic job is registered in Phase 1**; the table below is the plan for later phases:

| Periodic job | Cadence | Dedup key |
|---|---|---|
| `expire_approvals` | every minute | `expire_approvals:{yyyy-mm-ddThh:mm}` |
| `generate_daily_report` | every tick, per active workspace whose local time is at or past its `daily_report_hour` (workspace setting, default 20) and which has had **no job at all** for that local day (queued, running, succeeded or dead: the dedup index covers only queued and running jobs, so the tick looks at every status, otherwise a finished day would be enqueued again each minute). Implemented in `reporting/jobs.py` (Phase 6) | `daily_report:{ws}:{local_date}` |
| `refresh_tokens` | daily 03:00 UTC (meta accounts) | `refresh_tokens:{date}` |
| `account_health_check` | every 5 min for `degraded` accounts (`operations/jobs.py`, payload `{social_account_id}`, 1 attempt: the next tick is the retry). Calls `get_account_profile()` with no transaction open; success → `connected` + `account.recovered` + `resume_account`, transient failure → cooldown extended, auth error → `needs_reauth` | `health:{account}:{bucket5m}` |
| `promotion_expiry_notices` | every tick, per active workspace whose local time is at or past 09:00 and which has had no job for that local day in any status (same rule as the daily report). Implemented in `knowledge/promotion_notices.py` (Phase 6) | `promo_expiry:{ws}:{date}` |
| `retention_cleanup` | every tick from 02:00 UTC, once per UTC day: like the daily report, it looks for a job with the day's key in **any** status, so a finished day is not enqueued again. Implemented in `retention/jobs.py` (Phase 6) | `retention:{date}` |
| `media_cleanup` | every tick from 02:30 UTC, once per UTC day (any-status check like `retention_cleanup`). Implemented in `content/media_cleanup.py` (Phase 6) | `media_cleanup:{date}` |
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
| `draft_reply` | `{conversation_id, message_id?, requested}` (`message_id` is optional and no longer set) | inbound processing, release to automatic, fact change, manual "suggest reply" | 3 | **One job per conversation**: dedup `draft_reply:{conversation_id}`, `run_at = now + 8 s` on the first trigger and **not extended** by later ones. The job drafts for the newest inbound message at the time it runs. A message that arrives *while it runs* cannot enqueue (the running job owns the key), so at the end of T3 the job checks, under the conversation lock, whether a newer inbound message exists; if so it discards its result and raises `RescheduleJob(now + debounce)` (no attempt consumed). Nothing is swallowed and no second job exists. An explicit "suggest reply" uses its own key `draft_reply:{conversation_id}:requested` because it carries `requested = true`, which a job queued by a customer message does not. A fact change, a release and a customer message all share the first key, so a redraft waits for the conversation's debounce window |
| `send_reply` | `{reply_draft_id}` | approval decided / auto decision / owner reply / account resumed | 6 (backoff 1 / 5 / 15 / 30 / 30 min; a larger `Retry-After` wins) | retries only pre-acceptance errors; stops at the window end. An unusable account (needs reauth, disconnected) keeps the draft `queued` and retries every 5 minutes (the job may run out of attempts before the window ends; the expiry sweep ends the draft at the window end). Reconnecting the account resumes it: `resume_account` (below) makes the job due now, or creates a new one if it ended |
| `reconcile_send` | `{operation_id, round}` | send outcome unknown | one job per check, at +2 min and then every 2 min for `SEND_RECONCILE_WINDOW_MINUTES` (own dedup key per round) | echo / lookup; then `OUTCOME_UNCONFIRMED`. A late echo after that is recorded as our message (`reply.late_confirmation`) |
| `interpret_command` | `{command_id}` | command submit, clarification answer | 3 | |
| `generate_content` | `{content_id, version}` | `POST /content-items/generate` (and `content.create_draft`, P5-03b) | 3 (backoff 10 s / 60 s / 300 s; lease 150 s) | dedup `generate_content:{content_id}`. Three phases with no transaction open during the model call (workflows.md §E step 1); the brief lives on the queued `agent_runs` row, not in the payload. A late result is discarded when the draft was edited (a new version); a replay after a crash saves the run's stored output without a second call. `on_dead`: the run is `failed` with the job's code and the draft stays manual |
| `extract_fact_candidates` | `{extraction_run_id}` | paste & extract | 2 | |
| `publish_content` | `{content_id, version}` | content scheduled (`service.submit` self-approved, the `content_item` approval callback, `service.reapprove`), retries from `reconcile_publish` | 5 | dedup `publish:{content_id}:v{version}`; `run_at = scheduled_at`. Handler: `operations.publish.execute_publish` (workflows.md §E step 6). Lease 420 s (`timeout`; the polling budget is 5 min), extended by `heartbeat()` after each poll (G9). **Retries (G10)**: a transient or rate-limited error raises `RetryableError(retry_after_seconds = max(backoff[1, 5, 15, 30 min], Retry-After))`, so the **same job row** runs again; the operation's `max_attempts` (5) and `deadline_at` (= `execute_before`) decide when the item becomes `failed` instead. A used-up provider quota (G8) is not a failure: the job raises `RescheduleJob(oldest post + 24 h)` and spends no attempt. `on_dead` failsafe: a job that dies (unexpected error, exhausted attempts) makes a `scheduled` / `retry_scheduled` item `failed` with the job's code; an item that is `publishing` with an operation `in_progress` becomes `outcome_unknown` + `reconcile_publish` instead (the provider may have been called, so it is never failed blindly) |
| `reconcile_publish` | `{operation_id}` | publish outcome unknown (`publish_container` timeout or unexpected error), container still processing after 5 min of polling, or found `in_progress` by `reconcile_stuck_operations` | 10 | dedup `reconcile_publish:{operation_id}`, first check at +1 min. Reads the container: `PUBLISHED` → succeed (also past the deadline), the permalink fetched through `ContainerStatus.media_id`; `FINISHED` → `outcome_unknown → in_progress` and publish again (proven unpublished); `EXPIRED` or no container → clear the id, new container; `IN_PROGRESS` or an unreadable container → `RescheduleJob(+1 min)` on the same row (no attempt spent); `ERROR` → `failed MEDIA_REJECTED`; past the deadline → `failed PUBLISH_DEADLINE_PASSED` (proven unpublished) or `OUTCOME_UNCONFIRMED` (unreadable). A retryable error of the repeated publish queues a `publish_content` job at the backoff (no job is running to retry). `on_dead`: `failed OUTCOME_UNCONFIRMED`, never a second publish |
| `expire_approvals` | `{}` | scheduler | 1 | |
| `generate_daily_report` | `{workspace_id, local_date}` | scheduler (`reporting/jobs.py`); the on-demand `POST …/reports/daily/generate` runs the same service call inline and enqueues nothing | 3 | `reporting.service.generate_daily_report(scheduled=True)`: stores the report for `local_date` (the whole day, or up to the run time for today, so a 20:00 run is partial), audits `report.generated` and announces it with `report.daily_ready` (info, every `reports.view` holder, dedup `report:{local_date}`) in the same transaction. A re-run overwrites the row and does not announce again while the notification is unread. Does nothing for a workspace that is no longer `active` |
| `refresh_tokens` | `{}` (fans out `refresh_token` per account) | scheduler | 1 | |
| `refresh_token` | `{social_account_id}` | `refresh_tokens` | 3 | operation `refresh_token:{account}:{date}` |
| `account_health_check` | `{social_account_id}` | scheduler | 1 | |
| `resume_account` | `{social_account_id}` | reconnect (`accounts.reconnect_mock`, Phase 5); health restored (`health.recover`, Phase 6) | 3 | dedup `resume_account:{account}`. Does nothing unless the account is `connected` with `messaging`. For every `queued` reply draft of the account whose messaging window is still open (> 60 s left): `enqueue(send_reply, dedup send_reply:{draft}, run_at = now)` then `queue.expedite(...)`, so a sleeping job is made due, a running job is left alone and a dead or missing job is replaced. The send itself is the ordinary `send_reply` (ledger, reconcile, one operation per draft). It does **not** resume `on_hold` content (workflows.md §G.2) |
| `promotion_expiry_notices` | `{workspace_id, local_date}` | scheduler (`knowledge/promotion_notices.py`) | 1 | Announces every verified `promotion.*` fact whose `valid_until` is the day before `local_date` (it became unusable at 00:00 local, within the 24 h before the 09:00 run), once, with `knowledge.promotion_expired` (attention) to every `knowledge.verify` holder; dedup per recipient `promotion-expired:{fact_id}:{valid_until}`. Changes no data. Does nothing for a workspace that is no longer `active` |
| `retention_cleanup` | `{}` | scheduler (`retention/jobs.py`) | 1 | `retention.cleanup.run_retention`: every rule in batches of 1 000 rows, each batch its own transaction, then one system-level audit entry `retention.cleanup_ran` with the counts. Audit rows are never touched. A rule that was cut short (crash) is simply continued by the next day's run. [security-and-privacy.md §8](security-and-privacy.md) |
| `media_cleanup` | `{}` | scheduler (`content/media_cleanup.py`) | 1 | Deletes the file of every unused asset ([security-and-privacy.md §8](security-and-privacy.md)), then sets the row to `deleted`; one asset at a time, no transaction open during the delete. A failing delete leaves the row `ready` for the next run |
| `sweep_abandoned_agent_runs` | `{}` | scheduler | 1 | |
| `reconcile_stuck_operations` | `{}` | scheduler | 1 | **G11**: an operation `in_progress` for more than 15 minutes (`started_at`, reset at every attempt) becomes `outcome_unknown` and is handed to its reconciler: `send_reply` → `reconcile_send`, `publish_content` → `reconcile_publish`. A publishing worker that crashed therefore ends as `published` (the container is `PUBLISHED`) or as one more publish of the **stored** container (`FINISHED`), never as a blind second publish. A re-run of the publish job itself finds the item `publishing` and does nothing |
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
| `social_account.needs_reauth` / `social_account.degraded` (the audited status change) | hold due content; notification | `account_health_check` (degraded) |
| `account.reconnected` | audit (Phase 5: the mock reconnect action) | `resume_account` |

## 8. Testing hooks

- `jobs.run_due_jobs(clock, limit=100)`: claims and runs due jobs synchronously in the test thread until none are due. Used by integration tests and by the dev endpoint `POST /api/v1/dev/jobs/run-due`.
- `FrozenClock.advance(timedelta)`: combined with `run_due_jobs`, it simulates time passing (scheduled publishing, expiry, backoff, debounce).
- Concurrency test: two threads call `claim_one` on the same job; exactly one succeeds.
- Crash test: a handler raises after committing `in_progress`, the lease expires, and the job re-runs; the ledger prevents duplicate effects.
