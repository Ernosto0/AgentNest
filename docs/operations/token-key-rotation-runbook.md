# Token Encryption Key Rotation Runbook

- **Scope:** Operational procedures for rotating `TOKEN_ENCRYPTION_KEYS` and re-encrypting connected social account tokens in-place (Phase 8 Session 12, Task `P8-06`).
- **Invariants:** `INV-08` (token secrets never logged or exposed in audit entries), `INV-01` (tenant AAD binding strictly preserved).

---

## 1. Overview

AgentNest stores OAuth access tokens for Meta/Instagram accounts in `social_accounts.token_ciphertext`, encrypted using AES-256-GCM.
Each ciphertext is authenticated with Additional Authenticated Data (`AAD = "<workspace_id>:<account_id>"`).
The active encryption key is identified by `TOKEN_ENCRYPTION_ACTIVE_KEY_ID`, and key definitions are stored in `TOKEN_ENCRYPTION_KEYS` (formatted as `<key_id_1>:<base64_key_1>,<key_id_2>:<base64_key_2>`).

When a key is rotated:
1. New tokens and refreshed tokens are encrypted using the active key ID.
2. Older tokens encrypted under previous key IDs are safely decrypted and re-encrypted using the active key ID via `rotate_token_keys`.
3. An old key must be retained in `TOKEN_ENCRYPTION_KEYS` until all active accounts have been re-encrypted AND all retained database backups that may contain data under the old key have expired past the 35-day backup retention window.

---

## 2. Step-by-Step Rotation Procedure

### Step 1: Generate a New AES-256 Key

Generate a secure 32-byte (256-bit) base64-encoded key:

```bash
openssl rand -base64 32
# Example output: v8X...base64...=
```

Select a unique key identifier (e.g. `k2026_11`, incrementing version or date).

### Step 2: Update Server Configuration

In the production `.env` file on the server:

1. Append the new key to `TOKEN_ENCRYPTION_KEYS` (keeping existing keys intact):
   ```env
   # Before:
   TOKEN_ENCRYPTION_KEYS="k1:abc123oldkey..."
   TOKEN_ENCRYPTION_ACTIVE_KEY_ID="k1"

   # After (both keys present):
   TOKEN_ENCRYPTION_KEYS="k1:abc123oldkey...,k2026_11:v8Xnewkey..."
   TOKEN_ENCRYPTION_ACTIVE_KEY_ID="k2026_11"
   ```

2. Validate that:
   - Key IDs are non-empty and unique.
   - Keys decode to exactly 32 bytes.
   - `TOKEN_ENCRYPTION_ACTIVE_KEY_ID` exactly matches the newly added key ID.

### Step 3: Deploy or Restart Application & Worker

Restart the API and worker containers so the updated keyring is loaded into memory:

```bash
docker compose -f compose.prod.yml restart api worker
```

Verify service health via `/readyz` and inspect logs for startup errors.

### Step 4: Execute In-Place Token Re-Encryption

Execute the rotation job across all connected accounts. This can be done via the administrative script or worker job:

```bash
# Option A: Run administrative script
docker compose -f compose.prod.yml exec api python scripts/rotate_token_keys.py --batch-size 100

# Option B: Or trigger background worker job
docker compose -f compose.prod.yml exec api uv run python -c "
from app.core.db import get_session_factory
from app.core.clock import SystemClock
from app.jobs.queue import enqueue
from app.operations.key_rotation import RotateTokenKeysPayload

with get_session_factory()() as session:
    enqueue(session, 'rotate_token_keys', RotateTokenKeysPayload(batch_size=100), clock=SystemClock())
    session.commit()
print('Enqueued rotate_token_keys job.')
"
```

### Step 5: Verify Re-Encryption Progress

1. Query database to ensure no accounts remain on the old key ID:
   ```sql
   SELECT count(*)
   FROM social_accounts
   WHERE token_ciphertext IS NOT NULL
     AND token_key_id <> 'k2026_11'
     AND status <> 'disconnected';
   ```
   The count must be **0**.

2. Inspect `audit_logs` for `security.token_key_rotated` events:
   ```sql
   SELECT action, resource_type, resource_id, metadata, created_at
   FROM audit_logs
   WHERE action IN ('security.token_key_rotated', 'security.token_key_rotation_failed')
   ORDER BY created_at DESC
   LIMIT 20;
   ```

3. Confirm that no `security.token_key_rotation_failed` entries occurred.

---

## 3. Deprecating and Removing Retired Keys

Do **NOT** immediately delete old keys from `TOKEN_ENCRYPTION_KEYS`.

An old key may only be removed from `TOKEN_ENCRYPTION_KEYS` when:
1. All `social_accounts` have been re-encrypted (`count == 0`).
2. Retained database backups taken prior to key rotation have passed the **35-day backup retention period** (`backup_retention_days = 35`).
   - If an old backup snapshot (e.g. from 20 days ago) is restored during disaster recovery, the post-restore worker reconciliation needs the historical key to decrypt tokens and perform orderly disconnect or re-encryption.
3. Once 35 days have elapsed since key rotation completion, the retired key ID can safely be removed from `TOKEN_ENCRYPTION_KEYS` in `.env`.

