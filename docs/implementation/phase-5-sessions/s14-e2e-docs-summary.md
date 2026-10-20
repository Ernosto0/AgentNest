# Session 14: E2E, docs close-out and phase summary

**Plan:** `plan.md` §3 **P5-10 (E2E, docs, summary)** and §5 verification. **Depends on:** session 13. **Commits:** `P5-10b: …` (E2E), `P5-10c: …` (docs), `P5-10d: …` (summary).

## Read first
`frontend/e2e/` (existing scenario specs, Phase 4 seed), `docs/operations/local-development.md` §6 (demos), `phase-04-summary.md` as the summary template, `docs/implementation/phases/phase-05-content-and-scheduling.md` (demo scenario), the dev "run due jobs" API.

## Build: E2E (3 projects)
- `scenario-c.spec.ts`: add "fact change holds the scheduled post"; keep existing tests.
- `scenario-d.spec.ts`: story command → upload `story-sample.png` → schedule +2 min shows *Zamanlandı · time*; "Hemen yayınla" → *Yayınlandı · SİMÜLASYON*; edit after approval → *Taslak*; staff → *Onay bekliyor*.
- `scenario-f.spec.ts`: failure rule via the dev API; `publish invalid_media` → *Başarısız* + cause + "Düzenle ve yeniden gönder"; `publish transient ×1` → "Tekrar denenecek HH:MM" (AC-F7).
- Slow retry/reconcile paths are covered by integration tests; do not wait minutes in E2E.

## Build: docs
Every doc named in plan §2 (state-machines §5, workflows §E, integrations §3.2/§3.3, data-model §3.6, api-design §2.7/§2.3/§2.6/§2.9, background-jobs, observability §4, ADR-014/015 notes), plus `component-design.md`, `environment-variables.md`, `.env.example`, `local-development.md` (demos D, F, and the reconnect step of G). Grep each G-number: its resolution must be written in the named doc. Update `roadmap.md` / `task-breakdown.md` status if they track it.

## Build: phase summary
`docs/implementation/phase-summaries/phase-05-summary.md`: changes, tests proving each acceptance criterion (AC-C4, D1–D8, F1–F7, X5, INV-06, INV-18), demo steps (plan §5 manual demo), deviations (G1–G19 + P5-00), limitations (e.g. no `media_cleanup`, Story API unverified V-03), open questions. Then **stop and wait for review**.

## Verification (all must be run and reported honestly)
Full backend suite; evals `--all --provider fake --strict`; frontend lint/typecheck/test/i18n; OpenAPI regenerate + `git diff --exit-code`; `npm run e2e` all specs. Walk the manual demo (plan §5) on a fresh seed with API + worker + `npm run dev`; report any step that did not behave as written.

## Done when
- Everything above green or failures explicitly reported with output.
- Summary written; working tree clean except intended commits; nothing pushed; do **not** start Phase 6.
