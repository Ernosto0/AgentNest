# Session 6: System health and the connections screen

**Plan:** `plan.md` §2 **H13**, §3 **P6-05** (health and UI). **Depends on:** session 5. **Commits:** `P6-05c: …` (system health API), `P6-05d: …` (SystemHealth, Connections, dev panel).

## Read first
- `observability.md` §6 and `workflows.md` §G.2 step 4 (signature failures).
- `inbox/webhooks_router.py` (how the `webhook.signature_invalid` audit is written), `jobs/models.py`, `ai/models.py` (agent runs, tokens).
- `LLM_PRICE_TABLE` and `LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY` in `config.py`.
- `frontend/src/features/settings/{AutomationSettings,SettingsPage,MorePage}.tsx`, the `DevPanel`, and the J2/J6 failure texts.

## Build
- `operations/system_health.py` and `GET /…/system-health` (`system_health.view`), with the H13 shape. Every section is workspace-scoped except the labelled system-wide signature count. All values are counts and codes: no payloads and no text.
- `features/settings/SystemHealth.tsx` at `more/settings/system-health`:
  - sections in plain language;
  - error codes rendered through `errors.<CODE>.what`;
  - a refresh button.
- `features/settings/Connections.tsx` at `more/settings/connections`:
  - account status with the vocabulary badge, the last error as plain language and the capabilities;
  - **Yeniden bağlan (simülasyon)** (moved here from `AutomationSettings`, which links to this screen), and disconnect with confirmation;
  - `degraded_until` shown as local time.
- Point the Home banner action from session 4 to this screen.
- Dev panel: a **Sağlık kontrolünü şimdi çalıştır** button.
- Settings and More menu entries.
- Regenerate the OpenAPI files.
- Docs:
  - `api-design.md` §2.8 (shape);
  - `observability.md` §6 (anything that differs);
  - `local-development.md` §6 G and §7 (where things now live).

## Done when
- Backend tests pass:
  - system health numbers equal fixture counts (accounts, operations 24 h, jobs, webhook counts, AI runs, cost from a price table);
  - **AC-G4**: the invalid-signature counter shows in the response;
  - isolation;
  - staff get 403.
- Vitest tests pass for each section, reconnect (calls the route and refreshes the status) and the dev button.
- Phase 5 E2E specs that used the reconnect button still pass (update their locators only).
- Full backend and frontend checks are green.
