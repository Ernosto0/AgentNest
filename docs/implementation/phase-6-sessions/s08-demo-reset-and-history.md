# Session 8: Demo reset and seeded history

**Plan:** `plan.md` §2 **H15, H16**, §3 **P6-07**. **Depends on:** session 7. **Commits:** `P6-07a: …` (reset), `P6-07b: …` (history seed), `P6-07c: …` (test and E2E assertion updates for the new seed, if any).

This session changes the seed that every E2E spec starts from. Expect to update assertions in earlier specs, but never behaviour.

## Read first
- `local-development.md` §5, §6 and §8, and `api-design.md` §2.10.
- INV-12 and INV-20.
- `demo/{seed,facts_seed,connections_seed,simulator,dev_router}.py`, `app/cli.py` (`seed --reset`) and `jobs/testing.py` (`run_due_jobs`).
- `core/clock.py` (`FrozenClock`) and `integrations/storage/local.py`.
- `frontend/e2e/global-setup.ts` and `helpers.ts`.

## Build
- `demo/reset.py` (H15):
  - `reset_workspace(slug | id)`, shared by `seed --reset` and `POST /api/v1/dev/workspaces/{ws}/reset`;
  - re-create the workspace with a new id, delete the `sim_*` rows and the local media files of the old one, and leave the audit rows untouched;
  - audit `demo.reset` with `previous_workspace_id`;
  - `is_demo` only (else 403); a demo workspace that is not in the seed data → 409; returns `{workspace_id}`.
- `demo/history_seed.py` (H16):
  - yesterday's history for both studios, run through the real paths with a `FrozenClock` (the exact counts are in the phase doc), then store yesterday's report;
  - run by `seed` when a demo workspace has no conversations, and by reset;
  - leave no non-periodic job queued.
- Dev panel: **Demo'yu sıfırla**, with a confirmation, then navigate to the new workspace id.
- Regenerate the OpenAPI files.
- Docs: `api-design.md` §2.10, `local-development.md` §5 ("P6: one day of history" made concrete), §6 (finish with the reset) and §8.

## Done when
- Tests pass:
  - reset of a demo workspace: new id, same slug and members, facts, account and history present, and the old `sim_*` rows and media files gone;
  - a non-demo workspace → 403 and nothing changes;
  - with `DEMO_TOOLS_ENABLED=false`, the route returns 404 (INV-20);
  - other workspaces are byte-for-byte untouched (counts per table);
  - yesterday's report equals exactly 6 inbound, 4 replies, 1 escalation, 1 published post and 1 failed post (plus the derived metrics, asserted);
  - every history row is `is_simulated`;
  - no stray queued jobs;
  - `seed` run twice adds the history once.
- The **full backend suite** and the **full E2E suite** (3 projects) are green. Every spec or test changed because of the new history is listed in the report, with the reason.
- Frontend checks are green.
