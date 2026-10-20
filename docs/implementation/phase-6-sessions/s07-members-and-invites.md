# Session 7: Members and invites

**Plan:** `plan.md` §2 **H14**, §3 **P6-06**. **Depends on:** session 6. **Commits:** `P6-06a: …` (model, API, rules), `P6-06b: …` (UI and accept page).

## Read first
- `api-design.md` §2.2, `data-model.md` (`invites`, `workspace_members`) and `security-and-privacy.md` (sessions, CSRF, the permission matrix).
- User journey J1 step 1 (the invite as a QR code and the owner transfer).
- `identity/{models,service,repository,router,schemas}.py`.
- How login is CSRF-protected (`api/middleware.py`) and the test that enumerates the unsafe routes (`tests/security/`).
- `core/errors.py` (adding codes with tr/en).

## Build
- Migration `0014` `invites` (data-model, composite FK to the workspace).
- `identity/invites.py`: create (token per H14, sha256 only), list pending, revoke, and accept (signed in, or a new user with `{token, email, display_name, password}`). The rules, the single error `INVITE_INVALID` and the 409 cases are in H14.
- Members:
  - `PATCH /…/members/{user_id}` (role) and `DELETE` (remove), both with `members.manage`;
  - `LAST_OWNER_REQUIRED` on demoting or removing the last owner;
  - owner transfer works: promote the other person, then demote yourself.
- Audit: `member.invited`, `member.invite_revoked` (new; add it to the observability §5 catalog and give it activity templates), `member.joined`, `member.role_changed`, `member.removed`.
- Notification `member.joined` (info, to the owners). Add it to the catalog.
- Frontend:
  - `features/settings/Members.tsx`: the list with roles, role change, removal with confirmation, the invite sheet (the URL from `window.location.origin + invite_path`, a copy button and a QR code using the `qrcode` package), and the pending invites with revoke;
  - the public route `/invite/:token` (`features/invites/AcceptInvite.tsx`): the new-account form, or "Katıl" when signed in, then go to the workspace;
  - `members.json` in tr/en.
- Regenerate the OpenAPI files.
- Docs:
  - `api-design.md` §2.2 (exact shapes, invites list and revoke);
  - `data-model.md`;
  - `observability.md` §4 (codes) and §5 (actions);
  - `security-and-privacy.md` (if the CSRF or token handling needs a line).

## Done when
- Backend tests pass:
  - create, then accept as a new user and as an existing signed-in user;
  - an existing email while signed out → 409;
  - expired (frozen clock), reused, revoked and unknown tokens all return `INVITE_INVALID` with the same body;
  - already a member → 409;
  - role change;
  - last-owner demote and remove → 409; owner transfer works;
  - staff → 403;
  - isolation;
  - the audit entries;
  - the token is never stored or logged in clear;
  - CSRF on accept (the unsafe-routes test includes the new routes).
- Vitest tests pass: the invite sheet shows the URL and QR, revoke, role change, the last-owner error text, and both states of the accept page.
- Full backend and frontend checks and the OpenAPI drift check are green.
