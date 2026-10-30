# Backup, Media Protection & Restore Runbook

**Purpose:** Canonical operator runbook for nightly encrypted PostgreSQL backups, 35-day retention pruning, off-host key custody, media bucket protection, isolated database restoration, post-restore worker fencing, and deletion tombstone re-application (`P8-02`, `P8-03`, [ADR-025](../architecture/decisions/ADR-025-phase-8-hardening-contracts.md) §1.1, §3.3, §4.3).

---

## 1. Architecture & Backup Lifecycle Overview

```mermaid
flowchart LR
  pg[(PostgreSQL 16)] -->|pg_dump -Fc| bkp["scripts/backup.py<br/>AES-256-GCM (AGNBKP01)"]
  bkp -->|.dump.enc + .manifest.json| s3[(Off-site S3 Bucket<br/>35-day retention)]
  bkp -->|atomic write| status[".backup-status.json<br/>system_health (>26h alert)"]
  s3 -->|decrypt + verify SHA-256| rst["scripts/restore.py<br/>pg_restore + verify-db-roles"]
  rst -->|post-restore-reconcile| fence["Fence in_progress -> outcome_unknown<br/>Pause agents & revoke delegations<br/>Re-apply deletion tombstones"]
```

| Property | Canonical Contract |
|---|---|
| **Dump Format** | PostgreSQL custom format (`pg_dump --format=custom --no-owner --no-privileges`, magic header `PGDMP`) |
| **Encryption** | Authenticated `AES-256-GCM` (`AGNBKP01` binary envelope; canonical JSON header bound as GCM Additional Authenticated Data) |
| **Schedule** | Nightly at **02:00 UTC** (`0 2 * * *`) via host cron or systemd timer invoking `scripts/backup.sh` / `compose.prod.yml` `backup` service |
| **Retention** | **35 days** (`BACKUP_RETENTION_DAYS=35`, aligned with [security-and-privacy.md](../architecture/security-and-privacy.md) §8); expired archives are pruned **only after** a new backup is uploaded and verified |
| **Monitoring & Staleness** | Durable `.backup-status.json` heartbeat + `audit_logs` (`system.backup_succeeded` / `system.backup_failed`) read by `app.operations.system_health.backup_health()` with a **26-hour** staleness threshold (`ADR-025` §4.3) |

---

## 2. Encryption Key Custody & Off-Host Recovery

Production relies on two distinct key rings that **must** be backed up in an off-host password manager / secret vault (e.g., 1Password, Bitwarden, AWS Secrets Manager, or HashiCorp Vault) completely separate from the VPS:

1. **`BACKUP_ENCRYPTION_KEY`** (`id:urlsafe_base64_32_byte_key`, e.g. `b1:...`):
   - Encrypts and authenticates `.dump.enc` database archives.
   - Generate a fresh key with:
     ```bash
     python -m app.cli generate-key --kind backup-encryption --key-id b1
     ```
2. **`TOKEN_ENCRYPTION_KEYS`** (`id:urlsafe_base64_32_byte_key`, e.g. `k1:...`):
   - Encrypts connected Instagram `social_accounts.token_ciphertext` values stored inside PostgreSQL (`INV-10`).
   - Generate a fresh key with:
     ```bash
     python -m app.cli generate-key --kind token-encryption --key-id k1
     ```

> [!CAUTION]
> **Total VPS Loss Recovery Requirement:** Never store the sole copy of `BACKUP_ENCRYPTION_KEY` or `TOKEN_ENCRYPTION_KEYS` in `/opt/agentnest/.env` on the VPS. If the VPS disk is lost:
> - Without `BACKUP_ENCRYPTION_KEY`, off-site `.dump.enc` archives in S3 cannot be decrypted.
> - Without `TOKEN_ENCRYPTION_KEYS`, a restored database will have unreadable `social_accounts.token_ciphertext` values, forcing every connected workspace owner to re-authorize Instagram OAuth.
>
> **Key Rotation:** Both variables accept a comma-separated keyring (`b2:<new_key>,b1:<old_key>` with `BACKUP_ENCRYPTION_ACTIVE_KEY_ID=b2`). Retain retired keys in the keyring for at least **35 days** so all retained backups remain decryptable.

---

## 3. Off-Site S3 Backup Bucket & Media Bucket Protection

### 3.1 Least-Privilege Backup Bucket Credentials (`BACKUP_S3_*`)

