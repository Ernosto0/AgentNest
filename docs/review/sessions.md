# Pre-Launch Fix Sessions

**Source:** [pre-launch-problems.md](pre-launch-problems.md) (reviewed 2026-11-15 at `f1cc494`).
**How to use:** start a new Claude Code session for each block below and paste its prompt. Run them in order. Sessions 1 to 4 make the product ready for assisted pilots; sessions 5 to 8 are for public launch.

| # | Session | Problems | Needs from you | Ready for |
|---|---|---|---|---|
| 1 | Get CI passing | P-01, P-18 | GitHub access (`gh`), Railway dashboard for the "wait for CI" toggle | Pilots |
| 2 | Pilot runbook and small fixes | P-04, P-05, P-06, P-17, P-19 | Decide on waitlist collector | Pilots |
| 3 | Live acceptance | P-02, P-03 | Your Instagram professional account, Meta app, OpenAI key, presence at the keyboard | Pilots |
| 4 | Ops: domain, backups, error tracking | P-07, P-08, P-12 | Registered domain, Railway access, Sentry DSN, Meta dashboard | Pilots |
| 5 | UI polish | P-13, P-14, P-15, P-16 | None | Public |
| 6 | Self-service signup | P-10 | Email sending configured | Public |
| 7 | Plans and quotas | P-11 | Tier limits from the pricing doc confirmed | Public |
| 8 | Payments (optional) | P-11 (payment part) | iyzico or PayTR merchant account | Public |

**Not a coding session:** P-09 (legal review, LICENSE, legal entity). Book counsel now; it has the longest lead time. The domain purchase in P-07 is also yours to do before session 4.

**Rules that apply to every session** (each prompt repeats them):
- Railway deploys `main` directly. Until session 1 turns on "wait for CI", do not push anything to `main` that has not passed the local checks.
- Other sessions may be working in the same tree. Do not use `git stash` and do not reset or discard files you did not change.
- At the end of each session, update the problem's entry in `pre-launch-problems.md` with a short status line (date, commit, what was done, what is left).

---

## Session 1. Get CI passing

**Covers:** P-01, P-18. **May need a second session** if the test suites, which have not run in 40+ commits, show many failures. If so, start the next session with the same prompt plus "Continue from where the previous session stopped; read the P-01 status line first."

```text
Goal: get the GitHub Actions CI run on `main` fully green, then stop Railway from deploying red commits.

Read first:
- docs/review/pre-launch-problems.md, entries P-01 and P-18.
- The CI workflow files under .github/workflows/ and .railway/railway.ts.

Background: none of the last 40 CI runs on `main` succeeded. Each run stops at a lint or format step, so the backend tests, frontend tests, evals and Playwright suite never ran. Railway deploys `main` directly, so untested commits reach production.

Steps:
1. Frontend lint: frontend/src/app/router.tsx has three `@typescript-eslint/no-explicit-any` errors in the `lazyNamed` helper (lines 9, 13, 22). Type it properly with generics. Use a narrow, commented eslint-disable only if a correct generic is not practical.
2. P-18 in the same file area: the build warns that WorkPages.tsx and NotFoundPage.tsx are imported both lazily (router) and statically (ConversationPage, InboxWorkspace, CategoryPage, MetricItems, WorkspaceGate). Make the imports consistent so `npm run build` prints no such warning.
3. Backend format: run `uv run ruff format .` in backend/ (3 files expected).
4. Before pushing, run locally every step the CI workflow runs, in the same order: backend ruff check, ruff format --check, mypy app, pytest, OpenAPI client regeneration and drift check, evals with the fake provider; frontend lint, typecheck, i18n:check, unit tests, build, Playwright. Fix what fails. Fix real bugs in the code rather than weakening tests; if a test is genuinely wrong, explain why in the commit message.
5. Push to a branch, open a PR, and watch the CI run to the end with `gh run watch`. Repeat until green. Then merge.
6. Tell me exactly how to turn on Railway's "wait for CI" (check suites) option for the api, worker and web services (and landing, if it is a separate service), or set it in .railway/railway.ts if that file supports it.

Rules:
- Railway deploys `main`; do not push to `main` directly. Work on a branch.
- Other sessions may share this working tree: no `git stash`, no resetting files you did not change.
- Group fixes into small, clearly named commits.

Done when: the CI run on `main` is green end to end, the build has no chunk warnings, and the Railway gating step is either done or written down for me. Update the P-01 and P-18 entries in docs/review/pre-launch-problems.md with a status line. If you run out of room, write down in the P-01 entry exactly which steps still fail and why.
```

---

## Session 2. Pilot runbook and small fixes

**Covers:** P-04, P-05, P-06, P-17, P-19.

