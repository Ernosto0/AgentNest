# Session 05 report: durable coordinator

**Status:** Offline complete, operator reviewed. Combined regressions and the final focused checks passed. No live/model-quality acceptance is claimed.

## Baseline and preserved work

Started from clean `main` at `d7d3c01` on 2026-10-27 in the actual Windows checkout `C:\Users\ernos\AgentNest` (the requested Linux path does not exist in this environment). The operator read common rules and Sessions 01–04 reports. This subsession read the Session 05 brief, canonical contract, source repositories, broker, runner, queue/worker and lease/recovery tests. Sessions 01–04 remain the foundation; Session 08's early audit is preserved for its owning session to replace. No commit, push, deployment, paid model call or live Meta action occurred.

## Implemented behavior

- `app/agent/coordinator.py` claims one thread under account/thread/session locks, persists a unique token, cursor, controller epoch, delegation version, deletion generation and a 90-second lease, commits, calls the model outside a transaction, then rechecks freshness and the activation deadline before local tool dispatch. Tool handlers commit local reads/intents; network effects belong to operations jobs.
- Explicit complete, customer/approval/operation wait, handoff/failure and server-owned `sleep_until` scheduling paths. Matching persisted action/approval/operation scope is required; owner wait fails closed until Session 09 owns that service. Waiting workers return immediately. Recovery detects persisted approval/operation outcomes even if a callback wake was lost. Unknown operations stay unresolved.
- Durable `agent_wake`, `agent_continue`, `agent_wake_due`, `agent_recover` and stale-approval-cleanup handlers. Event wake keys include the cursor, so an inbound event committed after a handler returns but before its worker finalizes cannot be swallowed by an old running row. Thread claims coalesce duplicate computation. Recovery excludes indefinite waits/terminal states from its bounded SQL batch and rotates eligible rows.
- Migration `0021`, after `0020`, stores activation cursor/start/call/tool counters, cumulative token reservation and a safe outcome code. Each activation permits 8 calls including repairs, 12 tools and 120 seconds; unresolved goals permit 24 calls. Each step conservatively reserves 40,000 tokens for original/repair, within a 960,000 goal cap; context/schema is bounded at 16,000 UTF-8 bytes and output at 800 tokens per call. Three identical tool dispatches are allowed; the fourth hands off. Retries/restarts never refund reservations. Known usage is reconciled from linked runs, including stale results and crashes before result bookkeeping; unknown transport usage retains its reservation. No dollar-price assumption is introduced.
- Legacy and agent runners serialize workspace daily admission and repair reservation under the same workspace lock/count semantics. Denied agent repairs retain the already consumed call in legacy budget reads. A step with prior model-call evidence cannot be submitted again; recovery creates another charged step.
- Successful built-in read requests checkpoint only closed routing arguments; a non-null fact cursor must match an existing scoped fact key. Resume reloads current scoped domain data rather than storing customer bodies or tool results in generic steps. Later write/effect handlers must recover observations from their durable domain/action records and use stable intent admission. A synthetic internal-intent tool test proves a repeated proposal after a committed-intent/worker crash admits only one action.
- Own-message/echo/outbound events are rejected by the conversational event writer. Terminal goals mark the latest processed cursor, preventing a second goal from a duplicate wake at that cursor.
- Policy and pause/resume transactions enqueue stale cleanup after epoch advancement and never lock approvals. Approval callbacks now use approval -> account -> action order; cleanup matches it. Existing authorization/executor paths use account -> action. Cleanup closes stale pending rows without touching in-flight ledger outcomes. Approval decisions enqueue a durable wake.

Affected contracts: canonical account-agent contract and data model now document migration 0021, budgets, read checkpoints, wake dedup change, recovery and lock order. No new HTTP contract was introduced, so OpenAPI/client regeneration is not required.

## Verification evidence

Environment: Python 3.12 local venv, PostgreSQL 16 `agentnest_test` at localhost:5433, frozen clocks, fake LLM and mock Instagram only. Test database fixtures rebuild their disposable schema. The operator started local PostgreSQL; no credentials or personal production data were used.

| Command / evidence | Actual result |
|---|---|
| `.venv\Scripts\pytest.exe tests/integration/agent/test_coordinator.py -q --tb=short` (initial version) | 10 passed in 10.47s; superseded by the clean operator reruns below. |
| Operator `.venv\Scripts\python.exe -m pytest tests/integration/agent/test_coordinator_review.py -q --tb=short --basetemp tmp-s05-review -p no:cacheprovider`, `COOKIE_SECURE=false` | 2 passed in 2.24s: denied repair cannot refund legacy quota; concurrent stale decision/cleanup cancels without deadlock. The third real-worker stale-inbound/wakeup test subsequently passed in the combined operator run. |
| `.venv\Scripts\mypy.exe app evals` | Passed, 265 source files after final source changes. |
| `.venv\Scripts\lint-imports.exe` | Passed, 19 contracts / 0 broken. |
| Focused `ruff check` and `ruff format` on changed Session 05 backend/tests/migration files | Passed. |
| Whole-backend `ruff check` / `ruff format --check` | Same baseline 3 lint issues and 3 formatting issues recorded by Session 02, in unchanged matching.py, draft_content.py, knowledge/values.py and test_templates.py. Not silently fixed. |
| `git diff --check` | Passed before final report update; operator will recheck final diff. |

