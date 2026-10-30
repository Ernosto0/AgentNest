# ADR-025: Phase 8 Production Hardening Contracts (RLS Runtime Boundary, Auth/Email, Data Rights, and Alerting)

- **Status:** Accepted
- **Date:** 2026-10-30
- **Deciders:** Engineering Lead
- **Technical Story:** Phase 8 Session 01 (`P8-01` through `P8-12` contract alignment before Sessions 02–16 implementation)

---

## Context and Problem Statement

Phase 8 hardens AgentNest for multi-tenant production operations (`docs/implementation/phases/phase-08-hardening.md`). Following Phase 7.5, the schema contains **58 application tables** across 18 model modules (plus `alembic_version`, **59 database tables total**), including the Phase 7.5 account-agent, customer-memory, owner-request, and public-comment tables introduced in migrations `0021`–`0030`.

Before implementing Sessions 02–16, five cross-cutting architectural contracts must be settled explicitly so later sessions do not invent ad-hoc bypasses or break invariants (`INV-01` through `INV-20`):

1. **PostgreSQL Row-Level Security (RLS) and pre-context bootstrap (`P8-03`):** How non-bypass runtime database roles enforce `FORCE ROW LEVEL SECURITY` on tenant tables while still permitting pre-workspace authentication, membership discovery, invite/OAuth token resolution, webhook signature/account ingestion, and global worker job claiming/sweeps without granting `BYPASSRLS`.
2. **Authentication hardening and transactional email delivery (`P8-04` / `OQ-16`):** How login throttling, active session management, password change/reset invalidation, and SMTP email delivery work without leaking account existence or persisting raw tokens/PII in job payloads.
3. **Data-rights export, erasure, workspace deletion grace period, and reconciliation exceptions (`P8-05`):** How owner-initiated conversation/customer export and erasure, 7-day workspace deletion grace/cancellation, in-flight operation reconciliation guards (`INV-05`), and backup-restore tombstones (`P8-02`) interact with append-only audit/fact-history tables (`ADR-022`) and Phase 7.5 records (`ADR-024`).
4. **Meta deauthorization and data-deletion callbacks (`P8-05` / `V-06`):** How Meta's `signed_request` callbacks verify authenticity, map provider identity server-side (`INV-01`), enqueue idempotent deletion/disconnect work, and expose a privacy-preserving confirmation status page while keeping unverified live payload shapes (`V-06`) provisional.
5. **Retention expansion, token key rotation, and operator alerting (`P8-06`, `P8-07`):** How `run_retention_cleanup` extends to Phase 7.5 tables under provisional legal periods (`OQ-12`), how `TOKEN_ENCRYPTION_KEYS` rotates ciphertexts in place, and how operator alerts deduplicate, cool down, and emit recovery notices.

---

## Decision Outcome

### 1. Database Roles, Table Classification, and RLS Bootstrap Contract (`P8-03` / Sessions 05–06)

#### 1.1 Database Role Separation

Production and test PostgreSQL environments separate schema migration authority from runtime execution:

| Role | Privileges | Purpose |
|---|---|---|
| `agentnest_migrator` | Schema/table owner; DDL authority; used by Alembic (`alembic upgrade head`) | Creates/alters tables, indexes, RLS policies, and tightly scoped `SECURITY DEFINER` bootstrap functions. |
| `agentnest_app` | `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`; DML (`SELECT, INSERT, UPDATE, DELETE`) on application tables except append-only restrictions | Default runtime role for FastAPI (`DATABASE_URL`). Subject to all RLS policies. |
| `agentnest_worker` | `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS` (or shares `agentnest_app` role with identical RLS enforcement) | Runtime role for background worker. Must never rely on `BYPASSRLS`; uses explicit transaction-scoped GUC binding (`SET LOCAL app.workspace_id = '<uuid>'`) or audited `SECURITY DEFINER` bootstrap helpers. |

