# Session 9: Retention, cleanup jobs and the backend close-out

**Plan:** `plan.md` §2 **H17, H18**, §3 **P6-08**, §5 (mutation spot-checks), §6. **Depends on:** session 8. **Commits:** `P6-08a: …` (retention_cleanup), `P6-08b: …` (media_cleanup, promotion_expiry_notices), `P6-10a: …` (acceptance map, isolation and simulation-flag additions, mutation results).

Two parts: build the last backend features first, then close out the whole backend. Do not start the close-out until both jobs are committed and green.

## Read first
- `security-and-privacy.md` §8 and `data-model.md` §4 (lifecycle).
- `environment-variables.md` (Retention), `background-jobs.md` §4 and §6, and `business-knowledge.md` §4 (promotions).
- `content/media.py`, `integrations/storage/local.py` and the `media_assets` status constraint.
- INV-12 and INV-17 (the H17 exceptions and the "no audit purge" decision).
- `acceptance-criteria.md` (every criterion and the DoD).
- `phase-5-sessions/ac-test-map.md` (the format to copy) and the acceptance tables of the phase summaries 1–5.
- `tests/isolation/` (`foreign_ids` conftest) and `tests/integration/test_simulation_flag.py`.

## Build: retention and cleanup (P6-08a, P6-08b)
- Settings: the existing `RETENTION_*` variables plus the four new ones from H17, in `config.py` and `.env.example`.
- `core/retention.py` and the `retention_cleanup` job (periodic 02:00 UTC, `retention:{date}`):
  - every rule in H17, in batches of 1 000 rows, one transaction per batch;
  - audit rows are never touched;
  - write a system-level `retention.cleanup_ran` audit with the counts.
- `media_cleanup` job (02:30 UTC, `media_cleanup:{date}`):
  - H18; delete the file through `MediaStorage`, then set the row to `status = deleted`;
  - the content detail shows the deleted-media text (tr/en) instead of a broken image.
- `promotion_expiry_notices` (per workspace at 09:00 local, `promo_expiry:{ws}:{date}`):
  - H18, `knowledge.promotion_expired` to the `knowledge.verify` holders;
  - add the type to the notification catalog.
- Register the jobs in `app/handlers.py`.
- Docs: `security-and-privacy.md` §8 (what is implemented and the audit-purge deferral), `environment-variables.md`, `background-jobs.md`, `data-model.md` §4, `business-knowledge.md` §4, observability §4.4.

## Build: backend close-out (P6-10a)
- `docs/implementation/phase-6-sessions/ac-test-map.md`: **every** criterion AC-A1…AC-G5 and AC-X1…X8, each mapped to the test(s) that prove it today, with the file and test name. Where the file name differs from the one in `acceptance-criteria.md`, either correct the doc or note why. Mark anything not proven by an automated test as **(manual)** or **GAP**.
- Close every GAP that a backend test can close. List the ones that need E2E for session 10.
- Isolation: add `foreign_ids` coverage for every Phase 6 route (reports, drill-down, activity, operations, system health, members, invites, dev reset and health check). Listing endpoints must never return another workspace's rows.
- Simulation flag (AC-X2 additions): `daily_reports.has_simulated_data`, the notifications created in Phase 6, the history seed rows and the `is_simulated` of activity entries.
- Settings safety (AC-X6) and the redaction and schema tests (AC-X7) cover the new settings and response models: no token field in the invite responses, and the invite token is not logged.
- Run the plan §5 mutation spot-checks one by one, and revert each. Every one must turn a named test red; any that survives gets a new test. Record the results in a table at the end of `ac-test-map.md`.

## Done when
- Frozen-clock retention tests pass for each of these:
  - each rule just before and just after its limit;
  - message text nulled at 365 days, while the metadata is kept and the report counts for that day are unchanged;
  - webhook rows deleted at 90 days;
  - notifications deleted only 90 days after being read, never unread ones;
  - jobs by status;
  - batching (more than 1 000 rows);
  - the audit table row count is unchanged;
  - `retention.cleanup_ran` is written;
  - orphaned media and old published media are deleted from disk, while the media of a scheduled item is kept;
  - each promotion expiry is announced once, the Lisbon workspace at its own 09:00;
  - isolation of the per-workspace job.
- `ac-test-map.md` is complete, with no backend-closable GAP left open.
- The mutation table is filled in and every mutation is reverted (`git diff` is clean apart from the new tests and docs).
- The **full** backend suite, `lint-imports` and the evals (`--all --provider fake --strict`) are green.
