# Phase 8 — Session 01 Report: Baseline, Contracts & Acceptance Plan

- **Session:** `S01` (`docs/implementation/phase-8-sessions/phase-08-sessions.md`)
- **Date:** 2026-10-30
- **Status:** `offline complete` (Baseline inventory, architectural contracts, ADR-025, legal/platform dependency checklist, and Phase 8 acceptance mapping complete; Phase 8 and Gate 3 remain open pending Sessions 02–16 and live staging/production verification)
- **Branch / Commit Baseline:** `main` at `e74a2b5` (`Add Phase 8 implementation plan and session briefs documentation`; preceded by `3e25fd9` and `f0d95f9`)
- **Alembic Migration Head:** `20261029_0030_agent_content_intents.py` (revision `0030`, 30 migrations total in `backend/migrations/versions/`)
- **New Architectural Decision Recorded:** `docs/architecture/decisions/ADR-025-phase-8-hardening-contracts.md`

---

## 1. Baseline Verification Results

All baseline static analysis, import boundary, typecheck, i18n, and unit test suites were executed on the clean `e74a2b5` tree (with `META_LIVE_ACCESS_TOKEN` and `META_LIVE_IG_USER_ID` cleared per `CLAUDE.md`):

| Check | Command | Exit Code | Result Summary |
|---|---|---|---|
| Backend Lint | `backend/.venv/Scripts/ruff.exe check .` | `0` | `All checks passed!` |
| Backend Format | `backend/.venv/Scripts/ruff.exe format --check .` | `0` | `563 files already formatted` |
| Backend Import Contracts | `backend/.venv/Scripts/lint-imports.exe` | `0` | `Analyzed 349 files, 2849 dependencies. Contracts: 19 kept, 0 broken.` |
| Backend Typecheck | `backend/.venv/Scripts/mypy.exe app evals` | `0` | `Success: no issues found in 298 source files` |
| Backend Unit Tests | `backend/.venv/Scripts/pytest.exe tests/unit -q` | `0` | `1490 passed in 7.20s` (DB-backed integration/isolation suites require local PostgreSQL TCP access on `localhost:5433`) |
| Frontend Lint | `npm.cmd run lint` | `0` | `eslint .` passed cleanly |
| Frontend Typecheck | `npm.cmd run typecheck` | `0` | `tsc -b --noEmit` passed cleanly |
| Frontend i18n Parity | `npm.cmd run i18n:check` | `0` | `i18n check passed: en, tr \| 1415 keys \| 888 literal t() calls verified` |

---

## 2. Codebase & Infrastructure Inventory (`existing` / `missing` / `needing extension`)

