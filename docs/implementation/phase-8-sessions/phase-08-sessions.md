# Phase 8: Implementation Plan and Sessions

**Status:** Planned; no Phase 8 implementation or acceptance is claimed by this document.
**Canonical phase:** [Production hardening and pilot readiness](../phases/phase-08-hardening.md).
**Session count:** 16 sequential sessions. Each session is a scope boundary, not a promise that it fits one work period.

## Short plan

Harden the existing application for the first real-business pilot: make deployment and recovery repeatable, enforce database tenant isolation, strengthen authentication, implement complete data-rights workflows, add operational controls, then verify security and production readiness.

1. **Session 01:** inventory the current system and settle the implementation contracts and acceptance checklist.
2. **Sessions 02–04:** package the production environment, automate deployment and rollback, and prove backup recovery.
3. **Sessions 05–06:** introduce transaction-scoped RLS and prove isolation across the expanded application.
4. **Sessions 07–08:** harden authentication and deliver invitation/password-reset email flows.
5. **Sessions 09–12:** implement export, erasure, Meta callbacks, retention and key rotation.
6. **Sessions 13–14:** add operator alerts and prepare the legal and conditional OSS artifacts.
7. **Sessions 15–16:** complete the security review, App Review package and production/pilot acceptance.

Legal and platform preparation starts in Session 01 and continues alongside these sessions. Session 14 consolidates counsel-reviewed artifacts; it is not the first time counsel is consulted. Optional staging uses the same deployment artifacts in Sessions 02–04.

## Execution order and task coverage

| Session | Scope | Phase task coverage |
|---|---|---|
| 01 | Baseline, contracts and acceptance plan | Phase-start re-plan; all P8 tasks |
| 02 | Production images, Compose and Caddy | P8-01 packaging; optional P8-12 |
| 03 | Deployment, migrations and rollback | P8-01 delivery; optional P8-12 |
| 04 | Backups, media protection and restore drill | P8-02; optional P8-12 |
| 05 | RLS roles and transaction infrastructure | P8-03 foundations |
| 06 | Tenant policies and isolation verification | P8-03 completion |
| 07 | Login, password and session hardening | P8-04 authentication |
| 08 | SMTP, invitations and password reset | P8-04 email; OQ-16 |
| 09 | Conversation/customer export | P8-05 export |
| 10 | Conversation/customer and workspace deletion | P8-05 erasure |
| 11 | Meta deauthorization and deletion callbacks | P8-05 provider callbacks; V-06 |
| 12 | Retention, key rotation and dependency auditing | P8-06 |
| 13 | Operator monitoring and alerts | P8-07 |
| 14 | Privacy/legal artifacts and conditional OSS readiness | P8-08; conditional P8-11 |
| 15 | Security review and remediation | P8-09 |
| 16 | App Review preparation, production acceptance and pilot | P8-10; phase acceptance and close-out |

Run one assigned session at a time in this order. An externally pending check can be carried forward only when the next work does not depend on it and the report states that boundary. Do not declare the pending session or phase fully accepted. Session 01 must record this split explicitly, including any departure from the canonical phase's task ordering.

## Starting state and gates

The [roadmap](../roadmap.md) and [Phase 7.5 summary](../phase-summaries/phase-7.5-summary.md) allow Phase 8 hardening against stable offline contracts. Phase 7.5 still has varied-journey, real-model, platform and founder/phone acceptance outstanding. Real comment capabilities remain disabled until their authentic capability evidence is accepted. Re-read the latest reports rather than treating this snapshot as current implementation evidence.

- **Offline implementation:** can use fictional data, mocks, disposable databases, local containers and email capture. Keep fake/mock/local development usable without external credentials.
- **External dependencies:** identify the hosting/domain/storage/email choices, Meta app access and business-verification owner, OQ-02 licensing decision, OQ-04 hosting/transfer review, OQ-12 retention review and OQ-13 disclosure review. Track OQ-03 pilot access and OQ-09 model-quality/cost evidence as pilot dependencies too.
- **Production/data gate:** Gate 3 requires Phase 8 controls and counsel review of OQ-04, OQ-12 and OQ-13. A successful local rehearsal does not close this gate.
- **Live pilot gate:** additionally requires the applicable Phase 7 and Phase 7.5 model/platform/workflow acceptance. App Review preparation does not itself grant permissions.
- **Conditional work:** P8-11 executes only after OQ-02 is resolved. P8-12 staging is optional; record whether it is selected or deferred.

