# Session 7: Publish executor and reconciliation

**Plan:** `plan.md` §2 **G1, G8, G9, G10, G11, G14**, §3 **P5-06**. **Depends on:** session 6. **Commit:** `P5-06: …` (may split: executor core, then retries/reconcile).

This is the riskiest session. Take care with transaction boundaries.

## Read first
`workflows.md` §E step 6 and §B step 3.4, `state-machines.md` §5/§6, `background-jobs.md` §3/§6, `ADR-011`, the Phase 4 `operations/send.py` and `reconcile.py` (follow the same patterns exactly), `health` module (`handle_auth_error`, `record_success`), error mapping table in `integrations.md` §G.1, `unit/test_side_effect_calls.py`.

## Build
`operations/publish.execute_publish(session_factory, clock, settings, workspace_id, content_id, version, *, provider=None, sleep=time.sleep)`:
1. **T1:** lock item; wrong status/version → no-op (and cancel the waiting op). Due checks: workspace active, `assert_executable`, payload hash, account `connected` + capability, else `on_hold (ACCOUNT_UNAVAILABLE)` + `content.on_hold` notification. Past `execute_before` → `failed (PUBLISH_DEADLINE_PASSED)`. Quota (G8): read-only check → `get_publishing_quota` with **no transaction open** → T1 re-checks; exhausted → `retry_scheduled` at the oldest publish + 24 h if before `execute_before`, else `failed`. Get/create op `publish:{id}:v{n}` (`ON CONFLICT DO NOTHING` + `FOR UPDATE`); an already `succeeded` op repairs the item to `published`. Op `in_progress`, item `publishing`. Commit.
2. Create container if no `provider_ref.container_id` → **T2** commit the id.
3. Poll (G9): every 10 s up to 5 min, `heartbeat()` between polls, no transaction open, elapsed measured with the `Clock`, sleeper injected. `ERROR` → `failed (MEDIA_REJECTED)`; `EXPIRED` → clear id, back to step 2; `PUBLISHED` → step 5. Timeout → enqueue `reconcile_publish`.
4. `publish_container`. Outcome unknown → op `outcome_unknown` + `reconcile_publish` at +1 min.
5. **T3:** `get_media` best effort → op `succeeded`, item `published`, `content.published` notification + audit, `health.record_success`.
6. Error mapping: transient/rate-limited → op `retry_wait`, item `retry_scheduled` using `RetryableError(retry_after_seconds=max(backoff[1,5,15,30 min], retry_after))` on the same job row (G10); permanent → `failed` immediately; auth → `health.handle_auth_error` + item `on_hold (ACCOUNT_UNAVAILABLE)`, op `failed ACCOUNT_NEEDS_REAUTH`; permission → `failed (CAPABILITY_MISSING)`.
- Jobs in `operations/jobs.py`: `publish_content` (max_attempts 5, `on_dead` failsafe → item `failed`), `reconcile_publish` (10). `reconcile_publish` re-reads the container: `FINISHED` → `outcome_unknown → in_progress` + publish again; `PUBLISHED` → succeed. Never blind retry.
- G11: extend `reconcile_stuck_operations` to `publish_content` (`in_progress` > 15 min → `outcome_unknown` → `reconcile_publish`).
- Register the content hooks (`content/hooks.py`) so cancel/hold reach the ledger without `content` importing `operations`; register in `app/handlers.py`; add import contracts.
- Replace any stub handler from session 6.
- Docs: background-jobs §3/§6 (G9, G10, G11), workflows §E (G8).

## Done when
- Tests, **each asserting `sim_published_media` count (INV-06)**: AC-D5; AC-F1…F6 in the file names given by `acceptance-criteria.md`; quota exhaustion → `retry_scheduled`; deadline passed → `failed`; `auth_revoked` at due time → `on_hold`; `timeout_after_success` → reconcile → exactly one post; cancel during `publishing` → 409; polling uses the sleeper, no transaction open while polling (assert via test hook or code-review checklist noted in the report).
- Full backend checks green.
