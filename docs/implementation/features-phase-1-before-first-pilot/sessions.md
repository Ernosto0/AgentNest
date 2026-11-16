# Feature Phase 1: Before the First Pilot

**Status:** Implemented offline; stopped for review. Sessions 01 to 05 are done (see [s01-report.md](s01-report.md), [s02-report.md](s02-report.md), [s03-report.md](s03-report.md), [s04-report.md](s04-report.md), [s05-report.md](s05-report.md) and the [phase summary](../phase-summaries/features-phase-1-summary.md)). Nothing is committed. The next migration is `0049`.
**Source:** [pre-launch-feature-recommendations.md](../../review/pre-launch-feature-recommendations.md) §4, step 1.
**Features:** F-02 (test chat), F-01 (installable app and push), D-01 (visible "never invents a price" guarantee).
**Sessions:** 5, run in order. Each session is a scope boundary, not a time promise.
**Why this phase first:** these three features address the two biggest pilot risks: owners not trusting the assistant, and owners not seeing approvals (RK-03).

---

## 1. Plan

| Session | Feature | Scope | Main deliverables |
|:---:|---|---|---|
| 01 | F-02 | Test chat backend and scope update | Sandbox conversation for real workspaces, endpoints outside the dev panel, report exclusion, `mvp-scope.md` update |
| 02 | F-02 | Test chat UI | "Try your assistant" screen, last onboarding step, permanent button on the Assistant page |
| 03 | F-01 | Installable app and push subscriptions | Manifest, icons, push-only service worker, `push_subscriptions` table, VAPID config |
| 04 | F-01 | Web Push owner channel | `web_push` channel in the registry, delivery for approvals, owner questions and failures, opt-in prompt, iOS guide |
| 05 | D-01 | Visible guarantee and phase close-out | Fact source beside every number in a draft, "Unverified values: 0" report line, demo script, phase summary |

## 2. Starting state

- `main` at `f1cc494` or later. Migration head was `20261114_0045_hardening_and_recovery_fixes.py` and the next migration was `0046`. **Session 01 used `0046` (`assistant_test_chat`), so the next free migration is `0047`.** Confirm the head before editing; another session may have moved it.
- Simulation exists only in the dev panel: `backend/app/demo/dev_router.py` (`/simulate/customer-message`, `/simulate/comment`, `/simulate/owner-native-reply`) and `backend/app/demo/simulator.py`. These routes require `DEMO_TOOLS_ENABLED`.
- Inbox models already have `is_simulated` columns (`backend/app/inbox/models.py`).
- The owner-channel abstraction exists: `backend/app/integrations/channels/base.py` (`OwnerChannel` protocol), `registry.py`, and `backend/app/notifications/delivery_policy.py` (quiet hours). Only `web` and `telegram` are registered.
- `frontend/public/` has `app-icon-1024.png` only. There is no manifest and no service worker.
- Workspace creation is `frontend/src/features/workspaces` (`CreateWorkspaceWizard`). The Assistant page is `frontend/src/features/agent/AgentPage.tsx`.
- "PWA install + Web Push" is on the deferred list in [mvp-scope.md](../../product/mvp-scope.md) §4. Session 01 moves it, and F-02, into scope.

## 3. Common working rules

Before each session, read [CLAUDE.md](../../../CLAUDE.md), [invariants.md](../../invariants.md), this file's common rules and the session brief, and the previous session's report in this folder.

1. **Preserve unrelated work.** Check `git status`, the migration head and uncommitted changes first. Other sessions may be working in the same tree. Do not use `git stash`. Do not reseed or reset shared databases.
2. **Follow the invariants.** Every new tenant table has `workspace_id NOT NULL`, RLS enabled and forced, and policies on `app.workspace_id`. Foreign IDs return 404. There are no external calls inside a DB transaction. Time comes from the injected `Clock`. Secrets never appear in the repo, logs, job payloads, API responses or the frontend.
3. **Keep simulated data marked.** Anything simulated has `is_simulated = true` and a visible badge. It never reaches Instagram and never counts in reports.
4. **Update docs with contracts.** When a schema, endpoint, state, job type, env var or notification type changes, update the matching document in `docs/architecture/` or `docs/operations/` in the same change.
5. **Ship both languages.** Every user-facing string has Turkish and English translations, and `npm run i18n:check` passes.
6. **Report truthfully.** Separate what is implemented offline, what local tests verified, and what still needs a real phone or account. Do not record expected passes.
7. **Do not commit or push** unless the user asks.

