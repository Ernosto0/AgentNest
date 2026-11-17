# Pre-Launch Problems

**Reviewed:** 2026-11-15, at commit `f1cc494` on `main`.
**Companion document:** [pre-launch-feature-recommendations.md](pre-launch-feature-recommendations.md) lists features to add. This file lists things that are broken, missing or inconsistent today.

## How this was checked

- Read the code, the product and operations docs, and the CI history on GitHub.
- Ran locally: backend `ruff check`, `ruff format --check` and `mypy app`; frontend `lint`, `typecheck`, `i18n:check` and `build`.
- **Not done:** the full backend and frontend test suites were not run, and the app was not opened live. UI findings (P-13 to P-16) come from fixture screenshots taken on 2026-11-09 in `.tmp/today-fixed-browser/`. Later redesign commits may have changed those screens, so confirm each one in the running app before fixing it.

## Summary

| ID | Problem | Severity |
|---|---|---|
| P-01 | CI is red on `main`; tests do not run; Railway deploys anyway | Blocks any launch |
| P-02 | No recorded end-to-end proof against a real Instagram account | Blocks any launch |
| P-03 | No recorded eval run against the real LLM | Blocks any launch |
| P-04 | Pilot onboarding checklist does not match the code | Blocks any launch |
| P-05 | Comment features cannot work on a real account (scope never requested) | Blocks the comment feature |
| P-06 | Landing waitlist form may send nothing | Blocks any launch |
| P-07 | Production runs on a `railway.app` subdomain | Blocks any launch |
| P-08 | Backups are not part of the Railway setup | Blocks any launch |
| P-09 | Legal sign-off is open and there is no LICENSE | Blocks real customer data |
| P-10 | No self-service signup | Blocks public launch |
| P-11 | No billing, plans or owner-visible usage limits | Blocks public launch |
| P-12 | No frontend error tracking and no product analytics | Should fix before pilots |
| P-13 | Today screen is very long on a phone; command box is buried | Polish |
| P-14 | Seven-day content grid repeats "no story" seven times | Polish |
| P-15 | Instagram performance chart looks flat | Polish |
| P-16 | Header search label is cut off on desktop | Polish |
| P-17 | `index.html` has no favicon, description or share tags | Polish |
| P-18 | Two lazy-loaded routes are not actually split | Polish |
| P-19 | Pricing document promises things that are not built | Should fix before selling |

---

## Blocks any launch

### P-01. CI is red on `main`, so the tests do not run, and Railway deploys anyway

**Problem.** None of the last 40 CI runs on `main` succeeded. Each run stops at a lint or format step, so the backend tests, frontend tests, evals and Playwright suite never execute. Railway deploys `main` directly ([.railway/railway.ts](../../.railway/railway.ts)), so untested commits reach production.

**Evidence.**
- Latest run (commit `f1cc494`): frontend fails at `npm run lint`; backend fails at `ruff format --check`.
- Frontend, reproduced locally: three `@typescript-eslint/no-explicit-any` errors in [router.tsx](../../frontend/src/app/router.tsx) at lines 9, 13 and 22 (the `lazyNamed` helper).
- Backend, reproduced locally: `ruff format --check` reports 3 files that would be reformatted.
- An earlier run (commit `e9a7317`) failed at `mypy app` and at the "regenerate the OpenAPI client" drift check. `mypy` passes locally at `f1cc494`. The OpenAPI drift check has not run since, so its current state is unknown.

**Suggested fix.**
1. Type the `lazyNamed` helper without `any` (or add a narrow, commented `eslint-disable` if a correct generic is not practical).
2. Run `uv run ruff format .` in `backend/` and commit the three files.
3. Push and watch the run through to the end. Fix whatever the later steps reveal, starting with the OpenAPI drift check.
4. Turn on Railway's "wait for CI" option for the `api`, `worker` and `web` services so a red commit cannot deploy.

