# Phase 7 Session 2: Meta adapter and offline contracts

**Date:** 2026-10-23 (Europe/Istanbul). **Scope:** P7-03, P7-04, P7-05 and P7-09 offline. **Status:** implementation and verification complete; operator accepted Session 2 after independent diff, static-log and JUnit review. Phase gates remain pending.

## Authorization and gates

The owner explicitly authorized offline Sessions 1–4 while keeping the prerequisite gates pending. Gate 1, Gate 2, V-01/V-02/V-03/V-05/V-08/V-09, P7-00's research-based final re-plan and all live Meta/S3 acceptance remain pending. No real-account Meta requests, real S3 requests, paid calls, production credentials or pushes were made. The prior accepted Session 1 head is `92c5ed1` on local `main`.

## Changes

- Added `MetaInstagramProvider`: signed webhook delegation, account profile, UTF-8-limited text send, outbound reconciliation lookup, image/story containers, status, publish, media/permalink, publishing quota and token refresh. It uses fixed Graph hosts, a pinned configured version, 15-second requests, no redirects, no environment proxy inheritance and no adapter retries.
- Added content-free Graph/HTTP/transport error mapping with explicit precedence. Connect failures remain transient; send/publish 5xx, response/read/write/protocol ambiguity and malformed successful responses become `ProviderOutcomeUnknown`. Reads, refresh and invisible container creation use transient errors for those conditions. Missing/invalid successful IDs cannot cause blind resends.
- Added lazy registry `account_ref(account: SocialAccount, settings: Settings) -> AccountRef`. It snapshots ciphertext, key ID and tenant/account AAD without retaining ORM rows or sessions. Send, publish (including quota/reconciliation), DM reconciliation and health checks use it. Decryption happens only when an actual adapter request needs a token; unavailable/tampered ciphertext is a safe auth error.
- Extended internal `TokenInfo(expires_at, access_token=None)` with a repr-hidden optional returned token. Meta expiry uses the injected `Clock` plus validated `expires_in`; the Session 3 refresh consumer must encrypt the returned token immediately and never put it in logs, jobs, API responses or ledger results.
- Added final structured operation logs that reflect response validation failures as well as HTTP failures. Logs contain operation/provider/duration/outcome only. Graph response message text and transport exception chains are suppressed; httpx/httpcore request logs below WARNING are disabled even with application DEBUG logging. Refresh uses the required unversioned query-token endpoint; normal Graph requests use bearer headers.
- Hardened story reply/mention and unsupported attachments, message-unsend normalization and scoped idempotent deletion. Unsends deduplicate by account and mid separately from the original message, update only the matching workspace/account message and create no draft. Other-app Meta echoes bypass own-send matching even with identical text and supersede pending drafts as native replies. Mock behavior remains compatible.
- Added forward migration `0016` to extend the inbound-event type check. It preserves existing rows and refuses downgrade while deletion events exist. OAuth moves to `0017`; no historical migration was edited.
- Added 28 explicitly labelled synthetic JSON fixtures, fixture provenance documentation, parameterized adapter-neutral mock/Meta cases, and provider, registry, migration and webhook integration tests. Existing mock-specific database and failure-injection assertions remain intact.

## Verification

| Check | Result |
|---|---|
| Final focused provider/shared-contract/registry/webhook/migration tests | 281 passed in 12.05 seconds |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed; 464 files |
| `uv run mypy app evals` | Passed; 246 source files |
| `uv run lint-imports` | Passed; 19 kept, 0 broken |
| Full `uv run pytest -q --tb=short --junitxml=var/phase7-evidence/s02-backend-results.xml` | 2,827 passed in 682.75 seconds (11m 22s); exit 0 |
| `git diff --check` | Passed |

Static checks, focused logs/JUnit and the full suite log/JUnit are saved under ignored `backend/var/phase7-evidence/s02-*`. The focused suite covers all fixture response/webhook shapes, request paths/bodies/headers and token timing, taxonomy and precedence, safe Retry-After handling, malformed responses, redaction, final outcome logs, sender/recipient/time filtering, fixed-host pagination, story ingestion, scoped deletion and native-app draft supersession. Registry execution tests use persisted encrypted synthetic tokens and guards proving no executor transaction is open during Meta HTTP requests, including ambiguous-send and ambiguous-publish reconciliation. Migration tests upgrade an isolated real `0015` schema, preserve old rows, refuse lossy downgrade and restore the old constraint after an authorized test cleanup.

