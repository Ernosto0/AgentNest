# Phase 6: session briefs

Phase 6 (reports, activity, failure UX and demo completion) is split into **11 Claude sessions**. `plan.md` in this folder is the authoritative plan: tasks P6-01…P6-10, decisions H1–H18, import contracts and verification. Each session brief says only *which slice* of the plan to build, what it depends on, and when it is done.

## Before you start (owner)
1. Commit this folder: `Phase 6: implementation plan and session briefs`.
2. Confirm or change the ⚑ decisions in `plan.md` §2. A changed decision is edited in `plan.md` before its session runs.
   - **H1:** drill-down list per metric. Needed before session 1.
   - **H10:** new column for the circuit window. Needed before session 5.
   - **H14:** invite accept takes an email; the UI builds the link. Needed before session 7.
   - **H15:** demo reset re-creates the workspace with a new id. Needed before session 8.
   - **H17:** no audit purge in Phase 6. Needed before session 9.

## Order

Run strictly in this order, **one session at a time**, on `main`. Do not run sessions in parallel:
- the migrations are numbered 0012–0014;
- almost every session touches the i18n catalogs, `errors.py`, `config.py`, the router and the generated OpenAPI files;
- the tests and the E2E suite share one Postgres database and fixed ports.

| # | Brief | Plan task | Size | Depends on |
|---|---|---|---|---|
| 1 | [s01-reporting-metrics.md](s01-reporting-metrics.md) | P6-01 (metrics core) | L | Phase 5 + plan commit |
| 2 | [s02-reporting-api-jobs-commands.md](s02-reporting-api-jobs-commands.md) | P6-01 (job, API, summary, drill-down), P6-02 | L | 1 |
| 3 | [s03-activity-and-report-ui.md](s03-activity-and-report-ui.md) | P6-03, P6-01 (UI) | L | 2 |
| 4 | [s04-notifications-and-home.md](s04-notifications-and-home.md) | P6-04 | L | 3 |
| 5 | [s05-circuit-and-reauth.md](s05-circuit-and-reauth.md) | P6-05 (backend) | L | 4 |
| 6 | [s06-system-health-and-connections.md](s06-system-health-and-connections.md) | P6-05 (health, UI) | M | 5 |
| 7 | [s07-members-and-invites.md](s07-members-and-invites.md) | P6-06 | L | 6 |
| 8 | [s08-demo-reset-and-history.md](s08-demo-reset-and-history.md) | P6-07 | L | 7 |
| 9 | [s09-retention-and-backend-closeout.md](s09-retention-and-backend-closeout.md) | P6-08, P6-10 (backend close-out, AC map) | L | 8 |
| 10 | [s10-e2e-completion.md](s10-e2e-completion.md) | P6-09 | L | 9 |
| 11 | [s11-dod-review-and-summary.md](s11-dod-review-and-summary.md) | P6-10 (DoD, docs, summary) | M | 10 |

Why this order:
- **Reporting (1–3) comes first** because the commands, the report screen, Home (4) and the seeded history (8) all read it.
- **Home (4) comes before the circuit work (5).** Its banners only read the account status, which already exists.
- **System health (6) follows the circuit work (5)** so it can show degraded accounts.
- **Members (7) comes before demo reset (8)** so the reset covers every new table.
- **Demo reset (8) adds yesterday's history.** It is the one session expected to update earlier E2E specs.
- **Retention (9) comes after every table it cleans exists**, and the backend close-out runs in the same session, after it.
- **E2E (10) runs after the backend close-out**, the same order as Phase 5.
- **Session 11 is the DoD gate.**

Sessions that must stay on their own (never merge them further): **1** (the biggest query work), **5** (changes the send and publish paths), **8** (changes the seed every E2E spec uses) and **11** (the gate).

## Operator protocol
The operator session starts each session, checks its result, and either moves on or stops. It does not write code or fix anything itself.