These briefs authorize no execution by themselves. Deployment, real-account actions, paid model evaluations, App Review submission, public release, commit and push require authorization in the implementation session's context. Complete independent preparation and record remaining external actions without inventing acceptance evidence.

## Common working rules

Before each session, read this plan, its section below, [CLAUDE.md](../../../CLAUDE.md), [invariants](../../invariants.md), the canonical phase, the current roadmap and the previous session report. At phase start also read every document in the phase's read-first list. Session-specific references below supplement those documents.

1. Inspect branch/worktree, recent commits, actual migration head and existing code. Preserve unrelated changes. Reuse working controls rather than reimplementing them from the phase checklist.
2. Settle missing contracts before coding. New architectural decisions need an ADR; do not silently override accepted invariants or infer legal/provider rules.
3. Update schema, API, state, job, configuration and operations documentation with the corresponding implementation. New APIs require permission/isolation checks, generated client updates and Turkish/English UI/error text as applicable.
4. Use `WorkspaceContext`, injected `Clock`, committed operation evidence and existing disconnect/deletion fences. External calls never run inside database transactions. Jobs, logs, audit metadata and alerts carry IDs/codes rather than personal bodies or secrets.
5. Keep database-role and RLS changes compatible with authentication, membership resolution, OAuth/webhook routing, worker polling, recovery and CLI operations. Privileged bootstrap paths need explicit, narrow contracts and tests.
6. Use a dedicated disposable database for destructive migration, deletion, restore and E2E checks. Do not reseed or restore over data to preserve.
7. Reports distinguish implemented behavior, verified local evidence and external acceptance. Do not pre-create reports containing expected passes.

## Session briefs

### Session 01 — Baseline, contracts and acceptance plan

**Depends on:** the stable Phase 7/7.5 baseline and current reports.

**Work:**
- Inventory production configuration, auth/session APIs, email stubs, tenant tables, worker entry points, storage, retention, data-rights helpers, Meta callbacks and deployment files. Mark each item as existing, missing or needing extension.
- Build a table-by-table tenant/global classification and runtime-role matrix, including all Phase 7.5 records. Define how login, membership lookup, OAuth/webhooks and global job discovery work before a workspace context exists.
- Specify export formats and authorization, deletion scope/grace/cancellation semantics, reconciliation exceptions, callback status privacy, alert thresholds and the production acceptance evidence. Record significant new decisions in ADRs before dependent implementation.
- Open the legal/platform dependency checklist now. Identify decisions needed for later sessions; keep legal periods and provider contracts provisional until reviewed or verified.
- Map the six canonical phase acceptance criteria to sessions and evidence artifacts. Record the sequence rationale: infrastructure before RLS, email before alerts, data-rights services before provider callbacks.

**Verify and finish:** inspect actual code and migration head, record a baseline check result and relevant prior evidence, and publish the inventory, contract decisions, gate checklist and next-session handoff in `s01-report.md`. No broad implementation belongs in this session.

### Session 02 — Production images, Compose and Caddy

**Depends on:** Session 01 deployment/configuration contracts.

**Work:**
- Add or complete the multi-stage, non-root backend image shared by API and worker, frozen dependency installation, frontend production build and static serving.
- Create `compose.prod.yml` for Caddy, API, worker and optional PostgreSQL, with persistent volumes, health checks, restart behavior, graceful shutdown and bounded log storage.
- Configure TLS and routes for the SPA, `/api`, `/webhooks` and `/oauth`; preserve callback/redirect paths. Apply security headers and a CSP compatible with the actual application.
- Document server `.env` ownership/permissions and exclude secrets from build context, image layers and frontend assets. Keep production startup checks enforced.
- If staging is selected, parameterize the same artifacts for its separate hostname, credentials and data.

