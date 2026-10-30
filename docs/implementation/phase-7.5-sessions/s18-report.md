# Session 18 report: rollout and close-out

**Status: offline rehearsal and documentation complete; real/model/manual acceptance pending.**
Session 17's final regression evidence is recorded below. This report does not
authorize a real-account cutover or declare Phase 7.5 complete.

## Baseline and changes

Started from clean `main` at `f0d95f9` on 2026-10-30. Session 17 worked concurrently on
its evaluator and report; those changes were preserved. No migration, API contract,
provider capability or production configuration was changed by Session 18.

- Added `test_rollout_rehearsal.py`: committed-transaction, two-account mock cutover
  proves one account's pending approval is cancelled after legacy rollback while the
  other account stays active and sends through the ledger. Further cases cover an
  approved queued send fenced before dispatch, a pending owner question retained without
  agent continuation, and a timeout-after-success operation retaining `outcome_unknown`
  evidence and only one remote mock effect. Existing tests also cover populated 0018
  upgrade, epoch fencing, stale legacy/agent dispatch and recovery.
- Extended `test_dm_api.py` to prove the owner pause API increments the epoch before a
  legacy rollback. The runbook uses the workspace-scoped API path.
- Added the [operator runbook](../../operations/account-agent-rollout.md) for activation,
  pause, rollback, reconciliation, memory, questions, approvals, moderation, budgets and
  disconnect. Added Phase 8 data/security and Phase 9 owner-channel handoffs.
- Wrote the [provisional phase summary](../phase-summaries/phase-7.5-summary.md).

## Verification

Windows PowerShell, Python 3.12 via `python -m uv`, Postgres 16 in Docker. Dedicated
disposable `agentnest_s18_test` database; the test harness rebuilt its schema to current
head. Both live Meta inputs were blanked. Exact command from `backend/`:

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://agentnest:agentnest@localhost:5433/agentnest_s18_test'
$env:META_LIVE_ACCESS_TOKEN=''
$env:META_LIVE_IG_USER_ID=''
python -m uv run pytest tests/integration/agent/test_rollout_rehearsal.py -q --tb=short
```

The final combined run with the existing populated-upgrade and controller API tests
passed **6 tests in 13.87s** using the same isolated database:

```powershell
python -m uv run pytest tests/integration/agent/test_rollout_rehearsal.py tests/integration/agent/test_migration.py tests/integration/agent/test_dm_api.py -q --tb=short
```

This includes the final pause assertion.

`python -m uv run ruff format
tests/integration/agent/test_rollout_rehearsal.py` reformatted the file, and targeted
`ruff check` and `ruff format --check` passed. An exploratory `mypy` invocation against
the test file failed with 95 errors in three imported test modules, mostly untyped
shared fixtures and nullable claims; the required `mypy app evals` gate is separate.
Session 17's final regression run passed: backend **3307 passed, 10 intentional live-probe
skips**; frontend **516 passed**; strict legacy fake eval **166/166**; agent journey
command **69 passed**; and production-build Playwright **177 passed, 3 intentional skips**
across three browser projects. Ruff, format, mypy, import rules, frontend lint, typecheck,
i18n and build passed. The generated API client had no drift. The initial failing full
runs and Docker interruption remain documented in [Session 17](s17-report.md); clean
reruns supersede them. The 60-case scripted fixture still exercises one repeated
two-turn path, so broader behavioral/model quality acceptance remains open. No
live-account action, paid model evaluation, deployment or push occurred.

The exact drill coverage is:

| Required state | Evidence |
|---|---|
| Populated legacy upgrade and other accounts retained | `test_migration.py::test_upgrade_backfills_legacy_and_downgrade_refuses_agent_evidence`; `test_rollout_rehearsal.py::test_rollback_fences_pending_approval_and_keeps_other_account_active` |
| Queued jobs and old controller epoch | `test_dm.py::test_legacy_job_queued_before_cutover_never_calls_legacy_model`; `test_dm.py::test_cutover_racing_claimed_send_never_dispatches_displaced_controller` |
| Waiting owner question | `test_rollout_rehearsal.py::test_waiting_question_survives_rollback_without_agent_dispatch` |
| Pending and approved action | `test_rollout_rehearsal.py::test_rollback_fences_pending_approval_and_keeps_other_account_active`; `test_rollout_rehearsal.py::test_approved_queued_send_is_fenced_by_rollback` |
| Ambiguous operation | `test_rollout_rehearsal.py::test_rollback_keeps_ambiguous_send_for_reconciliation` |
| Worker crash and recovery | `test_dm.py::test_crash_after_result_commit_before_wake_is_recovered_without_second_effect`; `test_coordinator.py::test_committed_intent_is_not_duplicated_after_worker_crash` |

The four named `test_dm.py`/`test_coordinator.py` tests were also rerun separately on the
same dedicated database: **4 passed in 12.58s**. The worker-crash and cutover paths are
covered by separate committed-transaction tests; their combined interleaving is still
a final release drill to repeat with the founder trial environment.

## Acceptance and handoff

The new rehearsal adds offline evidence for **AC75-17** (controller switch/pause
fencing), **AC75-16** (uncertain send remains visible) and **AC75-22** (legacy account
remains functional). It does not prove real provider reconciliation, phone usability or
model behavior. AC75-23 and G7.5-D/E remain pending: R75-01 through R75-06 lack
authentic capability evidence, and production Meta comment capabilities stay disabled.
G7.5-C awaits authorized real-model evaluation with a spending budget and human rating.

The phase summary records the exact clean full-suite and eval outcomes. A named founder
account and action list require explicit authorization before an application-ledger trial.
Use the runbook's sanitized evidence list, perform
Windows and real-phone TR/EN walkthroughs, then rerun required checks after any fix.
Do not turn a pending external gate into a pass or downgrade agent evidence.