| Area / Artifact | Path(s) | Status | Findings & Phase 8 Action Required |
|---|---|---|---|
| **Local Dev Compose & DB Init** | `docker-compose.yml`, `docker/postgres/init/01-create-test-db.sql` | `existing` (needs extension in S05) | Runs PostgreSQL 16 (`agentnest` and `agentnest_test` on port `5433`) using a single superuser role (`agentnest`). Needs runtime role separation (`agentnest_migrator`, `agentnest_app`, `agentnest_worker` with `NOBYPASSRLS`) in Session 05. |
| **Production Container Packaging** | `Dockerfile`, `.dockerignore` | `missing` | Create multi-stage production `Dockerfile` (serving API, worker, migration commands, and built SPA assets as non-root user) and `.dockerignore` in Session 02. |
| **Production Compose & TLS Proxy** | `compose.prod.yml`, `Caddyfile` | `missing` | Create single-VPS production stack (`caddy`, `api`, `worker`, `postgres`, `backup`) and reverse-proxy config in Session 02. |
| **CI Workflow** | `.github/workflows/ci.yml` | `existing` | Runs backend lint/typecheck/migrations/pytest, frontend lint/typecheck/i18n/tests/build, and Playwright E2E. |
| **Deploy Workflow** | `.github/workflows/deploy.yml` | `missing` | Create staging/production build, migration (`alembic upgrade head`), rollout, `/readyz` gate, and rollback workflow in Session 03. |
| **Backup & Restore Automation** | `scripts/backup*`, `scripts/restore*`, `docs/operations/backup-restore.md` | `missing` | Create `pg_dump -Fc` encrypted offsite backup script, restore script, post-restore reconciliation (`in_progress` -> `outcome_unknown`, deletion tombstone re-application), and drill runbook in Session 04. |
| **Health & Readiness Endpoints** | `backend/app/api/router.py`, `backend/app/core/db.py` | `existing` | `GET /healthz` and `GET /readyz` exist; `check_readiness` verifies `SELECT 1` and `MigrationContext.get_current_revision() == migration_head()`. |
| **System Health Endpoint** | `backend/app/operations/system_health.py` | `needing extension` | Reports DB, worker heartbeat, queue depth, dead jobs, and account status counts. Needs backup status, alert status, and RLS/role readiness visibility in Sessions 04 and 13. |
| **Core Configuration** | `backend/app/core/config.py`, `.env.example`, `docs/operations/environment-variables.md` | `needing extension` | Has core DB, auth, AI, Meta, token encryption, S3, and 10 `RETENTION_*` settings. Missing in `Settings` and `.env.example`: `SMTP_URL`, `MAIL_FROM`, `OPERATOR_ALERT_EMAIL`, `SENTRY_DSN`, `TRUSTED_PROXY_CIDRS`, `MIGRATION_DATABASE_URL`, password-reset TTL, login throttle parameters, and workspace deletion grace days. |
| **Database Session & RLS Binding** | `backend/app/core/db.py`, `backend/app/api/deps.py`, `backend/app/jobs/worker.py` | `needing extension` | Currently connects with default DB user and filters by `workspace_id` in Python queries only; `SET LOCAL app.workspace_id` is **not** bound on API or worker transactions, and zero tables have `ENABLE/FORCE ROW LEVEL SECURITY`. |
| **Auth & Session Endpoints** | `backend/app/identity/router.py`, `backend/app/identity/service.py`, `backend/app/identity/models.py` | `needing extension` | Has `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `PATCH /auth/me`, CSRF protection, and Argon2id hashing. Missing: per-IP/per-email login throttling, `GET /auth/sessions`, `DELETE /auth/sessions/{id}`, `POST /auth/sessions/revoke-all`, `POST /auth/password`, and `POST /auth/password-reset/{request,confirm}`. |
| **Invites & Transactional Email** | `backend/app/identity/invites.py`, `backend/app/integrations/email/` | `needing extension` / `missing` | `invites` table and create/list/revoke/accept routes exist, returning raw invite URL once to owner. Email adapter (`SMTP` + dev/test outbox capture) and emailed invites/password-reset/workspace-deletion/alert delivery are **missing** (Session 08). |
| **Storage Abstraction** | `backend/app/integrations/storage/{base,local,s3,registry}.py` | `existing` | `MediaStorage` protocol with `LocalMediaStorage` and `S3MediaStorage` (`put`, `open`, `delete`, `presign_get`) is implemented and wired via `build_media_storage`. |
| **Data-Rights Helpers (Internal)** | `backend/app/memory/service.py`, `backend/app/comments/privacy.py`, `backend/app/owner_requests/service.py`, `backend/app/operations/conversation_deletion.py` | `needing extension` | Internal helpers exist for customer memory export/erasure (`export_customer`, `erase_customer`, `erase_account`, `erase_source`), comment erasure/redaction (`erase_account`, `redact_receipts`, `redact_media_caches`), owner question redaction (`redact`), and account disconnect conversation deletion (`delete_account_conversations`). Missing: unified owner-facing Conversation/Customer Export API (`Session 09`), unified Conversation/Customer Deletion & Workspace Deletion Grace/Cancel/Purge service (`Session 10`), and Meta Deauthorize & Data-Deletion Callbacks (`Session 11`). |
| **Retention & Media Cleanup Jobs** | `backend/app/retention/cleanup.py`, `backend/app/retention/jobs.py`, `backend/app/content/media_cleanup.py` | `needing extension` | `run_retention_cleanup` currently covers `inbound_events`, `agent_runs`, `messages`, `reply_drafts`, `notifications`, and `jobs`. `run_media_cleanup` covers orphan/published `media_assets`. Needs extension in Session 12 to invoke `memory.service.retention_batch`, `comments.privacy.retention_batch`, `owner_requests` redaction, and `agent_*` step/event/task retention, plus `rotate_token_keys`. |
| **Operator Alerting** | `backend/app/operations/alerts.py` (planned) | `missing` | No operator alert evaluator, deduplication/cooldown state table, or recovery notification job exists yet (Session 13). |

---

## 3. Complete Table Classification & Runtime-Role Matrix (59 Tables)

The codebase defines **58 SQLAlchemy-mapped tables** across 18 model modules plus **`alembic_version`** (**59 database tables total**: 4 Global Category A + 6 Hybrid Category B + 49 Strictly Tenant-Scoped Category C).

### 3.1 Runtime Database Roles (`ADR-025` §1.1)

- **`agentnest_migrator`:** Owns schema, tables, RLS policies, and `SECURITY DEFINER` bootstrap functions. Used only by `alembic upgrade` / DDL scripts.
- **`agentnest_app`:** API runtime role (`NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`). Subject to `FORCE ROW LEVEL SECURITY` on all tenant tables. Granted `SELECT, INSERT` only on `audit_logs` and `fact_versions` (`REVOKE UPDATE, DELETE`).
- **`agentnest_worker`:** Worker runtime role (`NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`). Subject to the same RLS and append-only constraints as `agentnest_app`.

### 3.2 Table-by-Table Matrix

#### Category A — Global / User-Scoped Root Tables (4 existing tables; no `workspace_id`, no tenant RLS)

| # | Table | Module | Primary Key | Scope & Runtime Access Pattern |
|---|---|---|---|---|
| 1 | `alembic_version` | Alembic | `version_num` | Global migration state. `SELECT` by runtime roles (`/readyz`); `INSERT/UPDATE/DELETE` by `agentnest_migrator` only. |
| 2 | `users` | `identity/models.py` | `id` | Global user identity (`email` unique). Queried during `POST /auth/login`, session validation, password change/reset, and member display. |
| 3 | `sessions` | `identity/models.py` | `id` | User auth sessions (`user_id` FK -> `users.id`, `token_hash` unique). Queried by `token_hash` on every authenticated request before workspace context exists. |
| 4 | `workspaces` | `identity/models.py` | `id` | Root tenant record (`status IN ('active', 'deleting')`). Read during membership resolution, daily report / promotion notice scheduling, and workspace settings/deletion lifecycle. |

*(Phase 8 Sessions 07–08 will add global user/auth tables `password_reset_tokens` and `login_throttles` in Category A.)*

#### Category B — Hybrid / Cross-Boundary Bootstrap & System Tables (6 existing tables)

| # | Table | Module | `workspace_id` | Pre-Context Access Pattern | Tenant-Context Access Pattern & RLS Policy |
|---|---|---|---|---|---|
| 5 | `workspace_members` | `identity/models.py` | `NOT NULL` (PK `(workspace_id, user_id)`) | `list_memberships(user_id)` and `get_membership(workspace_id, user_id)` run after auth session validation to discover workspaces and build `WorkspaceContext`. | Member list/role update/removal inside workspace routes. Policy allows `workspace_id = current_setting('app.workspace_id')` OR pre-context lookup via `app.user_id` / `SECURITY DEFINER` membership helper. |
| 6 | `invites` | `identity/models.py` | `NOT NULL` (`token_hash` unique) | `accept_invite(token)` looks up invite by `token_hash` before caller knows `workspace_id`. | Owner create/list/revoke under `app.workspace_id`. Pre-context token lookup via narrow `SECURITY DEFINER` function `resolve_invite_by_token_hash(text)` returning `workspace_id`, then binds `SET LOCAL app.workspace_id`. |
| 7 | `oauth_states` | `integrations/instagram/models.py` | `NOT NULL` (`state_hash` unique) | `complete_callback(state)` resolves `workspace_id` by `state_hash` on `GET /oauth/instagram/callback` before `WorkspaceContext` exists. | Created under `app.workspace_id` in `start_connect`. Callback resolves `workspace_id` via `SECURITY DEFINER` helper `consume_oauth_state(text)` and binds `SET LOCAL app.workspace_id`. |
| 8 | `inbound_events` | `inbox/models.py` | `NULL` (`dedup_key` unique) | `ingest_webhook` inserts events before/without workspace context (`UNKNOWN_ACCOUNT` events have `workspace_id IS NULL`). | `process_inbound_event` reads/updates rows where `workspace_id = current_setting('app.workspace_id')`; `retention_cleanup` sweeps expired rows. |
| 9 | `audit_logs` | `audit/models.py` | `NULL` (no FK to `workspaces`; insert-only) | System events (`auth.login`, `auth.login_failed`, `webhook.signature_invalid`, `retention.cleanup_ran`) insert with `workspace_id IS NULL`. | `REVOKE UPDATE, DELETE` for runtime roles. `INSERT` allowed when `workspace_id IS NULL` or `workspace_id = current_setting('app.workspace_id')`; tenant `SELECT` restricted to `workspace_id = current_setting('app.workspace_id')`. |
| 10 | `jobs` | `jobs/models.py` | `NULL` (`dedup_key` partial unique) | Worker claims next due job globally (`FOR UPDATE SKIP LOCKED`), heartbeats, and finalizes status; scheduler enqueues periodic jobs (`workspace_id IS NULL`). | Tenant transactions enqueue jobs with `workspace_id = current_setting('app.workspace_id')`. When worker executes a job with `job.workspace_id IS NOT NULL`, `job.session_factory` automatically binds `SET LOCAL app.workspace_id = '<job.workspace_id>'`. |

*(Phase 8 Sessions 10, 11, and 13 will add system tables `deletion_tombstones`, `data_deletion_requests`, and `operator_alert_states` in Category B.)*

#### Category C — Strictly Tenant-Scoped Tables (49 existing tables; `workspace_id NOT NULL`, `ENABLE` + `FORCE ROW LEVEL SECURITY`)

Every table below has `workspace_id UUID NOT NULL` and will enforce `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` with policy `workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid`:

| # | Table | Module | Phase Introduced | Special Constraints / Pre-Context Notes |
|---|---|---|---|---|
| 11 | `business_facts` | `knowledge/models.py` | Phase 1 | Composite `(workspace_id, id)` unique; read by AI/reporting/promotion notices under `app.workspace_id`. |
| 12 | `fact_versions` | `knowledge/models.py` | Phase 1 | **Insert-only (`INV-07`)**: `REVOKE UPDATE, DELETE` for runtime roles in addition to tenant RLS. |
| 13 | `fact_candidates` | `knowledge/models.py` | Phase 1 | Strictly tenant-scoped. |
| 14 | `fact_references` | `knowledge/models.py` | Phase 1 | Strictly tenant-scoped. |
| 15 | `approved_answers` | `knowledge/models.py` | Phase 1 | Strictly tenant-scoped. |
| 16 | `owner_commands` | `commands/models.py` | Phase 2 | Strictly tenant-scoped (`expire_commands` sweeps per-workspace). |
| 17 | `agent_runs` | `ai/models.py` | Phase 2 | Strictly tenant-scoped (`sweep_agent_runs` and `retention_cleanup` sweep per-workspace). |
| 18 | `approvals` | `approvals/models.py` | Phase 2 | Strictly tenant-scoped (`expire_approvals` sweeps per-workspace). |
| 19 | `automation_policies` | `policy/models.py` | Phase 3 | PK `(workspace_id, action_class)`; strictly tenant-scoped. |
| 20 | `social_accounts` | `integrations/instagram/models.py` | Phase 3 | Strictly tenant-scoped under RLS. **Pre-context webhook/callback lookup:** resolved via narrow `SECURITY DEFINER` function `resolve_social_account_by_external(provider_kind, external_account_id)` returning `(id, workspace_id, status)`. |
| 21 | `conversations` | `inbox/models.py` | Phase 3 | Strictly tenant-scoped. |
| 22 | `messages` | `inbox/models.py` | Phase 3 | Strictly tenant-scoped. |
| 23 | `reply_drafts` | `inbox/models.py` | Phase 3 | Strictly tenant-scoped (`expire_reply_drafts` sweeps per-workspace). |
| 24 | `media_assets` | `content/models.py` | Phase 4 | Strictly tenant-scoped (`media_cleanup` sweeps per-workspace). |
| 25 | `content_items` | `content/models.py` | Phase 4 | Strictly tenant-scoped. |
| 26 | `operations` | `operations/models.py` | Phase 3 | Strictly tenant-scoped (`reconcile_stuck_operations` sweeps per-workspace). |
| 27 | `notifications` | `notifications/models.py` | Phase 2 | Strictly tenant-scoped. |
| 28 | `daily_reports` | `reporting/models.py` | Phase 5 | Strictly tenant-scoped. |
| 29 | `report_items` | `reporting/models.py` | Phase 5 | Strictly tenant-scoped. |
| 30 | `report_source_gaps` | `reporting/models.py` | Phase 5 | Strictly tenant-scoped. |
| 31 | `sim_inbound_messages` | `integrations/instagram/models.py` | Phase 3 | Simulator table; strictly tenant-scoped. |
| 32 | `sim_sent_messages` | `integrations/instagram/models.py` | Phase 3 | Simulator table; strictly tenant-scoped. |
| 33 | `sim_failure_rules` | `integrations/instagram/models.py` | Phase 3 | Simulator table; strictly tenant-scoped. |
| 34 | `sim_containers` | `integrations/instagram/models.py` | Phase 4 | Simulator table; strictly tenant-scoped. |
| 35 | `sim_published_media` | `integrations/instagram/models.py` | Phase 4 | Simulator table; strictly tenant-scoped. |
| 36 | `sim_public_comments` | `comments/models.py` | Phase 7.5 | Simulator table; strictly tenant-scoped. |
| 37 | `sim_comment_effects` | `comments/models.py` | Phase 7.5 | Simulator table; strictly tenant-scoped. |
| 38 | `sim_private_replies` | `comments/models.py` | Phase 7.5 | Simulator table; strictly tenant-scoped. |
| 39 | `account_agents` | `agent/models.py` | Phase 7.5 | Account-agent configuration & kill switch; strictly tenant-scoped. |
| 40 | `agent_delegations` | `agent/models.py` | Phase 7.5 | Delegation leases & epochs; strictly tenant-scoped. |
| 41 | `agent_threads` | `agent/models.py` | Phase 7.5 | Durable customer/comment/owner threads; strictly tenant-scoped. |
| 42 | `agent_owner_tasks` | `agent/models.py` | Phase 7.5 | Durable owner tasks (`OwnerTask`); strictly tenant-scoped. |
| 43 | `agent_events` | `agent/models.py` | Phase 7.5 | Thread event log; strictly tenant-scoped. |
| 44 | `agent_sessions` | `agent/models.py` | Phase 7.5 | Goal/activation sessions (`agent_recover` sweeps per-workspace); strictly tenant-scoped. |
| 45 | `agent_steps` | `agent/models.py` | Phase 7.5 | Step execution ledger; strictly tenant-scoped. |
| 46 | `agent_actions` | `agent/models.py` | Phase 7.5 | Governed tool/effect actions; strictly tenant-scoped. |
| 47 | `customer_identities` | `memory/models.py` | Phase 7.5 | Provider-scoped customer identity (`INV-18`); strictly tenant-scoped. |
| 48 | `customer_source_fences` | `memory/models.py` | Phase 7.5 | Erasure fence (`SourceFence`, `erased_through_at`); strictly tenant-scoped. |
| 49 | `customer_memories` | `memory/models.py` | Phase 7.5 | Active structured customer memory; strictly tenant-scoped. |
| 50 | `customer_memory_versions` | `memory/models.py` | Phase 7.5 | Customer memory version history (`MemoryVersion`); strictly tenant-scoped. |
| 51 | `customer_memory_sources` | `memory/models.py` | Phase 7.5 | Provenance linkage (`MemorySource`); strictly tenant-scoped. |
| 52 | `customer_summary_versions` | `memory/models.py` | Phase 7.5 | Rolling customer summary versions (`SummaryVersion`); strictly tenant-scoped. |
| 53 | `owner_questions` | `owner_requests/models.py` | Phase 7.5 | Structured agent-to-owner questions (`recover_questions` sweeps per-workspace); strictly tenant-scoped. |
| 54 | `owner_answers` | `owner_requests/models.py` | Phase 7.5 | Owner answers to agent questions; strictly tenant-scoped. |
| 55 | `public_media` | `comments/models.py` | Phase 7.5 | Public IG media cache; strictly tenant-scoped. |
| 56 | `public_threads` | `comments/models.py` | Phase 7.5 | Public comment thread state; strictly tenant-scoped. |
| 57 | `public_comments` | `comments/models.py` | Phase 7.5 | Public IG comments; strictly tenant-scoped. |
| 58 | `public_comment_actions` | `comments/models.py` | Phase 7.5 | Public comment reply/hide/delete/private-reply actions; strictly tenant-scoped. |
| 59 | `private_reply_opportunities` | `comments/models.py` | Phase 7.5 | Comment-to-DM 7-day private reply windows; strictly tenant-scoped. |

### 3.3 Pre-Context Bootstrap Workflows (`ADR-025` §1.4)

1. **Login & Session Validation (`POST /auth/login`, `get_current_user`):**
   - Queries `users` and `sessions` (Category A, global). No `app.workspace_id` required.
2. **Membership Lookup (`GET /workspaces`, `get_workspace_context`):**
   - Queries `workspace_members` and `workspaces`. Once membership `(workspace_id, user_id)` is verified in `get_workspace_context`, the FastAPI dependency executes `SET LOCAL app.workspace_id = '<workspace_id>'` on the request's database session before returning `WorkspaceContext`.
3. **Invite Acceptance (`POST /auth/invites/accept`):**
   - Calls `resolve_invite_by_token_hash(token_hash)` (`SECURITY DEFINER`) to obtain `workspace_id`, binds `SET LOCAL app.workspace_id = '<workspace_id>'`, locks the `invites` row, creates the `workspace_members` row, and records `member.invite_accepted`.
4. **OAuth Callback (`GET /oauth/instagram/callback`):**
   - Calls `resolve_oauth_state_by_hash(state_hash)` (`SECURITY DEFINER`) to obtain `workspace_id`, binds `SET LOCAL app.workspace_id = '<workspace_id>'`, consumes the `oauth_states` row, upserts `social_accounts`, and enqueues workspace-scoped jobs.
5. **Inbound Webhook Ingestion (`POST /webhooks/instagram`):**
   - Verifies HMAC-SHA256 signature first. Calls `resolve_social_account_by_external(provider_kind, external_account_id)` (`SECURITY DEFINER`) to resolve `(social_account_id, workspace_id, status)`.
   - If unknown, inserts `inbound_events` with `workspace_id = NULL, status = 'ignored', error_code = 'UNKNOWN_ACCOUNT'` and returns `200`.
   - If matched, binds `SET LOCAL app.workspace_id = '<workspace_id>'`, inserts `inbound_events`, and enqueues `process_inbound_event` with `workspace_id`.
6. **Worker Job Execution & Periodic Global Sweeps (`app/jobs/worker.py`):**
   - Worker claims next due `jobs` row globally (`Category B`).
   - When `job.workspace_id IS NOT NULL`, `job.session_factory` wraps every opened session with `SET LOCAL app.workspace_id = '<job.workspace_id>'`.
   - When `job.workspace_id IS NULL` (global periodic jobs: `refresh_tokens`, `enqueue_health_checks`, `reconcile_stuck_operations`, `agent_recover`, `expire_approvals`, `expire_reply_drafts`, `expire_commands`, `sweep_agent_runs`, `retention_cleanup`, `media_cleanup`), the job iterates active `workspaces.id` (Category A) and opens per-workspace transactions with `SET LOCAL app.workspace_id = '<workspace_id>'` so every Category C read and write executes under active tenant RLS.

---

## 4. Settled Phase 8 Contracts (`ADR-025` §§2–4)

### 4.1 Conversation & Customer Export (`P8-05` / Session 09)
- **Authorization:** Requires `data.export` permission (Owner only per `ADR-013`). Cross-workspace or nonexistent IDs return `404`.
- **Format:** Deterministic JSON (`schema_version: "1.0"`, `exported_at`, `workspace_id`, `social_account_id`, `customer_identity`, `conversations`, `messages`, `reply_drafts`, `operations_summary`, `customer_memory` via `memory.service.export_customer`, `owner_questions_and_answers`, and `public_comments` linked strictly by provider-evidenced `external_author_id == external_participant_id` on the same `social_account_id`).
- **Exclusions:** Never exports `access_token_ciphertext`, webhook secrets/signatures, internal prompts, or unlinked third-party comments in shared public threads (`INV-18`).

### 4.2 Conversation/Customer Erasure, Workspace Deletion Grace Period & Reconciliation Guards (`P8-05` / Session 10)
- **Conversation / Customer Erasure (`data.delete`, Owner-Only):**
  - Wipes/redacts personal data across DM `conversations`/`messages`/`reply_drafts`, `customer_identities`/`customer_memories`/`customer_memory_versions`/`customer_memory_sources`/`customer_summary_versions` (advancing `customer_source_fences.erased_through_at` via `memory.service.erase_customer` so in-flight model turns cannot re-write erased facts — `INV-18`), `agent_threads`/`agent_events`/`agent_sessions`/`agent_steps`/`agent_actions`/`agent_owner_tasks`, `owner_questions`/`owner_answers` (`owner_requests.service.redact`), customer-authored `public_comments`/`public_comment_actions`/`private_reply_opportunities`, `inbound_events.payload_json`, and associated `MediaStorage` objects.
- **Reconciliation Exceptions (`INV-05`, `ADR-022`):**
  - If an `operations` row is `in_progress` or `outcome_unknown`, text/PII fields are scrubbed immediately and the memory fence is advanced, while the minimal operation state-machine key (`id`, `status`, `idempotency_key`, `provider_ref.message_id`/`text_sha256`) is retained until reconciliation finishes (`succeeded` or `failed`) or deferred via `delete_customer_data` job (`RescheduleJob` while `unresolved() == True`).
  - Append-only `audit_logs` and `fact_versions` are never deleted (`INV-06`, `INV-07`).
- **Workspace Deletion Lifecycle (`workspace.manage` / `data.delete`, Owner-Only):**
  - **Request:** Sets `workspaces.status = 'deleting'`, `deletion_requested_at = now()`, `deletion_scheduled_at = now() + 7 days` (provisional 7-day grace period per `ADR-013` / `OQ-12`). Immediately pauses `account_agents`, revokes `agent_delegations`, cancels pending `reply_drafts`/`approvals`/`content_items`, and emails workspace owners.
  - **Cancel:** Allowed while `status == 'deleting'` and `now() < deletion_scheduled_at`. Restores `status = 'active'` and records `workspace.deletion_cancelled`.
  - **Purge & Backup-Restore Fencing:** After `deletion_scheduled_at` (and once no `in_progress` operations remain), deletes all workspace `MediaStorage` objects outside the DB lock, hard-deletes all workspace rows and `workspaces`, writes a `deletion_tombstones` record, and logs `workspace.purged`. Post-restore reconciliation checks `deletion_tombstones` so a restored backup never resurrects purged workspaces/customers or re-sends `in_progress` operations.

### 4.3 Meta Deauthorization & Data-Deletion Callbacks (`P8-05` / Session 11)
- **Verification:** Validates Meta `signed_request` HMAC-SHA256 signature with `META_APP_SECRET` (or `MOCK_INSTAGRAM_APP_SECRET` in simulator mode). Invalid signatures return `400`/`401` and log `webhook.signature_invalid`.
- **Deauthorize (`POST /api/v1/webhooks/meta/deauthorize`):** Resolves `social_accounts` by server-owned `external_account_id`, transitions account to `disconnected`, clears `access_token_ciphertext`, pauses `account_agents`, revokes `agent_delegations`, cancels pending drafts/approvals/scheduled content, and enqueues `delete_account_conversations` if configured.
- **Data-Deletion (`POST /api/v1/webhooks/meta/data-deletion` & `GET /api/v1/webhooks/meta/data-deletion/{confirmation_code}`):** Creates an idempotent `data_deletion_requests` row with an opaque `confirmation_code`, enqueues erasure, and returns `{url, confirmation_code}`. The status endpoint returns **only** opaque status (`confirmation_code`, `status`, `requested_at`, `completed_at`) with zero personal data. Live Meta payload nuances remain tagged provisional under `V-06`.

### 4.4 Operator Alert Thresholds & Cooldowns (`P8-07` / Session 13)
1. **Dead job (`jobs.status == 'dead'`):** Immediate trigger per `(job_type, workspace_id)`, 1h cooldown, recovery notice when cleared/retried.
2. **Backup failure / stale backup heartbeat:** > 26h since last successful backup marker or explicit failure marker, 6h cooldown, recovery notice on next successful backup.
3. **Webhook signature-failure burst:** ≥ 10 `webhook.signature_invalid` audit events within a rolling 60-minute window, 1h cooldown.
4. **Account stuck in `needs_reauth`:** `social_accounts.status == 'needs_reauth'` for > 24 hours, 24h cooldown per account, recovery notice on reconnect/disconnect.
5. **Agent dead wake / stuck session:** `agent_wake` dead job or `agent_sessions` stuck in active state > 30 minutes without step progress, 1h cooldown.
6. **Unresolved `outcome_unknown` operation:** `operations.status == 'outcome_unknown'` older than reconciliation window, 2h cooldown.
7. **Capability loss:** Connected `social_accounts` losing required messaging/publishing/comment permissions during refresh or health check, 6h cooldown.
8. **AI budget exhaustion / circuit open:** `account_agents` daily token/cost budget exhausted or LLM provider circuit breaker open, 6h cooldown.

---

## 5. Legal, Platform & Operational Dependency Checklist

The following open questions (`docs/research/open-questions.md`), platform verifications (`docs/research/platform-capabilities.md`), and external deployment dependencies (`docs/implementation/phases/phase-08-hardening.md`) are tracked explicitly. Provisional defaults are engineered as configurable settings and **must not** be marked legally/externally resolved without real counsel review or live platform evidence:

### 5.1 Open Questions (`OQ-*`) & Platform Verifications (`V-*`, `R75-*`)

| ID | Canonical Open Question / Verification (`docs/research/open-questions.md`) | Current Status | Engineering Handling in Phase 8 | Blocking Session / Gate |
|---|---|---|---|---|
| `OQ-02` | **Open-source core license** (`Apache-2.0`, `AGPL-3.0`, or another) | **Open (Product / Legal)** | Repository remains **private** (`ADR-019`); conditional OSS readiness (`P8-11`: `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, boundary check) is deferred in Session 14 until `OQ-02` is decided. | Conditional `P8-11` (Session 14) |
| `OQ-03` | **Whether pilot businesses can be served under Standard Access as app testers** and which features require Advanced Access (`V-01`) | **Open (Platform Verification)** | Onboarding checklist (`P8-10`, Session 16) supports tester-role onboarding under Standard Access while preparing App Review submission packet for Advanced Access. | Session 16 / Gate 3 |
| `OQ-04` | **Hosting region and cross-border transfer basis under KVKK** (Türkiye vs EU hosting; foreign LLM API transfer basis) | **Open (Needs Legal Counsel)** | Deployment stack (`P8-01`) is region-agnostic; cross-border LLM processor and hosting disclosures are drafted in `docs/legal/` (`P8-08`, Session 14) for counsel review. | Session 14 / Gate 3 |
| `OQ-05` | **Legal entity applying for Meta Business Verification and signing DPAs** | **Open (Legal / Business)** | Required before live Meta App Review submission and production DPA execution (`P8-10`, Session 16). | Session 16 / Gate 3 |
| `OQ-09` | **LLM model per task and acceptable monthly cost per workspace** | **Open (Product / Pilot)** | Model names and per-account daily token/run budgets are configurable via settings (`OPENAI_MODEL`, `account_agents` budget controls) and monitored by operator alerts (`P8-07`, Session 13). | Session 16 (Pilot) |
| `OQ-12` | **Retention periods for messages, raw webhooks, agent run inputs, and Phase 7.5 records** | **Provisional (Needs Legal Counsel)** | Configurable via `RETENTION_*` env vars (30d/90d/180d) and 7-day workspace deletion grace period (`P8-05`, `P8-06`). Kept explicitly provisional in code and docs until counsel review in Session 14. | Sessions 12, 14 / Gate 3 |
| `OQ-13` | **Whether automation disclosure is legally required in Türkiye for automated DMs, and exact wording** | **Open (Needs Legal Counsel)** | Prepared in `docs/legal/` (`P8-08`, Session 14) for counsel sign-off before Gate 3. | Session 14 / Gate 3 |
| `OQ-16` | **Email delivery (SMTP) for invitations and password reset** | **Open (Engineering / Ops)** | Implemented via standard SMTP (`SMTP_URL`, `MAIL_FROM`) + dev/test outbox capture in `P8-04` (Session 08), compatible with Postmark, Resend, SES, or Mailpit. | Session 08 / Session 16 |
| `V-01..V-11`, `R75-01..R75-06` | **Live Meta Graph API / Instagram webhook / callback verification** (`V-06` deauthorize & data-deletion payload shapes) | **Provisional (Needs Live Meta App)** | Simulator + contract unit/integration tests in Session 11 (`P8-05`); live callback & Graph API verification tracked for Session 16 (`P8-10` / Gate 3). Never fabricate live verification results. | Session 11 (provisional) / Session 16 (live) |

