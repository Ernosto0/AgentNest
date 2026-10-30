# Phase 8.5 Session 03 report: shared controls and modal behavior

Executed2026-10-31, Europe/Istanbul. Scope:P8.5-03 only. **Implemented and locally
verified; feature-wide migration, manual screen-reader and physical-device
acceptance remain pending.** No whole-phase acceptance is claimed.

## Baseline and preserved work

Started from `main@ebb1f88` (accepted Session02), after Session01 `88da6c2` and
Phase8 deployment/backup through Session04 (`276dac6`). Read the repository
working rules, phase/session/specification, current roadmap, baseline decisions,
previous report and relevant invariant/auth/approval/provenance/testing contracts.
ADR-025 future auth/reset/privacy contracts remain undelivered browser work;
nothing in03 adds those APIs or controls.

Preserved dirty README/roadmap/task-breakdown/user-journeys changes, untracked
phase plans/specification and concept. No backend/schema/API, permission, query
key, route, status key or effect behavior changed. No commit, push, deployment,
E2E reset, live provider/model/email/waitlist/storage call or user-data reset was
performed by this agent. The operator reviews and commits this work.

## Implemented behavior and sources

- **S01:** `components/Button.tsx` uses semantic action/focus tokens and44px
  targets. Backwards-compatible `pending` disables duplicate activation and
  exposes busy state; optional visible `disabledReason` joins descriptions
  without replacing the button node. Native type defaults to `button`, explicit
  submit remains available. React19 refs support explicit overlay opener return.
- **S02:** `TextField.tsx`, `FormFields.tsx`, `Field.tsx`, `fieldIds.ts` keep native
  input/textarea/select/checkbox/radio behavior. Caller/generated IDs, external
  descriptions, hints and errors are correctly linked; invalid/readonly/disabled
  and16px form roles use semantic styling. Native values, names, password-manager
  attributes and caller refs are forwarded. Old knowledge `editors/fields.tsx`
  re-exports shared textarea/select to preserve every existing consumer.
- **S03:** `Card.tsx` uses a quiet surface/border. `Layout.tsx` provides page/panel
  headers, native-control filter groups, divided rows and labelled internally
  scrollable tables. `Pagination.tsx` accepts caller-owned previous/next callbacks
  and localized labels. All new primitives have actual interactive DEV specimen
  consumers; no data/search/cursor backend abstraction was added.
- **S04:** `BottomSheet.tsx`, `modalFocus.ts` implement topmost-only Escape/backdrop,
  initial/trapped/returned focus, nested-safe background `inert`/`aria-hidden`,
  exact attribute/scroll-style restoration, safe-area padding and long-content
  scrolling with reachable header/footer. `dismissible={false}` disables close
  button/Escape/backdrop. `initialFocusRef` chooses a safe initial target;
  `returnFocusRef` supplies an explicit opener. Detached openers safely fall back
  to prior focus or the parent modal. Dirty-form decisions remain feature-owned
  through `onClose`; new dirty-state business behavior is outside03.
- **S05:** semantic `EmptyState`, `ErrorMessage`, `FullScreenStatus`; `Feedback.tsx`
  supplies linked validation summary, static-by-default notices, decorative
  skeletons and dismissible noncritical toasts. Static notices are not repeated
  live announcements. Conflict/removed-source presentation uses explicit labels
  and existing localized errors, without inventing a success or recovery action.
- **S06/S07:** `StatusBadge`, `SimulatedBadge` and `LanguageSwitch` adopt semantic
  tokens. Canonical status keys, distinct labels/icons and per-result simulation
  remain unchanged. LanguageSync/saved-locale behavior is unchanged.
- `dev/SharedReference.tsx` extends the existing DEV-only reference with all new
  controls, real local interactions and long/nested sheets. Both TR/EN use local
  fonts; it makes no API calls. Production excludes this fixture. Usage examples
  and migration/handoff notes: `components/README.md`, `dev/README.md`.

No feature page was migrated beyond the shared knowledge field compatibility
module. Whole-feature filters/tabs, dirty editors, effect outcomes and role/account
matrices remain with their assigned sessions. These controls do not imply a new
menu framework or global search contract.

## Checks and observed evidence

Final commands from `frontend/`, run separately, all exit0:

| Command | Observed outcome |
|---|---|
| `npm.cmd run lint` | Clean;0 errors/warnings |
| `npm.cmd run typecheck` | Passed |
| `npm.cmd test` | **533 passed in35 files** |
| `npm.cmd run i18n:check` | EN/TR parity:1415 keys,888 literal calls |
| `npm.cmd run build` | Passed; existing >500kB monolithic-chunk warning remains |
| `node scripts/ui-components.mjs` | Four fixture browser scenarios and eight axe scans passed |
| `git diff --check` from repository root | Clean |

