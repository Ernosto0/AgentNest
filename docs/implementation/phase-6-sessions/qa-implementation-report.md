# Phase 6 owner Q&A implementation

**Implementation date:** 2026-10-22 (Europe/Istanbul). **Final verification:** 2026-10-23.
**Scope:** Q1, Q2 and Q8 from [phase-6-qa.md](phase-6-qa.md).
**Status:** implementation and local verification complete. This follow-up does not approve Gate 1 or start Phase 7.

## Result

- Every stored report generation preserves its aggregate values and minimal contributing membership. Regeneration appends a new revision; old generations remain addressable through `snapshot_id`. Historical links, API requests, frontend cache entries and pagination stay on the selected generation.
- One SQL statement captures all metric row sets; SQL aggregations over those saved rows produce the report values. Counts agree with contributing membership. The median uses original response durations and is rounded once to one decimal. Source text and raw payloads are never copied into report evidence.
- Failed inbound-event retention writes content-free source-gap markers in the same transaction as deletion. Existing snapshots remain explainable after source deletion and privacy redaction. Regeneration over unavailable sources returns `REPORT_SOURCES_RETAINED_OUT` instead of silently producing reduced historical counts.
- Reconnect guidance names the Instagram connection screen in Turkish and English in both backend and frontend catalogs.
- API, data-model, workflow, retention, component and acceptance contracts, plus generated OpenAPI/TypeScript schemas, are updated together.

## Migration and existing data

Migration `0015` follows `0014`. `daily_reports` is unique by workspace/date/revision, rather than workspace/date alone. `report_items` has a composite tenant/report FK and deliberately has no source-record FK. `report_source_gaps` records source completeness independently of the retained source rows.

The local development database (`localhost`, `agentnest`) was upgraded to `0015`. Both existing report IDs and all their aggregate values were compared before/after and preserved. The owner's demo data was not reset.

Legacy reports have `evidence_complete=false`: their original membership was never stored and cannot be reconstructed honestly from mutable current records. Their saved values remain readable, with a UI explanation; detail requests return `REPORT_EVIDENCE_UNAVAILABLE`. Explicit regeneration creates a separate complete generation only while sources remain available. If old system-wide cleanup audits show prior deletions, migration conservatively marks pre-cleanup history uncertain for then-existing workspaces, because those old counts cannot identify the lost tenant/day.

Downgrade refuses when multiple generations exist instead of discarding history. Reporting migration tests exercise real upgrades from 0014, legacy cleanup uncertainty, reporting schema/metadata parity and the downgrade guard.

## Verification

| Check | Result |
|---|---|
| Backend Ruff lint / formatting | Passed; 454 Python files formatted |
| Backend mypy | Passed; 243 source files |
| Import contracts | Passed; 18 kept, 0 broken |
| Full backend pytest | 2,543 passed in 712.11 seconds (11m 52s); 0 failures, errors or skips, verified from JUnit XML |
| Frontend lint / typecheck | Passed |
| Full frontend Vitest | 31 files, 479 passed |
| Frontend production build | Passed; existing large-chunk advisory remains |
| Translation check | Passed; 1,159 keys, 736 literal calls |
| OpenAPI export and TypeScript regeneration | Passed; both regenerated artifacts match their saved hashes |
| Scenario E, all three browser projects, zero retries | 9 passed in 3.6 minutes; mobile WebKit, mobile Chromium and desktop Chromium |
| Local development migration | Passed; revision 0015, both existing reports preserved |
| `git diff --check` | Passed |

Backend checks: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app evals`, `uv run lint-imports`; the full suite ran with the project virtual environment's `python -m pytest -q --tb=short --junitxml=var/phase6-qa-evidence/backend-results.xml`. Frontend checks: `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, `npm run i18n:check`. The browser command was `npm run e2e -- scenario-e.spec.ts --retries=0 --reporter=list` with the isolated database and ports described below.

Lifecycle tests cover historical state changes across all 20 metrics, regeneration between pages, old links, equal-clock revision ordering, simultaneous first reads, source deletion, text redaction, original median precision, gap transaction rollback, wrong-day/foreign snapshots, cursor binding and composite tenant FKs. Frontend tests cover pinned navigation/paging, unavailable legacy evidence, refused regeneration and reconnect guidance.

Browser verification uses a temporary isolated database, API port 8300, frontend port 5473, fake LLM/mock Instagram and a separate local media directory. Each temporary browser database is removed afterward. Local logs are under `backend/var/phase6-qa-evidence/` (ignored).

The backend run's session was unavailable when work resumed on October 23, so no result is inferred from it. Docker/PostgreSQL were offline after the environment resumed; the blocked attempt was stopped, the existing Compose database service was started, and the full suite was restarted with a saved log and JUnit XML result.

The first browser run passed the six existing Scenario E cases; the three new cases failed because their setup reused an already-escalated customer and assumed today's attention count matched yesterday's snapshot. The corrected regression measures today's baseline and creates two distinct new customers through the simulator API. It retains the original historical equality assertions and zero retries. Initial traces are preserved under `initial-browser-fixture/`.

The metadata comparison is scoped to reporting tables. An exploratory global Alembic comparison also exposed pre-existing invite-model constraint drift; this follow-up leaves that unrelated schema unchanged.

## Remaining phase gate scope

This follow-up implements the three approved code changes. It does not establish a root cause for session 11's intermittent WebKit failure, replace a full A-G browser run, resolve the separately required invariant ADRs, or supply a GitHub CI result. The [original Phase 6 summary](../phase-summaries/phase-06-summary.md) remains the historical record of session 11; its AC-E3 implementation gap is superseded by this follow-up and its verification.

Unrelated changes to the landing page, README, ignore rules and codebase-exploration tooling are preserved outside this follow-up.
