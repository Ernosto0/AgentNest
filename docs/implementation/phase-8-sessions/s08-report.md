# Phase 8 — Session 08 Report: SMTP, Invitations and Password Reset

- **Session:** `S08` (`docs/implementation/phase-8-sessions/phase-08-sessions.md` §Session 08, `docs/implementation/phases/phase-08-hardening.md` `P8-04`, `docs/architecture/decisions/ADR-025-phase-8-hardening-contracts.md` §2, `OQ-16`)
- **Date:** 2026-11-03
- **Status:** `complete`
- **Branch / Commit Baseline:** `main` at `669a040`
- **Alembic Migration Head:** `20261103_0034_password_reset_and_invite_email.py` (revision `0034`, 34 migrations total)

---

## 1. Summary of Implemented Artifacts & Contracts

| Artifact / File | Status | Implementation Summary |
|---|---|---|
| `backend/migrations/versions/20261103_0034_password_reset_and_invite_email.py` | **Created** | Alembic migration `0034`: added optional `email` column to `invites` table, created `password_reset_tokens` table (`id` UUID PK, `user_id` FK to `users.id` ondelete CASCADE, `token_hash` LargeBinary, `expires_at` DateTime, `used_at` DateTime nullable, `created_at` DateTime), created indices on `user_id` and `(token_hash, used_at, expires_at)`, and granted runtime SELECT/INSERT/UPDATE privileges to `agentnest_app` and `agentnest_worker`. |
| `backend/app/core/email.py` | **Created** | Transactional email delivery adapter and in-memory outbox (`InMemoryEmailOutbox`, `email_outbox`). Implements: 1. In-memory email capture for offline/development environments; 2. Configurable live SMTP delivery via standard `smtplib` with STARTTLS / TLS; 3. Multipart MIME message building (text + HTML); 4. Localized TR/EN invitation email templates preserving manual URL & assisted-onboarding presentation; 5. Localized TR/EN password reset email templates with 60-minute expiry notice; 6. Host-header injection prevention: links strictly use `settings.frontend_origin` (falling back to `settings.app_base_url`). |
| `backend/app/identity/models.py` | **Updated** | Added `email: Mapped[str | None]` column to `Invite` model. Defined `PasswordResetToken` model (`UUIDPrimaryKeyMixin, TimestampMixin, Base`) with Argon2/SHA256 token hash storage. |
| `backend/app/identity/schemas.py` | **Updated** | Added optional `email: EmailStr | None` to `InviteCreate`, `InviteOut`, and `PendingInviteOut`. Added `PasswordResetRequest(email: EmailStr)` and `PasswordResetConfirm(token: str, new_password: str)`. |
| `backend/app/core/errors.py` | **Updated** | Added `"PASSWORD_RESET_TOKEN_INVALID": ErrorSpec(400)` and `"PASSWORD_TOO_WEAK": ErrorSpec(400)`. |
| `backend/app/activity/groups.py` | **Updated** | Added `"auth.password_reset_requested"` and `"auth.password_reset_completed"` under the `"system"` activity group. |
| `backend/app/core/i18n/` | **Updated** | Added TR and EN explanations for `PASSWORD_RESET_TOKEN_INVALID` and `PASSWORD_TOO_WEAK` in `en.json` and `tr.json`, along with localized activity feed item templates. |
| `backend/app/api/deps.py` | **Updated** | Added `/api/v1/auth/password-reset/request` and `/api/v1/auth/password-reset/confirm` to `CSRF_EXEMPT_PATHS` (unauthenticated entry points). |
| `backend/app/identity/invites.py` | **Updated** | Updated `create_invite()` to accept optional recipient email. When provided, automatically dispatches invitation email while preserving full invite URL and token for manual QR/assisted onboarding in the API response. |
| `backend/app/identity/service.py` | **Updated** | 1. `request_password_reset()`: Enumeration-resistant (always returns 202 without leaking account existence); invalidates prior unused tokens for the user; generates 32-byte cryptographically secure token; stores SHA256/Argon2 digest; dispatches localized email with 60-minute expiry and trusted-origin URL. 2. `confirm_password_reset()`: Verifies token existence, single-use, and expiration; validates password strength (minimum 12 chars & deny-list); updates Argon2id password hash; marks token as used; invalidates all active user sessions in the same transaction; emits `auth.password_reset_completed` audit event. |
| `backend/app/identity/router.py` | **Updated** | Exposed unauthenticated endpoints `POST /api/v1/auth/password-reset/request` (status 202) and `POST /api/v1/auth/password-reset/confirm` (status 204). Updated invite creation to forward email address. |
| `backend/tests/unit/identity/test_password_reset_and_email.py` | **Created** | Comprehensive unit test suite (9 tests) verifying: in-memory outbox recording and clearing; text & HTML template rendering in TR/EN; invitation email dispatch; enumeration resistance; single-use token constraints; token expiration; password policy enforcement; session revocation upon reset; and trusted origin construction resisting Host header injection. |
| `frontend/src/features/auth/hooks.ts` | **Updated** | Added typed React Query mutations: `useRequestPasswordReset()` and `useConfirmPasswordReset()`. |
| `frontend/src/features/auth/ResetPasswordPage.tsx` | **Created** | Password reset view supporting both request flow (`/reset-password`) and confirm flow (`/reset-password/:token`), with responsive TR/EN form validation, error handling, and success feedback. |
| `frontend/src/features/auth/LoginPage.tsx` | **Updated** | Added "Forgot password?" navigation link pointing to `/reset-password`. |
| `frontend/src/app/router.tsx` | **Updated** | Registered public routes `/reset-password` and `/reset-password/:token`. |
| `frontend/src/features/settings/Members.tsx` & `hooks.ts` | **Updated** | Added optional recipient email field to `InviteSheet` dialog, enabling instant invite dispatch while preserving manual URL presentation. |
| `frontend/src/i18n/locales/` | **Updated** | Added all localized strings for password reset and emailed invitations in `en/common.json` and `tr/common.json`. |
| `frontend/src/features/auth/resetPassword.test.tsx` | **Created** | Frontend unit test suite verifying both request and confirm flows, mock API interactions, and user feedback. |

