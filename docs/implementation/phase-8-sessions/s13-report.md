# Phase 8 — Session 13 Report: Operator Monitoring and Alerts

- **Session:** `S13` (`docs/implementation/phase-8-sessions/phase-08-sessions.md` §Session 13, `docs/implementation/phases/phase-08-hardening.md` `P8-07`, `docs/architecture/decisions/ADR-025-phase-8-hardening-contracts.md` §4.3)
- **Date:** 2026-11-03
- **Status:** `complete` (External uptime runbook, Sentry privacy integration, operator alerting engine for all 8 canonical conditions, durable `operator_alert_states` deduplication & recovery, operational CLI, email notifications, and comprehensive runbooks implemented and verified)
- **Branch / Commit Baseline:** `main` at `69ecdc6`
- **Alembic Migration Head:** `20261103_0037_operator_alert_states.py` (revision `0037`)

---

## 1. Summary of Implemented Artifacts & Contracts

| Artifact / File | Status | Implementation Summary |
|---|---|---|
| `docs/operations/uptime-monitoring-runbook.md` | **Created** | Comprehensive operational runbook for external uptime monitoring: probes `/readyz` every 60s (5s timeout), verifies dependency breakdown (database, redis, disk), response payloads, failure classification (503 vs 500 vs timeout), incident response playbooks, and multi-vendor probe configurations (Uptime Kuma, Better Uptime, Datadog Synthetics, AWS Route53). |
| `backend/app/core/sentry.py` | **Created** | Optional Sentry-compatible error reporting integration (`init_sentry`): enabled conditionally via `SENTRY_DSN`, sets strict sample rates and environments, and enforces deep privacy scrubbing via `before_send` (`scrub_sentry_event`) — removes request headers (`Authorization`, `Cookie`, `X-Forwarded-For`), strips customer user PII (`id`, `username`, `email`, `ip_address`), and recursively masks sensitive fields (`token`, `secret`, `key`, `password`, `authorization`, `cookie`, `credential`) in extra/contexts data (`INV-08`, `INV-18`, `ADR-022`). |
| `backend/app/main.py` | **Updated** | Wired `init_sentry(settings)` into FastAPI application lifecycle in `create_app()`. |
| `backend/migrations/versions/20261103_0037_operator_alert_states.py` | **Created** | Migration revision `0037` (down: `0036`): creates Category B system table `operator_alert_states` with unique `alert_key`, status (`firing`, `resolved`), severity (`critical`, `warning`), cooldown, timestamps (`first_fired_at`, `last_fired_at`, `resolved_at`), notification count, and detail payload. Explicitly grants DML permissions to runtime roles `agentnest_app` and `agentnest_worker`. |
| `backend/app/operations/models.py` | **Updated** | Added `OperatorAlertState` SQLAlchemy declarative model representing durable alert lifecycle state. |
| `backend/app/operations/operator_alerts.py` | **Created** | Core operator alerting engine: 1. Evaluates all 8 canonical operational conditions across system and tenant boundaries; 2. Respects multi-tenant RLS by sweeping active workspaces under `set_tenant_context(session, ws_id)` for Category C tables (`SocialAccount`, `Operation`, `AgentSession`, `AccountAgent`); 3. Enforces durable deduplication, cooldown suppression, re-alerting with incremented notification count, and recovery notice emission (`firing -> resolved`) using `operator_alert_states`; 4. Emits append-only audit logs (`security.operator_alert_fired`, `security.operator_alert_resolved`, `security.alert_delivery_failed`) without secret leakage; 5. Dispatches localized operator email notifications. |
| `backend/app/core/email.py` | **Updated** | Added `send_operator_alert_email`: sends bilingual (TR/EN) operator alert and resolution emails with status badges, severity banners, incident metadata, and secret-free detail tables. |
| `backend/app/operations/payloads.py` | **Updated** | Added `EvaluateOperatorAlertsPayload` schema for worker background jobs. |
| `backend/app/operations/jobs.py` | **Updated** | Added `@job_handler("evaluate_operator_alerts", ...)` worker job and `enqueue_operator_alert_evaluation()` periodic scheduler hook (default 5-minute interval). |
| `backend/app/handlers.py` | **Updated** | Registered `app.operations.operator_alerts` in `load_handlers()`. |
| `backend/app/activity/groups.py` | **Updated** | Registered `"security.operator_alert_fired"`, `"security.operator_alert_resolved"`, and `"security.alert_delivery_failed"` in `"system"` activity group. |
| `backend/app/core/i18n/` | **Updated** | Added bilingual localized templates in `en.json` and `tr.json` for operator alert audit actions. |
| `scripts/evaluate_alerts.py` | **Created** | Cross-platform operational CLI tool supporting `--email`, `--json`, `--no-resolve`, and `--verbose`, exiting with distinct operational codes: 0 (healthy), 1 (critical firing), 2 (warning firing). Avoids worker/email dependency as the sole detector. |
| `docs/operations/operator-alerting-runbook.md` | **Created** | Canonical operational runbook covering all 8 conditions with incident severity, alerting thresholds, cooldown defaults, triage SQL, remediation steps, and escalation paths (A1–A8 playbooks). |
| `backend/pyproject.toml` & `backend/uv.lock` | **Updated** | Added `sentry-sdk==2.73.0` dependency. |
| `backend/tests/unit/core/test_sentry.py` | **Created** | Unit test suite (5 tests) verifying Sentry initialization, disabled state when DSN is unset, and deep privacy scrubbing (headers, PII, nested sensitive fields). |
| `backend/tests/unit/operations/test_operator_alerts.py` | **Created** | Unit test suite (14 tests) verifying all 8 alert conditions, deduplication and cooldown suppression, re-alerting after cooldown, resolution emission, RLS tenant context switching, delivery failure auditing, worker job handler, and CLI script execution. |

