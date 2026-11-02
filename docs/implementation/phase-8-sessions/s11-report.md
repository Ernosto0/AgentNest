# Phase 8 — Session 11 Report: Meta Deauthorization and Data-Deletion Callbacks

- **Session:** `S11` (`docs/implementation/phase-8-sessions/phase-08-sessions.md` §Session 11, `docs/implementation/phases/phase-08-hardening.md` `P8-05 provider callbacks`, `docs/architecture/decisions/ADR-025-phase-8-hardening-contracts.md` §3.4, `V-06` provisional)
- **Date:** 2026-11-03
- **Status:** `complete` (Local implementation & test coverage complete; authentic provider acceptance tagged provisional under `V-06` until live dashboard verification in Session 16 / Gate 3)
- **Branch / Commit Baseline:** `main` at `e72590d`
- **Alembic Migration Head:** `20261103_0036_data_deletion_requests.py` (revision `0036`)

---

## 1. Summary of Implemented Artifacts & Contracts

| Artifact / File | Status | Implementation Summary |
|---|---|---|
| `backend/migrations/versions/20261103_0036_data_deletion_requests.py` | **Created** | Migration `0036` creating Category B system table `data_deletion_requests` (`id`, `confirmation_code` unique, `provider`, `provider_user_id`, `status`, `workspace_id`, `requested_at`, `completed_at`, `details`), status constraint (`pending`, `in_progress`, `completed`, `not_found_or_already_erased`), foreign key to `workspaces(id)` with `SET NULL`, indices, and runtime grants to `agentnest_app` and `agentnest_worker`. |
| `backend/app/operations/models.py` | **Updated** | Added `DataDeletionRequest` SQLAlchemy model matching the database migration schema. |
| `backend/app/operations/meta_callbacks.py` | **Created** | Implemented core callback service adhering strictly to `ADR-025 §3.4`: 1. `parse_and_verify_signed_request()` validates length bounds, splits `<encoded_sig>.<payload>`, decodes URL-safe base64, computes HMAC-SHA256 with constant-time equality check, enforces `algorithm == "HMAC-SHA256"`, and extracts `user_id`; 2. Invalid signatures/payloads record `webhook.signature_invalid` in audit log; 3. `handle_deauthorization()` maps server-owned `SocialAccount`, sets `status = "disconnected"`, clears tokens/capabilities, pauses active `AccountAgent`, and emits audit logs (`meta.deauthorized`, `social_account.disconnected`), handling unknown accounts safely without leaking state; 4. `handle_data_deletion_request()` checks existing requests for replay idempotency, creates unguessable confirmation codes (`del_...`), resolves page owner vs customer identity (`CustomerIdentity.provider_subject_hash == SHA256(user_id)`), orchestrates erasure via Session 10 `erase_customer()`, records anticipatory tombstones for unknown users, inserts `data_deletion_requests`, and returns Meta-compliant `{"url": "...", "confirmation_code": "..."}`; 5. `get_data_deletion_status()` returns strictly privacy-preserving status, never echoing PII, IDs, or message contents. |
| `backend/app/operations/meta_callbacks_router.py` | **Created** | Mounted endpoints: `POST /api/v1/webhooks/meta/deauthorize`, `POST /api/v1/webhooks/meta/data-deletion`, `GET /api/v1/webhooks/meta/data-deletion/{confirmation_code}`, plus public proxy aliases under `/webhooks/meta/...`. Exposes both JSON status and bilingual (TR/EN) HTML status page (`_render_status_html`) when visited in a browser. |
| `backend/app/api/deps.py` | **Updated** | Added `/api/v1/webhooks/meta/deauthorize` and `/api/v1/webhooks/meta/data-deletion` to `CSRF_EXEMPT_PATHS`. |
| `backend/app/main.py` | **Updated** | Mounted `meta_callbacks_router`. |
| `backend/app/activity/groups.py` | **Updated** | Registered actions `"meta.deauthorized"` and `"meta.data_deletion_requested"` under the `"system"` group. |
| `backend/app/core/i18n/` | **Updated** | Added localized TR and EN activity template strings in `en.json` and `tr.json`. |
| `docs/operations/meta-callbacks-runbook.md` | **Created** | Detailed runbook for Meta App settings configuration, signed_request verification, developer dashboard testing, status page behavior, and V-06 tracking. |
| `backend/tests/unit/operations/test_meta_callbacks.py` | **Created** | Comprehensive unit test suite (13 tests) verifying valid signed_requests, invalid signature refusal, malformed formats, deauthorization lifecycle, unknown account safety, audit logging, customer erasure routing, reconciliation pending status, unknown user anticipatory tombstones, idempotent replay, privacy-safe status output, and HTTP endpoints via `TestClient`. |
| `frontend/openapi.json` & `frontend/src/api/schema.d.ts` | **Regenerated** | Synchronized frontend OpenAPI client schema and TypeScript definitions. |

