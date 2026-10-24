# Gate 1 close-out

**Date:** 2026-10-24 (Europe/Istanbul). **Status:** in progress; not signed off.
This is the current Gate 1 record. Earlier Phase 6 session reports remain historical
evidence. Gate 2, live Meta acceptance, Phase 8 and Gate 3 are separate.

## Decisions and fixes

- The owner accepted [ADR-021](../../architecture/decisions/ADR-021-simulation-provenance-boundary.md)
  and [ADR-022](../../architecture/decisions/ADR-022-privacy-redaction-and-audit-retention.md)
  on October 24. INV-09/17 and AC-X2 now state the precise provenance/privacy boundaries.
  All mock-provider results still require flags and badges; audit rows stay append-only.
  No application audit purge is added. Production purge/privileges/legal review remain Phase 8.
- Media retention now writes workspace `media.deleted` with the conditional status change,
  in one transaction. It carries only `reason=retention`. Audit failure rolls the transition
  back; retry repairs an already-removed file and produces exactly one event. Catalog,
  activity group, both languages and lifecycle documentation change together.
- The reporting membership/retention defect was already fixed by migration 0015 and
  the [owner Q&A implementation](qa-implementation-report.md). It is not reopened or rebuilt.
  The walkthrough's stale description of current-state historical lists is corrected.
- The existing [CI run for bfa1724](https://github.com/Ernosto0/AgentNest/actions/runs/40011121524)
  passed backend/security, failed four frontend tests (493/497), and skipped E2E.
  Those four failures reproduce on Node 22. Their fixtures passed jsdom `Blob` objects
  to Node fetch's `Response`; replacing those bodies with binary bytes preserves every
  preview assertion and passes all 497 tests on Node 22. No product behavior is changed.
- CI previously documented offline execution without enforcing it. The Linux-only
  `.github/scripts/offline-tests.sh` runs test descendants as the same user with a separate
  primary group, filters that group's IPv4/IPv6 traffic to loopback, and restores the rules
  afterward. The Actions runner keeps its original group/network. Original loopback
  destinations remain allowed through Docker's port forwarding. Dependency installation
  happens first. Fake/mock/local settings and blank manual probe inputs are explicit.
  A disposable Ubuntu container verifies the non-root user/group boundary, local TCP,
  rejected external TCP with a matching firewall counter, and the IPv6 output rule.
- Playwright retries are zero locally and in CI. Failed diagnostic artifacts are retained.

## Browser investigation

The session-11 full-run WebKit report-return failure is historical and unexplained;
its original trace is no longer present in the working tree. Its saved JSON error and
earlier trace analysis remain under `backend/var/session-11-evidence/`. An isolated
pass cannot clear it. Current full-suite navigation must pass with zero retries.

An initial repeated Scenario E diagnostic produced **7 passed / 2 failed** in 5.7 minutes.
These were separate count/baseline failures, not the old return-link failure. Worker logs
and failure traces show seeded approvals/drafts expiring during live comparisons late
in the evening: `attention_now` changed from 3 to 2, or a baseline of 2 expired before
two new complaint drafts appeared. Scenario E now invokes the existing expiry service
at current time before measuring baselines, and waits for both new approval drafts
before comparing live counts. It neither moves deadlines nor alters product expiry,
count assertions, timeouts or retry behavior. The next diagnostic was **4 passed /
2 failed**: expiry was stable, but the historical-regeneration fixture's two additions
could equal the saved count rather than exceed it after expiry. It now creates enough
distinct customers to exceed that saved count, retaining both exact delta and strict
greater-than assertions. Both failed runs remain available; neither is reported green.

## Verification

| Check | Current result |
|---|---|
| Media cleanup focused integration | 17 passed, including audit rollback and idempotency |
| Backend Ruff / format / mypy / import contracts | Passed; 476 formatted files, 251 typed source files, 19 contracts |
| Frontend Node 22 full suite | 497 passed, 31 files, 65.87 seconds |
| Frontend lint / typecheck / translations | Passed; 1,170 keys |
| Fake-model eval | 166/166; zero hard failures |
| OpenAPI export / client regeneration | Zero drift |
| Offline CI wrapper | Disposable Linux smoke passed; actual GitHub workflow pending |
| Full backend | Running; do not infer a result |
| Repeated Scenario E after fixture correction | Running |
| Full production-build E2E, all projects, zero retries | Pending |
| Reviewed-revision GitHub CI: backend/frontend/E2E/security | Pending |

Draft review: [PR #1](https://github.com/Ernosto0/AgentNest/pull/1). The owner authorized
publishing this branch and a draft PR; no merge is authorized or performed.

Local logs, JUnit, Playwright JSON and failure traces are ignored under
`backend/var/gate1-evidence/`. The browser stack uses a separate
`agentnest_gate1_e2e_test` database, ports 8400/5573 and its own media directory.
The existing development database/demo is not reset or migrated by this follow-up.
Backend pytest retains its `_test` database-name guard.

## Owner acceptance and final gate

The owner reported **both unassisted Windows and real-phone walkthroughs completed**
in this conversation on October 24. When asked for device/date/scenario detail, the
owner said they did not know those details and explicitly requested skipping them.
Record this as **owner-reported manual acceptance**, without independently verified
device/version/date records. Those optional details are omitted at the owner's request;
automated emulation is not substituted for the owner's confirmation.

Gate 1 can close only when the current automated/CI results, the navigation investigation,
owner-reported walkthrough acceptance and final invariant review are recorded. Nothing here accepts
Gate 2, authentic Meta recordings or production/customer-data readiness.
