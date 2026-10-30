# Phase 8.5 Session 04 report: shell, navigation and route compatibility

Executed 2026-10-31, Europe/Istanbul. Scope: P8.5-04 only. **Implemented and
locally verified; operator review and real-stack/human acceptance remain pending.**

## Baseline and scope

Started from `main@76dac88`, accepted Session03. Read Sessions01–03 reports,
baseline decisions, CLAUDE, invariants, phase/session/specification, current
roadmap and relevant navigation/auth/authorization/provenance/ADR025 contracts.
Phase8 deployment and backup work through Session04 is present; it does not add
security/reset/privacy browser APIs. These remain upstream dependencies for23.

Preserved existing README/roadmap/task-breakdown edits, the pre-existing planned
redesign paragraph in user-journeys, and untracked planning/specification/concept
files. Updated only implemented navigation paragraphs in user-journeys; the
operator must stage those independently of the pre-existing paragraph. No backend,
API/schema, effect, permission, query-key or product route changed. No database,
worker, real provider, paid model, email, waitlist or storage service was used.
This agent did not commit, push, deploy or invoke destructive E2E setup.

## Implemented behavior

- **S09 — shell:** `frontend/src/app/layout/AppShell.tsx` and `navigation.ts`
  implement a240px expanded charcoal sidebar from1200px, a96px tablet rail from
  768px with expand-label button, and five native phone tabs below768px. Compact
  tablet uses an `AN` text abbreviation with the full retained product name
  available accessibly; expanded/sidebar and phone show the full wordmark.
  Phone brand and controls reflow into two rows so360px does not truncate identity.
  Direct desktop Assistant, Knowledge and Reports links retain existing URLs.
  Staff keep Reports for server-authorized inbox metrics; Activity/Health stay
  owner/manager and developer tools use the existing metadata gate.
- Page context supplies native workspace/parent links without a second h1. The
  feature still owns its heading. Nested routes select one desktop parent;
  phone More covers its nested destinations. Working content can use1440px;
  settings/legacy forms keep a readable column. Router declarations are unchanged.
- `SimulationBanner.tsx` uses one compact static disclosure for demo/offline
  context. Non-demo fake-AI workspaces receive only the offline notice. Demo
  context never labels all provider effects simulated. Existing per-result
  badges, feature connection warnings and account/controller semantics remain.
- **S10 — workspace selection:** `WorkspaceSwitcher.tsx` consumes an explicit
  safe-section/filter mapping. Conversation/content/question/thread details fall
  back to their list; memory/task details fall back to Assistant; saved report
  evidence falls back to Reports. Known categories and utility sections remain.
  Only section-specific filters are carried; account/detail/cursor/snapshot and
  arbitrary identifiers are discarded. Unknown paths fall back to workspace home.
  `baseline-decisions.md` records this reviewed refinement to the initial handoff.
- **S11 — notifications:** semantic bell styling retains the existing notification
  query, server `unread_count`,9+ visual cap and accessible full-count name. It
  adds neither polling nor a live region. Full notification redesign remains22.
- **S12 — destination launcher:** `DestinationLauncher.tsx` reuses the shared
  BottomSheet. Header button and Ctrl/Cmd+K open localized native destination
  links, filtered locally with Turkish-aware casing. Arrow/Enter and Tab work;
  Escape closes even with nonempty filter text. Pointer launch explicitly returns
  to the header opener, including WebKit; shortcut launch restores prior focus.
  Shared modal trapping/background isolation is retained. No record-search,
  command execution, mutation or extra private-context query is introduced.
- **R32 — More:** shared PageHeader/ListRow and semantic panels group assistant/
  business, workspace and account destinations. Existing workspace-create/switch
  and sign-out remain available. Local24px stroke icons extend the existing family.
  TR/EN catalogs supply all new labels. Only the navigation Home label becomes
  Today/Bugün; the Home feature heading remains unchanged until06.

Tests and E2E selectors were scoped to the intended main-content destination or
notification bell after desktop navigation introduced legitimate duplicate links.
Existing auth, effect and feature-heading assertions were retained. Existing
phase1/i18n/scenario navigation expectations now use Today while Home headings
continue to assert their current labels. `user-journeys.md` documents shipped
navigation, launcher, environment context and safe switching.

## Verification

Commands were run individually from `frontend/` unless stated otherwise:

