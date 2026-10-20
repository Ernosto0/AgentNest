# Session 11: Local MVP DoD review, docs close-out and phase summary

**Plan:** `plan.md` §5 (verification), §6 (owner items), §3 **P6-10**. **Depends on:** session 10. **Commits:** `P6-10b: …` (docs close-out), `P6-10c: …` (phase summary).

## Read first
- `acceptance-criteria.md` (the DoD), `roadmap.md` (Gate 1) and `local-development.md` (all of it: it is followed literally).
- `phase-05-summary.md` (the summary template).
- `ac-test-map.md`.
- Every session report the operator passed on (non-blocking questions and deviations).

## Build: docs close-out
- For each H1–H18, check that the resolution is written in the doc the plan names (grep each one).
- Check that every new contract is documented:
  - endpoints, job types, env vars (`.env.example` too), error codes, notification types and audit actions;
  - the migrations 0012–0014.
- `component-design.md` (new frontend features).
- `local-development.md` §6 must now describe the full 15-minute walkthrough A–G + reset with no "Phase 6 will add" notes.
- Update `roadmap.md` / `task-breakdown.md` status if they track it.

## Build: DoD run
- Run every check in plan §5 and report each result honestly:
  - the full backend suite;
  - the evals `--all --provider fake --strict`;
  - the frontend lint, typecheck, test and i18n checks;
  - the OpenAPI drift check;
  - `npm run e2e` (3 projects).
- **Windows walkthrough (DoD 2):** on a fresh `seed --reset` with the API, the worker and `npm run dev`, follow `local-development.md` from §1 setup through §6 **exactly as written**, in Windows PowerShell. Note every step that needed knowledge not in the doc, then fix the doc (or the code, with a test).
- **Phone (DoD 3):** cannot be done by a session. Write the owner's checklist into the summary: LAN host flag, firewall, URL, the walkthrough steps, and what to look for (no horizontal scroll, banners, badges).
- **Invariants (DoD 4):** list every open question that touches an invariant (at least Phase 5 Q6 for INV-09 and the H17 audit purge for INV-12) with a recommendation.
- **CI (AC-X8, Gate 1):** state plainly that GitHub CI has not run, because nothing is pushed, and what the owner must do.

## Build: phase summary
Write `docs/implementation/phase-summaries/phase-06-summary.md` in the Phase 5 format. It covers:
- changes by session and commit;
- the test results table;
- acceptance per criterion: AC-E1…E5, AC-G1…G3, AC-X3, AC-X4 and the full DoD table, linking `ac-test-map.md`;
- demo steps, with the steps that did not behave as written;
- deviations (H1–H18 plus those found while building, by session);
- known limitations (none may contradict the DoD; say so where one does);
- the open questions for review, including the operator's collected ones.

Then **stop and wait for review**.

## Done when
- Everything above is green, or each failure is explicitly reported with its output.
- The summary is written and the working tree is clean apart from the intended commits.
- Nothing is pushed, and Phase 7 is **not** started.
