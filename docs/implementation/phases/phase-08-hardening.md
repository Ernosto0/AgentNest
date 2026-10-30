# Phase 8: Production Hardening and Pilot Readiness

> **Gate 3** (real customer data) requires this phase **plus** the legal review of OQ-04, OQ-12 and OQ-13. Re-plan the details at the start of the phase.

## Objective
Make the system safe to run for real businesses: deployment on a single VPS, backups with a tested restore, database-level tenant isolation, authentication hardening, data export and deletion paths, Meta deauthorize and data-deletion callbacks, security headers, dependency auditing, operator alerts, privacy artifacts, a security review against the threat model, and App Review preparation.

## Implementation sessions

The [Phase 8 implementation plan and 16 session briefs](../phase-8-sessions/phase-08-sessions.md) define the short plan, task coverage, sequential scope, verification and handoffs. Session 01 re-plans against the actual baseline; external legal/platform and production acceptance remain explicit gates.

## Read first
[deployment.md](../../architecture/deployment.md) · [security-and-privacy.md](../../architecture/security-and-privacy.md) · [ADR-013](../../architecture/decisions/ADR-013-authentication-and-tenancy.md) · [ADR-017](../../architecture/decisions/ADR-017-configuration-and-secrets.md) · [ADR-019](../../architecture/decisions/ADR-019-open-source-and-hosted-boundary.md) · [open-questions.md](../../research/open-questions.md)

## Scope and tasks (in order)

**Phase 7.5 handoff:** Extend P8-03 RLS and isolation coverage to `account_agents`,
delegations, threads/events/sessions/steps/actions, owner tasks/questions, customer
identities/memory/summaries and public media/comment/thread records. P8-05 must call the
account-scoped memory export/erase service and coordinate source, derived summary,
prompt-snapshot, owner-question and comment erasure with the existing disconnect fence;
unresolved operations retain minimal reconciliation evidence. P8-06 sets legally reviewed
retention periods for these records. P8-07 must alert on agent dead/recovery jobs,
unresolved outcomes, capability loss and budget exhaustion. P8-09 reviews broker reference
scope, public/private context separation, owner demotion and cutover races. P8-10 needs
actual permission and app-workflow evidence for each new Meta capability before enabling
it. See the [agent rollout runbook](../../operations/account-agent-rollout.md); this
handoff does not claim Phase 8 implementation or real-account acceptance.

| ID | Task | Size |
|---|---|---|
| P8-01 | Backend Dockerfile (multi-stage, non-root), `compose.prod.yml` (caddy, api, worker, optional postgres), Caddyfile (TLS, SPA, `/api`, `/webhooks`, `/oauth`, security headers + CSP), deploy workflow (build on tag → GHCR → SSH deploy → migrate → restart), `.env` handling on the server | M |
| P8-02 | Backups: nightly encrypted `pg_dump` to an off-site bucket (35-day retention), media bucket protection; restore script; **restore drill** runbook executed and recorded | M |
| P8-03 | Postgres RLS: policies on all tenant tables keyed on `current_setting('app.workspace_id')`; set per transaction from `WorkspaceContext`; a system role for jobs that sets the workspace explicitly; tests proving a query without the setting returns nothing | L |
| P8-04 | Auth hardening: login throttling (per IP + email, exponential), session listing and revoke-all, password change, SMTP integration for invites and password reset (OQ-16), `COOKIE_SECURE` enforced | M |
| P8-05 | Data rights: conversation export and deletion, workspace deletion with grace period, Meta deauthorize + data-deletion callbacks (`signed_request` verification) + status endpoint (V-06) | M |
| P8-06 | Retention: finalise periods after legal review; key rotation procedure + re-encryption job; `pip-audit` and `npm audit` in CI | S |
| P8-07 | Operator monitoring: uptime check on `/readyz`; optional Sentry-compatible DSN; operator email alerts for dead jobs, signature-failure bursts, accounts in `needs_reauth` > 24 h, and backup failure | S |
| P8-08 | Privacy and legal artifacts (with counsel): privacy policy (product), KVKK aydınlatma metni template for businesses, DPA template, sub-processor register, breach runbook, automation disclosure wording (OQ-13) | M (non-code) |
| P8-09 | Security review: walk the threat model (T1–T22), run an authenticated scan (e.g., OWASP ZAP baseline), review the dependency list, fix findings, document residual risks | M |
| P8-10 | App Review preparation: privacy policy URL, data deletion URL, screencasts per permission, test user instructions; submit when ready | M (non-code) |
| P8-11 | OSS readiness (only after OQ-02): LICENSE, CONTRIBUTING (with CLA or DCO per the decision), CODE_OF_CONDUCT, SECURITY.md, issue templates | S |
| P8-12 | Staging environment (optional): same compose on a smaller VM with a test Meta account | S |

## Acceptance criteria
1. Fresh VPS to running HTTPS instance with documented commands. `/readyz` is green.
2. The restore drill succeeds and its measured RPO and RTO are recorded.
3. RLS tests pass. The isolation suite passes with RLS enabled.
4. Security review findings are fixed or documented with accepted risk.
5. Legal artifacts are reviewed by counsel. OQ-04, OQ-12 and OQ-13 are resolved in open-questions.md.
6. The first pilot business is onboarded on production using the assisted onboarding checklist.

## Explicitly excluded
Billing, self-service signup at scale, multi-region, high availability.