### 5.2 External Deployment & Infrastructure Dependencies

| Dependency | Phase 8 Task | Engineering Handling | Live Requirement |
|---|---|---|---|
| **VPS Host** (`P8-01`) | `P8-01`, `P8-12` | Portable Docker Compose + Caddy stack (`compose.prod.yml`, `Caddyfile`); parameterized via env vars so optional staging (`P8-12`) requires zero file forks. | Needed for live staging/production rollout & AC-1 verification (Session 16). |
| **Domain Name & DNS / TLS** (`P8-01`) | `P8-01` | Configured via `APP_BASE_URL`, `FRONTEND_ORIGIN`, and Caddy domain env vars. | Needed for live HTTPS `/readyz` & Meta webhook/callback URLs (Session 16). |
| **S3-Compatible Object Storage** (`P8-01`, `P8-02`) | `P8-01`, `P8-02` | `S3MediaStorage` (`S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`) for media objects and encrypted off-site `pg_dump` backups (35-day retention). | Needed for live off-site backup and media bucket policy verification (Session 16). |
| **SMTP Provider** (`P8-04`, `OQ-16`) | `P8-04`, `P8-07` | Standard `SMTP_URL` / `MAIL_FROM` (`OPERATOR_ALERT_EMAIL` for alerts); dev/test outbox capture used in CI/offline tests. | Needed for live invite, password-reset, and alert email delivery (Session 16). |
| **Optional Sentry DSN** (`P8-07`) | `P8-07` | Optional `SENTRY_DSN` integration with `send_default_pii=False` and secret scrubbing in Session 13. | Optional in production. |