New `controls.test.tsx` covers native type/pending duplicate protection, visible
reason linkage, supplied/generated IDs, merged feedback, retained input,
textarea/select/checkbox/radio semantics, error-summary focus, restrained notices,
loading, toast dismissal and cursor callbacks. `BottomSheet.test.tsx` covers
focus/trap/return, nesting, topmost Escape, background/scroll restoration,
nondismissible behavior, latest callback, missing opener and explicit-opener
fallback. Existing full feature/status/language tests pass after shared migration.

Fixture browser environment: Windows, Node26.4.0, Europe/Istanbul,
**Chromium156.0.8078.4 and WebKit27.2**, each with **TR360×900 and EN1440×900**.
Vite DEV origin `http://127.0.0.1:5186`; service workers blocked; every API and
external-origin request blocked. Observed **0 API calls,0 external requests and
0 page errors**. Each engine/locale passed axe WCAG2A/AA,2.1AA and2.2AA tag scans
on the controls and open modal: **0 violations across8 scans**. This is browser
egress isolation, not a host-wide network sandbox or real backend verification.

Keyboard automation proves initial focus, forward/reverse Tab wrapping, nested
Escape, explicit opener return, default prior-input return and parent close
return. Error-summary links focus the invalid field and saving retains the entered
value. Caller-controlled pagination advances the visible fixture row. The long
phone sheet occupies y16–900 with884px height; desktop sheet y24–876 with852px
height,512px width. Header/footer remain within the900px viewport. Document widths
equal viewport widths; CSS200% stress probes also report no horizontal page
scroll. This CSS probe is not physical-device/browser zoom acceptance.

WebKit exposed its native pointer behavior: a clicked button need not become
focused. Returning to prior focus alone therefore cannot guarantee opener focus.
The optional `returnFocusRef` now gives callers a deliberate opener target; tests
also verify default prior-focus behavior and detached-target fallback. No global
button focus behavior was changed to override platform conventions.

Raw browser observations: [components.json](evidence/s03/components.json).
Full-page controls and actual viewport sheet captures:

| Browser | Controls | Open sheet |
|---|---|---|
| Chromium TR360 | [controls](evidence/s03/chromium-tr-360-controls.png) | [sheet](evidence/s03/chromium-tr-360-sheet.png) |
| Chromium EN1440 | [controls](evidence/s03/chromium-en-1440-controls.png) | [sheet](evidence/s03/chromium-en-1440-sheet.png) |
| WebKit TR360 | [controls](evidence/s03/webkit-tr-360-controls.png) | [sheet](evidence/s03/webkit-tr-360-sheet.png) |
| WebKit EN1440 | [controls](evidence/s03/webkit-en-1440-controls.png) | [sheet](evidence/s03/webkit-en-1440-sheet.png) |

TR360 modal and EN1440 full controls captures were visually inspected for readable
hierarchy, wrapping, focus and footer placement. All status specimens retain
labels/icons; mock sent result retains its separate simulation modifier. Browser
axe contrast findings are zero on actual control/notice/status surfaces. The
existing Session02 measured palette/local font evidence is inherited; no new
font or third-party asset/dependency was added. Session01 before captures stay
frozen, and these are shared specimens rather than claimed redesigned feature
screens.

Production output measured with the same `gzipSync` as prior sessions:
JS830381 bytes/239685 gzip versus02's827152/238334 (+3229 raw/+1351 gzip);
CSS35939/8230 versus02's35212/8029 (+727 raw/+201 gzip).
Fonts remain173280 bytes total. The
shared interaction cost stays far below the50KiB-gzip JS review trigger; this
build comparison is not route timing or field performance acceptance. The DEV
reference string is absent from production JS.

## Acceptance, limitations and handoff

Updated **S01–S07** in [screen-coverage.md](screen-coverage.md), with explicit
observed evidence and remaining dependencies. This supplies local shared-pattern
evidence for **UI-02,UI-03,UI-07,UI-08,UI-09**, preserves canonical truth/provenance
under **UI-05**, and keeps API/permission/route ownership under
**UI-01,UI-04,UI-06,UI-10**. It does not close whole-application acceptance.

No final check failure remains. Actual screen-reader speech, physical phone,
software keyboard, real200% browser zoom, broader role/account/controller states,
all feature-specific conflict/removed-source interactions and production browser
acceptance remain pending their owners. Browser automation and accessible
relationships do not substitute for a human screen-reader walkthrough. Real-stack
E2E was deliberately left to the operator's later dedicated disposable database
run; no default E2E setup was invoked. Backend regression was not rerun because
there is no backend/API change.

Session04 can use shared headers/rows/notices and BottomSheet for navigation
drawer/launcher. Pass a stable explicit opener ref, label navigation as navigation
and retain native links/URL state. Session05 can use shared fields, linked
validation and pending controls without importing from knowledge editors. Keep
feature queries, role checks, failure-retained values and canonical errors/statuses
authoritative. Session06+ owns further collection/feature adoption; no later
session is declared implemented here.