**Checks.** Backend, from `backend/`: `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run lint-imports && uv run pytest <paths>`. Frontend, from `frontend/`: `npm.cmd run lint && npm.cmd run typecheck && npm.cmd test && npm.cmd run i18n:check && npm.cmd run build`.

**Report.** Each session writes `sNN-report.md` in this folder. It records status, baseline commit, migration head, files changed, contracts, exact test commands and results, invariant notes, open questions and the handoff to the next session.

---

## 4. Session briefs and prompts

### Session 01: Test chat backend and scope update (F-02, part 1)

**Goal.** A real workspace can send test customer messages and get the draft the assistant would produce, with the facts it used. Nothing is sent, and nothing counts in reports.

**Work**
- Update [mvp-scope.md](../../product/mvp-scope.md): move "PWA install + Web Push" out of §4 Deferred, and add the test chat and the visible guarantee to the in-scope list. Add a "Feature Phase 1" entry to [roadmap.md](../roadmap.md) that links to this file.
- Read the simulation path in `demo/simulator.py` and `demo/dev_router.py`. Extract the shared ingestion and drafting logic into a service that does not depend on `DEMO_TOOLS_ENABLED`.
- Add a sandbox conversation per workspace (or per user). It uses `is_simulated = true` and a clearly synthetic customer identity, and it is never linked to a real Instagram account.
- Add workspace-scoped endpoints, for example `POST /workspaces/{id}/assistant/test-chat/messages`, `GET .../test-chat` and `POST .../test-chat/reset`. Restrict them to owner and manager roles. The response includes the draft text, the decision (`auto`, `approval_required`, `human_required` or `blocked`), the reason, and the list of facts used (key, display value, verified date).
- Draft generation stays asynchronous if it is today. The endpoint must then either poll or return a run ID. Follow the existing job pattern; do not add a second one.
- Guarantee that nothing is sent: the send executor and the operations ledger must refuse simulated conversations. Add a test that proves no `send_reply` job or operation row is created.
- Exclude test chat from reports, the home "attention" counts, customer memory, approval queues and the notification feed. Check `reporting/definitions.py` and `reporting/metrics.py`; most metrics already filter `is_simulated`, so verify each one.
- Add rate limits per workspace so the test chat cannot be used as a free LLM.
- Update `docs/architecture/api-design.md` with the new endpoints.

**Out of scope.** UI (Session 02). Changing draft quality or prompts.

**Done when.** Tests cover role checks, isolation (a foreign workspace gets 404), no send or operation, report exclusion, reset, and the rate limit. All backend checks pass.

```text
Implement Feature Phase 1, Session 01 (test chat backend and scope update) from docs/implementation/features-phase-1-before-first-pilot/sessions.md.

Read CLAUDE.md, docs/invariants.md, and the file's "Starting state" and "Common working rules" first. Then follow the Session 01 brief: update mvp-scope.md and roadmap.md, extract the simulation path out of the dev-only router into a service, add workspace-scoped test-chat endpoints that return the draft, decision, reason and facts used, prove that nothing is ever sent or counted in reports, and add rate limits.

Run the backend checks, write docs/implementation/features-phase-1-before-first-pilot/s01-report.md, and stop. Preserve unrelated work. Do not commit or push.
```

---

### Session 02: Test chat UI (F-02, part 2)

**Goal.** The owner can try the assistant at the end of setup and at any time from the Assistant page.

**Depends on.** Session 01 endpoints.