---

## 6. Canonical Phase 8 Task & Acceptance Criteria Mapping

### 6.1 Canonical Phase 8 Task Mapping (`P8-01` through `P8-12`)

| Task ID | Canonical Description (`docs/implementation/phases/phase-08-hardening.md`) | Assigned Session(s) | Notes on Session Split / Ordering |
|---|---|---|---|
| `P8-01` | Production packaging (`Dockerfile`, `compose.prod.yml`, `Caddyfile`), deploy workflow, `.env` handling | **S02**, **S03** | Split into S02 (container packaging, compose stack, Caddy proxy) and S03 (`.github/workflows/deploy.yml`, migration gate, rollback runbook). |
| `P8-02` | Backups (daily encrypted `pg_dump`, 35-day retention), media bucket protection, restore script & restore drill | **S04** (and post-RLS drill in **S06**) | Implemented and drilled locally in S04; re-verified with RLS policies and roles active in S06. |
| `P8-03` | Postgres RLS (`current_setting('app.workspace_id')`, non-bypass runtime roles, tenant policies, isolation suite) | **S05**, **S06** | Split into S05 (runtime roles, GUC lifecycle, pre-context bootstrap, core RLS migration) and S06 (complete 49-table Category C coverage, Phase 7.5 RLS policies, schema introspection & isolation test suite). |
| `P8-04` | Auth hardening (login throttling, session listing/revocation, password change) & SMTP integration for invites/password reset (`OQ-16`) | **S07**, **S08** | Split into S07 (login throttling, session management, password change) and S08 (SMTP adapter, emailed invites, hashed single-use password reset flow). |
| `P8-05` | Data rights: conversation/customer export & deletion, workspace deletion with 7-day grace period, Meta deauthorize + data-deletion callbacks (`V-06`) | **S09**, **S10**, **S11** | Split into S09 (export service/API), S10 (customer/conversation erasure, workspace deletion grace/cancel/purge, reconciliation guards), and S11 (Meta `signed_request` deauthorize & data-deletion callbacks + privacy-safe status endpoint). |
| `P8-06` | Finalize retention cleanup across all tables (`OQ-12`), token encryption key rotation, `pip-audit` & `npm audit` in CI | **S12** | Extends `run_retention_cleanup` to Phase 7.5 tables, adds `rotate_token_keys`, and wires dependency vulnerability checks in CI. |
| `P8-07` | Operator monitoring (`/readyz` uptime check, optional Sentry DSN, operator email alerts) | **S13** | Implements durable operator alert evaluator, cooldowns, recovery notices, system health extensions, and optional Sentry hook. |
| `P8-08` | Privacy and legal artifacts with counsel (`OQ-04`, `OQ-12`, `OQ-13`) | **S14** | Prepares privacy notice, retention schedule, subprocessor list, KVKK transfer basis, and disclosure templates in `docs/legal/`; counsel sign-off remains a live Gate 3 requirement. |
| `P8-09` | Security review (`T1`–`T22` threat model walk, authenticated scan, dependency review, remediation, residual risks) | **S15** | Executes full security regression suite, `T1`–`T22` audit, OpenAPI/route matrix checks, and records findings/remediations. |
| `P8-10` | App Review preparation (screencasts, reviewer instructions, test account, Business Verification `OQ-05`) | **S16** | Prepares submission packet and onboarding runbook; live submission requires external Meta credentials and `OQ-05`. |
| `P8-11` | Conditional open-source repository readiness (only if `OQ-02` decided) | **S14** | Grouped with S14 documentation/legal work; remains deferred/private until `OQ-02` is decided. |
| `P8-12` | Optional staging environment | **S02–S04** (parameterization), **S16** | `compose.prod.yml`, `Caddyfile`, deploy, and backup scripts are parameterized by env vars in S02–S04 so staging requires no forked files; live staging VM provisioning remains optional/external. |