**Append-only table privilege restriction (`INV-06`, `INV-07`, `ADR-022`):**
- On `audit_logs` and `fact_versions`, `REVOKE UPDATE, DELETE` is enforced for `agentnest_app` and `agentnest_worker`. Only `SELECT` and `INSERT` are granted at runtime.

#### 1.2 Tenant Context GUC and Session Lifecycle

- Every tenant-scoped transaction binds `SET LOCAL app.workspace_id = '<workspace_uuid>'` inside the active SQLAlchemy transaction (`SET LOCAL` scopes the setting to the current transaction and automatically resets on `COMMIT`/`ROLLBACK`, preventing connection-pool bleed).
- Tenant RLS policies evaluate:
  ```sql
  workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid
  ```
- When `app.workspace_id` is unset or empty (`''`), `nullif(..., '')::uuid` evaluates to `NULL`, and `workspace_id = NULL` evaluates to `UNKNOWN` (`false`), causing direct table queries on strictly tenant-scoped tables to return **zero rows** (reads) and fail check constraints (writes) by default.

#### 1.3 Complete Table Classification (59 Tables Total)

All 58 SQLAlchemy-mapped tables (plus `alembic_version`) are classified into three RLS categories:

1. **Category A — Global / Identity Root Tables (4 tables; no `workspace_id`, no tenant RLS):**
   - `alembic_version` (read-only to runtime for `/readyz`; owned by `agentnest_migrator`)
   - `users` (`identity/models.py`)
   - `sessions` (`identity/models.py` — `AuthSession`)
   - `workspaces` (`identity/models.py` — tenant root table; `id` is the workspace UUID)
   - *Plus Phase 8 global auth tables added in Sessions 07–08:* `password_reset_tokens` (user-scoped, no `workspace_id`) and `login_throttles` (keyed by IP/email hash, no `workspace_id`).

2. **Category B — Hybrid / Cross-Boundary Bootstrap & System Tables (6 existing tables + Phase 8 system tables):**
   - `workspace_members` (`workspace_id`, `user_id` PK): Needs pre-context lookup by `user_id` during login/workspace listing (`GET /workspaces`) and by `(workspace_id, user_id)` when resolving `WorkspaceContext`, as well as tenant-scoped member listing/management once `app.workspace_id` is set.
   - `invites` (`workspace_id NOT NULL`, unique `token_hash`): Needs pre-context lookup by `token_hash` during `POST /auth/invites/accept` before the caller knows `workspace_id`, and tenant-scoped CRUD when `app.workspace_id` is set.
   - `oauth_states` (`workspace_id NOT NULL`, unique `state_hash`): Needs pre-context lookup/consumption by `state_hash` during Meta OAuth callback (`GET /oauth/instagram/callback`) before `workspace_id` is known.
   - `inbound_events` (`workspace_id NULL`, `social_account_id NULL`, unique `dedup_key`): Written during webhook ingestion before a workspace context exists (`UNKNOWN_ACCOUNT` events have `workspace_id IS NULL`); read/updated by `process_inbound_event` under tenant context and swept by `retention_cleanup`.
   - `audit_logs` (`workspace_id NULL`, insert-only): Accepts system-level events with `workspace_id IS NULL` (`auth.login`, `auth.login_failed`, `webhook.signature_invalid`, `retention.cleanup_ran`) and workspace-scoped events (`workspace_id = current_setting('app.workspace_id')`). Reads require matching `app.workspace_id` (or system health/test harness scope).
   - `jobs` (`workspace_id NULL`): Claimed globally by the worker (`FOR UPDATE SKIP LOCKED`) across due jobs (`workspace_id IS NULL` for periodic/system jobs, or `workspace_id = <uuid>` for tenant jobs). Once a job with `job.workspace_id IS NOT NULL` is claimed, the worker binds `SET LOCAL app.workspace_id = '<job.workspace_id>'` on every session opened via `job.session_factory()`.
   - *Phase 8 additions in this category:* `deletion_tombstones`, `data_deletion_requests` (keyed by confirmation code for Meta callbacks and backup-restore fencing), and `operator_alert_states` (durable alert deduplication/cooldown table).

