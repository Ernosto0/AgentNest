# Session 14 report: agent settings and overview UI

**Status:** Offline complete and operator reviewed; focused backend/component checks and all three production-build browser projects passed.
This is offline fake/mock work. No live account action, paid evaluation, deployment,
commit or push was performed. Session 17/full phase and human phone acceptance remain separate.

## Baseline and scope

Started on clean `main` at `156e734` after Session 13. Implemented Session 14 in
`frontend/src/features/agent`, settings/navigation/cache integration, additive personality
contract fields and a bounded account overview. Session 15 owns its concurrently added
work/detail/reporting surfaces; Session 16 owns Meta adapter work. No migration was needed;
head remains `0030`. No OAuth work was overwritten.

## Behavior and contracts

- `/w/:workspaceId/more/agent` selects the connected account (optional `?account=UUID`)
  and shows current controller/state, persisted session counts, pending information and
  approval counts, recent action outcomes and provider capability availability. Simulation
  provenance stays visible. Unknown/queued actions are never labelled sent.
- Owner/manager edit 500-character goals, voice, channel styles and two TR/EN examples.
  PATCH personality uses its existing optimistic persona version. Goals are optional for
  old clients and preserve controller request metadata. The actual model context already
  reads `goals.instructions` as bounded untrusted data; the new test proves an API-saved
  goal reaches that model context without entering system authority.
- A local illustrative conversation sample uses saved/edited examples or tone, explicitly
  states it makes no model call, incurs no model cost and sends nothing. It is not a
  model-quality evaluation or promise that all style settings affect a generated result.
- All ten delegated actions have business-language labels, independent automatic/ask/off
  controls, daily limits and customer/authenticated-member request scopes. Preview binds
  config/delegation versions and request UUID; apply sends that same payload. The preview
  shows before/after modes, limits and source sets, including removed scopes.
- Owners deliberately confirm controller migration; pause/resume use backend config
  versions. The UI explains pending/in-flight effects cannot be undone. Managers cannot
  change delegation/control; staff can view settings and submit their own requests.
- Stale saves retain local edits and offer an explicit discard/refetch/review path. New
  field edits clear old save status. Successful saves adopt the returned version.
- The existing topic automation page remains for legacy accounts and opens the agent UI
  once agent controlled. Reconnect/disconnect/control changes invalidate agent caches.
  Request composer sends an idempotent task UUID, lists only requester-visible tasks and
  links to Session 15 progress/clarification routes. Overview links to questions/comments.
- New member-readable `GET /accounts/{id}/agent` exposes state/version/epoch, simulation,
  aggregate status counts and last-ten body-free action metadata. It does not expose
  prompts, private bodies, controller request IDs or hidden evidence. Unknown/foreign
  account/workspace IDs return 404. Account-agent contracts and generated API types updated.

## Verification and environment

Windows PowerShell, Python 3.12, Node/npm locked dependencies. Fake model, mock Instagram,
local media. Initial backend tests used disposable `agentnest_test`. Further verification
uses Python 3.12 in `agentnest-s14-api` on Docker network `agentnest_default` with
`UV_PROJECT_ENVIRONMENT=/tmp/s14-venv`; test database is the separate disposable
`agentnest_s14_backend_test`. The real API browser database is `agentnest_s14_e2e_test`.
Host virtualenv and development databases were preserved.

Actual verification evidence:

- `python -m uv run --directory backend pytest tests/integration/agent/test_settings_overview.py -q --tb=short`: 2 passed on Windows before socket exhaustion.
- `docker exec -e TEST_DATABASE_URL=postgresql+psycopg://agentnest:agentnest@postgres:5432/agentnest_s14_backend_test agentnest-s14-api uv run pytest tests/integration/agent/test_settings_overview.py tests/integration/agent/test_personality_context_loop.py -q --tb=short`: 7 passed; final run includes foreign persisted account isolation and saved-goal/model-context proof.
- Changed-module Ruff lint/format and mypy passed; `lint-imports`: 19 contracts kept.
- `npm.cmd --prefix frontend test -- src/features/agent/agent.test.tsx --maxWorkers=1`: 7 passed, covering owner/manager/staff, exact preview/apply, stale save/recovery, capability loss, local sample and explicit migration.
- `npm.cmd --prefix frontend test -- --maxWorkers=1`: 512 passed / 33 files at that checkpoint. Later recovery/capability-label edits have focused verification; final combined frontend result belongs to commander verification.
- Frontend lint/typecheck/i18n/build passed at the stable Session 15 schema checkpoint. The existing large-bundle warning remains. Last production build also passed with direct local API base URL for browser verification.
- `git diff --check`: passed at inspected checkpoint.

