# Meta Deauthorization and Data-Deletion Callbacks Runbook

- **Tracking:** `P8-05 provider callbacks`, `ADR-025 §3.4`, `V-06` provisional
- **Target Audience:** System Administrators, Security Engineers, and Meta App Administrators
- **Environment Scope:** Production VPS and Staging Environments

---

## 1. Overview and Requirements

Meta (Facebook / Instagram Graph API) developer policy requires all production applications utilizing Instagram Login or Graph API permissions to provide:
1. **Deauthorization Callback URL**: Triggered when a user removes the application from their Meta / Instagram account settings ("Apps and Websites").
2. **Data Deletion Request URL**: Triggered when a user requests deletion of their platform data via Meta account settings.
3. **Data Deletion Status URL**: Returned by the data deletion callback so the user can verify that their data deletion request was fulfilled.

In AgentNest, these endpoints are implemented with strict cryptographic verification of Meta's `signed_request`, server-owned identity mapping (`INV-01`), durable status tracking via `data_deletion_requests`, and privacy-preserving confirmation status queries.

---

## 2. Configured Endpoints

| Purpose | Canonical Endpoint (`/api/v1`) | Public Proxy / Alias Endpoint | HTTP Method |
|---|---|---|---|
| **Deauthorization Callback** | `/api/v1/webhooks/meta/deauthorize` | `/webhooks/meta/deauthorize` | `POST` |
| **Data Deletion Callback** | `/api/v1/webhooks/meta/data-deletion` | `/webhooks/meta/data-deletion` | `POST` |
| **Confirmation Status** | `/api/v1/webhooks/meta/data-deletion/{code}` | `/webhooks/meta/data-deletion/{code}` | `GET` |

> [!NOTE]
> Both `/api/v1/...` and `/webhooks/...` routes are supported. The endpoints accept both `application/x-www-form-urlencoded` (`signed_request=...`) and `application/json` (`{"signed_request": "..."}`).

---

## 3. Cryptographic Verification Contract (`INV-01`)

Meta transmits requests signed with the application's App Secret:
```
signed_request = <encoded_sig>.<payload>
```
1. **Signature Parsing & Verification:**
   - The signature is extracted from `<encoded_sig>` using URL-safe Base64 decoding.
   - An expected HMAC-SHA256 digest is computed over `<payload>` using `META_APP_SECRET`.
   - The signature is verified with `hmac.compare_digest()` to prevent timing attacks.
   - If invalid, the request returns HTTP `401 Unauthorized` and records an audit event `webhook.signature_invalid`.
2. **Payload Validation:**
   - The payload is parsed as JSON.
   - The algorithm must equal `"HMAC-SHA256"`.
   - The `user_id` (or `app_scoped_user_id`) is extracted.
   - If malformed, the request returns HTTP `400 Bad Request` and records `webhook.signature_invalid`.

---

## 4. Processing Lifecycle

### 4.1 Deauthorization Callback
1. Verifies the `signed_request`.
2. Queries server-owned `social_accounts` for active connections matching `external_account_id == user_id`.
3. If an account matches:
   - Sets `status = "disconnected"`.
   - Clears `token_ciphertext = None`.
   - Clears `capabilities = {}`.
   - Pauses any active `AccountAgent` in that workspace (`operating_mode = "paused"`).
   - Emits `meta.deauthorized` and `social_account.disconnected` audit records.
4. If no account matches, emits a system-level `meta.deauthorized` audit entry without leaking account existence to the caller.
5. Returns `{"status": "ok"}` with HTTP 200.

### 4.2 Data Deletion Callback
1. Verifies the `signed_request`.
2. Replay check: if a request for the same `provider_user_id` exists, returns the existing confirmation URL and code idempotently.
3. Generates an unguessable 32-character URL-safe confirmation code (`del_...`).
4. Checks server-owned records:
   - **Page / Account Owner:** If matching a `social_accounts.external_account_id`, disconnects the account and records a durable tombstone in `deletion_tombstones`.
   - **Customer Identity:** If matching an end-customer identity (`CustomerIdentity.provider_subject_hash == SHA256(user_id)`), routes through `erase_customer()`. If in-flight operations are settling, status is set to `in_progress`; otherwise `completed`.
   - **Unknown / Already Erased:** Writes an anticipatory tombstone in `deletion_tombstones` and records status as `not_found_or_already_erased`.
5. Records the row in `data_deletion_requests` and emits `meta.data_deletion_requested` in `audit_logs`.
6. Returns Meta's mandatory JSON response:
   ```json
   {
     "url": "https://<APP_HOST>/api/v1/webhooks/meta/data-deletion/<confirmation_code>",
     "confirmation_code": "<confirmation_code>"
   }
   ```

### 4.3 Confirmation Status Endpoint
- **JSON Request (`Accept: application/json`):**
  ```json
  {
    "confirmation_code": "del_...",
    "status": "completed",
    "requested_at": "2026-11-03T02:00:00Z",
    "completed_at": "2026-11-03T02:00:01Z"
  }
  ```
- **Browser Visit (`Accept: text/html`):** Renders a bilingual (TR/EN) clean status card with confirmation code, timestamp, and privacy guarantees.
- **Privacy Assurance:** Never reveals usernames, external account IDs, workspace IDs, or conversation contents.

---

## 5. Meta Developer Dashboard Setup

1. Open **Meta for Developers** (`developers.facebook.com`) -> Select your App.
2. Navigate to **App Settings** -> **Basic**.
3. Under **User Data Deletion**:
   - Select **Data Deletion Request URL**.
   - Enter: `https://<YOUR_APP_DOMAIN>/api/v1/webhooks/meta/data-deletion`
4. Under **Deauthorization Callback URL**:
   - Enter: `https://<YOUR_APP_DOMAIN>/api/v1/webhooks/meta/deauthorize`
5. Click **Save Changes**.

---

## 6. Verification and V-06 Status Tracking

> [!IMPORTANT]
> - **Local / CI Status:** Cryptographic verification, replay resistance, identity mapping, erasure orchestration, and status rendering are covered by automated unit and integration suites (`test_meta_callbacks.py`).
> - **V-06 Status (Provisional):** Marked provisional until live verification during Phase 8 Session 16 (`P8-10` / Gate 3) using an active Meta App Dashboard test event and App Review validation.
