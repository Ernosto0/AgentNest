# Phase 5: session briefs

Phase 5 (content and scheduling) split into 14 Claude sessions. `plan.md` in this folder is the authoritative plan (task details P5-00…P5-10, decisions G1–G19, import contracts, verification). Each session brief only says *which slice* of it to build, what it depends on, and when it is done.

## Order

Run strictly in this order, one session at a time, on `main`. Migrations are numbered 0008–0011 and several sessions touch the same shared files, so do not run sessions in parallel.

| # | Brief | Plan task | Size | Depends on |
|---|---|---|---|---|
| 1 | [s01-followups-debounce-resume.md](s01-followups-debounce-resume.md) | P5-00 Q2, Q6 | M | Phase 4 |
| 2 | [s02-followups-policy-ui.md](s02-followups-policy-ui.md) | P5-00 Q3, Q4, Q5 | M | 1 |
| 3 | [s03-media.md](s03-media.md) | P5-01 | M | 2 |
| 4 | [s04-content-model.md](s04-content-model.md) | P5-02 | M | 3 |
| 5 | [s05-mock-publishing.md](s05-mock-publishing.md) | P5-05 | M | 4 |
| 6 | [s06-submission.md](s06-submission.md) | P5-04 | M | 5 |
| 7 | [s07-publish-executor.md](s07-publish-executor.md) | P5-06 | L | 6 |
| 8 | [s08-impact-handlers.md](s08-impact-handlers.md) | P5-07 | S | 7 |
| 9 | [s09-generation-and-evals.md](s09-generation-and-evals.md) | P5-03 (generation), P5-09 | M | 8 |
| 10 | [s10-content-commands.md](s10-content-commands.md) | P5-03 (commands) | M | 9 |
| 11 | [s11-frontend-foundation.md](s11-frontend-foundation.md) | P5-08 (part 1) | M | 10 |
| 12 | [s12-frontend-flows.md](s12-frontend-flows.md) | P5-08 (part 2) | L | 11 |
| 13 | [s13-backend-closeout.md](s13-backend-closeout.md) | P5-10 (backend) | M | 12 |
| 14 | [s14-e2e-docs-summary.md](s14-e2e-docs-summary.md) | P5-10 (E2E, docs, summary) | M | 13 |

Why this order: the mock provider (5) must exist before submission and the executor can be tested; the executor (7) and impact handlers (8) finish the backend publishing path; generation and commands (9, 10) come after because the cancel command needs the cancel route from session 6; the frontend (11, 12) starts once the OpenAPI surface is stable.

## How to start a session

Open a fresh Claude session in the repo and paste:

> Read `CLAUDE.md`, `docs/invariants.md`, then `docs/implementation/phase-5-sessions/README.md` (this file, "Rules for every session") and `docs/implementation/phase-5-sessions/<brief>.md`. Then do exactly that brief. Stop when its "Done when" list is met and report.

## Rules for every session

1. **Read first:** `CLAUDE.md`, `docs/invariants.md`, the brief, the plan sections the brief names, and the architecture docs it lists. `git log --oneline -15` to see what earlier sessions landed. Check that the prerequisite sessions' commits exist; if not, stop and say so.
2. **Work on `main`, nothing pushed.** One local commit per plan task (`P5-xx: …`). Use the commit attribution line the session instructions specify. Never `--no-verify`.
3. **Do not invent architecture.** The plan's G1–G19 are the settled answers to doc gaps. If something is still missing or contradictory, stop and raise it as a question instead of guessing.
4. **No scope creep.** Out of scope: video/Reels, carousels, image generation, S3, real Meta adapter, `media_cleanup` job (see `docs/product/mvp-scope.md`).
5. **Docs in the same change:** if a contract changes (schema, endpoint, state, job type, env var, error code), update the matching doc in the same commit. Each brief lists the docs expected.
6. **Checks after every task** (from `backend/`):
   `uv run ruff check . ; uv run ruff format --check . ; uv run mypy app evals ; uv run lint-imports ; uv run pytest <task tests>`
   Frontend (from `frontend/`): `npm run lint ; npm run typecheck ; npm test ; npm run i18n:check`.
   Commands must work on Windows PowerShell (no Makefile or bash-only steps in required paths). See `docs/operations/local-development.md` and the memory note on shell/CRLF/test-DB quirks.
7. **Invariants that bite in this phase:** workspace isolation on every query (foreign IDs → 404); LLM output is a proposal; prices/hours/URLs only via `{{fact:key}}`; external side effects only through the `operations` ledger, reconcile before retry; no external call or `sleep` inside a DB transaction; time from the injected `Clock`; everything simulated carries `is_simulated` and a badge; secrets never logged.
8. **Finish with a short session report** (not the phase summary, except session 14): commits made, tests run and their result, deviations from the brief, open questions. Then stop. Do not start the next session.
9. **If tests fail at the end, say so with the output.** Do not report done with red checks.