| Check | Observed final result |
|---|---|
| `npm.cmd run lint` | Exit0; no findings |
| `npm.cmd run typecheck` | Exit0 |
| `npm.cmd test` | Exit0;36 files,552 tests,61.22s at the integration revision before adding the route-manifest compatibility assertion |
| `npm.cmd test -- src/app/layout/navigation.test.tsx` | Exit0;20 tests after adding the manifest assertion; all32 concrete routes and2 wildcard fallbacks still match |
| `npm.cmd run i18n:check` | Exit0; EN/TR1437 keys,892 literal calls |
| `npm.cmd run build` | Exit0;276 modules; pre-existing >500kB chunk warning remains |
| `node scripts/ui-shell.mjs` | Exit0;12 production fixture scenarios across Chromium156.0.8078.4/WebKit27.2 |
| `git diff --check` from root | Exit0; only Git's Windows line-ending normalization notices |

The20 focused tests prove safe switching across11 section/detail combinations,
parent selection, all baseline route matches, owner/manager/staff and dev gating,
localized filtering/keyboard navigation, pointer/shortcut focus return, no
command mutation, URL/history retention and revoked/foreign membership fallback.
Existing notification navigation and per-result simulation assertions pass in the
full suite. Initial test failures due to old Home labels and unscoped duplicate
links were corrected; no required assertion was disabled.

`frontend/scripts/ui-shell.mjs` serves the production build at loopback5185,
intercepts all API GETs with fictional responses, rejects mutations and blocks
all external origins. No E2E global setup is imported. Final evidence is
[shell.json](evidence/s04/shell.json), plus24 **viewport** captures named
`{chromium|webkit}-{tr|en}-{width}-{role}-{more|launcher}.png`. They are not
full-page screenshots; the fixed phone tab bar is shown at its actual viewport
edge. Frozen Session01 before-captures remain unchanged.

Each browser covered TR360 staff, EN390 manager, TR768 owner, EN1024 staff,
TR1440 owner and EN1920 manager, all900px tall. All12 final scenarios have:

- Zero shell and open-launcher axe violations under WCAG2/2.1/2.2 AA tags,
  zero page errors and zero attempted external requests.
- Document width equal to viewport, usable long-name selection and correct
  compact/expanded sidebar or five-tab phone navigation.
- Authoritative unread12 displayed as9+, staff report access, hidden staff
  Activity/Health and no developer entry when metadata disables tooling.
- Locale-aware filtering, input focus entry, Escape, pointer-opener return,
  shortcut prior-field return and tablet label expansion.
- Direct inbox query retained across refresh; safe workspace switch removes old
  account/snapshot/arbitrary IDs; browser Back/Forward restores the proper URLs.

TR360 phone, TR768 rail and EN1920 desktop captures were visually inspected for
brand readability, hierarchy, wrapping, focus and tab placement. The exact query
list is recorded in JSON: initial More still makes4 GETs (auth, metadata,
workspace, notifications), matching the original baseline. Launcher opening and
filtering issue no requests. Cold local More timings range708–931ms including
`networkidle` and fixture fulfillment; these are not field/API latency measurements.

Using the same Node `gzipSync` measurement, production JS is841049 bytes/243272
gzip versus Session03's830381/239685 (+10668/+3587). CSS is37112/8357 versus
35939/8230 (+1173/+127). Local fonts remain173280 bytes; no image or third-party
asset/dependency was added. These changes are below the50KiB-gzip JS review trigger.

## Acceptance and handoff

Updated R32 and S09–S12 in `screen-coverage.md`. This supplies local evidence for
UI-01/02/03/04/07/08/09/10 without closing whole-application acceptance. UI-05/06
remain authoritative through unchanged feature APIs, status/provenance and data
contracts. Unsupported navigation counts/search/metrics were omitted.

No final implementation/check failure remains in the listed checks. Real-stack
E2E is assigned to the operator's dedicated disposable database after05; it was
not run by this session. Actual screen-reader speech, physical phone/software
keyboard, real browser200% zoom, all nested feature states and owner acceptance
remain pending their sessions. Browser fixtures do not satisfy those human gates.

Session05 can consume the stable shell, shared fields/headers and existing
RequireAuth return-to behavior for login, invites, picker and the three-step
wizard. Preserve the newly documented safe-switch boundary and S03 pointer vs
shortcut focus return. Do not migrate Home, inbox/content details or add upstream
security/reset/privacy controls as part of05. Operator review/commit follows;
there is no deployment or live-account authorization here.
