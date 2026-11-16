# Feature Phase 1, Session 02: Test chat UI (F-02, part 2)

**Status:** Implemented and verified offline (unit/component tests, mocked-API screenshots). Not committed. Not run against the real backend or a real model.
**Baseline:** `main` at `f1cc494` plus the uncommitted Session 01 work in the tree. No backend files were changed and no migration was added (head is still `0046`; Session 03 uses `0047`).

## 1. What was built

An owner or manager can try the assistant as a customer, at the end of workspace setup and at any time from the Assistant page. It is built only on the Session 01 endpoints (`GET`, `POST /messages`, `POST /reset` under `/api/v1/workspaces/{id}/assistant/test-chat`), using the types already in `schema.d.ts`.

- **Chat screen** (`TestChat`): customer bubble, then the assistant reply with the **SIMULATED** badge on every reply, a standing "practice only, nothing is sent, nothing counts in reports" notice, the decision with a plain-language lead sentence ("Would wait for your approval", "A person would be asked to answer", ...), the reasons as plain sentences, and the facts used. For `human_required` or `blocked` there is no reply text; the screen says the assistant would not answer by itself, explains why, and shows `suggestion_text` only under "Wording to start from (not sent)". The server's ⟦ ⟧ markers around unverified values render as highlighted text with a hint.
- **Reasons:** each policy code maps to a TR/EN sentence (`testChat.reason.*`): all codes in the s01 handoff, plus `CONTAINS_*`, `AUTO_RATE_GUARD`, `HUMAN_TAKEOVER`, `CONTROLLER_CHANGED`, `POLICY_AUTO`. An unknown code gets a generic fallback sentence; a raw code is never shown. Duplicate sentences are collapsed.
- **Shared facts component** `frontend/src/components/FactsUsed.tsx`: takes plain `{label, display, verified_at}[]` (exported type `FactSource`), optional `timeZone` and `emptyLabel`. Shows "6.000 ₺ / ay" with "from: Monthly membership, verified Nov 3" (date in the workspace time zone, INV-19; year added only when it is not the current year). It is not tied to test-chat types, ready for Session 05.
- **Starter questions** (`suggestions.ts`): 4 to 6, in the workspace business language, computed from `business_category` and verified, usable facts (`useFacts`). Order: hours, a price question (names the first verified price item by label, else a generic "How much does it cost?"), location, booking (only if a booking/schedule fact exists), a question typical for the business type, a complaint (shows the hand-over), then the second price item, a service and contact if there is room. A question never contains a price, hour or contact value; unverified/expired facts are never used. Tapping one sends it.
- **Polling:** `useTestChat` uses `refetchInterval` as a function: 1.5 s while any turn is `pending`, `false` otherwise (a test proves it stops). Sending adds the pending turn to the cache and decrements the quota optimistically, then refetches. The send button is disabled while a turn is pending.
- **Quota and 429:** the remaining quota is shown only when 5 or fewer are left (gentle), and sending is disabled at zero. `TEST_CHAT_RATE_LIMITED` shows "Slow down a little" with the retry time from `params.retry_after` when present; what the owner typed is kept. The generic error catalog also got `errors.TEST_CHAT_RATE_LIMITED`.
- **Reset:** "Start over" clears the chat and brings the starter questions back.
- **Entry points:**
  - Route `/w/:id/more/agent/test` (`TestChatPage`, lazy). Staff see a "owners and managers only" notice and no request is made.
  - Button "Try your assistant" on the Assistant page header (`AgentPage.tsx`), hidden for staff, shown even without a connected account.
  - Last, skippable step of `CreateWorkspaceWizard`: the workspace is created at the end of the third step as before; the fourth step ("Try it") then shows the same chat for the new workspace (`WizardTryStep.tsx`) with a note that no business details exist yet, so most answers will say a person is needed. The bottom button reads "Skip for now" until a message is sent, then "Continue to business details"; both go to the knowledge checklist. Nothing navigates automatically.

## 2. Files

New: `frontend/src/components/FactsUsed.tsx`, `frontend/src/features/test-chat/{hooks.ts,suggestions.ts,TestChat.tsx,TestChatPage.tsx,testChat.test.tsx}`, `frontend/src/features/workspaces/WizardTryStep.tsx`, `frontend/src/i18n/locales/{en,tr}/testChat.json` (keys `testChat.*`, `factsUsed.*`).
Changed: `frontend/src/app/router.tsx` (route), `features/agent/AgentPage.tsx` (button), `features/workspaces/CreateWorkspaceWizard.tsx` (4-step progress, `created` state, try step), `features/workspaces/wizard.test.tsx`, `src/i18n/index.ts` (registers the new catalog), `locales/{en,tr}/common.json` (`entry.steps.try`, `entry.wizardIntro` now mentions trying the assistant, `errors.TEST_CHAT_RATE_LIMITED`).
Screenshots and this report are under `docs/implementation/features-phase-1-before-first-pilot/`.