**Verify and finish:** validate Compose, build images, inspect non-root execution, and exercise routing, SPA deep links, headers and health locally. Real TLS evidence remains pending until an authorized hosted instance exists. Hand off reproducible build/run commands.

### Session 03 — Deployment, migrations and rollback

**Depends on:** Session 02 artifacts.

**Work:**
- Implement tag-triggered image build/publish to GHCR and SSH deployment using narrowly scoped credentials, verified host identity and pinned image versions.
- Add deployment preflight, one-off migrations before restart, readiness checks and failure reporting. Prevent overlapping deployments.
- Separate migration/runtime credentials. Document backward-compatible migration requirements and the safe response to a failed migration.
- Implement application rollback to the previous image only where schema compatibility permits; distinguish this from database restoration. Preserve worker leases and uncertain-operation reconciliation during restarts.
- Write a fresh-server deployment runbook and optional staging setup using the same process.

**Verify and finish:** rehearse against disposable/local infrastructure, including failed readiness, interrupted deployment and worker restart. Record hosted steps separately if unavailable; do not label YAML inspection as an executed production deployment.

### Session 04 — Backups, media protection and restore drill

**Depends on:** Sessions 02–03 and the selected storage/key custody contracts.

**Work:**
- Schedule nightly encrypted `pg_dump` uploads to an off-site bucket with the canonical 35-day retention, failure exit status and monitoring hooks for Session 13.
- Document least-privilege backup credentials, encryption-key recovery, media bucket protection and the consistency limits between database and media backups.
- Add a restore procedure into a fresh isolated database/environment, with integrity checks, correct ownership/privileges and production-equivalent role verification.
- Fence restored workers from real effects until accounts, pending operations and reconciliation state are inspected. Account for erased data reappearing in older backups and reapply required deletion restrictions before use.
- Execute a restore drill with fictional data; record backup age, measured RPO/RTO, recovered media references and failures. An actual off-site/hosted drill is separate evidence if unavailable locally.

**Verify and finish:** prove backup encryption, failed-upload visibility and usable restored data. Revisit the drill after RLS/role changes in Sessions 05–06 and during Session 16 acceptance; the early drill alone cannot prove the final system restores correctly.

### Session 05 — RLS roles and transaction infrastructure

**Depends on:** Session 01 table/role matrix and Sessions 02–04 operational contracts.

**Work:**
- Introduce separate migration, application and worker privileges. Runtime roles must not be superusers, table owners that bypass policies, or holders of unrestricted `BYPASSRLS`.
- Set the workspace setting transaction-locally from validated context and make absent/invalid context fail closed. Never trust a caller-supplied workspace without membership/account routing checks.
- Cover commit, rollback, pooled connection reuse, nested transactions and worker transaction boundaries. Use an explicit workspace for tenant job processing.
- Implement the approved narrow bootstrap paths for identity/membership, OAuth/webhook lookup, periodic tenant discovery and global queue claim/recovery without exposing general tenant reads.
- Restrict audit/history mutation privileges according to existing ADRs; any privileged retention path waits for the Session 12 decision.

**Verify and finish:** test the actual runtime roles, context reset after commit/rollback, missing context, cross-workspace connection reuse and worker discovery/dispatch. Deliver the context mechanism and role provisioning needed by Session 06; do not claim complete RLS coverage yet.

### Session 06 — Tenant policies and isolation verification

**Depends on:** Session 05 infrastructure and inventory.

**Work:**
- Add policies to every inventoried tenant table, including appropriate read/write checks and protection against changing a row's workspace. Resolve any indirect ownership paths explicitly.
- Cover `account_agents`, delegations, threads/events/sessions/steps/actions, owner tasks/questions, identities/memory/summaries, public media/comments/threads and legacy domain tables.
- Ensure table ownership or administrative test connections cannot conceal missing enforcement. Use forced RLS where required by the approved role design.
- Exercise HTTP routes, background jobs, OAuth/webhook processing, exports/deletion helpers and recovery under production-equivalent privileges.
- Update restore/provisioning procedures to preserve policies and grants, and rerun the relevant restore verification.

**Verify and finish:** prove no tenant rows are visible without context, foreign reads/writes fail, same-tenant behavior works, and pooled connections do not leak scope. Run the full isolation suite with RLS enabled and record coverage for every inventory row.