---

## 2. Verification Outcomes

### 2.1 Static Analysis & Quality

| Check | Command | Exit Code | Result Summary |
|---|---|---|---|
| Backend Lint | `uv run ruff check .` | `0` | All checks passed (0 errors) |
| Backend Formatting | `uv run ruff format --check .` | `0` | 588 files checked, all formatted |
| Backend Typecheck | `uv run mypy app evals` | `0` | Success: no issues found in 309 source files |
| Import Architecture | `uv run lint-imports` | `0` | 19 contracts kept, 0 broken |
| Python Dependency Audit | `uv run pip-audit` | `0` | No known vulnerabilities found |
| Frontend Lint | `npm.cmd run lint` | `0` | ESLint passed cleanly |
| Frontend Typecheck | `npm.cmd run typecheck` | `0` | `tsc -b --noEmit` passed cleanly |
| Frontend i18n Check | `npm.cmd run i18n:check` | `0` | Passed: en, tr \| 1548 keys \| 1025 literal t() calls verified |

### 2.2 Test Suite Execution

| Test Suite | Command | Exit Code | Result Summary |
|---|---|---|---|
| Sentry Integration Unit Suite | `uv run pytest tests/unit/core/test_sentry.py -v` | `0` | `5 passed in 0.45s` |
| Operator Alerts Unit Suite | `uv run pytest tests/unit/operations/test_operator_alerts.py -v` | `0` | `14 passed in 0.88s` |
| Combined Backend Hardening Suite (S07–S13) | `uv run pytest tests/unit/operations/test_operator_alerts.py tests/unit/core/test_sentry.py tests/unit/operations/test_key_rotation.py tests/unit/retention/test_retention_phase8.py tests/unit/operations/test_meta_callbacks.py tests/unit/operations/test_workspace_lifecycle_and_erasure.py tests/unit/operations/test_data_rights_export.py tests/unit/identity/test_password_reset_and_email.py tests/unit/test_activity_templates.py tests/unit/test_import_rules.py -q` | `0` | `70 passed in 5.34s` |
| Frontend Vitest Suite | `npm.cmd test` | `0` | `43 test files passed, 589 tests passed in 156.87s` |

---

## 3. Canonical Task Coverage & Gate 3 Tracking

- **P8-07 External Uptime Monitoring:**
  - Standardized external probes targeting `/readyz` every 60 seconds with a 5-second timeout.
  - Dependency status inspection (`database`, `redis`, `disk`) documented in `docs/operations/uptime-monitoring-runbook.md` with turnkey configs for Uptime Kuma, Datadog Synthetics, Better Uptime, and Route53.
- **P8-07 Privacy-Preserving Sentry Error Reporting:**
  - Optional `sentry-sdk` integrated with strict privacy scrubbing (`scrub_sentry_event`): sanitizes request headers (`Authorization`, `Cookie`), wipes user identification, and recursively masks sensitive payload keys (`INV-08`, `INV-18`, `ADR-022`).
- **P8-07 Canonical 8 Operational Alert Conditions:**
  1. *Dead background jobs:* queries non-dead-letter `Job` entries with `status='failed'`, `attempt >= max_attempts`, and `completed_at` within 24h.
  2. *Stale or failed backups:* queries `backup_manifests` for any failed backup or absence of a successful backup within 26 hours.
  3. *Webhook signature failure bursts:* aggregates `security.webhook_signature_invalid` audit logs over the last 15 minutes (threshold ≥ 10).
  4. *Accounts stuck in `needs_reauth`:* queries `SocialAccount` where `connection_status='needs_reauth'` and `updated_at < now() - 24h`.
  5. *Agent dead wake/recovery jobs or stuck sessions:* flags failed `wake_agent` / `agent_recovery` jobs and `AgentSession` stuck in active state without updates for > 30m.
  6. *Unresolved operations in `outcome_unknown`:* queries `Operation` with `status='outcome_unknown'` and `updated_at < now() - 30m`.
  7. *Capability loss:* flags `AccountAgent` where `status='disabled'` or `last_error` indicates disabled capabilities.
  8. *AI budget exhaustion & open circuits:* queries `workspaces` with exhausted monthly token budgets or open circuit breaker flags.
- **P8-07 Durable State, Deduplication, and Recovery Tracking:**
  - Tracked in Category B system table `operator_alert_states` with explicit cooldown suppression, re-alerting with incremented notification count, and recovery notice emission (`firing -> resolved`).
  - Out-of-band operational CLI (`scripts/evaluate_alerts.py`) ensures operators can detect and evaluate conditions independently of the background worker or email pipeline.
- **Gate 3 Status:**
  - Remains open as planned pending final legal counsel sign-off on provisional retention periods (`OQ-12`), while all operational alerting and monitoring requirements of Session 13 are fully implemented and verified.

---

## 4. Handoff to Session 14

- **Next Session:** `S14` — Privacy/Legal Artifacts and Conditional OSS Readiness (`docs/implementation/phase-8-sessions/phase-08-sessions.md` §Session 14, `P8-08`).
- **Prerequisites Satisfied:** Retention sweeps (S12), audit boundary (S12), privacy scrubbing (S13), and operator alerting (S13) are in place.
- **Scope for S14:**
  - Verify and finalize privacy policy, terms of service, and DPA documentation against current retention/erasure behavior.
  - Review telemetry/tracking notices and conditional open-source readiness checklist.
  - Consolidate final compliance documentation for Phase 8.