Store database backups in a dedicated off-site bucket (`BACKUP_S3_BUCKET`) or isolated prefix (`BACKUP_S3_PREFIX=postgres/nightly`), ideally in a separate region or provider account from the VPS. Provision a dedicated IAM access key (`BACKUP_S3_ACCESS_KEY_ID` / `BACKUP_S3_SECRET_ACCESS_KEY`) scoped strictly to the backup bucket and prefix:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListBackupPrefixOnly",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::agentnest-backups",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["postgres/nightly/*"]
        }
      }
    },
    {
      "Sid": "ReadWriteDeleteBackupObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::agentnest-backups/postgres/nightly/*"
    }
  ]
}
```

- **Object Lock / Versioning Recommendation:** Enable S3 Object Versioning (and optional Governance-mode Object Lock for 7–14 days) on `agentnest-backups` so compromised host credentials cannot silently destroy recent restore points, with an S3 lifecycle rule expiring noncurrent versions after 35 days.

### 3.2 Media Bucket Protection (`S3_BUCKET`) & Cross-Store Consistency Limits

Workspace media assets (`media_assets` table) are stored as content-addressed objects in `S3_BUCKET` while their metadata rows (`storage_key`, `sha256`, `status`, `deleted_at`) live in PostgreSQL:

1. **Bucket Versioning & Lifecycle:** Enable S3 Versioning on `S3_BUCKET` with:
   - Noncurrent version expiration after **35 days** (matching database backup retention so any `media_assets` row present in a 35-day-old PostgreSQL backup still has its underlying object recoverable).
   - Abort incomplete multipart uploads after **7 days**.
   - Never grant public write or bucket-wide `s3:*` permissions to the runtime `S3_ACCESS_KEY_ID`.
2. **Consistency Limits Between PostgreSQL and Object Storage:**
   - A PostgreSQL `pg_dump -Fc` snapshot is point-in-time consistent across all relational tables, whereas S3 object storage is updated asynchronously around database commits.
   - **Case A — Object uploaded after DB snapshot, before disaster:** The S3 object exists in `S3_BUCKET`, but the restored PostgreSQL snapshot has no `media_assets` row for it. The orphaned object is harmless and inert; `media_cleanup` or lifecycle rules can reclaim unreferenced objects.
   - **Case B — Media deleted after DB snapshot, before disaster:** The restored PostgreSQL snapshot may show `media_assets.status = 'ready'` for an object that was deleted in S3 after the snapshot. If S3 Versioning is enabled (35-day noncurrent retention), the object version can be restored; otherwise, any content item referencing a missing S3 object is held (`status = 'on_hold'`) during post-restore inspection before publishing.

---

## 4. Nightly Backup Execution & Scheduling

### 4.1 Running a Backup Manually or via Docker Compose

```bash
# Host CLI (uses local pg_dump or --postgres-container)
./scripts/backup.sh \
  --output-dir /var/backups/agentnest \
  --s3-bucket agentnest-backups \
  --s3-prefix postgres/nightly \
  --status-file /opt/agentnest/.backup-status.json

# Or via the Compose backup profile in compose.prod.yml
docker compose -f compose.prod.yml --profile backup run --rm backup
```

### 4.2 Nightly Cron / Systemd Timer Configuration (`02:00 UTC`)

Install `/etc/cron.d/agentnest-backup` (owned by `root`, mode `0644`):

```cron
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# Run encrypted PostgreSQL backup nightly at 02:00 UTC and log output
0 2 * * * deploy cd /opt/agentnest && /opt/agentnest/scripts/backup.sh --postgres-container agentnest-postgres-1 >> /var/log/agentnest-backup.log 2>&1
```

### 4.3 Standalone Archive Inspection & Decryption

Any `.dump.enc` file can be authenticated and decrypted into a standard `pg_dump -Fc` file without restoring it:

```bash
python scripts/backup.py decrypt \
  --input /var/backups/agentnest/agentnest-20261030T020000Z.dump.enc \
  --manifest /var/backups/agentnest/agentnest-20261030T020000Z.manifest.json \
  --output /tmp/agentnest-decrypted.dump
```

---

## 5. Step-by-Step Restore Procedure & Post-Restore Reconciliation

> [!IMPORTANT]
> **Never start the `worker` container against a restored database before running `post-restore-reconcile`.** Restoring a backup from hours earlier may contain operations that were `in_progress`, reply drafts that were `sending`, active autonomous `account_agents`, or customer data that was erased after the snapshot was taken (`INV-05`, `INV-18`, `ADR-025` §3.3).

### Step 1 — Stop Runtime Containers (`api` and `worker`)

```bash
cd /opt/agentnest
docker compose -f compose.prod.yml stop worker api
```

### Step 2 — Prepare Tombstone Manifest for Post-Snapshot Erasures

If any customer, conversation, social account, or workspace deletion was processed after the backup snapshot timestamp (check operator deletion receipts or external audit trail), list them in `tombstones.json`:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-10-30T21:00:00Z",
  "workspaces": [],
  "social_accounts": [],
  "conversations": [],
  "customers": [
    {
      "workspace_id": "ee35983a-c2bb-4a23-9c20-caa4c1b06a7b",
      "social_account_id": "1957d846-7512-40d4-98e5-4d28b691021f",
      "external_customer_id": "cust-erased-202",
      "reason": "post_snapshot_gdpr_erasure"
    }
  ]
}
```