---

## 2. Verification Outcomes

### 2.1 Static Analysis & Quality

| Check | Command | Exit Code | Result Summary |
|---|---|---|---|
| Backend Lint | `backend/.venv/Scripts/ruff.exe check .` | `0` | All checks passed (0 errors) |
| Backend Typecheck | `backend/.venv/Scripts/mypy.exe app` | `0` | Success: 0 issues in 297 source files |
| Import Architecture | `backend/.venv/Scripts/lint-imports.exe` | `0` | 19 contracts kept, 0 broken |
| Frontend Lint | `npm.cmd run lint` | `0` | ESLint passed cleanly |
| Frontend Typecheck | `npm.cmd run typecheck` | `0` | `tsc -b --noEmit` passed cleanly |
| Frontend i18n Check | `npm.cmd run i18n:check` | `0` | Passed: en, tr \| 1536 keys \| 1010 literal t() calls verified |

### 2.2 Test Suite Execution

| Test Suite | Command | Exit Code | Result Summary |
|---|---|---|---|
| Password Reset & Email Unit Suite | `pytest tests/unit/identity/test_password_reset_and_email.py -q` | `0` | `9 passed in 0.61s` |
| Frontend Password Reset Vitest Suite | `vitest run src/features/auth/resetPassword.test.tsx` | `0` | `2 passed in 1.54s` |

---

## 3. Canonical Task Coverage

- **P8-04 Email & Password Reset (OQ-16):**
  - SMTP delivery adapter with dev/offline in-memory capture outbox (`InMemoryEmailOutbox`).
  - Emailed workspace invitations with assisted-onboarding manual URL/QR code link preservation.
  - Single-use, 60-minute hashed token password reset (`POST /api/v1/auth/password-reset/request` returning 202 generic response without account enumeration).
  - Password strength enforcement on reset (minimum 12 characters, common password deny-list).
  - Complete invalidation of all user sessions upon password reset confirmation (`POST /api/v1/auth/password-reset/confirm`).
  - Host-header injection resistance by enforcing canonical `frontend_origin` / `app_base_url`.
  - Localized TR/EN email and web templates.