```text
Goal: make the pilot onboarding runbook match the code, make the landing waitlist actually deliver, label the comments feature honestly, and fix the small polish items in index.html and the pricing doc.

Read first:
- docs/review/pre-launch-problems.md, entries P-04, P-05, P-06, P-17, P-19.
- docs/operations/pilot-onboarding-checklist.md, backend/app/cli.py, backend/app/integrations/instagram/oauth.py, frontend/src/app/router.tsx, landing/src/waitlist.ts, landing/README.md, docs/product/pricing-and-unit-economics.md.

Tasks:
1. P-04 runbook. The checklist calls `python -m app.cli create-workspace` and `seed-facts`, which do not exist; uses invite URL /invites/accept?token=… while the route is /invite/:token; and lists Facebook Login permissions while oauth.py requests instagram_business_* scopes. Decide which is less work and more robust: add the two CLI commands, or rewrite section 2 around what exists (create-user, then the in-app workspace wizard and paste-to-extract). Recommend one to me before building it. Fix the invite URL and permission list. Check whether the "linked Facebook Page with admin rights" requirement still applies to Instagram Login (business login), and correct it. Then do a dry run of the checklist against a local fresh workspace and fix anything else that does not match.
2. P-05 comments. The OAuth flow requests no comment scope, so comment tools and the comments queue cannot work on a real account. On real (non-fake) Meta connections, hide or clearly label the comments queue as "not available yet" until the scope is granted. Check the capability gate code and reuse it rather than adding a new flag. Add a note to the App Review package docs that the comment scope must be added.
3. P-06 waitlist. The landing form posts to VITE_WAITLIST_ENDPOINT; if unset it only shows "preview" mode. Ask me whether I already have a form service. If not, add a small backend `POST /waitlist` endpoint (email + optional business name, rate limited with the existing throttling, stored and emailed to OPERATOR_ALERT_EMAIL), with tests, and document the landing variable to set. Make sure CORS allows the landing origin.
4. P-17 frontend/index.html: add favicon links (create a simple icon set from the existing logo asset if one exists; ask me if none does), meta description, Open Graph and Twitter tags, and a theme-color that works in dark mode (media-specific theme-color tags). Do the same review for landing/index.html.
5. P-19 pricing doc: mark every tier feature that is not built today as "planned" (WhatsApp owner channel, multiple Instagram accounts, data export, Russian and German replies, comment automation on real accounts, quota warnings). Check each against the code before marking it.

Rules:
- Work on a branch and open a PR; let CI pass before merging. Do not push directly to `main` (Railway deploys it).
- Other sessions may share this working tree: no `git stash`, no resetting files you did not change.
- Keep tr and en i18n keys in sync (`npm run i18n:check`).

Done when: CI is green on the PR, the checklist dry run passes, and each entry (P-04, P-05, P-06, P-17, P-19) in docs/review/pre-launch-problems.md has a status line.
```

---

## Session 3. Live acceptance against real Instagram and the real LLM

**Covers:** P-02, P-03. **You must be present** to perform the Instagram actions on your phone and in the Meta dashboard.

```text
Goal: record the first real end-to-end proof that Pivoris works against a real Instagram professional account and the real OpenAI model. I will do the actions on Instagram; you drive the app, logs and recordings.

Read first:
- docs/review/pre-launch-problems.md, entries P-02 and P-03.
- docs/implementation/phase-summaries/phase-07-summary.md and docs/research/platform-capabilities.md (items V-01, V-02, V-03, V-05, V-08, V-09).
- backend/evals/ (how runs and reports work) and the account-agent journey tests.

Part A: real LLM evals (P-03). Do this first; it does not need me.
1. Confirm the OpenAI key and model config with `python -m app.cli check-config` (do not print secrets).
2. Run `uv run python -m evals run --all --provider openai` against gpt-6-luna, then the account-agent journeys.
3. Commit the reports under backend/evals/reports/. Write a short summary: pass rate per suite, the worst failures (especially Turkish reply quality, grounding and escalation), total tokens and cost per full run.
4. Record a recommendation on model per task for OQ-09 in docs/research/open-questions.md. Do not change prompts or models in this session; list suggested fixes instead.

Part B: real Instagram acceptance (P-02). Walk me through each check one at a time, tell me what to do, then verify in logs and the database:
1. Connect the account through the real OAuth flow.
2. Receive a real DM through the signed webhook.
3. Approve a reply in the app; confirm it is sent exactly once.
4. Publish a scheduled image once.
5. Reply from the native Instagram app; confirm the echo supersedes the pending draft.
6. Revoke access in Instagram settings, confirm the app notices, then reconnect.
For each check, save sanitised recordings (no tokens, no real user IDs or names; replace with stable fakes) under backend/tests/contract/fixtures/meta/ and add contract tests that replay them. Update platform-capabilities.md with the date and result of each V-item.

Rules:
- If a check fails, find the root cause and fix it on a branch with a test, then re-run the check. If the fix is large, stop and write it up instead.
- Never commit secrets or unsanitised payloads. Grep the fixtures for tokens and IDs before committing.
- Work on a branch, PR, CI green, then merge. Other sessions may share this tree: no `git stash`.

Done when: eval reports are committed with a cost figure, all six Instagram checks are recorded as pass (or have a written failure and plan), and P-02 and P-03 in docs/review/pre-launch-problems.md have status lines.
```

