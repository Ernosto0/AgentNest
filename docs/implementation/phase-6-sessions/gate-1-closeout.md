# Gate 1 close-out

**Implementation:** 2026-10-24. **Final review:** 2026-10-25 (Europe/Istanbul).
**Status:** Gate 1 criteria verified on reviewed application/test code `b47b019`;
[PR #1](https://github.com/Ernosto0/AgentNest/pull/1) tracks landing on `main`.
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
- The uploaded HTML report contains structured results, independently parsed for all 174
  statuses and retry indexes. Standalone JSON uses a path relative to the Playwright config
  directory (`frontend/e2e/playwright-report/results.json`); the artifact upload now includes
  that path as well. A local list-only reporter invocation verifies the path. This additional
  upload path changes no runtime code, test, test command or execution setting.

## Browser investigation

The session-11 full-run WebKit report-return failure is historical and unexplained;
its original trace is no longer present in the working tree. Its saved JSON error and
earlier trace analysis remain under `backend/var/session-11-evidence/`. An isolated
pass cannot clear it. Current full-suite navigation passes with zero retries: all 174 CI cases, including the original report-return case, and an independent eight-case Windows WebKit regression run. The old failure mechanism is not claimed identified; acceptance rests on the complete current-revision evidence, not the earlier isolated retry.

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
| Offline CI wrapper | Disposable Linux smoke and full GitHub backend/eval/frontend/E2E runtime suites passed |
| Full backend CI, b47b019 | 2,905 passed / 4 intended live-probe skips; zero failures/errors; JUnit time 445.402 seconds |
| Isolated Windows full backend | 2,905 passed / 4 intended live-probe skips; zero failures/errors; 1,441.53 seconds |
| Scenario E diagnostics | Failed runs retained above; final correction is being verified by full E2E |
| Full production-build E2E CI, all projects | 174/174 passed (58 each); zero retries, unexpected/flaky/skipped results; 17.0 minutes |
| Windows WebKit visibility/report-return regressions | 8/8 passed (four cases, two independent repetitions); zero retries/failures/flaky/skipped; 4.1 minutes |
| Reviewed-revision GitHub CI | [b47b019 run](https://github.com/Ernosto0/AgentNest/actions/runs/40129750466): all four jobs passed; GitGuardian also passed |

Draft review: [PR #1](https://github.com/Ernosto0/AgentNest/pull/1). The owner authorized
publishing the branch and a draft PR. Main landing and its approval are tracked through that PR.

Local logs, JUnit, Playwright JSON and failure traces are ignored under
`backend/var/gate1-evidence/`. The first browser diagnostic used `agentnest_gate1_e2e_test` and ports 8400/5573. Final Windows verification uses an isolated Git worktree at `C:\Users\ernos\AgentNest-gate1-review`, `agentnest_gate1_unit_test` and `agentnest_gate1_browser_test`, browser ports 8500/5673 and its own media directory. Final evidence is under that worktree's ignored `backend/var/gate1-evidence/`.
The existing development database/demo is not reset or migrated by this follow-up.
Backend pytest retains its `_test` database-name guard.

## Gate 1 invariant evidence review

This map concerns the local fictional demo. It does not assert production RLS,
legal retention periods, real-provider behavior or a security audit for real customers.
The full backend CI result above covers the backend paths; UI-dependent rows also
require the complete three-project E2E result before sign-off.

| Invariant | Evidence and disposition |
|---|---|
| INV-01 tenancy | `tests/isolation/`, API security checks, composite-FK tests; production RLS remains Phase 8 |
| INV-02 grounding | Claim-validator/rendering tests and strict fake evals; verified-value grounding retained |
| INV-03 untrusted input | Injection/prompt tests, inbox adversarial tests and import contracts separating customer input from commands |
| INV-04 deterministic permissions | Policy table, staff denial and executor approval tests; model flags only escalate |
| INV-05 verifiable outcomes | Send/publish ledger, outcome-unknown and reconciliation tests |
| INV-06 no duplicate effects | Dedup, concurrent execution, crash/recovery and mock remote-effect-count tests |
| INV-07 durable work | Queue restart, lease recovery and scheduling tests |
| INV-08 SQL reporting | Exact-value/day-boundary and immutable snapshot/membership/source-retention lifecycle tests; Q&A fix retained |
| INV-09 provenance | Mock propagation, production refusal and UI badges; owner-accepted ADR-021 resolves the neutral-media/internal-state question |
| INV-10 secrets | Schema allow-lists, redaction and encrypted-token tests; current CI secret scan passed |
| INV-11 provider constraints | Mock contract, messaging window, capability, JPEG and publishing-quota tests; real Meta verification remains Gate 2 |
| INV-12 auditing | Workflow audit/catalog tests plus new atomic `media.deleted` rollback/idempotency evidence; no audit purge path |
| INV-13 failures/recovery | Reauth, rate-limit, circuit, notifications and health recovery tests; browser G1/G3 required |
| INV-14 offline demo | Credential-free settings, fake evals and CI runtime firewall; full browser CI required |
| INV-15 ledger boundary | `tests/unit/test_side_effect_calls.py` and import contracts |
| INV-16 bound approvals | Stale version/hash, double decision, expiry, edit/cancel and executor rejection tests |
| INV-17 history/privacy | Edit rejection, retained report evidence and bounded scoped erasure tests; owner-accepted ADR-022 resolves the privacy exception |
| INV-18 truthful status | Frontend status component tests and publish/failure/reconciliation browser scenarios; full E2E required |
| INV-19 time | Injected-clock, workspace-local scheduling/reporting and DST boundary tests |
| INV-20 production tool refusal | Settings safety and dev-route absence tests; no production configuration is enabled by this follow-up |

## Concurrent-work interference and isolated validation

The first local full backend run ended **2,903 passed / 4 skipped / 2 setup errors**
(`workspaces` missing and a truncation deadlock in the shared `agentnest_test` database).
The first full browser attempt was stopped after failures, not reported as a clean run.
It found the stale lowercase simulation-banner assertion, now replaced with exact checks
for both current simulation/real-account explanations. It also recorded WebKit visibility
failures, and then cascading seed failures.

During that run, another task changed category enums, templates and migration files in
this checkout. Direct seed reproduction showed the new category enum rejecting the
unchanged `gym` / `pilates_studio` seed. Its uncommitted changes and staged files are
preserved. The shared test database also had concurrent schema activity. No isolated
retry is substituted for the failed full runs: complete validation is repeated on the
fixed `b47b019` code snapshot, independent dependencies and dedicated databases. CI's
independent checkout passed all 2,905 backend tests; the dedicated Windows rerun also passed all 2,905, including both formerly errored cases. The older navigation failure is
not claimed fixed merely because interference was discovered.

## Owner acceptance and final gate

The owner reported **both unassisted Windows and real-phone walkthroughs completed**
in this conversation on October 24. When asked for device/date/scenario detail, the
owner said they did not know those details and explicitly requested skipping them.
Record this as **owner-reported manual acceptance**, without independently verified
device/version/date records. Those optional details are omitted at the owner's request;
automated emulation is not substituted for the owner's confirmation.

| Local MVP DoD | Acceptance evidence |
|---|---|
| 1. AC-A through G and AC-X pass in CI | All four jobs green for reviewed code `b47b019`; backend 2,905 passed / four intentional live-only skips, frontend 497 tests, fake eval 166/166, E2E 174/174 with zero retries |
| 2. Unassisted Windows walkthrough | Owner-reported complete; optional device/date metadata omitted at owner's request |
| 3. Real-phone walkthrough | Owner-reported complete; automated emulation is not substituted |
| 4. No open local-MVP invariant issue | ADR-021/022 accepted by owner; media-deletion auditing implemented; evidence map and complete regression results above |
| 5. Limitations do not contradict this scope | Historical failures retained and superseded by current complete verification; real Meta, production/legal/privilege work remain outside this local fictional demo |

The final evidence follow-up changes documentation and adds the standalone JSON path to
artifact upload only. Application code, tests and test-execution settings match the fully
verified `b47b019` snapshot. The path is independently checked through Playwright's
list-only JSON reporter. Main landing and its fresh pipeline are tracked through PR #1.

Gate 2, authentic Meta recordings, Phase 7 live acceptance, Phase 8 and real-customer-data
Gate 3 remain pending. The other task's category/template/prompt changes in the original
checkout are preserved and are not included in this verification.