**Work**
- A "Try your assistant" screen, built mobile-first in the existing design system (`frontend/src/components`; note the `.an-card` CSS gotcha). It is a chat view where the owner types as a customer and sees the proposed reply with the "simulated" badge.
- Under each reply, show the decision and the facts used ("from: Monthly membership, verified 3 Nov"). For `human_required` or `blocked`, explain in plain words why a person would be asked. Session 05 reuses this fact-source component, so make it a shared component.
- Show 4–6 suggested questions based on the workspace's category and its verified facts, so the owner does not face an empty box.
- Add a Reset button.
- Add it as the last step of `CreateWorkspaceWizard` (skippable), and as a permanent button on `AgentPage.tsx`.
- Add TanStack Query hooks with typed API clients, following the existing feature folders.
- Add component tests: rendering, the facts-used list, the human-required explanation, and the empty and error states. Add TR and EN strings.

**Out of scope.** Backend changes beyond small fixes found while integrating.

**Done when.** All frontend checks pass. The report includes screenshots at phone width (mocked API is fine; see the working-environment notes).

```text
Implement Feature Phase 1, Session 02 (test chat UI) from docs/implementation/features-phase-1-before-first-pilot/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 02 brief and s01-report.md first. Build the mobile-first "Try your assistant" screen on the Session 01 endpoints: show the simulated badge, the decision with a plain-language reason, a reusable "facts used" component, suggested starter questions and reset. Add it as the last, skippable step of CreateWorkspaceWizard and as a permanent button on the Assistant page. Add TR and EN strings and tests.

Run the frontend checks, capture phone-width screenshots, write s02-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

---

### Session 03: Installable app and push subscriptions (F-01, part 1)

**Goal.** The web app can be installed on a phone, and the backend can store a user's push subscription.

**Work**
- Add `manifest.webmanifest` with name, short name, Turkish-first description, theme and background colours from the design tokens, `display: standalone` and `start_url`. Generate 192, 512 and maskable icons from `frontend/public/app-icon-1024.png`, plus an Apple touch icon. Link them in `frontend/index.html`. Coordinate with P-17 in the problems document (favicon and meta tags) if it is not done yet.
- Add a minimal service worker that handles `push` and `notificationclick` only. It has no offline cache and no fetch handler. Clicking a notification opens the deep link in the payload, which is limited to the app's own origin. Register it in `main.tsx` only in production builds, or behind a flag for local testing.
- Add the next migration (`0047_push_subscriptions` after Session 01 took `0046`; confirm the head first) with a tenant table: `workspace_id`, `user_id`, endpoint, `p256dh` and `auth` keys (keys encrypted with the existing token encryption helper), user agent label, `created_at`, `last_success_at`, `revoked_at`. Enable RLS and add grants. Make the endpoint unique per user.
- Add endpoints to subscribe, list the current user's devices, and unsubscribe. Return no key material in responses.
- Add `WEB_PUSH_VAPID_PUBLIC_KEY`, `WEB_PUSH_VAPID_PRIVATE_KEY` and `WEB_PUSH_SUBJECT` settings. The public key is served to the frontend through an endpoint. Document them in `docs/operations/environment-variables.md`, and add a CLI command or documented step that generates a key pair.
- Choose the push library (for example `pywebpush`). Record the dependency choice in the report and run the dependency audit runbook.
- Update `docs/architecture/data-model.md`.

**Out of scope.** Sending notifications (Session 04). The opt-in UI beyond a developer test button.

**Done when.** Migration upgrade and downgrade are clean, RLS isolation tests pass, keys are never returned, and Lighthouse or Chrome DevTools reports the app as installable on a production build.

```text
Implement Feature Phase 1, Session 03 (installable app and push subscriptions) from docs/implementation/features-phase-1-before-first-pilot/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 03 brief and s02-report.md first. Add the web manifest and icons, a push-only service worker (no offline cache), the next migration (0047 after Session 01 took 0046) with an RLS-protected push_subscriptions table with encrypted keys, subscribe, list and unsubscribe endpoints, and VAPID settings. Document the env vars and the data model.