### 6.2 Mapping the 6 Canonical Acceptance Criteria (`phase-08-hardening.md`)

| # | Canonical Acceptance Criterion (`docs/implementation/phases/phase-08-hardening.md`) | Implementing & Verifying Session(s) | Verification & Evidence Artifacts |
|---|---|---|---|
| **1** | **Fresh VPS to running HTTPS instance with documented commands. `/readyz` is green.** | **S02**, **S03**, **S16** | `Dockerfile`, `compose.prod.yml`, `Caddyfile`, `.github/workflows/deploy.yml`, `docs/operations/runbooks.md`; local/CI production container & `/readyz` smoke verification in S02–S03; live VPS HTTPS verification in S16. |
| **2** | **The restore drill succeeds and its measured RPO and RTO are recorded.** | **S04**, **S06**, **S16** | `scripts/backup*`, `scripts/restore*`, post-restore reconciliation command (`in_progress` -> `outcome_unknown` + tombstone re-application), `docs/operations/backup-restore.md`, and executed restore drill report with measured RPO/RTO in S04 (and post-RLS drill in S06 / live drill in S16). |
| **3** | **RLS tests pass. The isolation suite passes with RLS enabled.** | **S05**, **S06**, **S15**, **S16** | Alembic RLS migrations (`ENABLE` + `FORCE ROW LEVEL SECURITY` on all 49 Category C tables), `NOBYPASSRLS` runtime roles (`agentnest_app`, `agentnest_worker`), schema introspection test, and `tests/isolation/` passing with RLS enabled in S05–S06 and S15–S16. |
| **4** | **Security review findings are fixed or documented with accepted risk.** | **S15** (building on **S05–S13**) | `T1`–`T22` threat-model walk, `tests/security/`, `tests/isolation/`, `pip-audit`, `npm audit`, remediation commits, and documented residual risk register in `docs/implementation/phase-8-sessions/s15-report.md`. |
| **5** | **Legal artifacts are reviewed by counsel. `OQ-04`, `OQ-12` and `OQ-13` are resolved in `open-questions.md`.** | **S01**, **S12**, **S14**, **S16** | Configurable retention/grace implementation (S10, S12), legal artifact package in `docs/legal/` (S14), and external counsel review status tracked honestly in `docs/research/open-questions.md` and `s14-report.md` / `s16-report.md` (never marked resolved without actual counsel sign-off). |
| **6** | **The first pilot business is onboarded on production using the assisted onboarding checklist.** | **S16** | Assisted onboarding checklist (`docs/operations/pilot-onboarding.md`), App Review packet (`P8-10`), Gate 3 readiness package (`docs/implementation/phase-summaries/phase-08-summary.md`), and live pilot onboarding record once external prerequisites are met. |

