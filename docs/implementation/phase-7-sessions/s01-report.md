# Phase 7 Session 1: token crypto, configuration and S3 storage

**Date:** 2026-10-23 (Europe/Istanbul). **Scope:** P7-01 and P7-06, offline implementation only. **Status:** implementation and verification complete; operator accepted Session 1 after independent diff review, focused tests and JUnit inspection. Phase gates remain pending.

## Authorization and gates

The owner explicitly directed: “Proceed with offline Sessions 1–4; keep gates pending.” This exception is recorded near the session-plan overview. Gate 1 and Gate 2 remain pending: Phase 6 acceptance/invariant/owner/CI evidence is not completed by this session, and V-01/V-02/V-03/V-05/V-08/V-09 still need dated live findings and sanitized recordings. This session makes no live Meta or S3 calls, uses no real integration credentials, does not push, and does not claim real-account acceptance. P7-00's research-based final re-plan remains pending.

## Changes

- Added `TokenKeyRing` with strict 32-byte base64 key validation, active-key selection, AES-256-GCM, random 12-byte nonce prefixes, retained-key reads for rotation, content-free crypto errors and workspace/account AAD.
- Added all Session 1 settings and secret exclusions. Startup validates enabled Meta credentials and key rings, selected S3 configuration, and any supplied key ring in every environment. Fake/mock/local defaults remain credential-free.
- Added `S3MediaStorage`, registry selection and a narrow typed injectable client protocol. Every method validates storage keys. Uploads preserve content type, reads return seekable bytes and close the response body, missing objects raise `StorageObjectNotFound`, deletion is idempotent, and presigned GET URLs carry the requested TTL. Explicit credentials, SigV4 and disabled SDK retries prevent hidden retry behavior.
- Added `cryptography`, `boto3` and development S3 typing dependencies; synchronized the lockfile. Added the S3 API-layer import restriction and the rule that only the S3 adapter imports boto3.
- Added crypto, configuration and offline SDK-stub tests. Updated former “S3 not implemented” expectations to explicit unavailable-storage injection, and kept the production seed-refusal test credential-free using a valid mock-only configuration.
- Updated `.env.example`, environment reference, storage/config ADR implementation notes, integration contract and session brief together. No schema, endpoint, public media route or provider adapter was added.

## Contract adaptations

1. `S3_ENDPOINT_URL` is optional for AWS. `S3_REGION` defaults to `auto` as specified in the brief; AWS deployments must set the actual bucket region. Bucket, non-empty region and explicit credentials are required whenever S3 is selected.
2. Session 1 I2 and its detailed safety bullets differed about development. Checks now apply in every environment. The planned tunnel exception is not implemented: local storage produces simulator-only `localmedia:` references and there is no established public serving/security contract. Meta therefore requires S3 even when `MEDIA_PUBLIC_BASE_URL` is supplied. That field remains reserved.
3. `StorageObjectNotFound` is the existing protocol's missing-object exception and subclasses the brief's `FileNotFoundError`.
4. The overview's crypto method names now match Session 1's detailed `encrypt`/`decrypt` contract.

## Verification

| Check | Result |
|---|---|
| Focused crypto/settings/storage tests | 142 passed in 1.02 seconds |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed; 456 files |
| `uv run mypy app evals` | Passed; 244 source files |
| `uv run lint-imports` | Passed; 19 kept, 0 broken |
| Full `uv run pytest -q --tb=short --junitxml=var/phase7-evidence/s01-backend-results.xml` | 2,627 passed in 689.45 seconds (11m 29s); exit 0 |
| `git diff --check` | Passed |

Static-check logs, full pytest log and JUnit XML are saved under ignored `backend/var/phase7-evidence/s01-*`. S3 tests inject SDK clients with explicit synthetic credentials and `botocore.stub.Stubber`; signing tests run locally without network requests. They verify request parameters, SigV4 signing/TTL, missing-key and permission-error distinctions, key rejection before SDK calls, factory configuration and response-body closure. Crypto tests cover rotation, random nonces, empty/Unicode plaintext, tampered nonce/ciphertext/tag, wrong keys, truncated blobs and changed tenant/account AAD. Configuration tests cover every environment and secret-free diagnostics.

JUnit independently confirms 2,627 tests, 0 failures, 0 errors and 0 skipped, with suite time 689.400 seconds. The operator independently reran the three focused files: 142 passed in 1.72 seconds. No baseline failures were encountered, and no full-suite rerun was needed.

The full backend run explicitly sets `TEST_DATABASE_URL` to the known local `agentnest_test` database. Its resolved target was checked as localhost:5433/agentnest_test before execution; the existing conftest refusal for names not ending `_test` remains intact. The existing Docker postgres service was already healthy. Only the test database is rebuilt by the test harness; no development demo reset or migration was run.

## Limitations and next review

- Live Meta fetches, credentials, OAuth, provider methods, webhook changes and live acceptance belong to later work and remain unverified.
- The simulator still expects localmedia URLs. Default mock/local publishing remains the required regression path. Mixed mock/S3 publishing is not implemented by this session and must not be advertised as supported.
- Secured local-media tunnel serving remains pending; the reserved setting cannot enable it.
- No frontend changes were needed for this foundations session. Gate acceptance is separate from passing local backend checks.

## Local commits

- `8c257e5` — `P7-01: AES-GCM token encryption key ring and startup config checks` (includes the dependency/configuration prerequisites and existing S3-placeholder fixture adjustments).
- `P7-06: S3 media storage backend with presigned URLs` — the following local commit contains the adapter, registry, storage tests, import rules, storage documentation and this report. Its SHA is included in the operator handoff rather than embedded into its own commit.

Session 1 is accepted by the operator. This child agent stops here; the operator controls starting the fresh Session 2 agent. Local gate acceptance and live verification remain separate.