## 3. Checks run (from `frontend/`; Vitest from PowerShell)

| Command | Result |
|---|---|
| `npm.cmd run typecheck` | passes |
| `npm.cmd run i18n:check` | passes (en, tr, 2376 keys, 1729 literal `t()` calls) |
| `npm.cmd test` (full) | 50 files, 744 tests passed |
| `npx vitest run src/features/test-chat` | 16 passed |
| `npm.cmd run build` | built OK (existing Rollup `INEFFECTIVE_DYNAMIC_IMPORT` warnings only) |
| `npm.cmd run lint` | **3 errors, all pre-existing in `src/app/router.tsx` lines 9, 13, 22 (`no-explicit-any` in `lazyNamed`)**; the same lines are in `HEAD`. No warnings or errors from files I wrote (one `react-refresh` warning in `FactsUsed.tsx` was fixed). I did not fix the router `any`s because they are not mine. |

The new tests cover: starter questions from verified facts only (and no values stated); tap to send, pending then ready, simulated badge, decision, reason sentence, facts with source and date, and polling stops; human-required explanation with an unknown reason code falling back, suggestion marked "not sent" with a highlighted unverified value; 429 message with retry time and kept text; low quota note and send disabled at zero; reset; load error with retry; staff blocked with no request; `FactsUsed` (time zone date, unknown date, empty); suggestion logic in TR and with no facts; the Assistant page button for owner, manager and not staff; the wizard step (skip, and send then continue, no navigation until chosen). Not tested in unit tests: iOS/real-device behaviour, keyboard overlap with the on-screen keyboard.

## 4. Screenshots (390 px wide, 2x, mocked `**/api/v1/**` on a Vite dev server)

Path: `docs/implementation/features-phase-1-before-first-pilot/screenshots/s02/`
- `01-empty-suggestions-tr.png` empty state with suggested questions (TR)
- `02-approval-reply-with-facts-en.png` approval_required reply, reasons, facts used (EN)
- `03-human-required-explained-tr.png` approval reply plus a complaint with the human-required explanation and suggested wording (TR)
- `04-writing-and-low-quota-en.png` pending "writing" state and low-quota note (EN)
- `05-wizard-final-step-tr.png` wizard final step (TR)
- `06-assistant-page-button-tr.png` Assistant page button (TR)

The script checked no horizontal overflow and no page errors for each. Full-page shots were taken in a tall viewport so the fixed bottom navigation sits at the bottom. The fixtures are hand-written, so the reply wording is illustrative, not real model output. Port 5173 was already in use by someone else's server, so I used my own Vite on 5188 and stopped it afterwards (5173 untouched). The script lives outside the repo (session scratchpad).

## 5. Invariants

INV-09 (badge on every simulated reply, plus a notice that nothing is sent or counted); INV-02 (the UI only displays server-grounded facts, suggestions never state values, unverified values are highlighted and never shown as the reply); INV-18 (wording says "would be sent", "would wait", never "sent" or "approved"); INV-19 (dates in the workspace time zone); INV-10 (no secrets involved); both languages shipped with `i18n:check` passing.

## 6. Deviations and open questions

1. **Wizard order.** The workspace is created at the end of step 3 (as before) and the try step runs after creation, because the endpoints need an existing workspace. The progress bar now shows 4 steps and "Step 4 of 4"; the existing tests were updated, and the success path no longer navigates straight to the knowledge checklist.
2. **The wizard chat has no facts**, so answers are mostly "a person is needed". I said so in the UI. If product prefers the chat after knowledge entry, the same `TestChat` can move to the checklist; the permanent button covers that.
3. **Legacy pipeline only** (s01 open question 1): the UI does not say that an account running the agent controller may behave differently. Needs a product decision.
4. Date format follows the app (en: "Nov 3", tr: "3 Kas"), not "3 Nov" from the brief's example.
5. Starter questions are in the workspace's business language, not the UI language, because that is what its customers write; the chat labels stay in the UI language.
6. "Customer message" input is a textarea; Ctrl/Cmd+Enter sends. The input is not sticky above the bottom nav; on a long chat the owner scrolls to it (new messages scroll into view automatically, not tested in jsdom).
7. Not verified: real backend integration (the s01 endpoints were only exercised through mocks matching `schema.d.ts`), the real model's behaviour, `Retry-After` header (only `params.retry_after` is used), and screen-reader behaviour on a device.
8. No backend fixes were needed.

## 7. Handoff to Session 03 and 05

- Session 03's migration number is still `0047`.
- Session 05 should import `FactsUsed` and `FactSource` from `@/components/FactsUsed` and feed it the server's placeholder-to-fact mapping (`rendered_facts` has `label`, `display`, and a version but no verified date today, so the draft API will need `verified_at`).
- Working-tree note: Session 01's uncommitted backend changes are present and untouched; the other modified files in `git status` (docs, backend) are not mine.
