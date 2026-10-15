# ADR-017: Environment-based configuration, startup safety checks, encrypted tokens

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
The same code runs as a local demo (fake LLM, mock Instagram, demo tools), in CI, and in production (real providers, real customer data). Misconfiguration, such as demo tools or mock accounts enabled in production, or a missing encryption key, could cause false "success" reports or data exposure. Meta access tokens must be stored safely.

## Decision

### Configuration
- One `Settings` class (`pydantic-settings`) reads environment variables (and `.env` in development). The full list is in [environment-variables.md](../../operations/environment-variables.md).
- `APP_ENV` ∈ `development` | `test` | `production` selects defaults. **Production defaults are safe:** demo tools off, `COOKIE_SECURE=true`, JSON logs, `fake` LLM not allowed.
- `.env` is git-ignored. `.env.example` is committed with every variable documented and **no real secrets**.
- The frontend receives **no secrets**. Its only build-time variable is `VITE_API_BASE_URL`.

### Startup safety checks (fail fast, refuse to start)
In `production`:
- `SECRET_KEY` set, ≥ 32 bytes, not the example value.
- `TOKEN_ENCRYPTION_KEYS` set and valid when any Meta integration is enabled.
- `DEMO_TOOLS_ENABLED` must be false.
- `LLM_PROVIDER` must not be `fake`.
- `INSTAGRAM_ENABLED_PROVIDERS` may include `mock` only if `ALLOW_SIMULATED_WORKSPACES=true`. Even then, mock accounts can only be connected to workspaces with `is_demo = true` (enforced in the connect service and by a DB check constraint).
- `MEDIA_STORAGE_BACKEND` must be `s3` if `meta` is enabled.

In every environment: log the effective non-secret configuration at startup (secrets redacted).

### Secrets in storage
- Instagram tokens: **application-level authenticated encryption** (AES-256-GCM via `cryptography`'s `AESGCM`, or Fernet) with a key from `TOKEN_ENCRYPTION_KEYS`. Format `key_id:base64key`, comma-separated; `TOKEN_ENCRYPTION_ACTIVE_KEY_ID` selects the key for new writes. Ciphertext rows store `token_key_id` to allow rotation (a re-encryption job is added when needed).
- Tokens are decrypted only inside the Meta provider adapter at call time and never logged, serialised in API responses, or placed in job payloads (jobs carry `social_account_id` only).
- Passwords: argon2id hashes. Session tokens: only SHA-256 hashes stored.
- Webhook secrets (`META_APP_SECRET`, `MOCK_INSTAGRAM_APP_SECRET`, `TELEGRAM_WEBHOOK_SECRET`) only from the environment.

### Log redaction
- The structured logger has a redaction processor for keys matching `token|secret|password|authorization|cookie|code` and for `Authorization` headers.
- Message text and customer handles are not logged at INFO. IDs are logged instead ([observability.md](../observability.md)).

## Alternatives considered
- A secrets manager (Vault, cloud KMS) from day one: unnecessary for local demo and single-VM pilots. The key-ID design allows moving the key into a KMS later without changing the data format.
- DB-level encryption (pgcrypto): the key would travel in SQL, and access would be harder to restrict.

## Consequences
- A `scripts`-free key generation command: `uv run python -m app.cli generate-key`.
- A `secret-scan` step in CI (e.g., gitleaks) from Phase 1.

## Revisit when
- Hosting moves to a platform with a managed KMS. Then use envelope encryption with a KMS-held key-encryption key.