### Session 07 — Login, password and session hardening

**Depends on:** Sessions 05–06 identity/bootstrap contracts.

**Work:**
- Add per-IP and per-email login throttling with exponential backoff, bounded state and safe concurrency. Define trusted proxy handling so forwarded headers cannot bypass limits.
- Implement authenticated session listing, individual revocation where supported by the settled contract, revoke-all and password change with current-password verification.
- Define session invalidation after password change/reset and avoid revealing session tokens or account existence.
- Reuse and verify secure cookies, session expiry and existing CSRF/origin protections; keep development HTTP usable under development configuration.
- Provide the necessary TR/EN account-security UI, typed APIs and audit events.

**Verify and finish:** test throttle boundaries/recovery/concurrency, revoked/expired sessions, wrong-password refusal, password-change races and production cookie enforcement. Verify one user's session management cannot affect another user.

### Session 08 — SMTP, invitations and password reset

**Depends on:** Session 07 authentication behavior and OQ-16 delivery contract.

**Work:**
- Add configurable SMTP delivery with local email capture for credential-free development and safe production validation.
- Connect existing invitation flows to email while retaining the approved assisted-onboarding workflow.
- Implement password reset with short-lived, single-use, hashed tokens, generic request responses, throttling, trusted-origin links and the Session 07 invalidation policy.
- Use durable delivery/retry semantics without storing raw reset credentials or personal message bodies in generic job payloads/logs. Define secure token handoff before implementing queued email.
- Add TR/EN templates and reset/invitation success, expiry and failure states.

**Verify and finish:** test capture-server delivery, resend/retry behavior, token expiry/replay, host-header injection, enumeration resistance and session invalidation. Live SMTP delivery remains separately recorded when credentials are available.

### Session 09 — Conversation/customer export

**Depends on:** Sessions 05–06 RLS and Session 01 data-rights contract.

**Work:**
- Implement permission-checked conversation/customer export with a documented, versioned machine-readable format and bounded resource use.
- Inventory and include authorized source messages, linked public/private records, customer identities, memory, summaries and relevant owner-question/context records, applying the account-scoped memory export service.
- Define treatment of shared conversations and other people's data; public/private context separation and explicit identity evidence remain enforced.
- Exclude tokens, secrets and unauthorized internal/user data. Use bounded, private, expiring retrieval if an asynchronous archive is needed.
- Audit requests and results with IDs/codes; add the necessary TR/EN interface and generated API types.

**Verify and finish:** demonstrate complete fixture export, foreign-ID refusal, unauthorized-role refusal, safe large exports and consistency with concurrent deletion. Supply the record inventory and service interfaces Session 10 will erase.

### Session 10 — Conversation/customer and workspace deletion

**Depends on:** Session 09 inventory and Session 01 erasure/grace-period decisions.

**Work:**
- Implement idempotent conversation/customer erasure and workspace deletion with explicit grace period, cancellation boundary, state transitions and permission checks.
- Call the account-scoped memory erase service and existing disconnect fence; coordinate messages, source/derived memory, summaries, prompt snapshots, owner questions, comments, attachments and export artifacts.
- Fence queued work and in-flight model results against data resurrection. Stop new effects for a workspace entering deletion according to the approved state contract.
- Preserve immutable audit/report/ledger evidence according to ADR-022. Retain only minimal evidence for unresolved operations until reconciliation; do not claim immediate total erasure while those remain unresolved.
- Cover media references, object cleanup failures, backup restoration restrictions, progress/error reporting and the necessary TR/EN destructive-action UI.

**Verify and finish:** test grace/cancel boundaries, repeated requests, partial failures, restart, disconnect races, concurrent send/model completion and unknown outcomes. Verify other customers/accounts/workspaces remain intact and completion status accurately reflects pending cleanup.

### Session 11 — Meta deauthorization and data-deletion callbacks

**Depends on:** Session 10 erasure services and verified V-06 provider contract.