### 6.3 Sequence Rationale & Departures from Canonical Task List

1. **Infrastructure & Backups (`P8-01`, `P8-02` in Sessions 02–04) before RLS (`P8-03` in Sessions 05–06):**
   - Container entrypoints, database initialization scripts, and backup/restore tooling must establish separated database roles (`agentnest_migrator`, `agentnest_app`, `agentnest_worker`) and post-restore reconciliation before RLS locks down table access.
2. **RLS Enforcement (`P8-03` in Sessions 05–06) before Auth, Email, Data-Rights, Retention & Alerts (`P8-04`–`P8-07` in Sessions 07–13):**
   - Every new table and query added in Sessions 07–13 (`password_reset_tokens`, `login_throttles`, export queries, erasure jobs, Meta callback lookups, retention sweeps, and alert evaluators) is built and tested directly under active `FORCE ROW LEVEL SECURITY` with `NOBYPASSRLS`, eliminating late retrofit regressions.
3. **Email Delivery (`P8-04` in Session 08) before Workspace Deletion (`P8-05` in Session 10) and Operator Alerts (`P8-07` in Session 13):**
   - Emailed invites, password resets, workspace deletion confirmation notices, and operator alert/recovery notifications all depend on the transactional SMTP email adapter and outbox contract introduced in Session 08.