Expanded tests now include duplicate concurrent claims, successful restart within the activation, expired claim budget preservation, stale cursor/epoch/deletion/takeover, real worker read/followup, durable read checkpoint resume, scheduled wake through recreated workers, 201 indefinite waits preceding runnable recovery, committed action intent crash/replay, echo rejection, stale usage/no-open-model-transaction, transient retry, and operator stale-inbound/cleanup/quota tests. These implementations passed in the final combined and focused operator runs below.

Failed verification attempts are retained:

1. Initial combined agent/runner/jobs command: 1 failed, 66 passed, 24 setup errors. Failure was the old persistence assertion expecting the thread-only wake key (updated to the new cursor key). Setup errors were local secure cookies with HTTP TestClient and restricted default temporary directory access.
2. With process-only `COOKIE_SECURE=false` and workspace basetemp: 77 passed, 18 setup errors because the requested nested basetemp parent was absent. Using a direct existing-workspace parent resolves it.
3. Broader command with valid basetemp: 4 failed, 95 passed; local enabled providers excluded mock. No code pass was inferred from a focused retry.
4. `COOKIE_SECURE=false`, `INSTAGRAM_ENABLED_PROVIDERS=mock`, `LLM_PROVIDER=fake`; `.venv\Scripts\pytest.exe tests/integration/agent tests/integration/ai/test_runner.py tests/integration/jobs tests/integration/approvals tests/integration/inbox/test_send.py tests/integration/content/test_publish.py -q --tb=short -p no:cacheprovider --basetemp tmp-session05-final`: **18 failed, 169 passed in 111.48s**. All failures were existing publishing paths with `MEDIA_REJECTED`, consistent with local storage configuration; operator is rerunning with explicit `MEDIA_STORAGE_BACKEND=local`. The clean combined operator rerun below resolves these failures and includes the later tests.

## Acceptance and remaining boundaries

Final operator verification used process-only `COOKIE_SECURE=false`, `INSTAGRAM_ENABLED_PROVIDERS=mock`, `LLM_PROVIDER=fake`, `MEDIA_STORAGE_BACKEND=local` and ran `.venv\Scripts\python.exe -m pytest tests/integration/agent tests/integration/ai/test_runner.py tests/integration/jobs tests/integration/approvals tests/integration/inbox/test_send.py tests/integration/content/test_publish.py -q --tb=short -p no:cacheprovider --basetemp tmp-session05-operator`: **190 passed in 110.05s**. This clean combined rerun resolves the prior configuration failures. After the last context-bound change, `.venv\Scripts\python.exe -m pytest tests/integration/agent -q --tb=short -p no:cacheprovider --basetemp tmp-session05-final-agent` passed **41 tests in 29.01s**. All three operator regressions are included. Focused Ruff passed on 20 files; mypy passed 265 files; all 19 import contracts passed; final `git diff --check` passed. Operator inspection verified approval lock ordering, cursor-specific wake keys, bounded recovery, restart checkpoints, and charged stale/repair calls. These checks supersede the pending-result language in the historical verification table above.

Foundational AC75-02/08/14/15/21 behavior has passed offline tests and operator review. No end-to-end live DM/comment tool, paid model selection quality or external exactly-once guarantee is claimed. Actual DM projection/cutover is Session 07; owner question persistence/continuation is Session 09; comment executors are later than Session 10.

Read-only checkpoints survive restart by re-reading current facts/messages. Future write/effect tool observations must be rebuilt from their own domain/action records; generic personal output storage is deliberately absent. The Session 05 synthetic intent test validates stable action admission, not a remote effect. Session 07 must exercise real mock send-ledger recovery and wire controller epoch updates/legacy cutover explicitly. Long human waits are persisted, while owner-question semantics remain closed until Session 09.

## Next-session handoff

Migration head is `0021`. Session 06 should replace broker all-facts-then-slice retrieval with bounded scoped SQL, add context/personality/grounding per its brief, and retain safe read checkpoint behavior when read schemas change. Use `run_activation`, `claim`, `fresh`, `set_state`, `step_state`, `sleep_until` and the default broker interfaces. Keep fake offline configuration explicit in test processes; local `.env` contains production-like cookie/provider/storage choices and must not be edited for test convenience.

Session 07 must use stable intent admission and the existing DM ledger, recreate write-tool results from domain/action references on resume, and emit eligible customer/result wakes; do not route echo/outbound events to `add_event_and_wake`. Session 09 extends persisted owner wait validation/resolution. No automatic commit/push/deploy is authorized.
