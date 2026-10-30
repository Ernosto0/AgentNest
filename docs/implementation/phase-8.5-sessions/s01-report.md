# Phase 8.5 Session 01 report

Date: 2026-10-30 (Europe/Istanbul). Assigned scope: P8.5-01 inventory, baseline and design contracts. Status: **implemented and locally verified; operator review required; redesign and human acceptance remain unverified**. Branch/commit inspected: `main@641b1f5` (Phase8 Session02). No commit, deployment, external effect, database reset or paid evaluation performed by this session agent.

## Delivered

- [screen-coverage.md](screen-coverage.md): R01–R37 disposition, exact router reconciliation (32 concrete SPA patterns, two wildcard leaves),14 category values,11 typed editors, shared and nested controls, state/role/language/layout obligations, hidden task/question/comment/memory entry points. U/B/P statuses distinguish inventory, original captures and undelivered upstream contracts.
- [baseline-decisions.md](baseline-decisions.md): responsive shell and widths, route/query preservation, scoped account selection, safe workspace-switch handoff, destination-only launcher, local fonts/icons/identity, mutation/status truthfulness, typed source mapping and explicit omissions for unsupported trends/time savings/complete calendar/counts. Session02 packaging is ready to consume this record.
- `frontend/scripts/ui-baseline.mjs`: production-browser capture utility; local-only origin, intercepts all API GETs with fictional data, rejects API mutations, blocks external origins. Supports `UI_BASELINE_ORIGIN` and distinct `UI_BASELINE_OUTPUT` for later after-captures. Does not load destructive Playwright global setup or use credentials.
- [evidence/s01/baseline.json](evidence/s01/baseline.json) plus six original PNG captures: login TR390/EN1440; Today owner TR1440/EN390; More staff TR360; workspace picker owner EN1440. Height900, Chromium156.0.8078.4, Windows, Node26.4.0, timezone Europe/Istanbul. Empty report/no-account/content fixtures are explicitly labelled by this report; no source metrics or images invented in product code.

No product behavior was changed. No planning document, user-owned existing edit, backend contract or design-preview artifact was overwritten. Existing dirty deployment/backend/docs work and untracked phase/canonical/spec documents remain user-owned dependencies. Source contracts used: CLAUDE/invariants, UI specification and canonical phase, roadmap/testing strategy/current journeys/acceptance/personas/scope, state machines/workflows/API/security/account-agent contracts, ADR013/014/021/022/024/025, latest Phase7.5 summary and Phase8 Session02 report, current router/exports/hooks/schema and E2E setup. ADR025 future contracts were not mistaken for implemented security/privacy APIs.

## Checks and observed evidence

Commands ran separately from `frontend/` on the unchanged product baseline:

| Command/check | Observed result |
|---|---|
| `npm.cmd run lint` | Exit0, no findings |
| `npm.cmd run typecheck` | Exit0 |
| `npm.cmd run i18n:check` | Exit0; EN/TR1415 keys,888 literal calls verified |
| `npm.cmd test` | Exit0;33 files,516 tests passed;85.84s |
| `npm.cmd run build` | Exit0;270 modules; existing >500kB chunk warning |
| `npm.cmd run preview -- --host 127.0.0.1 --strictPort --port 5185` | Local production build served for fixture checks; no backend started |
| `node scripts/ui-baseline.mjs` | Exit0; six captures/JSON,0 page errors/external-origin attempts; all six document widths equal viewport |
| Router/export reconciliation |34 path declarations + index + pathless auth wrapper =36 objects;32 concrete pages R01–R32 and2 wildcard leaves R33. No additional delivered Phase8 SPA routes found |

Measured raw/gzip bytes: JS827145/238323; CSS29135/6659; zero font/image payload in these fixtures. Today made9 API GETs, auth2, More4, picker1. Both Today→More transitions added0 API requests; script now waits for URL and expected localized More heading before recording timing. The JSON retains exact measured cold/subsequent timings and payloads. Cold timing includes the `networkidle` quiet window; API latency is fixture fulfillment and is not a real-stack measurement. CLS is explicitly unmeasured (`null`). System fonts are the original baseline. Vite's reported gzip differs from Node gzip settings; subsequent comparisons must use the same method.

Interaction costs/source review: desktop and phone Home→Assistant/Knowledge/Reports each use More then target (2 activations), no global navigation search exists. Memory is reachable only from question/private DM thread context; task detail from Agent task row; comments from account Agent links. Session04 targets single desktop activation for Assistant/Knowledge/Reports while retaining current URLs and phone More.

Full real-stack `npm.cmd run e2e` was **not run**: its global setup resets database data, and a dedicated disposable target was not established for this documentation-only baseline. Backend/landing suites were not rerun because no backend/landing source changed. WebKit, screen reader, actual phone, zoom/software keyboard, image-heavy route timings and human acceptance remain pending. These are not failed tests or silently accepted states. No pre-existing frontend check failure was observed; the monolithic-chunk build warning is recorded for comparison.

## Acceptance and handoff

UI-01: source ownership/inventory delivered; redesigned route coverage pending each feature. UI-06: current typed sources mapped and unsupported claims omitted by decision; future implementations must preserve these bindings. UI-09: baseline assets/query/payload/timing and blocked-external fixture captures recorded; font/offline/CLS measurements belong to02 and performance reconciliation27. UI-10: route/query/hidden-entry contract documented; source and fixture navigation baseline recorded, full compatibility checks belong to04 and feature sessions. UI-02/04/05/07 are preserved by making no product mutations; redesigned/role-transition/state/localization acceptance is not claimed. UI-03/08/11/12 remain with their assigned sessions and external/human gates.

Next sequence:02 semantic tokens/local licensed Manrope+Inter/Latin-ext, local stroke icon normalization and development reference;03 shared controls/overlays with meaningful focus/keyboard tests;04 responsive shell/role-aware destinations/launcher/safe switch/route compatibility;05 auth/invite/picker/three-step onboarding. The operator serializes shared catalog/ledger changes and reviews before commit. Keep original S01 artifacts frozen; later capture runs must set `UI_BASELINE_OUTPUT` to their own session directory. No Session06 dashboard migration, undelivered reset/privacy controls, real-account gates or deployment is included.