3. **Category C — Strictly Tenant-Scoped Tables (49 existing tables; `workspace_id NOT NULL`, `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`):**
   - **Core & Knowledge (5):** `business_facts`, `fact_versions` (insert-only), `fact_candidates`, `fact_references`, `approved_answers`
   - **Commands, AI, Approvals, Policy (4):** `owner_commands`, `agent_runs`, `approvals`, `automation_policies`
   - **Integrations, Inbox, Content, Operations, Notifications, Reporting (11):** `social_accounts`, `conversations`, `messages`, `reply_drafts`, `media_assets`, `content_items`, `operations`, `notifications`, `daily_reports`, `report_items`, `report_source_gaps`
   - **Simulator Tables (8):** `sim_inbound_messages`, `sim_sent_messages`, `sim_failure_rules`, `sim_containers`, `sim_published_media`, `sim_public_comments`, `sim_comment_effects`, `sim_private_replies`
   - **Phase 7.5 Account Agent, Customer Memory, Owner Requests & Public Comments (21):**
     - Agent runtime (8): `account_agents`, `agent_delegations`, `agent_threads`, `agent_owner_tasks`, `agent_events`, `agent_sessions`, `agent_steps`, `agent_actions`
     - Customer memory (6): `customer_identities`, `customer_source_fences`, `customer_memories`, `customer_memory_versions`, `customer_memory_sources`, `customer_summary_versions`
     - Owner requests (2): `owner_questions`, `owner_answers`
     - Public comments (5): `public_media`, `public_threads`, `public_comments`, `public_comment_actions`, `private_reply_opportunities`
     *(Category C total: 5 + 4 + 11 + 8 + 21 = **49 strictly tenant-scoped tables**; Grand total: 4 + 6 + 49 = **59 database tables**.)*

#### 1.4 Pre-Context Bootstrap Mechanisms (Without `BYPASSRLS`)

Where an operation legitimately needs to resolve `workspace_id` or discover due work across workspaces before `app.workspace_id` is known, it must use one of two explicit, auditable mechanisms:

1. **Narrow `SECURITY DEFINER` SQL lookup functions (owned by `agentnest_migrator`, `search_path = public, pg_temp`, granted `EXECUTE` to runtime roles):**
   - **Webhook account resolution:** `resolve_social_account_by_external(p_provider_kind text, p_external_account_id text)` returns only `(id, workspace_id, status)` from `social_accounts`. The webhook router/ingestor then binds `SET LOCAL app.workspace_id` for that workspace before touching any tenant rows.
   - **Invite & OAuth state resolution:** Either `invites` / `oauth_states` use a `SECURITY DEFINER` lookup by `token_hash` / `state_hash` returning `workspace_id`, or a dual RLS policy permitting `workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid` alongside hash-bound lookup. Using narrow `SECURITY DEFINER` functions keeps table RLS policies strictly keyed on `app.workspace_id`.
   - **Periodic job discovery sweeps:** Global periodic jobs (`workspace_id IS NULL`) that scan across workspaces (`refresh_tokens`, `enqueue_health_checks`, `reconcile_stuck_operations`, `agent_recover`, `expire_approvals`, `expire_reply_drafts`, `expire_commands`, `sweep_agent_runs`, `retention_cleanup`, `media_cleanup`) either:
     - Query `workspaces` (Category A, global) to iterate active `workspace_id`s and bind `SET LOCAL app.workspace_id = '<ws_id>'` per workspace batch, **or**
     - Call a read-only `SECURITY DEFINER` discovery function returning `(workspace_id, target_id)` pairs, then process each target inside a transaction with `SET LOCAL app.workspace_id = '<workspace_id>'`.
     Iterating active workspaces or `(workspace_id, id)` pairs and executing all mutations inside per-workspace transactions with `app.workspace_id` set guarantees that **every mutation on a Category C table runs under active tenant RLS**.