Earlier full frontend attempts with four workers had 503/504 and 509/512 passes with
varying one-second asynchronous query timeouts under host load. The complete 512-test
single-worker run supersedes those runs; focused retries alone were not counted as acceptance.
Temporary schema/type failures during concurrent Session 15 implementation were resolved
by its regenerated client and clean build, not ignored.

## Browser and visual evidence

`frontend/e2e/agent-settings.spec.ts` uses actual authenticated backend requests and UI,
not route mocks. It saves goals, previews/applies delegation, activates, pauses/resumes,
reloads persisted goals, checks TR/EN, keyboard activation, Axe in main and horizontal
layout at configured mobile/desktop viewports. The same canonical spec runs under the
existing three-project config. A temporary port/config override isolates this run from
other sessions: API 8014, preview 5114, disposable browser database. The production
bundle has been used for the final browser attempts.

Final Linux production browser run: **3/3 passed in 21.6 seconds**, no retries: mobile
Chromium, desktop Chromium and mobile WebKit. All three use the actual backend and
prove the journey above, including Axe, keyboard, TR/EN and no horizontal overflow.
The successful command inside the official `mcr.microsoft.com/playwright:v1.64.1-noble`
container was `npm ci`, then `npm run build -- --outDir /tmp/s14-dist`, then
`npx playwright test --config e2e/s14-linux.config.ts`. That temporary config selected
the canonical `agent-settings.spec.ts` and existing three browser/device definitions,
served the production bundle on 5114, and proxied local 8014 to the isolated API
container on the Docker network. Build and test results contain no external calls.
The temporary configs/proxy were removed after copying evidence.

Earlier Windows TCP exhaustion caused
`EADDRINUSE`/Winsock 10048 in Python migrations, Vite proxy and Playwright login; WebKit
also failed loading dev imports when local connections could not open. Browser binaries
were installed after an initial missing-executable attempt. These setup/transport failures
remain documented and were superseded by the complete clean Linux three-project run;
an isolated successful retry was never treated as clearing the whole run.

Mobile Chromium full-page screenshot was visually inspected: labelled controls wrap,
no horizontal overflow, 44px touch controls, distinct sections and simulation/state shown.
The form is intentionally long because ten action scopes are independently reviewable.
Final screenshots for all three projects and `browser.log` live under
`%TEMP%/agentnest-s14-linux-evidence/`. Each screenshot uses its test output directory.
The mobile Chromium full-page screenshot was inspected directly. This automated viewport inspection is
not a real-phone owner walkthrough.

## Acceptance and demo

- AC75-03: persisted role/versioned goals/voice and bilingual UI evidence; local sample
  only. Real-model tone/personality quality stays with Session 17.
- AC75-17: owner controls, deliberate migration and honest pending-outcome UI evidence;
  lifecycle backend regressions retain authoritative fencing proof. Rollout drill is later.
- AC75-20: component/keyboard/Axe/three-project production browser evidence for this surface; full phase browser and
  manual-phone acceptance remain distinct gates.

Credential-free demo: log in as owner, More > Account assistant, choose mock account,
set goals/style, inspect the no-cost local sample, preview delegation, review exact scopes
and apply, deliberately enable the assistant, pause/resume and inspect actual state.
Submit an instruction and follow its progress; fake unscripted tasks may hand off rather
than claim model intelligence. Switch to manager/staff to inspect role restrictions.

## Handoff

Stable `features/agent/hooks.ts`: `Schema`, `agentKey(ws, account)`, `useRefreshAgent`,
configuration/control/task hooks. Session 15 detail links use the same account query key
and route conventions. No new external capability or grant is enabled by migration.
Final combined cross-session checks and full-phase E2E/evals stay with Sessions 17-18; live Meta/real-model and
manual phone gates remain open.

The operator reran the final agent/legacy automation component pair after the last
legacy-route guard edit: **12 passed**. Frontend lint and typecheck also passed.
An initial concurrent component run had one 1.5-second heading timeout; the isolated
test and complete 12-test pair both passed on clean reruns. The operator removed the
dedicated Session 14 test databases and temporary API/browser containers after review.