### Step 3 — Run `scripts/restore.sh` into a Fresh Isolated Database

`scripts/restore.py` refuses to overwrite a non-empty database unless `--allow-overwrite-disposable` is explicitly passed. Always restore into a fresh database (e.g. `agentnest_restored_<date>`), verify it, and then point `DATABASE_URL` / `MIGRATION_DATABASE_URL` to the verified database:

```bash
./scripts/restore.sh \
  --archive /var/backups/agentnest/agentnest-20261030T020000Z.dump.enc \
  --manifest /var/backups/agentnest/agentnest-20261030T020000Z.manifest.json \
  --target-database-url "postgresql://postgres:${POSTGRES_PASSWORD}@127.0.0.1:5432/agentnest_restored" \
  --create-target-db \
  --postgres-container agentnest-postgres-1 \
  --migrator-role agentnest_migrator \
  --runtime-roles agentnest_app,agentnest_worker \
  --tombstone-manifest /var/backups/agentnest/tombstones.json
```

`scripts/restore.sh` automatically performs:
1. **Target DB emptiness check:** Refuses non-empty targets unless `--allow-overwrite-disposable` is set.
2. **Cryptographic verification:** Verifies `.manifest.json` ciphertext SHA-256 and decrypts the `AGNBKP01` AES-256-GCM envelope (authenticating header metadata AAD and plaintext `PGDMP` SHA-256).
3. **`pg_restore`:** Restores schema and data with `--no-owner --no-privileges --role=agentnest_migrator --exit-on-error`.
4. **Schema & Role Verification (`verify-db-roles`):** Verifies `alembic_version` equals `migration_head()` (`0030`), checks public table counts, provisions/verifies `agentnest_migrator` ownership, confirms `agentnest_app` and `agentnest_worker` have `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`, and verifies `REVOKE UPDATE, DELETE` on append-only `audit_logs` and `fact_versions`.
5. **Post-Restore Worker Fencing & Tombstone Re-Application (`post-restore-reconcile`):**
   - Pauses all `account_agents` (`state = 'paused'`, bumping `controller_epoch` and `config_version`) and revokes all active `agent_delegations` (`revoked_at = now()`).
   - Transitions all `in_progress` `operations` to `outcome_unknown` (`last_error_code = 'RESTORED_FROM_BACKUP_OUTCOME_UNKNOWN'`) and all `sending` `reply_drafts` to `outcome_unknown`, enqueuing `reconcile_send` / `reconcile_publish` jobs so no ambiguous outbound message or post is ever blindly re-sent (`INV-05`).
   - Places any `publishing` or past-due scheduled `content_items` into `on_hold` (`hold_reason = 'RESTORED_FROM_BACKUP'`).
   - Cancels active `agent_sessions` and `agent_threads`, abandons in-flight `agent_steps`, cancels queued outbound jobs (`send_reply`, `publish_content`, `agent_wake`, `agent_continue`, `agent_wake_due`), and releases stale `running` job leases on idempotent jobs.
   - Re-applies all customer, conversation, social-account, and workspace erasures from `--tombstone-manifest` (and `deletion_tombstones` if present), scrubbing `messages`, `reply_drafts`, `conversations`, `customer_memories`, `owner_questions`, `public_comments`, and `inbound_events.payload`, and incrementing `customer_identities.generation`.
   - Records `system.post_restore_reconciled` in `audit_logs`.

> [!TIP]
> You can also run role verification and post-restore reconciliation directly via `app.cli`:
> ```bash
> python -m app.cli verify-db-roles --provision
> python -m app.cli post-restore-reconcile --tombstone-manifest /path/to/tombstones.json
> ```

### Step 4 — Post-Restore Operator Inspection Checklist (Before Starting Workers)

Before starting `api` and `worker` or unpausing any workspace agent, verify:

- [ ] `restore.py` exited `0` with `"verified": true` under `role_verification` and `alembic_revision` matching `expected_alembic_revision`.
- [ ] All post-snapshot erased customers/conversations/accounts in `tombstones.json` are confirmed absent from `conversations`, `messages`, and `customer_memories`.
- [ ] Start `api` first (`docker compose -f compose.prod.yml up -d api caddy`) and verify `GET /readyz` returns `200 {"status": "ok", "checks": {"database": true, "migrations": true}}`.
- [ ] Start `worker` (`docker compose -f compose.prod.yml up -d worker`) so enqueued `reconcile_send` / `reconcile_publish` jobs reconcile any `outcome_unknown` operations against the provider before human review.
- [ ] Inspect any remaining `outcome_unknown` operations and `on_hold` content items in the operator UI.
- [ ] Re-grant delegation and unpause `account_agents` per workspace only after confirming inbox and operation states.