**Work:**
- Verify the current official Meta contract for the selected login/product before settling endpoints, signature rules, response fields or identity mapping. Keep unresolved assumptions explicit.
- Implement strict `signed_request` verification, bounded parsing, invalid-signature refusal and replay/idempotency handling.
- Map provider identities using server-owned records; deauthorize by revoking credentials/capabilities and fencing future work. Route data-deletion requests through Session 10 orchestration.
- Implement the required confirmation/status endpoint with an unguessable reference, truthful pending/completed state and no account enumeration or personal data leakage.
- Publish callback configuration/runbooks and add proxy routes or public informational pages where the verified contract requires them.

**Verify and finish:** test signed/invalid/malformed/repeated requests, unknown identities, multi-account scope and pending reconciliation. Synthetic fixtures prove local handling only; authentic callback acceptance remains pending until evidenced.

### Session 12 — Retention, key rotation and dependency auditing

**Depends on:** Sessions 09–11 lifecycle services and counsel input for retention.

**Work:**
- Extend the retention inventory to Phase 7.5 sources, summaries, prompt/context snapshots, owner questions and public comments. Use counsel-reviewed periods; label any unresolved values provisional and keep Gate 3 open.
- Make cleanup bounded, idempotent and restartable, respecting source-derived erasure and unresolved-operation evidence. Reconcile backup retention with erasure obligations.
- Resolve the audit-purge decision through an ADR before adding any purge. Runtime audit rows remain append-only; an approved purge uses separate narrowly privileged execution.
- Implement token re-encryption with key IDs/AAD preserved, bounded batches, resumability and safe concurrency with refresh/disconnect. Prove old-key removal is safe before removing it; account for key custody needed by retained backups.
- Add `pip-audit` and `npm audit` CI checks with documented remediation/exception ownership, scope and expiry.

**Verify and finish:** test exact retention boundaries, cross-tenant cleanup, source-loss behavior, rotation retries/concurrency and unreadable/missing keys. Record audit findings and deferred legal decisions without presenting provisional settings as approved.

### Session 13 — Operator monitoring and alerts

**Depends on:** Session 08 email delivery, Session 04 backup signals and existing agent/operation health state.

**Work:**
- Add the external `/readyz` uptime-check runbook/configuration and optional Sentry-compatible error reporting with privacy scrubbing.
- Alert on dead jobs, backup failure, signature-failure bursts and accounts in `needs_reauth` for more than 24 hours.
- Include agent dead/recovery jobs, unresolved outcomes, capability loss and budget exhaustion from the Phase 7.5 handoff.
- Define thresholds, durable deduplication, cooldown/recovery messages and alert-delivery failure visibility. Avoid dependence on the failed worker/email path as the only detector.
- Document severity, operator action and escalation for each alert; payloads contain IDs/codes and safe links.

**Verify and finish:** inject each failure locally and prove alert timing, deduplication, recovery and redaction using `Clock` and email capture. Record actual external monitor/DSN activation separately when available.

### Session 14 — Privacy/legal artifacts and conditional OSS readiness

**Depends on:** Session 01 legal track and the implemented data/security controls.

**Work:**
- Prepare the product privacy policy, business KVKK information-notice template, DPA template, sub-processor register, breach runbook and automation disclosure wording for counsel review.
- Reconcile every claim with actual hosting/transfer arrangements, data flows, model/storage/email processors, retention, deletion exceptions and backup behavior.
- Record counsel review and decisions for OQ-04, OQ-12 and OQ-13 only when actually supplied. Feed required changes back into Sessions 10–12 and reverify affected behavior.
- Prepare stable public policy/deletion information URLs for Session 16, without making unsupported legal assurances.
- Only after OQ-02 is resolved, add the chosen LICENSE, CONTRIBUTING with the decided CLA/DCO approach, CODE_OF_CONDUCT, SECURITY.md and issue templates. Otherwise record P8-11 as conditionally deferred and keep the repository private.

**Verify and finish:** cross-check artifact statements against implementation and record reviewer/date/version or explicit pending review. Drafting artifacts is offline completion; counsel approval and public publication are separate evidence.

### Session 15 — Security review and remediation

**Depends on:** Sessions 02–14 implemented controls; pending external/legal items stay visible.