**Status (2026-11-16, PR #2, green run [43789959883](https://github.com/Ernosto0/AgentNest/actions/runs/43789959883) on `3c63804`):** partial. The CI part is done: every job is green (backend 3,549 passed and 13 skipped, evals and account-agent journeys, frontend lint/typecheck/i18n/unit/OpenAPI drift, Playwright 177 passed and 3 skipped across the three projects, gitleaks). What it took, beyond the two items listed above: `lazyNamed` typed with generics; 3 backend files formatted; four broken `lint-imports` contracts (this step had never run: `narrator.py` moved to `app/core`, `commands.service` now sends the Telegram notice through the channel registry after the commit instead of inside the transaction, `reporting.home_router` added to the existing API-deps exception); `frontend/openapi.json` and `schema.d.ts` regenerated (the CLI writes sorted keys, the committed copy was not sorted, so the drift check could never pass); `.github/scripts/offline-tests.sh` now passes the environment through `sudo` (on hosted runners `--preserve-env` is ignored, `HOME` was `/root` and `uv` failed before the first test); about 35 stale backend tests and the stale e2e specs updated (details in the commit messages), plus real fixes: one missing activity-feed action (`auth.password_reset_throttled`), a raw message key (`Operation completed: command.unsupported`) shown to the owner in demo mode, and three accessibility defects found by the axe e2e checks (launcher button name, Turkish sign-out-device label, low-contrast text). **Still open: Railway "wait for CI".** It cannot be set in `.railway/railway.ts`: the IaC reference documents no option for it, so it is a dashboard-only setting. Do this once per service (`api`, `worker`, `web`, and `landing`, which is a separate service with root directory `/landing` and is not in `railway.ts`): Railway dashboard, open the project, click the service, Settings, the GitHub source/trigger section, switch on **Wait for CI** (older UI name: "Enable check suites"). The switch appears only when the repo has a workflow with a `push` trigger on the deploy branch (`ci.yml` has `on: push: branches: [main]`) and the Railway GitHub app has accepted the updated permissions (banner in the GitHub installation settings). Railway then holds each deploy of `main` until all check suites finish and skips it if one fails, so deploys will wait for the CI run (about 40 minutes: backend 17, e2e 22). Re-check the switch after any `railway.ts` apply. Railway community threads report the wait counts every check suite on the commit, not just Actions, and some cases of deploys stuck in "waiting for CI"; if that happens, disconnect and reconnect the repo.

### P-02. No recorded end-to-end proof against a real Instagram account

**Problem.** The docs say every Meta fixture is synthetic and that real-account acceptance is still pending: receiving a real DM through a signed webhook, sending an approved reply once, publishing a scheduled image once, the native-app echo superseding a draft, and the revoke-then-reconnect path.

**Evidence.** [phase-07-summary.md](../implementation/phase-summaries/phase-07-summary.md) ("no live success is claimed"), [platform-capabilities.md](../research/platform-capabilities.md) (items V-01, V-02, V-03, V-05, V-08, V-09 open). The local `.env` now points at `meta` and `openai`, so live testing may have started, but nothing in the repository records the result.

**Suggested fix.** Run the six Phase 7 acceptance checks on the founder's own professional account. Save sanitised recordings under `backend/tests/contract/fixtures/meta/` and update `platform-capabilities.md` with dates. Do not onboard a pilot business before these pass.

### P-03. No recorded eval run against the real LLM

**Problem.** All 12 reports in `backend/evals/reports/` are from the `fake` provider. The roadmap lists the real-model quality run (gate G7.5-C) as still needed. Turkish reply quality, grounding and escalation behaviour on the production model are therefore unmeasured.

**Suggested fix.** Run `uv run python -m evals run --all --provider openai` and the account-agent journeys once against `gpt-6-luna`, commit the report, and record cost per run. This also settles OQ-09 (model per task).

### P-04. Pilot onboarding checklist does not match the code

**Problem.** [pilot-onboarding-checklist.md](../operations/pilot-onboarding-checklist.md) is the runbook for the first pilots, and three of its instructions are wrong. Following it in front of a business owner would fail.

| Checklist says | Code has |
|---|---|
| `python -m app.cli create-workspace …` and `seed-facts …` | Neither command exists in [cli.py](../../backend/app/cli.py). Available: `seed`, `create-user`, `generate-key`, `simulate-message`, `run-due-jobs`, `check-config` and others. |
| Invite link `https://agentnest.io/invites/accept?token=…` | The route is `/invite/:token` ([router.tsx:122](../../frontend/src/app/router.tsx#L122)). |
| Permissions `instagram_basic`, `instagram_manage_messages`, `instagram_manage_comments`, `pages_manage_metadata`, `pages_read_engagement` | The app requests `instagram_business_basic`, `instagram_business_manage_messages`, `instagram_business_content_publish`, `instagram_business_manage_insights` ([oauth.py:14-17](../../backend/app/integrations/instagram/oauth.py#L14-L17)). |

The checklist also requires a linked Facebook Page with admin rights. That is a Facebook Login requirement; check whether it still applies to the Instagram Login flow the code uses.

**Suggested fix.** Either add the two CLI commands or rewrite section 2 around what exists (`create-user`, then the in-app workspace wizard and paste-to-extract). Correct the invite URL and the permission list. Then do one dry run of the whole checklist on a fresh workspace.

**Status (2026-11-16, PR #5):** done. Section 2 is rewritten around what exists (`create-user`, the in-app workspace wizard, paste-to-extract and manual facts, with the real fact keys and value formats); no CLI commands were added because the dry run needed none. The invite URL is `/invite/:token`, the permission list is the four `instagram_business_*` scopes, and the Facebook Page requirement is removed: Meta's documentation says Instagram API with Instagram Login "does not require a Facebook Page to be linked to the Instagram professional account". The dry run (fresh DB, mock provider, fake LLM) also corrected the owner sign-up fields (one name field, 10-character minimum), the menu paths and button labels, the draft and approval wording, the disclosure behaviour (default text `Bu yanıt otomatik olarak hazırlanmıştır.`, added only to auto-sent replies, not `— Otomatik yanıt`), the pause runbook, the "50 operations per 24 hours" claim (it is the publish limit) and the `post-restore-reconcile` description. Still to confirm on the first real pilot: the real Meta consent screen and tester-invite menu names.

### P-05. Comment features cannot work on a real account

**Problem.** The agent has comment tools (`comment.reply`, `comment.hide`, `comment.private_reply` and others) and the UI has a comments queue, but the OAuth flow never asks for a comment permission. Even after the capability gates open, a real account would have no grant.

**Evidence.** [oauth.py:14-17](../../backend/app/integrations/instagram/oauth.py#L14-L17) lists four scopes; none covers comments. Research items R75-01 to R75-06 are open.

**Suggested fix.** This is expected while the capability is gated, but make the state explicit: hide or label the comments queue on real accounts until the scope is added and verified, and add the scope to the App Review package. See F-05 in the companion document.

**Status (2026-11-16, PR #5):** done for the UI and docs; the scope itself is still missing by design. When no connected account has a `comment_*` capability set (the same capability flags the agent uses, no new flag), the inbox labels the Comments tab "Henüz yok" / "Not yet", hides its count and replaces the list with "Yorumlar henüz kullanılamıyor". Mock accounts keep the list. [meta-app-review-package.md](../operations/meta-app-review-package.md) now says that `instagram_business_manage_comments` must be added to `SCOPES` and requested in App Review, and that the package's permission names are the Facebook Login ones and need reconciling before submission. Left: add the scope and close R75-01 to R75-06.

### P-06. Landing waitlist form may send nothing

**Problem.** The landing form posts to `VITE_WAITLIST_ENDPOINT`, a build-time variable. If it is not set, the form goes into "preview" mode and tells the visitor nothing was sent. The backend has no waitlist endpoint, so an external collector is required.

**Evidence.** [waitlist.ts](../../landing/src/waitlist.ts), [landing/README.md](../../landing/README.md). Whether the variable is set on Railway could not be seen from the repository.

**Suggested fix.** Submit the live form once and confirm the entry arrives. If no collector exists yet, point the variable at a form service or add a small `POST /waitlist` endpoint that emails `OPERATOR_ALERT_EMAIL`. Set `VITE_WAITLIST_WHATSAPP` as a fallback.

**Status (2026-11-16, PR #5):** done in code; needs one live check after deploy. `POST /api/v1/waitlist` stores one row per email (migration `0049`, up and down tested), is rate-limited through the existing throttle table, answers new and repeated emails alike, and emails `OPERATOR_ALERT_EMAIL` after the commit (best effort). The email is never logged in plain text; rows are deleted after `RETENTION_WAITLIST_DAYS` (365) or by `waitlist-delete --email`; `waitlist-list` prints them. CORS for the landing origin is limited to this route and set by `LANDING_ORIGINS` (`.env.example`, environment-variables.md). The landing form now asks for an email, sends the new body and is documented in landing/README.md. Left on Railway: set `VITE_WAITLIST_ENDPOINT` (build-time) and `LANDING_CONNECT_SRC` on the landing service, `LANDING_ORIGINS`, `OPERATOR_ALERT_EMAIL`, `SMTP_URL` and `MAIL_FROM` on the API, then submit the live form once.

### P-07. Production runs on a `railway.app` subdomain

**Problem.** `APP_BASE_URL`, `FRONTEND_ORIGIN` and `META_OAUTH_REDIRECT_URI` all use `web-production-b2f30.up.railway.app`. Business owners are asked to grant Instagram access on a generated hostname, and Meta App Review expects a stable domain with a privacy policy URL. The onboarding checklist already assumes `agentnest.io`.

**Suggested fix.** Decide the product name (OQ-10), register the domain, attach it in Railway, and update the three variables plus the redirect URI in the Meta dashboard in one change.

### P-08. Backups are not part of the Railway setup

**Problem.** The backup, restore and restore-drill tooling in `scripts/` was built for the single-VPS deployment. [.railway/railway.ts](../../.railway/railway.ts) defines only `Postgres`, `api`, `worker` and `web`; nothing runs `backup.py` there.

**Suggested fix.** Confirm what Railway's Postgres plan backs up and how long it keeps it. If that is not enough, add a scheduled service that runs `scripts/backup.py` to R2, and repeat the restore drill on Railway before real customer data arrives.

### P-09. Legal sign-off is open and there is no LICENSE

**Problem.** Gate 3 requires counsel to review hosting region and cross-border transfer (OQ-04), retention periods (OQ-12) and the automation disclosure (OQ-13). All three are still on provisional defaults. The repository has no `LICENSE` file (OQ-02), and the legal entity for Meta Business Verification is undecided (OQ-05).

**Evidence.** [open-questions.md](../research/open-questions.md) lists nothing under "Resolved". [phase-08-summary.md](../implementation/phase-summaries/phase-08-summary.md) marks the legal artifacts "offline drafted".

**Suggested fix.** Book the legal review now; it has the longest lead time of anything on this list. Keep the repository private until the license is chosen.

---

## Blocks public (self-service) launch

These do not stop assisted pilots, where the founder sets up each business in person.

### P-10. No self-service signup

**Problem.** The auth API has login, logout, password reset and invite acceptance, but no registration endpoint ([identity/router.py](../../backend/app/identity/router.py)). A new owner can only get an account through the CLI or an invite.

**Suggested fix.** Add email signup with verification, then route the new user into the existing workspace wizard. Protect it with the existing login throttling. Not needed for the first 10 to 15 pilots.

**Status (2026-11-17, PR #6):** done, behind the `SIGNUP_ENABLED` flag (default off). `POST /auth/register`, `/auth/resend-verification` and `/auth/verify-email` with signed, 24 h, single-use links; generic 202 answers (an existing address gets a "you already have an account" email); register and resend are throttled per email and per IP; the accepted terms version and time are stored on the user (`backend/app/identity/legal.py`, `TERMS_VERSION`). Unverified sessions get 403 `EMAIL_NOT_VERIFIED` everywhere except `/auth/me`, `/auth/logout`, `/meta` and verification. Migration 0050 marks all existing users verified; invite acceptance by a new user marks the email verified. Frontend: signup, check-your-email, verification and terms pages, then the workspace wizard; Playwright journey `signup.spec.ts`. **Left:** (1) legal review of the terms page text, which is a short placeholder, and of the privacy page, then bump `TERMS_VERSION`; (2) production needs `SMTP_URL` and `MAIL_FROM` before the flag goes on; (3) unverified accounts are never purged, and an unverified account blocks the same address from being used in an invite (add a cleanup job or let an invite replace an unverified account if this shows up); (4) no CAPTCHA, only the throttle.

### P-11. No billing, plans or owner-visible usage limits

**Problem.** No plan or subscription model exists in the code. The only limit is the global `LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY`, and the owner sees it only as a line in System Health after it is exhausted. The pricing document promises monthly reply quotas with warnings at 80% and 100%.

**Suggested fix.** For pilots, keep manual invoicing as planned. Before selling tiers, add a per-workspace plan record, a monthly reply counter, and the two warning notifications. Payment integration (iyzico or PayTR) can follow.

**Status (2026-11-17, PR #7):** partial: everything except taking payment is done. Each workspace has a plan (`starter` 500, `growth` 2,500, `pro` 7,500 AI replies per month; default `growth`, status `trial`, period from creation; per-workspace quota override), a concurrency-safe monthly counter (row lock plus an idempotent ledger, migration `0051`), warnings at 80% and 100% (once per period, owners and managers, every channel, tr/en), a 10% grace and then a pause: no model call, inbound DMs still stored and announced, a needs-human draft with reason `REPLY_QUOTA_PAUSED`, drafting resumes by itself on a plan change or the next period. Owners and managers see a usage meter in Settings and a notice on Today from 80%. Operator CLI: `plan-usage`, `plan-set`, `plan-reset`, `plan-extend`. The counting rule is in `app/plans/service.py` and [data-model.md](../architecture/data-model.md). **Still open:** payment (iyzico or PayTR), a self-service upgrade, the 100-reply trial cap and every other per-plan limit (seats, posts, retention); the plan `status` is stored but changes nothing. Pricing doc updated.

### P-12. No frontend error tracking and no product analytics

**Problem.** Sentry is wired into the backend only. A crash in the owner's browser is invisible. There is also no usage analytics, so the pilot metric "daily active owners" in [vision.md](../product/vision.md) can only be approximated from sessions.

**Suggested fix.** Add the Sentry browser SDK with the same DSN policy and PII scrubbing as the backend. Add one privacy-friendly analytics tool to the landing page and, if counsel agrees, to the app.

---

## Polish

Findings P-13 to P-16 are from the 2026-11-09 screenshots; verify before acting.

### P-13. Today screen is very long on a phone, and the command box is buried

**Problem.** At 390 px the Today screen is about 4,300 px tall with more than ten sections. The "ask your assistant" command box, which is the product's most distinctive control, comes sixth, after the content grid and the performance card.

**Suggested fix.** On phones, keep "waiting for you", the command box and today's three numbers at the top. Collapse the rest behind section headers or move it to the pages that already own it (Content, Reports).

**Status (2026-11-16, PR #3):** done. Redesign commits had already cut the phone page to about 2,900 px with the order waiting items, numbers, assistant box. PR #3 folds upcoming content and Instagram performance behind their headings on phones (about 2,100 px; the Content and Reports links stay visible). Desktop is unchanged.

### P-14. Seven-day content grid repeats "no story" seven times

**Problem.** Every day cell shows the same "+ no story" prompt, followed by a separate "no story planned" card that says the same thing again. The owner still has to design the story image, so the prompt asks for work the product cannot help with yet.

**Suggested fix.** Show the prompt once for the whole week. Revisit after story template cards exist (F-07).

**Status (2026-11-16, PR #3):** done. The per-day "No story" text was already reduced to a "+" icon and the duplicate card was gone when a plan existed. PR #3 removes the per-day buttons and the second draft button in the empty card; a week with no story shows one prompt. Revisit after F-07.

### P-15. Instagram performance chart looks flat

**Problem.** Reach and views share one vertical axis, so both lines look almost horizontal even when the cards above report +15% and +22%.

**Suggested fix.** Scale the axis to the data range instead of starting at zero, or draw each metric as its own small sparkline inside its card.

**Status (2026-11-16, PR #3):** done. Reach and views are two stacked lines, each on its own fitted axis with both ends labelled, so a non-zero baseline is stated. Chosen over per-KPI sparklines because it keeps the shared hover crosshair and the screen-reader table.

### P-16. Header search label is cut off on desktop

**Problem.** At 1440 px the command-palette trigger reads "Git…" next to the shortcut hint.

**Suggested fix.** Give the trigger a minimum width or drop the label and keep the icon plus shortcut.

**Status (2026-11-16, PR #3):** done. The label was not truncated: "Git…" is the whole Turkish label. It is now "Sayfaya git…" / "Go to page…" with a 240 px minimum width from 1200 px; below that it is icon only.

### P-17. `index.html` has no favicon, description or share tags

**Problem.** [frontend/index.html](../../frontend/index.html) contains only a title, a viewport tag and a fixed white `theme-color`. There is no favicon link, no meta description, no Open Graph tags and no web app manifest. The white theme colour is wrong in dark mode.

**Suggested fix.** Add the icon set, description and share tags. Add the manifest as part of F-01.

**Status (2026-11-16, PR #5):** done except the manifest (F-01) and a share image. `frontend/index.html` and `landing/index.html` now have `favicon.ico`, `favicon.svg`, an Apple touch icon, a description, Open Graph and Twitter tags and two media-specific `theme-color` tags. The icons are derived from the existing brand mark `landing/public/favicon.svg`. The app has no dark theme, so both app tags use the app canvas colour; the landing tags follow the visitor's chosen theme. No `og:image` or `og:url`: there is no share image and the production domain is undecided (P-07).

### P-18. Two lazy-loaded routes are not actually split

**Problem.** The build warns that `WorkPages.tsx` and `NotFoundPage.tsx` are imported both lazily (by the router) and statically (by `ConversationPage`, `InboxWorkspace`, `CategoryPage`, `MetricItems`, `WorkspaceGate`), so they stay in the main chunk.

**Suggested fix.** Import them lazily everywhere or statically everywhere. The size effect is small; the point is a build with no warnings.

**Status (2026-11-16, PR #2):** done. `router.tsx` now imports `WorkPages` and `NotFoundPage` statically (the other importers already did), and `npm run build` prints no chunk or dynamic-import warning.

### P-19. Pricing document promises things that are not built

**Problem.** [pricing-and-unit-economics.md](../product/pricing-and-unit-economics.md) lists these as tier features: WhatsApp owner channel, up to three Instagram accounts, data export, Russian and German replies, comment automation on real accounts, and quota warnings. None exists in a usable form today.

**Suggested fix.** Mark each row "planned" or remove it until it ships. Sell only what a pilot owner can use on day one.

**Status (2026-11-16, PR #5):** done. Every tier row that is not built is marked **Planned**, and section 8 records what the code shows for each: WhatsApp has only an unused formatter, one active Instagram account per workspace is enforced by a unique index, data export exists only per conversation and per customer, replies are `tr` and `en` only, comments work on the mock provider only, and there is no monthly quota, usage warning, plan or billing field. A banner at the top says per-plan limits are not enforced.

---

## What passed

- Backend `ruff check` and `mypy app` (347 source files): clean.
- Frontend `typecheck` and `i18n:check` (2,269 keys in `tr` and `en`): clean.
- Frontend production build: succeeds.
