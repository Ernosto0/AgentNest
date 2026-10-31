# Phase 8.5: Complete Application UI and UX Redesign

**Status:** Planned on 2026-10-30. This document records the requested redesign; it does not claim implementation or acceptance.
**Execution plan:** [28 implementation sessions](../phase-8.5-sessions/phase-8.5-sessions.md).
**Design specification:** [Application UI specification](../../product/ui-redesign-specification.md).
**Visual reference:** [Interactive AgentNest concept](https://agentnest-style-preview.woollyhero2.chatgpt.site), with retained [source and instructions](../../../design-preview/agentnest-today/README.md).

## 1. Objective

Replace the application's current generic, narrow stack of cards with the warm, refined workspace demonstrated by the concept: a charcoal-green navigation rail, warm off-white canvas, white working surfaces, deep teal actions, restrained sage accents, readable typography, visual content previews and layouts shaped around each task.

This is a complete UI phase. Every application route, tab, editor, dialog, drawer, notification, loading/empty/error state and role-dependent control must be inventoried, redesigned and verified. The same design language extends to the existing public landing page and transactional presentation surfaces. The result must remain Turkish-first, mobile-first, accessible, credential-free in local demo mode and faithful to the existing backend contracts.

The main product goals are:

1. Owners can identify what needs their decision, understand the assistant's current work and reach the next action without navigating a long settings form.
2. Desktop space supports conversations, previews and decision context side by side; phone layouts focus on one task at a time.
3. The interface distinguishes information requests, human approvals, delegated automatic actions and verified execution outcomes.
4. Business knowledge and content become useful working areas rather than undifferentiated lists of cards.
5. Secondary screens and difficult states receive the same design treatment as the dashboard.

## 2. Position in the roadmap

Phase 8.5 is a new presentation and interaction phase between the existing hardening and owner-channel plans. It does not renumber or replace Phase 8 or Phase 9.

- **Baseline:** the implemented Phase 7/7.5 offline application, existing regression suites, current frontend routes, and the Phase 8 contracts actually delivered when each session starts.
- **Proposed default sequence:** Phase 8 engineering, Phase 8.5 redesign, then the Phase 9 owner-channel experience. Phase 9's underlying adapter dependencies remain unchanged.
- **Independent work:** design inventory, tokens, components and existing-route migration can proceed against stable contracts when assigned. Use an isolated checkout if Phase 8 is changing overlapping frontend files. Backend/live acceptance is not a prerequisite for static design preparation.
- **Phase 8 dependencies:** complete the security, password reset, data-rights, deletion-status and operational extensions only against their delivered typed APIs. Record missing contracts as named dependencies and finish independent screens. Do not substitute pretend controls.
- **Final integration:** redesign acceptance includes every Phase 8 user-facing surface delivered in the agreed baseline. If required Phase 8 surfaces remain undelivered, report partial redesign acceptance with explicit remaining rows; do not declare the whole phase complete.
- **Existing gates:** production/data, platform capability, model quality, legal review, App Review and real-account acceptance remain owned by their existing phases. This plan adds UI acceptance; it does not retroactively redefine a completed gate or authorize a pilot.

Creating this plan does not start implementation. It does not authorize deployment of the application, live messages, public release, paid evaluations, commits or pushes. The already published standalone design concept remains a reference artifact, not an application deployment.

## 3. Read first

- [Repository working rules](../../../CLAUDE.md), [invariants](../../invariants.md), [roadmap](../roadmap.md) and [testing strategy](../testing-strategy.md).
- [UI specification](../../product/ui-redesign-specification.md), [current user journeys](../../product/user-journeys.md), [acceptance criteria](../../product/acceptance-criteria.md), [personas](../../product/personas-and-use-cases.md) and [MVP scope](../../product/mvp-scope.md).
- [State machines](../../architecture/state-machines.md), [workflows](../../architecture/workflows.md), [API design](../../architecture/api-design.md), [security and privacy](../../architecture/security-and-privacy.md), [account-agent contracts](../../architecture/account-agent-contracts.md).
- [ADR-013](../../architecture/decisions/ADR-013-authentication-and-tenancy.md), [ADR-014](../../architecture/decisions/ADR-014-approval-and-policy-model.md), [ADR-021](../../architecture/decisions/ADR-021-simulation-provenance-boundary.md), [ADR-022](../../architecture/decisions/ADR-022-privacy-redaction-and-audit-retention.md), [ADR-024](../../architecture/decisions/ADR-024-account-agent-and-delegated-autonomy.md), [ADR-025](../../architecture/decisions/ADR-025-phase-8-hardening-contracts.md).
- Latest [Phase 7.5 summary](../phase-summaries/phase-7.5-summary.md), [Phase 8 sessions](../phase-8-sessions/phase-08-sessions.md) and the latest actual session report. Inspect source, not just historical status text.

## 4. Scope and exclusions

### Included

- Shared design tokens, typography, icons, buttons, form controls, lists, tables, tabs, status badges, notices, skeletons, empty states, dialogs, drawers and feedback.
- Authenticated shell, public/auth shell, workspace switching, desktop navigation, mobile bottom navigation, breadcrumbs and a navigation/command launcher.
- All currently registered application routes, including developer tools and not-found paths; see the route inventory in the UI specification.
- Today dashboard, existing command workflows, inbox, conversation detail, content library, calendar/agenda, editing/media/scheduling, approval queue and decision history.
- Assistant overview, tasks and task clarification; voice/goals; delegation; legacy automation; owner questions; comments and moderation; private customer memory.
- Knowledge overview, all categories and value editors, suggestions, extraction, history and approved answers.
- Reports and evidence drilldowns, activity, notifications, settings, connections, members/invites, health and development-only tooling.
- Integration of Phase 8 account-security, reset, export/erase and deletion lifecycle UI when their contracts exist.
- Public landing/waitlist presentation and existing transactional/status presentation, with truthful feature availability and unchanged delivery/consent contracts.
- Route compatibility, permission visibility, internationalization, accessibility, performance checks, visual/browser evidence and final owner walkthrough.

### Excluded unless separately requested

- New social networks, billing, bookings/payments, CRM features, Reels/video production or AI image generation.
- New automation authority, broader customer identity linking, new report metrics or changed approval/state semantics.
- A framework rewrite, backend replacement, global service search or a new notification delivery channel.
- Dark-mode rollout. The app receives one finished light workspace with dark navigation; preserve an existing landing theme toggle without promising app theme parity.
- Marketing re-positioning, a product rename or copying the fictional studio, metrics, assistant name, photos and conversational claims into live business data.

## 5. Boundaries that the redesign must preserve

1. Reuse React, TypeScript, Vite, React Router, TanStack Query, Tailwind and i18next. Extract reusable UI from the concept; do not embed its standalone HTML, DOM event handlers or in-memory sample mutations in production screens.
2. Existing hooks, typed responses, error catalogs, authorization, workspace/account routing and query-cache boundaries remain authoritative. Any unavoidable API change gets an explicit contract decision and the usual backend/isolation checks.
3. Preserve all existing deep links, query parameters, notification targets, invite links and browser Back behavior. New tab state may use documented query parameters; a route rename requires a compatibility mapping and tests.
4. Navigation grouping is not authorization. Owner, manager and staff visibility must match current permissions; a disabled button never grants authority and hiding a route is not a security control.
5. Simulation provenance is per result/account, not inferred from the workspace, photo storage or an attractive global banner. Compact the global explanation but retain readable simulated badges on affected outcomes.
6. Approved, queued, sending, checking, scheduled and completed are distinct. No optimistic success label for an external effect; no automatic re-send from a redesigned retry button.
7. The agent's public comment context cannot expose private messages, owner-only answers or customer memory. Owner answers and task clarification are not approvals.
8. All dates use the workspace timezone. Reports, badges, calendar placement and scheduling share formatting helpers and actual persisted state.
9. Self-host production fonts and necessary visual assets, retaining license/source records and Turkish glyphs. CI and the core demo cannot depend on Google Fonts, Unsplash, analytics or image-CDN access.
10. Preserve user-entered data and meaningful focus across failed saves, drawer changes, refreshes and permission/conflict errors. Do not persist customer text in new browser storage or telemetry.

## 6. Tasks and implementation order

Each task maps to the equally numbered session. Sizes express scope, not a delivery-time promise. A large session can span work periods and must report partial completion honestly.

| ID | Deliverable | Dependencies | Size |
|---|---|---|---|
| P8.5-01 | Current route/control/state inventory, role map, baseline screenshots and UX contracts | Stable existing frontend; actual Phase 8 inventory | M |
| P8.5-02 | Semantic design tokens, typography, icons and licensed local assets | 01 | M |
| P8.5-03 | Accessible shared controls, forms, overlays, lists and state patterns | 02 | L |
| P8.5-04 | Responsive authenticated/public shells, navigation and deep-link compatibility | 03 | L |
| P8.5-05 | Login, invite acceptance, workspace selection and creation/onboarding | 04 | M |
| P8.5-06 | Today dashboard, readiness, attention hierarchy and existing commands | 04–05 | L |
| P8.5-07 | Inbox filters, conversation list and responsive list/detail workspace | 06 | M |
| P8.5-08 | Conversation messages, drafts, composer, takeover and source details | 07 | L |
| P8.5-09 | Content library, state tabs, thumbnails, empty and problem views | 08 | M |
| P8.5-10 | Read-only planning calendar/agenda and scheduling review flows | 09 | L |
| P8.5-11 | Content editor, media handling, preview, validation and recovery | 10 | L |
| P8.5-12 | Approval queue, all subject summaries, decision detail and history | 08, 11 | L |
| P8.5-13 | Assistant overview, owner task intake and task progress/clarification | 12 | L |
| P8.5-14 | Goals/voice, delegation controls, controller cutover and legacy automation | 13 | L |
| P8.5-15 | Owner questions, answer/proposal history and reusable-knowledge flow | 14 | M |
| P8.5-16 | Public comments, thread context and manual moderation results | 15 | L |
| P8.5-17 | Private customer memory, sources, correction and removal | 16 | M |
| P8.5-18 | Knowledge overview, readiness, category navigation and fact browsing | 17 | M |
| P8.5-19 | All typed fact editors, extraction, suggestions and version history | 18 | L |
| P8.5-20 | Approved-answer library, creation/archive and grounding review | 19 | M |
| P8.5-21 | Daily reports, evidence drilldowns and honest data visualization | 20 | M |
| P8.5-22 | Activity, notification center, bell and destination recovery | 21 | M |
| P8.5-23 | Settings, Phase 8 security/reset, privacy/export/erase/deletion surfaces | 22; delivered Phase 8 contracts | L |
| P8.5-24 | Instagram connections/OAuth, members, invites and ownership actions | 23 | L |
| P8.5-25 | System health, developer simulator and global fallback/error polish | 24 | M |
| P8.5-26 | Landing/waitlist and existing transactional/status visual alignment | 25; approved content/delivery contracts | L |
| P8.5-27 | Whole-app mobile, accessibility, TR/EN and performance remediation | 01–26 | L |
| P8.5-28 | Full regression, route/state coverage reconciliation and owner acceptance | 27 | L |

The sequence is an execution default. Session 01 may split an oversized session or move independent work only with an explicit updated dependency map; no route or acceptance item can silently disappear. Do not implement unassigned later sessions merely because they are listed here.

## 7. Acceptance criteria

| ID | Required outcome | Evidence |
|---|---|---|
| UI-01 | Every baseline route and added Phase 8 UI surface has an owner, redesigned layout, applicable state coverage and completed evidence row | Session 01 inventory reconciled in 28; route manifest diff |
| UI-02 | The application consistently expresses the concept's visual language through shared semantic tokens and components | Token/component reference; representative before/after captures; no unexplained legacy screen |
| UI-03 | Desktop, tablet and phone layouts are task-appropriate; primary tasks remain reachable with touch, keyboard and browser Back | Viewport matrix; all-route phone overflow check; split-view/back-navigation tests |
| UI-04 | Existing permission, workspace/account isolation and private/public context behavior is preserved | Owner/manager/staff matrix, workspace-switch tests and existing isolation/security suites |
| UI-05 | Approval, publishing, sending, unknown outcome, supersession, expiry and recovery labels remain truthful | Existing state tests plus redesigned UI integration/browser cases |
| UI-06 | Prices/facts, report values, assistant claims and calendar entries derive from authorized persisted data | Hook/API mappings; grounding/report evidence checks; no sample constants in runtime UI |
| UI-07 | All screens, errors, validation and state labels work in TR and EN with correct currency, glyphs, plurals and workspace time | i18n check; long-content captures; timezone/day-boundary cases |
| UI-08 | Keyboard, focus, dialogs, menus and contrast meet the specified accessibility targets; manual checks supplement automation | Axe on representative states; keyboard/screen-reader checklist; zoom/reflow evidence |
| UI-09 | Fonts/media work offline as required; no new third-party runtime dependency or unbounded rendering/query regression | Offline browser run; asset/license inventory; build/network/performance comparison |
| UI-10 | All existing deep links and workflow entry points remain valid, including notification/report targets and legacy automation | Route compatibility tests; direct URL/refresh/back-forward browser matrix |
| UI-11 | The landing/waitlist and delivered Phase 8 security/privacy/status surfaces use the same brand language without changing their contracts | Public/auth capture set; waitlist contract checks; Phase 8 integration evidence |
| UI-12 | Required regression checks pass; the owner completes the daily-work walkthrough on Windows and an actual phone | Session 28 report, required CI evidence and recorded device/owner acceptance |

Completion requires all twelve criteria. A screenshot or successful standalone concept cannot prove API integration, safety, accessibility of other screens or whole-phase acceptance.

## 8. Verification and evidence

Per session, run the focused checks for the changed behavior and capture the changed screens/states. Do not create tests that merely repeat CSS class strings or duplicate the implementation. Shared interactive controls, permissions, route state and effect-related status transitions merit meaningful tests.

The final session runs the existing frontend lint, typecheck, component tests, i18n parity and production build; configured Playwright Chromium/WebKit projects against the real fake/mock stack; current required backend, isolation/security, generated-client and fake-evaluation checks from CI. Run the landing package checks when changed. Record unrelated baseline failures distinctly and do not claim a clean acceptance run with failures outstanding.

Use disposable databases and local media roots for E2E. Existing E2E resets data. Never reseed the default database as part of a visual review. Mask personal data in screenshots and avoid tokens, customer messages and invite/reset secrets in artifacts.

Screen evidence uses the matrix in the UI specification: representative desktop and mobile states in both languages, all-route navigation/overflow coverage, role-specific controls, destructive confirmations and unusual operation outcomes. Record software/browser versions and environment; browser emulation is not a phone walkthrough.

## 9. Migration, completion and rollback

1. Establish tokens and shared components before migrating features; use current hooks and state helpers throughout.
2. Keep each intermediate session runnable. Remove old components only after their final consumer is migrated and associated regressions pass.
3. Preserve current URLs; do not maintain two separate mutation implementations for old and new layouts.
4. Update [user journeys](../../product/user-journeys.md) alongside each implemented navigation/interaction change. Until then, this specification is the planned target and the existing journey document describes current behavior.
5. Maintain a screen coverage ledger in this session directory from Session 01. Reports and the final phase summary are created from actual work, never pre-populated with expected passes.
6. At Session 28, produce `docs/implementation/phase-summaries/phase-8.5-summary.md` with changed files, acceptance evidence, demo steps, remaining limits and rollback instructions. Do not create that success summary during planning.
7. A UI rollback normally restores the previous frontend build. Recheck schema/API compatibility and applicable Phase 8 headers/CSP before selecting an artifact; a rollback never bypasses backend authorization or restores stale approved payloads.

## 10. Risks and decisions to settle in Session 01

| Risk/decision | Default and required action |
|---|---|
| Phase 8 frontend work changes during redesign | Freeze a named baseline per session, inspect worktree, isolate conflicting work and integrate delivered contracts before final acceptance |
| The concept implies data not present in APIs | Produce a data-source matrix; omit unsupported charts, trends, counts and availability claims or explicitly plan a separately reviewed contract extension |
| Calendar APIs return an incomplete or capped list | Prove full visible-range membership before calling it a complete calendar; otherwise provide the existing honest agenda and record the required range/pagination contract |
| Small, low-contrast concept metadata copied literally | Apply the production typography/contrast floors in the specification, not the sample's smallest text sizes |
| Warm copy obscures serious controls | Use explicit action/outcome wording for deletion, unknown sends, approvals and permission changes; warmth belongs in supporting copy |
| New navigation accidentally changes access | Existing permission sources decide visibility; verify every entry under all three roles and foreign/removed membership |
| Overlays erase context or become long forms | Use desktop detail panels, phone detail pages/full-screen editors and dirty-state handling according to task length |
| A partial migration is declared complete | Track all routes and nested controls; Session 28 reconciles source inventory, planned tasks and observed states |
| New legal/provider assumptions enter presentation copy | Reuse reviewed wording and capability evidence; label unresolved upstream decisions without inventing acceptance |

Session 01 records concrete decisions on breakpoints, secondary tab URLs, icon/font packaging, performance baselines and any missing data contracts. Significant architecture changes require an ADR before implementation; visual choices alone do not rewrite accepted ADRs.