**Work:**
- Review every threat in the current threat-model inventory, including the canonical T1–T22 scope and any later additions. Map each to implemented controls, tests, findings and residual risk.
- Review production privileges/RLS, authentication/reset, exports/deletion/callbacks, headers/CSP, secrets, dependencies, backups and operational access.
- Review agent broker reference scope, public/private separation, owner demotion, stale delegation, cutover races and uncertain-operation handling.
- Run an authenticated security scan against an isolated production-like instance using authorized test accounts. Record scan coverage; unauthenticated baseline output alone does not prove authenticated paths were checked.
- Fix findings within scope and retest. Document residual risks with severity, owner, mitigation and actual acceptance; flag unresolved blockers for Session 16.

**Verify and finish:** produce a reproducible security review record, sanitized scan evidence and retest results. Run full backend/isolation and frontend regressions, strict fake/agent checks as wired in the repository, production build and generated-client checks. Carry required failures forward as unresolved.

### Session 16 — App Review, production acceptance and pilot close-out

**Depends on:** Session 15 review, all applicable Phase 8 gates and the Phase 7/7.5 gates required by the proposed pilot actions.

**Work:**
- Prepare the App Review package: privacy/data-deletion URLs, permission-by-permission rationale, actual granted-scope/capability evidence, authentic workflow screencasts and test-user instructions. Include business-verification/OQ-05 dependencies.
- Keep new Meta capabilities disabled until authentic permission and application-workflow evidence exists. Submit the package only when ready and authorized; preparation, submission and approval are distinct statuses.
- Rehearse fresh-server HTTPS deployment and verify `/readyz`, production runtime roles, routes, cookies/headers, SMTP, uptime/alerts and safe worker restart.
- Execute the final restore drill using the final schema, RLS policies and runtime privileges; record measured RPO/RTO and the checks required before enabling restored workers.
- Run the final required regressions, production-build browser checks and data-rights/recovery walkthroughs. Resolve any fixes and rerun affected checks.
- When production/data and relevant platform/model gates are satisfied, onboard the first pilot using the assisted checklist and record an actual owner phone TR/EN walkthrough and rollback/recovery evidence.
- Write `../phase-summaries/phase-08-summary.md` with the six canonical acceptance criteria, exact evidence, pending items and Phase 9 handoff. Stop at the Phase 8 boundary for review.

**Verify and finish:** local checks and prepared packages may be offline complete while external acceptance remains pending. Phase 8 is fully complete only when the canonical acceptance criteria, including counsel review, real deployment/restore evidence and the first production pilot, are actually met. Report missing gates explicitly rather than treating session count as acceptance.

## Verification and reporting

Run relevant focused tests after each implementation slice and appropriate existing regressions. For backend changes, use the repository's current equivalents of:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy app evals
uv run lint-imports
uv run pytest <session-test-paths>
```

For frontend changes, from `frontend/`:

```powershell
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run i18n:check
npm.cmd run build
```

Regenerate OpenAPI/client types when API contracts change and check generated drift. Sessions 15–16 also run full required backend/frontend/eval/browser suites using [local-development.md](../../operations/local-development.md) and the current testing configuration. Record exact commands, environment, failures and intentional skips. Do not run paid/live evaluations without the relevant authorization and budget. Test backup/deploy/role behavior with actual containers and roles rather than only mocking the implementation.

Each executed session writes `sNN-report.md` in this directory with:

- Status: not started / in progress / offline complete / externally pending / complete, with unmet criteria.
- Baseline branch/commit, migration head, environment and unrelated work preserved.
- Implemented behavior, changed files/contracts and concrete reproduction/demo steps.
- Exact verification outcomes and sanitized evidence paths; unresolved failures and skipped checks.
- Canonical task/acceptance coverage, decisions/deviations and external/legal dependencies.
- Next-session interfaces, recovery/resume instructions and remaining acceptance work.

## Session invocation

> Implement Phase 8 Session NN using `docs/implementation/phase-8-sessions/phase-08-sessions.md`. Read the common rules, the selected session brief, current phase/gate status and the previous session report. Complete that session's authorized work and checks, update `sNN-report.md`, and stop at its boundary. Preserve unrelated work. Do not infer authorization for deployment, live account actions, paid evaluations, App Review submission, publication, commit or push from this planning document.
