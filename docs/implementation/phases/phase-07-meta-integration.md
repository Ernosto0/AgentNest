# Phase 7: Meta Instagram Integration

> **Gated.** Start only after Gate 1 (local MVP) and Gate 2 (research items V-01, V-02, V-03, V-05, V-08 and V-09 recorded in [platform-capabilities.md](../../research/platform-capabilities.md)). Before starting, re-read this plan against the research results and **update it**. Tasks below assume the documented behaviour.

**Owner exception (2026-10-23):** sequential offline Sessions 1-4 were authorized while both gates were pending. Gate 1 was subsequently closed on main after successful CI on 2026-10-25 ([close-out](../phase-6-sessions/gate-1-closeout.md)); Gate 2 remains pending. All four sessions are offline-complete and accepted by the operator: final backend 2,904 passed / 4 intentionally skipped manual probes, frontend 497 passed, strict fake eval 166/166 and required statics green. No real Meta/S3 calls, public tunnel, credentials collection, deployment, App Review or push are included. P7-00's final research-based re-plan, authentic recordings and all real-account acceptance remain pending. [Session plan](../phase-07-sessions.md) records the approved offline contract adaptations; these do not close any live criterion or authorize Phase 8.

**Offline contract updates:** Meta always requires S3; reserved local-media configuration cannot enable it. OAuth migration is `0017` after webhook deletion migration `0016`. Actual returned grants, disconnect invalidation, workspace `FOR NO KEY UPDATE` fencing and refresh attempt fences govern credentials. Optional erasure waits durably for uncertain sends, with no unconditional deletion deadline. The UI follows public provider/workspace policy and real provider provenance; the future manual adapter harness separates required reads from explicitly opted-in DM/image side effects. Full details/evidence are in the session reports and [Phase 7 summary](../phase-summaries/phase-07-summary.md).

## Objective
Connect a real Instagram professional account through Instagram Login and run the same workflows (C, E, G) through `MetaInstagramProvider`, with encrypted tokens, real signed webhooks, S3-compatible media with signed URLs, token refresh, and disconnection, first with the founder's own account and then with tester accounts.

## Read first
[platform-capabilities.md](../../research/platform-capabilities.md) · [integrations.md §3.4–3.5](../../architecture/integrations.md) · [ADR-010](../../architecture/decisions/ADR-010-instagram-provider-adapter.md) · [ADR-015](../../architecture/decisions/ADR-015-media-storage.md) · [ADR-017](../../architecture/decisions/ADR-017-configuration-and-secrets.md) · [workflows.md §G](../../architecture/workflows.md) · [security-and-privacy.md T5, T10, T18](../../architecture/security-and-privacy.md)

## Scope
**In:** token encryption; OAuth (connect, callback, reconnect, mismatch); `MetaInstagramProvider` (profile, send, containers, status, publish, media, quota, refresh, `find_recent_outbound`); Meta webhook handshake and signature with `META_APP_SECRET`; parser hardening with recorded fixtures; S3 storage backend + presigned URLs; `refresh_tokens` job; disconnect; capability detection from granted scopes; contract tests (`meta_live`); tunnel-based development documentation.
**Out:** comments, video/Reels, Facebook Login, the Human Agent tag, App Review submission (Phase 8).

## Prerequisites
Gate 1 and Gate 2. A Meta app with Instagram Login configured. The founder's test professional account. An S3-compatible bucket. A tunnel tool (e.g., `cloudflared`) for a public HTTPS webhook URL during development.

## Files and modules expected to change
```
backend/app/core/security.py (AES-GCM token crypto, key ring)
backend/app/integrations/instagram/{meta.py, oauth.py, error_mapping.py}
backend/app/integrations/storage/s3.py
backend/app/inbox/webhooks_router.py (Meta secret path)
backend/app/operations/{refresh.py}, jobs
backend/app/integrations/router.py (connect, callback, disconnect)
backend/tests/contract/fixtures/meta/*.json, tests/contract/test_meta_live.py
frontend/src/features/settings/Connections.tsx (real connect, reconnect, disconnect)
docs/operations/local-development.md (tunnel section), platform-capabilities.md (results)
```