---

## 2. Verification Outcomes

### 2.1 Static Analysis & Quality

| Check | Command | Exit Code | Result Summary |
|---|---|---|---|
| Backend Lint | `backend/.venv/Scripts/ruff.exe check .` | `0` | All checks passed (0 errors) |
| Backend Typecheck | `backend/.venv/Scripts/mypy.exe app` | `0` | Success: no issues found in 300 source files |
| Import Architecture | `backend/.venv/Scripts/lint-imports.exe` | `0` | 19 contracts kept, 0 broken |
| Frontend Lint | `npm.cmd run lint` | `0` | ESLint passed cleanly |
| Frontend Typecheck | `npm.cmd run typecheck` | `0` | `tsc -b --noEmit` passed cleanly |
| Frontend i18n Check | `npm.cmd run i18n:check` | `0` | Passed: en, tr \| 1548 keys \| 1025 literal t() calls verified |

### 2.2 Test Suite Execution

| Test Suite | Command | Exit Code | Result Summary |
|---|---|---|---|
| Meta Callbacks Unit Suite | `pytest tests/unit/operations/test_meta_callbacks.py -v` | `0` | `13 passed in 0.79s` |
| Combined Backend Hardening Suite (S07-S11) | `pytest tests/unit/operations/test_meta_callbacks.py tests/unit/operations/test_workspace_lifecycle_and_erasure.py tests/unit/operations/test_data_rights_export.py tests/unit/identity/test_password_reset_and_email.py tests/unit/test_activity_templates.py tests/unit/test_import_rules.py -q` | `0` | `44 passed in 1.38s` |
| Frontend Inbox & Settings Vitest Suite | `vitest run src/features/inbox/inbox.test.tsx src/features/settings/settings.test.tsx` | `0` | `24 passed in 6.81s` |

---

## 3. Canonical Task Coverage & V-06 Status

- **P8-05 Meta Deauthorization Callback:**
  - Strict HMAC-SHA256 signature verification over base64url payload with `META_APP_SECRET`.
  - Disconnects connected accounts (`status = "disconnected"`, tokens cleared, capabilities cleared).
  - Fences agent automation (`AccountAgent.state = "paused"`).
  - Emits `meta.deauthorized` and `social_account.disconnected`.
  - Replay-safe and handles unknown users gracefully without account enumeration.
- **P8-05 Meta Data Deletion Request Callback & Confirmation Endpoint:**
  - Durable `data_deletion_requests` tracking with unguessable `confirmation_code` (`del_...`).
  - Server-owned mapping: routes customer identities through Session 10 `erase_customer()` and records anticipatory tombstones for unknown users to prevent backup-restore resurrection.
  - Respects reconciliation guard (`INV-05`, `ADR-022`): returns `in_progress` while operations settle.
  - Returns Meta mandatory JSON format: `{"url": "...", "confirmation_code": "..."}`.
  - Privacy-preserving status endpoint (`GET /api/v1/webhooks/meta/data-deletion/{confirmation_code}`): returns only truthful status without PII or internal IDs; renders bilingual HTML status page for web browsers.
- **V-06 Tracking (Provisional):**
  - All local cryptographic verification, lifecycle orchestration, database mutations, and status responses are 100% verified with synthetic fixtures.
  - Authentic Meta callback verification remains provisional (`V-06`) until verified in the live Meta App Dashboard during Phase 8 Session 16 (`P8-10` / Gate 3).