---

### 2. Authentication Hardening and Email Delivery Contract (`P8-04` / `OQ-16` / Sessions 07–08)

1. **Login Throttling:**
   - Enforced on both normalized email (`lower(trim(email))`) and client IP.
   - Client IP is read from `request.client.host` by default; `X-Forwarded-For` is honored **only** when the immediate peer IP is in configured `TRUSTED_PROXY_CIDRS` (preventing header spoofing).
   - Threshold: 5 failed attempts within 15 minutes triggers exponential lockout (`60s`, `300s`, `900s`, `3600s` cap) returning `429 RATE_LIMITED` with `Retry-After` and recording `auth.login_throttled` in `audit_logs`.
2. **Session Management & Password Lifecycle:**
   - `GET /api/v1/auth/sessions` lists active (non-revoked, non-expired) sessions for the current user (`id`, `created_at`, `last_seen_at`, `expires_at`, `user_agent`, `ip_address`, `is_current`) and never exposes `token_hash` or raw tokens.
   - `DELETE /api/v1/auth/sessions/{session_id}` revokes one session owned by the caller; `POST /api/v1/auth/sessions/revoke-all` revokes all other active sessions (keeping current session unless `include_current=true`).
   - `POST /api/v1/auth/password` verifies `current_password`, enforces minimum length (≥ 12 chars), hashes with Argon2id, updates `users.password_hash`, and revokes all other sessions for that user in the same transaction.
3. **Password Reset & Transactional Email:**
   - `password_reset_tokens` stores only `token_hash` (SHA-256 of high-entropy random token), `user_id`, `expires_at` (default 60 minutes), `used_at`, and `created_at`. Requesting a new token invalidates prior unused tokens for that user.
   - `POST /api/v1/auth/password-reset/request` always returns `202 Accepted` regardless of whether the email exists (preventing account enumeration).
   - `POST /api/v1/auth/password-reset/confirm` consumes the token atomically (`used_at IS NULL AND expires_at > now()`), updates `password_hash`, and revokes **all** existing `sessions` for that user.
   - **Privacy in jobs (`ADR-022`):** Email delivery jobs (`send_transactional_email`) never store raw password-reset or invite URLs/tokens in `jobs.payload`. Instead, invite/reset token generation sends via the configured email adapter or stores only an encrypted/ephemeral outbox reference that is wiped immediately upon send.

---

### 3. Data-Rights Export, Erasure, Workspace Deletion, and Meta Callbacks (`P8-05` / Sessions 09–11)

#### 3.1 Conversation & Customer Export (`data.export`, Owner-Only)

- **Endpoints:**
  - `GET /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/export`
  - `GET /api/v1/workspaces/{workspace_id}/customers/{customer_identity_id}/export` (or by `(social_account_id, external_participant_id)`)
- **Authorization:** Requires `data.export` permission (Owner only per `ADR-013`). Cross-workspace or unlinked records return `404`.
- **Format (`schema_version: "1.0"` JSON):**
  - Includes: workspace/account metadata (internal IDs and public handles, never access tokens), conversation record, chronological `messages` (with redacted/delivery metadata), `reply_drafts` and `approvals` summaries, `operations` history (status/timestamps/error codes without provider secrets), `customer_identities`, active `customer_memories`, `customer_memory_versions`, `customer_summary_versions` (via `memory.service.export_customer`), `owner_questions`/`owner_answers` tied to that customer/thread, and `public_comments`/`public_threads` **only** where linked by provider-evidenced `external_author_id == external_participant_id` on the same `social_account_id` (`INV-18`).
  - Excludes: `social_accounts.access_token_ciphertext`, webhook signatures, internal prompt templates, other customers' comments in the same public thread, and system-internal dedup keys.
  - Emits `data_rights.customer_exported` or `data_rights.conversation_exported` in `audit_logs`.