---

## Session 4. Ops: domain, backups, frontend error tracking

**Covers:** P-07, P-08, P-12. **Before starting:** decide the product name (OQ-10) and register the domain.

```text
Goal: move production to the real domain, make sure the database is backed up and restorable on Railway, and add frontend error tracking and privacy-friendly analytics.

Read first:
- docs/review/pre-launch-problems.md, entries P-07, P-08, P-12.
- .railway/railway.ts, scripts/backup.py and the restore-drill scripts and docs under docs/operations/, backend Sentry setup (search for sentry_sdk), docs/product/vision.md (pilot metrics).

Tasks:
1. P-07 domain. Ask me for the domain. Produce one change list covering: Railway custom domains for web (and api and landing if separate), DNS records I must add, APP_BASE_URL, FRONTEND_ORIGIN, META_OAUTH_REDIRECT_URI, CORS and cookie domain settings, the redirect URI and privacy policy URL in the Meta app dashboard, and any hardcoded railway.app references in code or docs (grep for them). Apply the code and config parts; give me the dashboard steps as a checklist. After I confirm the switch, verify login, OAuth connect and webhook delivery on the new domain.
2. P-08 backups. Find out what Railway's Postgres plan backs up and for how long (ask me to check the dashboard if docs are not conclusive). If it is not enough for the retention in our docs, add a scheduled Railway service (cron) that runs scripts/backup.py to R2, with the needed variables documented. Then run the restore drill against a Railway copy and record the result and timings in the operations docs.
3. P-12 error tracking. Add the Sentry browser SDK to frontend/ using the same DSN policy and PII scrubbing rules as the backend (no message bodies, no customer names or handles, no tokens). Enable only when the DSN variable is set. Add source map upload in the build if it can be done without exposing maps publicly. Add a test or manual check that a thrown error reaches Sentry with scrubbed data.
4. P-12 analytics. Propose one privacy-friendly analytics tool (cookieless, EU-hosted if possible). Add it to the landing page. For the app itself, add it behind a config flag that stays off until counsel agrees, and track only page views and a "daily active owner" event.

Rules:
- Work on a branch, PR, CI green, then merge. Other sessions may share this tree: no `git stash`.
- Never commit secrets; document variables in .env.example only.

Done when: production answers on the real domain with OAuth and webhooks working, a backup and restore has been proven on Railway, frontend errors reach Sentry scrubbed, and P-07, P-08, P-12 have status lines in docs/review/pre-launch-problems.md.
```

---

## Session 5. UI polish

**Covers:** P-13, P-14, P-15, P-16.

```text
Goal: fix four UI problems found in screenshots from 2026-11-09. Later redesign commits may already have fixed some, so verify each in the running app first.

Read first:
- docs/review/pre-launch-problems.md, entries P-13 to P-16.
- The screenshots in .tmp/today-fixed-browser/ (if still present).
- The Today page components, the seven-day content grid, the Instagram performance chart, and the header command-palette trigger.

Steps:
1. Start the app with mocked API data and take screenshots of the Today screen at 390 px and 1440 px width, in light and dark mode. Compare with the old screenshots and tell me which of the four problems still exist.
2. P-13: on phones, keep "waiting for you", the command box and today's three numbers at the top. Collapse the other sections behind headers or link out to the pages that own them (Content, Reports). Desktop layout should not get worse.
3. P-14: show the "no story" prompt once for the week instead of in every day cell, and remove the duplicate "no story planned" card.
4. P-15: stop reach and views from looking flat. Either scale the axis to the data range or draw each metric as its own sparkline inside its card. Pick the option that reads best and explain why.
5. P-16: the header search trigger shows "Git…" at 1440 px. Give it a minimum width or show icon plus shortcut only. Check Turkish and English labels.
6. Take after screenshots at the same sizes and show me before and after.

Rules:
- Known CSS gotcha: .an-card is unlayered, so utilities like p-0 on Card are ignored.
- Keep tr and en i18n keys in sync. Update or add component tests and Playwright snapshots affected by the changes.
- Work on a branch, PR, CI green, then merge. Other sessions may share this tree: no `git stash`.

Done when: before/after screenshots show each problem fixed (or confirmed already fixed), CI is green, and P-13 to P-16 have status lines in docs/review/pre-launch-problems.md.
```

---

## Session 6. Self-service signup

**Covers:** P-10.