For each session N, in order:
1. **Pre-check.** Check that `git status` is clean and that `git log --oneline -20` shows the commits of session N-1 (their `P6-xx` prefixes are in the brief). If not, stop and report to the owner.
2. **Start.** Open a fresh Claude session (a new chat, or a fresh subagent with no inherited context) in the repo, with this prompt:
   > Read `CLAUDE.md`, `docs/invariants.md`, then `docs/implementation/phase-6-sessions/README.md` (this file, section "Rules for every session") and `docs/implementation/phase-6-sessions/<brief>.md`. Then do exactly that brief. Stop when its "Done when" list is met and report.
3. **Read the report** and check four things:
   - the listed commits exist;
   - checks are reported green, with the commands that were run;
   - the deviations are listed;
   - the open questions are listed.
4. **Decide what to do next:**
   - **Stop and ask the owner** if any of these is true: the report has a question marked **BLOCKING**; a check is red; the session stopped early; or the working tree is dirty.
   - **Otherwise, continue** with session N+1. Write down the non-blocking questions and deviations, and pass them all to session 11 by adding them to the prompt: "Also include these in the summary: …".
5. **After session 11, stop.** The phase waits for the owner's review. Do not start Phase 7.

If a session fails half-way (a crash, or the context runs out), start a **new** session with the same brief and add: "A previous attempt stopped part-way. Inspect `git log` and `git status`, keep what is committed and correct, and finish the brief." Never run two sessions of the same brief at once. Session 10 is the likeliest to need this; its brief says where it can safely be split.

## Rules for every session

1. **Read first:** `CLAUDE.md`, `docs/invariants.md`, the brief, the plan sections the brief names, and the architecture docs it lists. Run `git log --oneline -15` to see what earlier sessions landed. Check that the prerequisite sessions' commits exist; if they do not, stop and say so.
2. **Work on `main`, push nothing.** Make one local commit per plan task or sub-task (`P6-xx: …`, using the prefix in the brief). Use the commit attribution line the session instructions specify. Never use `--no-verify`.
3. **Do not invent architecture.** The plan's H1–H18 are the settled answers to doc gaps. If something is still missing or contradictory, stop and raise it as a question instead of guessing. Mark it **BLOCKING** if you could not finish the brief without it.
4. **No scope creep.** Out of scope: real Meta, deployment, email delivery, Telegram, per-workspace retention settings, audit purge (H17), video/Reels/carousels. See `docs/product/mvp-scope.md`.
5. **Docs go in the same change.** If a contract changes (schema, endpoint, state, job type, env var, error code, notification type, audit action), update the matching doc in the same commit. Each brief lists the docs expected. After an API change, regenerate `frontend/openapi.json` and `frontend/src/api/schema.d.ts` and commit them in the same change.
6. **Run the checks after every task.**
   - From `backend/`: `uv run ruff check . ; uv run ruff format --check . ; uv run mypy app evals ; uv run lint-imports ; uv run pytest <task tests>`
   - From `frontend/`: `npm run lint ; npm run typecheck ; npm test ; npm run i18n:check`
   - Commands must work in Windows PowerShell (no Makefile or bash-only steps in required paths). See `docs/operations/local-development.md` and the memory note on the shell, CRLF and test-DB quirks.
7. **These invariants are the ones most at risk in this phase:**
   - workspace isolation on every query, including every report metric and the activity feed; foreign IDs return 404;
   - reports come from SQL over persisted records and never from the LLM (INV-08);
   - every day boundary uses the workspace timezone (INV-19);
   - audit rows are insert-only (INV-12);
   - external calls never happen inside a DB transaction; time comes from the injected `Clock`;
   - everything simulated carries `is_simulated` and shows a badge;
   - secrets and message text never go into logs or audit metadata;
   - demo tools are absent when `DEMO_TOOLS_ENABLED=false` (INV-20).
8. **Finish with a short session report.** This is not the phase summary, except in session 11. List the commits made, the tests run and their results, any deviations from the brief, and open questions (marked BLOCKING where they block). Then stop. Do not start the next session.
9. **If tests fail at the end, say so and show the output.** Do not report done with red checks.