## Key interfaces and contracts
- OAuth `state`: random 32 bytes, stored hashed with `{user_id, workspace_id, expires_at (10 min), purpose: connect|reconnect, social_account_id?}`, single use.
- Token key ring: `TOKEN_ENCRYPTION_KEYS="k1:<base64 32 bytes>[,k2:…]"`, `TOKEN_ENCRYPTION_ACTIVE_KEY_ID=k1`.
- Config added: `META_APP_ID`, `META_APP_SECRET`, `META_WEBHOOK_VERIFY_TOKEN`, `META_GRAPH_API_VERSION`, `META_OAUTH_REDIRECT_URI`, `MEDIA_STORAGE_BACKEND=s3`, `S3_*`, `MEDIA_PUBLIC_URL_TTL_SECONDS`, `TOKEN_REFRESH_DAYS_BEFORE_EXPIRY` (20).

## Tasks (in order)

| ID | Task | Size |
|---|---|---|
| P7-00 | Re-plan: update this document and the error mapping with research findings; adjust capabilities (stories) | S |
| P7-01 | Token crypto + key ring + startup checks; unit tests (round trip, wrong key, rotation read) | S |
| P7-02 | OAuth connect/callback/reconnect with `state`; code exchange and long-lived exchange server-side; profile fetch; capabilities from scopes; upsert account; audit; frontend connect flow | M |
| P7-03 | `MetaInstagramProvider` messaging (send, `find_recent_outbound`, profile) with error mapping from fixtures | M |
| P7-04 | `MetaInstagramProvider` publishing (containers with presigned URLs, status, publish, media, quota) | M |
| P7-05 | Webhook handshake + Meta signature + parser hardening with recorded fixtures (attachments, story replies, echoes with `app_id`, reactions, deletions) | M |
| P7-06 | S3 storage backend; presigned URLs; config safety (meta requires s3) | S |
| P7-07 | `refresh_tokens` / `refresh_token` jobs; `needs_reauth` transitions from real errors; reconnect flow | S |
| P7-08 | Disconnect (token deletion, holds, cancellations); optional "delete conversation data" | S |
| P7-09 | Contract tests `-m meta_live` against the founder account; record and sanitise fixtures; run the full manual checklist below | M |
| P7-10 | Docs: tunnel setup, Meta app configuration steps, troubleshooting entries | S |

## Tests to add
- Unit and integration with fixtures (no network) for every Meta error mapping.
- Contract suite parameterised for `meta` using recorded fixtures (offline) plus `meta_live` (manual).
- Security: OAuth `state` replay or mismatch rejected; reconnect with a different account rejected; tokens absent from responses and logs.

## Acceptance criteria (manual + automated)
1. Founder account connected via OAuth. The account shows `connected` with capabilities. The token is encrypted in the DB.
2. A DM from a test follower appears in the inbox within seconds. The draft is grounded. Approval sends a **real** reply. The UI shows *Gönderildi* **without** the simulated badge.
3. A reply typed in the native Instagram app supersedes the pending draft (if V-02 confirmed; otherwise the documented fallback behaviour).
4. A scheduled feed image publishes at the scheduled time exactly once, and the permalink opens the real post. A story publishes if V-03 confirmed.
5. Revoking the app's access in Instagram settings leads to `needs_reauth` with a banner on the next operation. Reconnect restores `connected`.
6. Webhooks with an invalid signature are rejected.
7. All automated tests still pass. The mock remains the default for development.

## Known risks
RK-01, RK-02, RK-09. Standard Access limitations may block some features (V-01).

## Explicitly excluded
Comments, video/Reels, App Review submission, production deployment (Phase 8).
