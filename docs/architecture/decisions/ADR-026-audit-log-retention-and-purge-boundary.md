# ADR-026: Audit Log Retention, Privileged Purge Boundary, and Backup-Reconciled Erasure

- **Status:** Accepted
- **Date:** 2026-11-03
- **Deciders:** Engineering Lead
- **Technical Story:** Phase 8 Session 12 (`P8-06` retention expansion, key rotation, and dependency auditing; settling ADR-022 and ADR-025 §4 audit-purge boundary)

---

## Context and Problem Statement

ADR-022 and ADR-025 established that:
1. Historical business outcomes are never rewritten (`INV-17`).
2. Audit logs (`audit_logs`) and fact versions (`fact_versions`) are strictly append-only (`INV-06`, `INV-07`, `INV-12`).
3. Runtime database roles (`agentnest_app`, `agentnest_worker`) have `REVOKE UPDATE, DELETE ON audit_logs` enforced (`ADR-025 §1.1`).
4. The provisional two-year (730-day) audit retention period specified in open question `OQ-12` has had no automated purge path, with ADR-022 explicitly stating: *"Any audit purge requires its own accepted decision and verification... The proposed two-year production purge is deferred to Phase 8 and legal review (OQ-12), with a separate ADR required for its privileged identity, boundaries and database privileges."*
5. Data rights erasure workflows (`P8-05` / Sessions 10–11) erase customer and workspace personal data, while database backups have a 35-day retention (`backup_retention_days = 35`, `P8-02` / Session 04). How backup retention reconciles with erasure obligations must be documented unambiguously.

Before real customer data is onboarded (Gate 3), the architectural boundaries for audit log retention, privileged purging, and backup reconciliation must be settled.

---

## Decision Outcome

### 1. Audit Log Append-Only Integrity and Runtime Purge Prohibition

1. **No Runtime Application Purge:**
   The daily `retention_cleanup` background job and the FastAPI application runtime (`agentnest_app`, `agentnest_worker`) shall **never** attempt, possess, or execute `DELETE` or `UPDATE` statements on `audit_logs`. Runtime database roles lack these privileges and will fail closed if attempted.

2. **Audit Purge Deferral Pending Counsel Review (`OQ-12`):**
   Automated 730-day audit log deletion is **deferred**. Audit records continue to be retained indefinitely in the application database. Gate 3 remains open until legal counsel sign-off on `OQ-12` resolves whether production audit logs should be archived to cold storage, purged after 730 days, or retained longer for regulatory compliance.

3. **Narrow Out-of-Band Maintenance Purge Specification:**
   If/when audit purging is executed following counsel approval, it must satisfy all of the following requirements:
   - **Identity & Privilege:** Executed exclusively via an explicit, out-of-band administrative maintenance command or script by the schema owner (`agentnest_migrator`), completely outside normal worker job execution.
   - **Audit of the Purge:** Before deleting rows older than the agreed retention threshold, the purge script must record an immutable audit entry (`audit.purged`, including cutoff timestamp, row count, and executor identity) that is itself preserved.
   - **No Data Resurrection:** The purge must never delete tombstones in `deletion_tombstones` or active state ledger evidence.

### 2. Backup Retention Reconciled with Erasure Obligations

1. **35-Day Backup Retention:**
   Nightly encrypted database backups are retained for 35 days in off-site storage (`backup_retention_days = 35`, `ADR-025 §1.1`).

2. **Post-Restore Deletion Re-application:**
   When a database snapshot is restored into a fresh environment (e.g. during disaster recovery):
   - The post-restore reconciliation procedure (`scripts/restore.py`, `app.operations.backup_restore`) inspects `deletion_tombstones` and external tombstone manifests.
   - Any customer, conversation, or workspace erasure that occurred between the backup snapshot timestamp and the restore time is **immediately re-applied** prior to enabling worker processes.
   - In-flight or pending operations are marked `outcome_unknown` and reconciled without auto-resend (`INV-05`).
   - This prevents restored backups from resurrecting erased personal data or re-sending stale messages, satisfying GDPR/KVKK erasure obligations within backup lifecycles.

### 3. Key Custody and Rotation Deprecation Window

1. **Retained Key Ring (`TOKEN_ENCRYPTION_KEYS`):**
   `TOKEN_ENCRYPTION_KEYS` retains historical key entries alongside `TOKEN_ENCRYPTION_ACTIVE_KEY_ID`.
2. **Safe Key Removal Policy:**
   An old encryption key ID may only be removed from server environment configuration when:
   - All `social_accounts` have been re-encrypted to the active key (`token_key_id == active_key_id`).
   - All retained backup snapshots (older than or equal to 35 days) that were encrypted or contained tokens encrypted with that key have aged past `backup_retention_days`.

---

## Consequences

- **Positive:**
  - Preserves non-negotiable invariant `INV-12` (append-only audits) and `INV-06`/`INV-07` without granting dangerous `DELETE` privileges to runtime application/worker roles.
  - Transparently documents the reconciliation between 35-day backup retention and immediate/7-day data rights erasure.
  - Gate 3 remains explicitly open until legal counsel sign-off on `OQ-12`.
- **Trade-offs:**
  - Disk storage for `audit_logs` grows monotonically until an out-of-band maintenance archive or purge procedure is authorized by counsel. At pilot scale, audit volume is small (< a few thousand rows per month) and well within single-VPS PostgreSQL capacity.