#### 3.2 Conversation & Customer Erasure (`data.delete`, Owner-Only)

- **Scope:** Erases or tombstones personal data across:
  1. `conversations`, `messages`, `reply_drafts`
  2. `customer_identities`, `customer_memories`, `customer_memory_versions`, `customer_memory_sources`, `customer_summary_versions`, `customer_source_fences` (advancing `erased_through_at` via `memory.service.erase_customer` so in-flight model turns cannot repopulate memory — `INV-18`)
  3. `agent_threads`, `agent_events`, `agent_sessions`, `agent_steps`, `agent_actions`, `agent_owner_tasks`
  4. `owner_questions`, `owner_answers` (redacting customer PII via `owner_requests.service.redact`)
  5. `public_comments`, `public_comment_actions`, `private_reply_opportunities`, `public_threads` (where authored by the customer, via `comments.privacy`)
  6. `inbound_events` (scrubbing `payload_json` associated with the participant/conversation)
  7. Customer-specific `media_assets` stored in `MediaStorage` (deleted outside the DB transaction after recording deletion intent).
- **Reconciliation & Ledger Preservation Guard (`INV-05`, `ADR-022`):**
  - If the conversation/customer has an `operations` row in `in_progress` or `outcome_unknown` (or a `reply_drafts` row in `sending` / `outcome_unknown`), erasure **redacts** personal text (`messages.text`, `reply_drafts.draft_text`, `operations.provider_ref` text fields) immediately and advances the memory fence, while preserving the minimal `operations` state-machine keys (`id`, `workspace_id`, `social_account_id`, `operation_type`, `status`, `idempotency_key`, `provider_ref.message_id` / `text_sha256`, `correlation_id`) until reconciliation concludes (`succeeded` or `failed`), or defers final row purge via `delete_customer_data` job until `unresolved == false`.
  - Append-only `audit_logs` and `fact_versions` are **never** deleted (`INV-06`, `INV-07`); `ADR-022` guarantees they store no raw customer PII.

#### 3.3 Workspace Deletion Lifecycle (7-Day Grace Period & Backup-Restore Fencing)

- **Request (`POST /api/v1/workspaces/{workspace_id}/delete-request`, Owner-only):**
  - Transitions `workspaces.status` from `'active'` to `'deleting'`.
  - Sets `deletion_requested_at = now()`, `deletion_scheduled_at = now() + 7 days`, `deletion_requested_by = user.id` (provisional 7-day grace period per `ADR-013` / `OQ-12`).
  - Immediately pauses all outbound automation: `account_agents.operating_mode -> 'paused'`, revokes active `agent_delegations`, cancels `pending`/`queued` `reply_drafts`, `approvals`, `content_items` (`scheduled` -> `cancelled`), and disconnects/stops token refresh while preserving in-flight `in_progress`/`outcome_unknown` reconciliation jobs until settled.
  - Queues confirmation email to all workspace owners (`workspace.deletion_requested` audit event).
- **Cancellation (`POST /api/v1/workspaces/{workspace_id}/cancel-deletion`, Owner-only):**
  - Permitted only while `workspaces.status == 'deleting'` and `now() < deletion_scheduled_at` (before the hard-purge job claims the workspace).
  - Restores `workspaces.status = 'active'`, clears `deletion_requested_at` / `deletion_scheduled_at`, and records `workspace.deletion_cancelled` in `audit_logs`. Connected accounts remain paused/disconnected until explicitly re-enabled by the owner.
- **Hard Purge (`purge_deleted_workspace` job after `deletion_scheduled_at`):**
  - Verifies no `operations` remain in `in_progress` (if stuck > 15m, transitions to `outcome_unknown` and reconciles/terminates first).
  - Enumerates all `media_assets.storage_key` values for the workspace, deletes the objects from `MediaStorage` (`LocalMediaStorage` / `S3MediaStorage`) outside the DB lock, then deletes all Category C and workspace-scoped Category B rows and finally the `workspaces` row.
  - Writes a durable tombstone in `deletion_tombstones` (`entity_type`, `entity_id`, `workspace_id`, `purged_at`) and an `audit_logs` entry (`workspace.purged`, `workspace_id` retained as UUID without FK).