Verify that migration upgrade and downgrade are clean, that isolation holds, and that the app is installable. Write s03-report.md in the same folder and stop. Preserve unrelated work. Do not commit or push.
```

---

### Session 04: Web Push owner channel (F-01, part 2)

**Goal.** Owners get a phone notification for approvals, owner questions and failures, through the same delivery policy as Telegram.

**Depends on.** Session 03.

**Work**
- Implement a `WebPushChannel` that satisfies `OwnerChannel` in `backend/app/integrations/channels/web_push/`. Register it in `registry.py`. Keep core modules free of imports from it, and add an import-linter contract like the Telegram one.
- Deliver through the existing `notification_deliveries` ledger and `delivery_policy.py` (quiet hours, critical bypass). Send outside DB transactions. Retry on 5xx or timeout with the existing job pattern. Mark a subscription revoked on 404 or 410.
- Payloads carry a title, a short body and a deep link. They contain no customer message text and no personal data beyond what the notification type already allows, because push services are third parties. Write this rule in `docs/architecture/security-and-privacy.md`.
- Scope it to `approval.requested`, owner questions and publish or send failures first. List the notification types in `notifications/catalog.py`.
- Add per-user, per-type opt-in settings next to the Telegram ones in Settings.
- Show an opt-in prompt after the owner's first approval, not on first load. On iOS Safari outside standalone mode, show a short "Add to Home Screen" guide instead, because push does not work there until the app is installed.
- Add tests: delivery success, 410 revocation, quiet hours, isolation, payload contents (no message text), and that the import linter stays clean.
- Update `docs/architecture/integrations.md` §5 (owner channels).

**Out of scope.** Approve or reject buttons inside the notification. Approvals stay in the app, because action tokens in push payloads would need their own security review.

**Done when.** Offline tests pass. The report states whether a real device test (Android Chrome, and iOS from the home screen) was done or is still pending.

```text
Implement Feature Phase 1, Session 04 (Web Push owner channel) from docs/implementation/features-phase-1-before-first-pilot/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 04 brief, s03-report.md, and docs/architecture/integrations.md §5 first. Implement WebPushChannel against the OwnerChannel protocol, register it, deliver approvals, owner questions and failures through the existing delivery ledger and quiet-hours policy, revoke subscriptions on 404/410, keep customer text out of payloads, add per-type opt-in settings, the post-first-approval prompt and the iOS home-screen guide. Add an import-linter contract.

Run the backend and frontend checks, write s04-report.md in the same folder (state clearly whether a real-device test was done), and stop. Preserve unrelated work. Do not commit or push.
```

---

### Session 05: Visible guarantee and phase close-out (D-01)

**Goal.** Owners can see that every number in a reply comes from a verified fact, and that nothing unverified was sent.

**Work**
- In the draft and approval views (inbox conversation, approval list and detail, Telegram approval message), show the fact source beside each value that came from a `{{fact:key}}` placeholder: "from: <fact label>, verified <date>". Use the component from Session 02. Expose the rendered placeholder-to-fact mapping in the draft API if it is not exposed already. Do not compute it in the frontend.
- Add two lines to the daily report and its Telegram summary: replies sent, and "unverified values sent: 0". The second number comes from claim-validator results for sent replies, not from a constant. If it is ever above zero, it links to the drill-down.
- Write a short demo script in `docs/operations/` that starts with the price-change hold: change a price by command, then show the held scheduled post and the updated draft.
- Phase close-out: run all backend and frontend checks, then write `docs/implementation/phase-summaries/features-phase-1-summary.md`. It covers the changes, the tests behind each feature, demo steps, deviations, limitations, and items still waiting on a real device or account. Update `roadmap.md`.

**Done when.** All checks pass, the summary is written, and the session stops for review.

```text
Implement Feature Phase 1, Session 05 (visible guarantee and phase close-out) from docs/implementation/features-phase-1-before-first-pilot/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 05 brief and s04-report.md first. Show the verified-fact source beside every placeholder-derived value in drafts and approvals (web and Telegram), using a server-provided mapping. Add "replies sent" and "unverified values sent" lines to the daily report, computed from claim-validator results. Write the price-change-hold demo script.

Then close the phase: run all backend and frontend checks, write s05-report.md and docs/implementation/phase-summaries/features-phase-1-summary.md, update roadmap.md, and stop for review. Preserve unrelated work. Do not commit or push.
```