---

## 6. Executed Restore Drill Record (2026-10-30)

An end-to-end backup, tamper-rejection, isolated restore, role-verification, worker-fencing, and tombstone re-application drill was executed on **2026-10-30** against a disposable PostgreSQL 16 container (`agentnest-s04-drill`, schema revision `0030`, 59 public tables).

### 6.1 Measured RPO, RTO & Archive Metrics

| Metric | Measured Drill Value | Production Target / Threshold |
|---|---|---|
| **Backup Archive ID** | `agentnest-20261030T212245Z-s04-drill` | `agentnest-<YYYYMMDDTHHMMSSZ>` |
| **Alembic Schema Revision** | `0030` (59 public tables) | `0030` (`migration_head()`) |
| **Plaintext `pg_dump -Fc` Size** | `279,616` bytes (`273.1 KiB`) | Proportional to DB size |
| **Plaintext SHA-256** | `50eeedd18e1e3e91e0644a43731b1201cb44b81b51b16ec5910506550f310c92` | Verified on decrypt |
| **Encrypted `.dump.enc` Size** | `279,976` bytes (`273.4 KiB`) | `AGNBKP01` AES-256-GCM envelope |
| **Ciphertext SHA-256** | `e7b6eded1ef04da3c24c23d5c033ee871388ecebc3281b578e39bb9a3b35b99e` | Verified against `.manifest.json` |
| **Backup Creation Duration** | `0.250s` | `< 60s` for pilot data volumes |
| **Measured Snapshot Age (Drill RPO)** | `2.364s` (`2026-10-30T21:22:45.077Z` -> `21:22:47.441Z`) | Nightly RPO ceiling `< 24h` (`> 26h` alert per `ADR-025` §4.3) |
| **Measured Restore + Reconcile Duration (Drill RTO)** | `1.406s` (decrypt + `pg_restore` + role grants + `post-restore-reconcile`) | Target RTO `< 15m` |

### 6.2 Drill Verification Outcomes

1. **Unreadable Without Decryption:** Running `pg_restore --list` directly on `agentnest-20261030T212245Z-s04-drill.dump.enc` exited non-zero (`pg_restore: error: input file does not appear to be a valid archive`).
2. **Authenticated Encryption Tamper Rejection:** Flipping 1 byte of ciphertext or 1 byte of the authenticated JSON header raised `BackupTamperedError` (`AES-256-GCM authentication tag verification failed`).
3. **Non-Empty Target DB Protection:** Attempting to restore into the populated source database `agentnest_drill_src` without `--allow-overwrite-disposable` was refused (`Target database 'agentnest_drill_src' is not empty (59 tables found)`).
4. **Restored Data Integrity:** Restored into fresh isolated database `agentnest_restored_drill`; verified workspace `golkent-pilates-drill`, verified business fact `pricing.monthly_reformer` (`4500 TRY`) and `fact_versions`, kept conversation (`ayse_wellness`), and `media_assets` reference (`workspaces/<ws_id>/media/reformer-schedule-2026.jpg`).
5. **Post-Restore Worker Fencing:**
   - `in_progress` `send_reply` operation transitioned to `outcome_unknown` (`last_error_code = 'RESTORED_FROM_BACKUP_OUTCOME_UNKNOWN'`) and `reconcile_send` job enqueued (`enqueued_reconcile_jobs = 1`).
   - `sending` `ReplyDraft` transitioned to `outcome_unknown` (`fenced_reply_drafts = 1`).
   - Active `AccountAgent` paused (`state = 'paused'`, `paused_account_agents = 1`) and active `AgentDelegation` revoked (`revoked_agent_delegations = 1`).
   - Active `AgentSession` (`cancelled_agent_sessions = 1`), `AgentThread` (`cancelled_agent_threads = 1`), `AgentStep` (`abandoned_agent_steps = 1`), and queued `send_reply` job (`cancelled_outbound_jobs = 1`) fenced.
6. **Post-Snapshot Tombstone Re-Application:** Customer `cust-erased-202` from `tombstones.json` (`reapplied_customer_tombstones = 1`) had its `Conversation`, `Message`, and `CustomerMemory` rows purged, `InboundEvent.payload` nulled, and `CustomerIdentity.generation` incremented before workers could start.
7. **Least-Privilege Runtime Role Enforcement:** Connected directly as `agentnest_app` (`NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`) and verified `SELECT` on `audit_logs` succeeded while `DELETE FROM audit_logs` and `UPDATE fact_versions` failed with `psycopg.errors.InsufficientPrivilege`.
