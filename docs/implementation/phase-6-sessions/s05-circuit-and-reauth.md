# Session 5: Circuit breaker, health check and reauth completion

**Plan:** `plan.md` §2 **H10, H11, H12**, §3 **P6-05** (backend). **Depends on:** session 4. **Commits:** `P6-05a: …` (circuit and executor pause), `P6-05b: …` (health check, recovery, reconnect clears rules, dev route).

Take care: this session changes `send.py` and `publish.py`, which Phase 4 and Phase 5 proved with many tests. Run their full test folders after each change.

## Read first
- `workflows.md` §G (G.1, G.2) and §E step 6.
- `state-machines.md` §7.
- `background-jobs.md` §6 (`send_reply`, `publish_content`, `resume_account`).
- `operations/{health,send,publish,accounts,resume,jobs}.py`.
- `integrations/instagram/mock.py` (failure rules, `get_account_profile` with the `profile` operation).
- `jobs/queue.py` (`RescheduleJob`, `expedite`).
- The Phase 5 summary limitations about reconnect (P0-5).

## Build
- Settings `CIRCUIT_FAILURE_THRESHOLD` (5), `CIRCUIT_WINDOW_MINUTES` (10) and `CIRCUIT_COOLDOWN_MINUTES` (10), in `config.py` and `.env.example`.
- Migration `0013` `social_accounts.failure_window_started_at`. Implement `health.record_transient_failure` per H10:
  - it opens `degraded` through `transition_account` (audit `social_account.degraded`);
  - it creates the `account.degraded` notification;
  - `record_success` resets the counter and the window, and restores `connected` from a half-open `degraded`.
- Executors (H11):
  - send and publish skip the provider while `degraded_until > now`, using `RescheduleJob(degraded_until)`, and respect the window end and `execute_before`;
  - publish T1 no longer puts content `on_hold` for a `degraded` account.
- `account_health_check` job and periodic function (H12). The provider call happens with no transaction open:
  - success → `connected`, `account.recovered` and `resume_account`;
  - transient failure → the cooldown is extended;
  - auth error → `needs_reauth`.
- `reconnect_mock` calls a new `MockInstagramProvider.reauthorize(account)`, which deletes that account's `auth_revoked` rules. A reply queued during the reauth is then sent once.
- Dev route `POST /api/v1/dev/workspaces/{ws}/health-check` (demo only, `integrations.manage`).
- Add `account.degraded`, `account.recovered` and `account.permission_missing` (if not done in session 4) to the notification catalog.
- Regenerate the OpenAPI files.
- Docs:
  - `workflows.md` §G and §E 6 (H10–H12);
  - `state-machines.md` §7 (half-open);
  - `data-model.md` (the new column);
  - `background-jobs.md`;
  - `integrations.md` §3.3 (`reauthorize`);
  - `api-design.md` §2.10;
  - `environment-variables.md`.

## Done when
- These tests pass:
  - **AC-G1** `tests/integration/integrations/test_reauth.py`: send and publish → `needs_reauth`, a due post goes `on_hold`, a critical notification is created, reconnect clears the rule, and the queued reply is sent exactly once (assert the simulator count);
  - **AC-G2** `test_rate_limit.py`: the retry waits ≥ 60 s (frozen clock) and stays within the max attempts;
  - **AC-G3** `test_circuit.py`:
    - 5 failures in 10 minutes → `degraded`; 5 failures spread over 11 minutes → still `connected`;
    - **zero provider calls** while degraded (assert the mock call count);
    - a publish is rescheduled and not held;
    - the health check restores `connected` once the rule is removed;
    - a failing health check extends `degraded_until`;
    - recovery resumes a queued reply.
- All existing `tests/integration/inbox`, `content` and `jobs` tests still pass.
- Full backend checks and the OpenAPI drift check are green.