- **Backup-Restore Fencing:**
  - The post-restore reconciliation procedure (`scripts/restore-reconcile` / CLI command) checks `deletion_tombstones` (or external tombstone manifest) and immediately re-applies any workspace/customer deletions that occurred after the backup snapshot timestamp, while marking any restored `in_progress`/`sending` operations as `outcome_unknown` so a restored backup never re-sends stale replies (`INV-05`) or resurrects erased personal data.

#### 3.4 Meta Deauthorization and Data-Deletion Callbacks (`V-06` Provisional)

- **Endpoints:**
  - `POST /api/v1/webhooks/meta/deauthorize`
  - `POST /api/v1/webhooks/meta/data-deletion`
  - `GET /api/v1/webhooks/meta/data-deletion/{confirmation_code}`
- **Verification & Security (`INV-01`):**
  - Parses Meta `signed_request` (`<base64url_signature>.<base64url_payload>`), verifies HMAC-SHA256 using `META_APP_SECRET` (or `MOCK_INSTAGRAM_APP_SECRET` for simulator namespace), validates `algorithm == "HMAC-SHA256"`, and extracts `user_id` / `app_scoped_user_id`.
  - Invalid signatures or malformed payloads return `400`/`401` and log `webhook.signature_invalid` in `audit_logs` without mutating state.
  - Resolves target `social_accounts` / customer identity strictly from server-owned mappings.
- **Privacy-Safe Confirmation Status:**
  - `POST /api/v1/webhooks/meta/data-deletion` creates a durable `data_deletion_requests` record with a random opaque `confirmation_code`, enqueues idempotent erasure, and returns `{"url": "<APP_BASE_URL>/api/v1/webhooks/meta/data-deletion/<code>", "confirmation_code": "<code>"}`.
  - `GET /api/v1/webhooks/meta/data-deletion/{confirmation_code}` returns **only** opaque status metadata (`confirmation_code`, `status` in `pending | in_progress | completed | not_found_or_already_erased`, `requested_at`, `completed_at`). It **never** echoes IG usernames, external IDs, workspace names, or message contents.
  - Live Meta payload specifics remain tagged provisional under `V-06` until verified in a live Meta App dashboard during Session 16 (`P8-10` / Gate 3).

---

### 4. Retention Expansion, Token Key Rotation, and Operator Alerting (`P8-06`, `P8-07` / Sessions 12–13)

1. **Retention Coverage for Phase 7.5 Tables (`P8-06`):**
   - `run_retention_cleanup` is extended so every retention-governed table in `ADR-022` and `ADR-024` is swept in bounded batches under explicit per-workspace RLS context:
     - `owner_questions` & `owner_answers` (redacted after `RETENTION_MESSAGE_TEXT_DAYS`, default 180d provisional)
     - `agent_owner_tasks` (resolved/cancelled tasks redacted/purged after `RETENTION_MESSAGE_TEXT_DAYS`)
     - `agent_events`, `agent_steps`, `agent_actions`, `agent_sessions` (raw input/tool payloads scrubbed after `RETENTION_AGENT_INPUT_DAYS`, default 90d provisional, preserving step/action state ledger)
     - `customer_memories`, `customer_memory_versions`, `customer_summary_versions` (invoking `memory.service.retention_batch` after `RETENTION_CUSTOMER_MEMORY_DAYS`, default 180d provisional)
     - `public_comments`, `public_comment_actions`, `public_media` (invoking `comments.privacy.retention_batch` after `RETENTION_MESSAGE_TEXT_DAYS` / `RETENTION_PUBLISHED_MEDIA_DAYS`)
   - All retention periods remain configurable via `RETENTION_*` env vars and explicitly marked **provisional** pending legal counsel sign-off (`OQ-12`).
   - `audit_logs` remain append-only with no runtime `DELETE` privilege; automated 730-day audit purging is deferred unless a separate privileged maintenance procedure is approved after legal review (`OQ-12`).