```text
Goal: let a new business owner create an account without the CLI or an invite.

Read first:
- docs/review/pre-launch-problems.md, entry P-10.
- backend/app/identity/router.py and the rest of the identity module (login, logout, password reset, invite acceptance, throttling), the email sending code, and the frontend auth pages and workspace wizard.

Build:
1. Backend: `POST /auth/register` (email, password, name, accepted terms version), email verification with a signed, expiring token, and resend-verification. Reuse the password reset token and email patterns and the existing login throttling. Unverified users can log in only to a "verify your email" screen. Do not reveal whether an email already exists (same response either way; send a "you already have an account" email instead).
2. A config flag SIGNUP_ENABLED (default off) so pilots can stay invite-only; when off the endpoint returns 404 and the UI hides the link.
3. Frontend: signup page, "check your email" page, verification landing page, then hand-off into the existing workspace wizard. tr and en strings.
4. Record terms/privacy acceptance with version and timestamp for the legal review.
5. Tests: backend unit and API tests (happy path, duplicate email, expired token, throttling, flag off), frontend tests, one Playwright journey from signup to the wizard. Regenerate the OpenAPI client.

Rules:
- Work on a branch, PR, CI green, then merge. Other sessions may share this tree: no `git stash`.
- Add a migration if needed and check it upgrades and downgrades cleanly.

Done when: with SIGNUP_ENABLED on, a new user can sign up, verify, and land in the workspace wizard; CI is green; P-10 has a status line in docs/review/pre-launch-problems.md.
```

---

## Session 7. Plans, quotas and usage warnings

**Covers:** P-11 (everything except taking payment).

```text
Goal: give each workspace a plan with a monthly reply quota that the owner can see, with warnings at 80% and 100%. No payment integration in this session.

Read first:
- docs/review/pre-launch-problems.md, entry P-11.
- docs/product/pricing-and-unit-economics.md (tiers and quotas), the LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY limit and where it is enforced, the System Health page, and the notification system.

Build:
1. A per-workspace plan record (plan name, monthly reply quota, period start, status such as trial/active/past_due) with a migration. Seed tiers from the pricing doc; ask me to confirm the numbers before hard-coding them.
2. A monthly reply counter that counts what the pricing doc counts (confirm with me whether that is sent replies, drafted replies or LLM calls), resetting at the period boundary. Keep the global daily LLM cap as a safety net.
3. Warnings at 80% and 100% through the existing notification channels, sent once per period each. Define what happens at 100% (suggested: drafting continues but auto-send stops and the owner is told). Ask me to confirm.
4. Owner-visible usage: a usage meter in Settings and a small indicator on Today when above 80%.
5. Operator CLI commands to set a workspace's plan and extend a period, for manual invoicing during pilots.
6. Tests for counting, period reset, both warnings firing once, the 100% behaviour, and the CLI. Regenerate the OpenAPI client. tr and en strings.

Rules:
- Work on a branch, PR, CI green, then merge. Other sessions may share this tree: no `git stash`.
- Update pricing-and-unit-economics.md so "quota warnings" is no longer marked planned.

Done when: plans, counter, warnings and usage UI work end to end in tests and locally; CI is green; P-11 has a status line in docs/review/pre-launch-problems.md noting that payment is still open.
```

---

## Session 8. Payments (optional, before selling tiers)

**Covers:** the payment part of P-11. **Before starting:** open a merchant account with iyzico or PayTR and have sandbox credentials ready.

```text
Goal: let an owner pay for a plan online, building on the plan and quota model from the previous session.

Read first:
- docs/review/pre-launch-problems.md, entry P-11 and its status line.
- The plan, quota and notification code added in the plans session.
- The provider's subscription/recurring payment API docs (iyzico or PayTR; ask me which one I chose).

Build:
1. A payment provider adapter behind an interface, with a fake implementation for tests, matching how other integrations in backend/app/integrations/ are structured.
2. Checkout for a plan, recurring charges, and webhook handling that updates plan status (active, past_due, cancelled). Verify webhook signatures and make handling idempotent.
3. Owner billing page: current plan, next charge date, change plan, cancel, invoice history. tr and en strings.
4. Failed-payment flow: grace period, owner notification, then downgrade behaviour agreed with me.
5. Tests with the fake provider and recorded sandbox payloads (sanitised). Regenerate the OpenAPI client.
6. Write down what the legal review must confirm (distance selling contract, invoice/e-Arşiv obligations, KVKK text) in docs/research/open-questions.md.

Rules:
- Sandbox only. Never commit credentials or real card data.
- Work on a branch, PR, CI green, then merge. Other sessions may share this tree: no `git stash`.

Done when: a sandbox payment activates a plan end to end, renewal and failure paths are tested, CI is green, and P-11 is marked done in docs/review/pre-launch-problems.md.
```
