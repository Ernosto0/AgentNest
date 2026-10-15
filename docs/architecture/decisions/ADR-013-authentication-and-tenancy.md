# ADR-013: Built-in session auth; shared-schema multi-tenancy with composite keys

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
Users belong to one or more workspaces (the founder doing assisted onboarding belongs to several). The open-source core must be self-hostable without paid identity services. One workspace must never see another's data ([invariants.md](../../invariants.md) INV-01). The frontend is a browser SPA on the same site as the API.

## Alternatives
**Authentication:** (a) external IdP (Auth0, Clerk, Supabase Auth); (b) magic-link email only; (c) **built-in email + password with server-side sessions**; (d) JWT access/refresh tokens in local storage.

**Tenancy:** (i) database per tenant; (ii) schema per tenant; (iii) **shared schema with `workspace_id`**, enforced in application code + composite FKs, with Postgres RLS added later.

## Decision
**Authentication**
- Email + password (argon2id via `argon2-cffi`), **server-side sessions**: an opaque random token in an `HttpOnly; Secure; SameSite=Lax` cookie, with only a SHA-256 hash stored in `sessions`.
- CSRF protection for state-changing requests: `SameSite=Lax` plus a required custom header (`X-CSRF-Token` matching a per-session token exposed via `/auth/me`).
- Session TTL 14 days sliding, revocable. Login throttling per email+IP (Phase 8).
- Local demo uses seeded demo users with documented demo passwords. **No auth bypass mode.**
- Invitations: owner creates an invite → one-time link (shown in UI; emailed after OQ-16) → invitee sets a password.
- Google sign-in / magic links: later, as additions.

**Authorisation**
- Roles per membership: `owner`, `manager`, `staff`. Permission matrix in [security-and-privacy.md §3](../security-and-privacy.md).
- No global superuser in the product. The founder supports a customer by being **invited as a member** (role chosen by the owner, audited, revocable). Operational DB access in production is an infrastructure concern with its own audit.

**Tenancy**
- Every tenant-owned table has `workspace_id NOT NULL`.
- Child tables reference parents by **composite foreign keys** `(workspace_id, parent_id) → parent(workspace_id, id)`. The database therefore rejects cross-workspace references even if application code has a bug.
- All workspace-scoped API routes are `/api/v1/workspaces/{workspace_id}/…`. A dependency `require_membership(workspace_id, permission)` loads the membership and builds a `WorkspaceContext`. Services and repositories **require** a `WorkspaceContext` argument and filter by its ID. No repository method takes a bare entity ID without the context.
- Jobs carry `workspace_id` and rebuild a system `WorkspaceContext`. Webhooks resolve the workspace from the receiving account ID, never from payload data supplied by the sender.
- **Postgres RLS** policies keyed on a per-transaction `app.workspace_id` setting are added in Phase 8 as defence in depth.
- A dedicated **isolation test suite** creates two workspaces and asserts that every endpoint, using IDs from workspace B, returns 404 for workspace A members.

## Rationale
- Built-in sessions avoid third-party cost and keep self-hosting simple. HttpOnly cookies avoid token theft through XSS more effectively than local-storage JWTs.
- Shared schema is the simplest model that scales to thousands of small tenants. Composite FKs give DB-level integrity cheaply.
- Returning 404 (not 403) for other workspaces' resources avoids leaking existence.

## Trade-offs
- We own password security (hashing, reset, throttling). Mitigation: standard libraries, Phase 8 hardening checklist.
- Composite keys make schemas slightly more verbose.

## Consequences
- Every model has `(workspace_id, id)` unique constraints to serve as FK targets.
- Telegram/WhatsApp identities map to users via `channel_links`, created through an authenticated linking flow (one-time code shown in the web app).

## Revisit when
- Enterprise customers require SSO (add OIDC).
- A tenant needs physical data isolation (regulatory). Then use database-per-tenant for that tier only.