2. **Token Encryption Key Rotation (`P8-06`):**
   - `rotate_token_keys` job scans `social_accounts` where `access_token_ciphertext IS NOT NULL AND token_key_id != settings.token_encryption_active_key_id`, decrypts with the old key from `TOKEN_ENCRYPTION_KEYS` using `(workspace_id, social_account_id)` AAD, re-encrypts with `TOKEN_ENCRYPTION_ACTIVE_KEY_ID`, and records `security.token_key_rotated` in `audit_logs` without ever logging plaintext tokens (`INV-08`).
3. **Operator Alerting (`P8-07`):**
   - Evaluates 8 canonical conditions with durable state tracking (`operator_alert_states`: `alert_key`, `status`, `first_triggered_at`, `last_notified_at`, `resolved_at`, `cooldown_until`):
     1. Dead job (`jobs.status == 'dead'`, immediate per-job-type key, 1h cooldown)
     2. Backup failure / stale backup heartbeat (> 26h since last successful backup marker, 6h cooldown)
     3. Webhook signature failure burst (≥ 10 `webhook.signature_invalid` audit events in 1 hour, 1h cooldown)
     4. Connected account stuck in `needs_reauth` > 24 hours (per-account key, 24h cooldown)
     5. Account-agent dead wake or stuck recovery (`agent_wake` dead or `agent_sessions` stuck > 30m, 1h cooldown)
     6. Unresolved `outcome_unknown` operations (`operations.status == 'outcome_unknown'` older than reconciliation window, 2h cooldown)
     7. Capability loss (`social_accounts` capability downgrade / permission revoked on connected account, 6h cooldown)
     8. AI budget exhaustion / circuit open (`account_agents` daily budget exhausted or LLM provider circuit open, 6h cooldown)
   - Emits a recovery notice when an active alert condition clears (`status: firing -> resolved`).

---

## Consequences

- **Positive:**
  - Every Category C table (including all 21 Phase 7.5 tables) receives database-enforced `FORCE ROW LEVEL SECURITY` under non-bypass runtime roles (`INV-01`, `P8-03`).
  - Pre-context operations (login, invite acceptance, OAuth callback, webhook ingestion, worker job claiming, and periodic sweeps) have explicit, narrow contracts rather than ad-hoc RLS bypasses.
  - Data-rights erasure, workspace deletion, and backup restore respect `INV-05` (no blind retry of `in_progress`/`outcome_unknown` operations), `INV-06`/`INV-07` (append-only `audit_logs` and `fact_versions`), and `INV-18` (customer source fences and provider-evidenced linkage).
  - Packaging, compose, Caddy, deploy, and backup artifacts (`P8-01`, `P8-02`) are parameterized by environment variables so an optional staging environment (`P8-12`) can run with separate hostname, credentials, and database without maintaining forked deployment files.
- **Trade-offs / Risks:**
  - Any new tenant table added in future migrations must include `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`; Session 06 will enforce this with an automated schema introspection test over `Base.metadata.tables`.
  - Open questions `OQ-02` (open-source core license gating conditional `P8-11`), `OQ-03` (Standard vs Advanced Access for pilot businesses, `V-01`), `OQ-04` (hosting region & KVKK cross-border transfer basis), `OQ-05` (legal entity for Meta Business Verification and DPAs), `OQ-09` (LLM model/cost per workspace), `OQ-12` (data retention periods), `OQ-13` (automation disclosure in Türkiye), `OQ-16` (SMTP provider selection), and live Meta callback verification (`V-06`) remain tracked external/counsel dependencies across Sessions 08, 12, and 14–16.
