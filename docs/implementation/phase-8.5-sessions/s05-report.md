# Phase 8.5 Session 05 report: login, invite acceptance and workspace onboarding

Executed 2026-11-01, Europe/Istanbul. Scope: P8.5-05 only. **Implemented and locally verified; operator review and real-stack/human acceptance remain pending.**

## Baseline and scope

Started from `main@f6f9c3b` (accepted Session 04). Read Sessions 01–04 reports, baseline decisions, CLAUDE, invariants, phase/session/specification, current roadmap, and relevant auth/invites/workspaces contracts.

Preserved existing README/roadmap/task-breakdown edits and untracked planning/specification/concept files. No backend, API/schema, effect, permission, query-key or product route changed. No live database, worker, real provider, paid model, email, waitlist or storage service was used. This agent did not commit, push, deploy, or invoke destructive E2E setup.

## Implemented behavior

- **Public shell (`PublicShell.tsx`):**
  Implemented responsive two-column layout on desktop (`lg` 1024px+), with a quiet charcoal brand region (`aside` with `bg-navigation`, brand tagline, and metadata footer) and a focused form area (`main`). On viewports below 1024px (phone/tablet), it reflows into a single form-first column with top brand header and accessible `LanguageSwitch`. An optional header action slot accommodates actions like workspace picker sign-out.
- **Login screen (`LoginPage.tsx`, R01 / A01):**
  Redesigned within `PublicShell` with accessible field hierarchy, semantic `TextField` inputs, `name="email"`, `autoComplete="username"`, `name="password"`, `autoComplete="current-password"`, input mode, client validity checks, and `aria-busy` during mutations.
  Implemented `returnDestination` in `returnTo.ts` to sanitize and preserve redirect destinations from router state while preventing login loops (`/login`), open redirects (`//`), backslashes, or non-root paths. When redirected from protected routes due to session expiry or missing auth, renders a localized notice informing the user to sign in to continue. Inputs are preserved on error.
- **Invite acceptance (`AcceptInvite.tsx`, R02 / A02):**
  Redesigned within `PublicShell`. Differentiates between signed-in and signed-out states without guessing unauthenticated invite metadata:
  - Signed-in: displays current user name and email, instructions, a primary "Katıl / Join" button, and a secondary "Başka hesap kullan / Use another account" button that logs out and returns to the invite.
  - Signed-out: renders name, email, and password registration form.
  - Conflict state (409 CONFLICT_STATE `email_taken`): presents a prominent notice linking to `/login` with router state preserving the invite destination.
  - Invalid invite token (400 INVITE_INVALID): renders an error message with a link returning to login or workspaces.
- **Workspace picker (`WorkspacePickerPage.tsx`, R03 / A03):**
  Redesigned within `PublicShell`. Shows current user email and lists all authorized workspaces with `HomeIcon`, role badges (`t("workspaces.role.<role>")`), and if demo, a demo tag alongside `<SimulatedBadge />`. Long workspace names wrap cleanly with `break-words`. When the user has no memberships, displays a semantic `<EmptyState>`. Header provides a sign-out button that clears session and navigates to `/login`. Language switcher updates user locale preference via `useSaveLocale`.
- **Workspace onboarding wizard (`CreateWorkspaceWizard.tsx`, R04 / A04–A06):**
  Three-step creation flow:
  1. Business name (`business_name`): max 100 characters with hint and validation.
  2. Business category (`business_category`): 9 category radio cards with `has-checked` highlight styling.
  3. Market and regional settings (`market`, `default_locale`, `timezone`, `currency`): market selection automatically applies sensible defaults (TR vs Global) while allowing explicit overrides, accompanied by an explanatory notice outlining next steps in business knowledge.
  - Step indicator: accessible `<ol aria-label="..."><li aria-current="step">` tracking current step.
  - Back navigation: stepping backward retains all previously entered/selected values.
  - Unsaved changes guard: `useBlocker` and `beforeunload` intercept accidental navigation when dirty, presenting an accessible `<BottomSheet>` dialog with "Düzenlemeye devam et / Keep editing" and "Kaydetmeden ayrıl / Leave without saving" options.
  - Completion: on successful creation, navigates to `/w/:id/more/knowledge` readiness checklist.

## Verification

Commands were run individually from `frontend/`:

| Check | Observed final result |
|---|---|
| `npm.cmd run lint` | Exit 0; no findings |
| `npm.cmd run typecheck` | Exit 0; no TypeScript errors |
| `npm.cmd test` | Exit 0; 37 files, 561 tests pass (41.24s) |
| `npm.cmd run i18n:check` | Exit 0; EN/TR 1468 keys, 928 literal calls verified |
| `npm.cmd run build` | Exit 0; 279 modules transformed |
| `node scripts/ui-entry.mjs` | Exit 0; 8 production fixture scenarios across Chromium 156.0.8078.4 & WebKit 27.2 |
| `git diff --check` from root | Exit 0; clean line endings |

Unit test additions and updates:
- Added `frontend/src/features/auth/returnTo.test.ts` (5 tests): verifies safe return destination resolution, rejects loops, backslashes, protocol-relative paths, and preserves query/hash.
- Added `frontend/src/features/auth/login.test.tsx` (3 tests): verifies credential submission, redirect notice on protected return, and input retention on authentication failure.
- Added `frontend/src/features/workspaces/picker.test.tsx` (3 tests): verifies workspace roster rendering with roles/demo badges, empty membership state, and header sign-out.
- Updated `frontend/src/features/invites/acceptInvite.test.tsx` (4 tests): adjusted async form appearance check to `findByLabelText` to match the loading Skeleton transition.

Playwright fixture script `frontend/scripts/ui-entry.mjs`:
- Tested production build against loopback 5185 across Chromium 156.0.8078.4 and WebKit 27.2.
- Evaluated 4 viewport/locale combinations: TR 360 phone, EN 390 phone, TR 768 tablet, EN 1440 desktop.
- Ran automated Axe accessibility scans under tags `["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]` across all screens: Login, Invite (signed out), Workspace Picker, Wizard Step 1, Wizard Step 2, Wizard Step 3, and the Leave Wizard blocker dialog.
- Result: **0 Axe violations** across all scenarios and dialogs.
- Evaluated document width against viewport width (`scrollWidth === innerWidth`): **0 horizontal overflow**.
- Recorded evidence in `docs/implementation/phase-8.5-sessions/evidence/s05/entry.json` and 56 viewport PNG captures.

Bundle impact (measured with Node `gzipSync`):
- Production JS: 853,327 bytes / 247,052 gzip (vs S04: 841,049 / 243,272 -> +12,278 raw / +3,780 gzip).
- Production CSS: 38,574 bytes / 8,611 gzip (vs S04: 37,112 / 8,357 -> +1,462 raw / +254 gzip).
- Local fonts: 173,280 bytes unchanged.
- Total gzip JS change is well below the 50KiB review threshold.

## Acceptance and handoff

- Updated R01–R04 and A01–A06 in `screen-coverage.md`.
- Supplies local verification for UI-01, UI-02, UI-03, UI-04, UI-07, UI-08, UI-09, UI-10 on authentication and onboarding entry points.
- Real-stack E2E on dedicated disposable database remains to be executed by operator. Physical phone/software keyboard and human review remain pending whole-application acceptance.

Next session:
- **Session 06 — Today dashboard and commands:**
  Redesign `features/home` (local date/greeting, authorized metrics, prioritized decisions, upcoming content, real assistant/legacy work) and `features/commands` (command input, clarification chips, confirmations, fact-impact summaries, result cards).