JUnit independently confirms 2,827 tests, zero failures/errors/skips and suite time 682.158 seconds. The focused JUnit confirms 281 tests with zero failures/errors/skips. The operator independently reran the 142 adapter unit tests (142 passed in 0.29 seconds), reviewed the final diff and static logs, and accepted the implementation. The full backend suite was run once after stability; no full rerun was needed.

The test target was explicitly set and verified as `localhost:5433/agentnest_test`; its name ends `_test`, and the existing destructive-test guard remains unchanged. The existing healthy Docker Postgres service was reused. Test harness schema rebuilds and isolated migration schemas affect the test database only. No development reset or migration was run.

During focused development, the first migration attempt incorrectly reapplied the naming convention to an already expanded check-constraint name. That produced 133 cascading setup errors after 129 unit passes; `op.f(...)` fixed the migration. Subsequent test-authoring failures were a PowerShell Unicode literal becoming `?` and a missing synthetic webhook secret; both fixtures were corrected without weakening assertions. The two later failed focused logs/JUnit are retained under descriptive `s02-focused-*-failure*` names. The initial migration-run artifact was overwritten before archival; its error is recorded here rather than claimed as retained evidence. Final focused results are green.

## Adaptations and limitations

1. **Fixture provenance:** none of the JSON files is a recorded Meta response. They implement the repository's provisional offline contracts. Official public Meta content-publishing/quota/messaging pages were inaccessible or returned HTTP 429 during this session; third-party search results were not used as authority. Authentic sanitized recordings and V-05 remain necessary before live acceptance.
2. **Response safety:** malformed successful send/publish responses are ambiguous even with HTTP 200. Malformed error envelopes also follow the ambiguity rule. Rate-limit hints support numeric seconds and HTTP dates using the injected clock; pathological hints above signed-32-bit seconds are ignored to protect executor datetime arithmetic.
3. **Media contract:** Meta requires syntactically valid HTTPS URLs with a hostname and no embedded credentials. Malformed URLs and `localmedia:` are rejected before token access/network. Every non-`None` story caption, including an empty string, is rejected. These are stricter offline validations than only refusing localmedia. Default mock/local behavior and the Session 1 unsupported mixed mock/S3 limitation remain unchanged.
4. **Publication reconciliation:** Graph container-status fixtures intentionally carry no published media ID. `ContainerStatus.media_id=None` remains supported; a verified publication can therefore be recorded without an invented permalink. The real response shape remains a live research question.
5. **Pagination:** outbound lookup follows only cursors rebuilt on fixed paths/host, filters both sender and recipient and an inclusive time bound, deduplicates and sorts results, and refuses repeated/incomplete pagination (100-page bound per collection) instead of returning partial reconciliation evidence.
6. **Deletion ordering:** an unknown deletion mid is a no-op, matching this session's prescribed update-existing-message contract; no tombstone or new draft is created.
7. **Session boundaries:** OAuth, refresh jobs and full disconnect remain Session 3; frontend and the live contract harness remain Session 4. Passing offline tests does not satisfy any live acceptance criterion.

## Local commits

- `002c035` ? `P7-03: MetaInstagramProvider messaging, profile, lookup and error mapping` (includes token refresh shape and lazy encrypted registry integration for send, reconciliation and health).
- `0b4a0bd` ? `P7-04: MetaInstagramProvider publishing, container status, media and quota` (includes publishing executor token wiring and guarded registry integration tests).
- `4bec7ae` ? `P7-05: webhook parser hardening for story replies, deletions and echoes` (includes migration `0016`, deletion/native-app integration tests and matching contracts).
- `P7-09a: parameterised Meta contract tests with synthetic offline fixtures` ? the following local commit contains the labelled fixtures, parameterized shared suite, adapter tests and this report. Its SHA is supplied in the operator handoff rather than embedded into its own commit.

All commits stay on local `main`; nothing is pushed. Session 2 is accepted by the operator. This child stops here, and the operator controls starting the fresh Session 3 agent. Gates and live acceptance remain separate.