4. **Data-Rights Services (`P8-05` in Sessions 09–10) before Meta Provider Callbacks (`P8-05` in Session 11):**
   - Meta's deauthorization and data-deletion callbacks (`Session 11`) delegate directly to the idempotent account-disconnect, customer-erasure, and confirmation-tracking services built and verified in Sessions 09–10.
5. **Explicit Session Granularity & Grouping vs `phase-08-hardening.md`:**
   - Multi-part tasks (`P8-01`, `P8-03`, `P8-04`, `P8-05`) are split into focused 1-session units (`S02–S03`, `S05–S06`, `S07–S08`, `S09–S11`) so each session has a bounded blast radius and independent verification gate.
   - Conditional `P8-11` (OSS readiness, gated on `OQ-02`) is grouped into **Session 14** alongside `P8-08` (legal/privacy documentation), and optional `P8-12` (staging environment) is satisfied structurally by env-parameterized compose/Caddy/deploy/backup files in **Sessions 02–04** with live staging/production verification tracked in **Session 16**.

---

## 7. Handoff to Session 02 (`P8-01`: Production Container Packaging, Compose Stack & Reverse Proxy)

- **Ready to start:** Session 02 (`docs/implementation/phase-8-sessions/phase-08-sessions.md` §Session 02).
- **Inputs locked by Session 01:**
  - Exact entrypoints to package in `Dockerfile`: FastAPI (`uvicorn app.main:app`), worker (`python -m app.worker`), CLI (`python -m app.cli`), migrations (`alembic upgrade head` against `backend/migrations`), and static SPA assets built from `frontend/dist`.
  - Health/readiness contracts: `/healthz` (liveness) and `/readyz` (DB connectivity + Alembic head `0030` match).
  - Security headers & proxy boundary: Caddy TLS termination + security headers (`Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Content-Security-Policy`) and `TRUSTED_PROXY_CIDRS` forwarding rules settled in `ADR-025`.
