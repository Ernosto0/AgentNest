# Session 13: Backend close-out tests and mutation checks

**Plan:** `plan.md` §3 **P5-10 (backend part)** and §5 mutation spot-checks. **Depends on:** session 12. **Commit:** `P5-10a: …`.

## Read first
`testing-strategy.md`, `acceptance-criteria.md` (AC-X2, AC-X5, AC-F5), existing `integration/jobs/test_restart.py`, `test_concurrency.py`, `tests/isolation/` (`foreign_ids`, `conftest.py`), `test_simulation_flag.py`, the `@commits` crash-test pattern from Phase 4, the memory note on test-DB quirks.

## Build
- AC-X5 publish case in `integration/jobs/test_restart.py`: a scheduled publish survives a worker restart.
- AC-F5 in `integration/jobs/test_concurrency.py`: two threads execute the same publish → exactly one publication.
- `@commits` crash test: raise right after the T2 container-id commit → re-run → exactly one publication using the stored container id.
- Isolation: add content and media IDs to `foreign_ids`; every new route returns 404 for foreign ids.
- AC-X2: content items, media, containers carry `is_simulated` from the account; API responses expose it.
- Gap-fill: look at the coverage of AC-C4, AC-D1…D8, AC-F1…F7 (F7 is E2E) and add any missing backend test; produce a table AC → test name for the phase summary (save to the scratchpad or report; the final summary is session 14).
- **Mutation spot-checks** (apply, run the named test, confirm it goes red, **revert**; confirm `git diff` is clean afterwards):
  1. drop the container-id commit before publish → crash test red;
  2. allow publish without `FINISHED` → mock/executor test red;
  3. skip the version check in T1 → AC-D6 red;
  4. drop the `workspace_id` filter in the content repository → isolation test red.

## Done when
- Full `uv run pytest` green; `uv run python -m evals run --all --provider fake --strict` green; ruff, format, mypy, `lint-imports` clean.
- Mutation results listed in the report (mutation, test that failed, reverted: yes). No mutation left in the tree.
