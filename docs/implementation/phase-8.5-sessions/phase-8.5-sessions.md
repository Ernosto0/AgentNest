# Phase 8.5: UI Redesign Implementation Plan and Sessions

**Status:** Completed and locally verified across all 28 sessions (Session 01–28); physical operator device walkthrough pending live deployment.
**Canonical phase:** [Complete application UI and UX redesign](../phases/phase-8.5-ui-redesign.md).
**Screen and design contract:** [UI specification](../../product/ui-redesign-specification.md).
**Session count:** 28 sequential scope boundaries. A session can span multiple work periods; its number is not an estimate in days.

## Short plan

1. Inventory the real application and its Phase 8 dependencies before changing the presentation.
2. Establish reusable tokens, components and responsive shells.
3. Migrate daily work: Today, inbox, content and approvals.
4. Migrate the assistant, questions, comments, memory and business knowledge.
5. Migrate reporting, notifications, settings, security/privacy, team and operator surfaces.
6. Align the public/transactional presentation, then complete accessibility, responsive and regression verification across the entire inventory.

The [interactive concept](https://agentnest-style-preview.woollyhero2.chatgpt.site) supplies the visual direction. Its sample numbers, photos, fictional identity, miniature type sizes and local-only actions are not production requirements. Preserve the existing typed APIs and all invariants.

## Session and acceptance mapping

Every session inherits UI-01 route coverage, UI-02 visual consistency, UI-04 authorization, UI-05 truthful state and UI-07 localization. The last column lists additional emphasis, not an exemption from those common requirements.

| Session | Scope | Task | Additional acceptance emphasis |
|---|---|---|---|
| 01 | Inventory, contracts and baseline | P8.5-01 | UI-06, UI-09, UI-10 |
| 02 | Tokens, fonts, icons and assets | P8.5-02 | UI-08, UI-09 |
| 03 | Shared interactive components and states | P8.5-03 | UI-03, UI-08 |
| 04 | Shell, navigation and routing | P8.5-04 | UI-03, UI-10 |
| 05 | Login, invites and workspace onboarding | P8.5-05 | UI-03, UI-10 |
| 06 | Today and commands | P8.5-06 | UI-06 |
| 07 | Inbox workspace | P8.5-07 | UI-03, UI-10 |
| 08 | Conversation, drafts and composer | P8.5-08 | UI-03, UI-06 |
| 09 | Content library | P8.5-09 | UI-06 |
| 10 | Calendar, agenda and scheduling | P8.5-10 | UI-03, UI-06 |
| 11 | Content editing, media and preview | P8.5-11 | UI-03, UI-06, UI-09 |
| 12 | Approvals and history | P8.5-12 | UI-06, UI-10 |
| 13 | Assistant overview and tasks | P8.5-13 | UI-06 |
| 14 | Voice, delegation and legacy controls | P8.5-14 | UI-03 |
| 15 | Owner questions | P8.5-15 | UI-06 |
| 16 | Comments and moderation | P8.5-16 | UI-06, UI-10 |
| 17 | Customer memory | P8.5-17 | UI-06 |
| 18 | Knowledge overview and categories | P8.5-18 | UI-03, UI-06 |
| 19 | Typed editors, extraction and suggestions | P8.5-19 | UI-03, UI-06 |
| 20 | Approved answers | P8.5-20 | UI-06 |
| 21 | Reports and saved evidence | P8.5-21 | UI-06, UI-10 |
| 22 | Activity and notifications | P8.5-22 | UI-06, UI-10 |
| 23 | Settings, account security and privacy | P8.5-23 | UI-10, UI-11 |
| 24 | Connections, members and invites | P8.5-24 | UI-10, UI-11 |
| 25 | Health, developer tools and fallbacks | P8.5-25 | UI-09, UI-10 |
| 26 | Landing and transactional presentation | P8.5-26 | UI-09, UI-11 |
| 27 | Cross-app remediation | P8.5-27 | UI-03, UI-07, UI-08, UI-09 |
| 28 | Final regression and acceptance | P8.5-28 | UI-01 through UI-12 |

## Common execution rules

Before each session, read [CLAUDE.md](../../../CLAUDE.md), the canonical phase, UI specification, current roadmap and the previous session report. Read the referenced workflow/state/ADR contracts relevant to the session. Inspect branch/commit, actual routes, API/schema changes and unrelated work; the baseline may have moved since planning.

1. Run the assigned session in order. Keep later work at an explicit boundary; do not declare a partial session complete to fit a work period.
2. Use shared semantic tokens and React components. Preserve existing hooks, permission checks, query keys, scope, error catalogs and server-owned status.
3. Update implemented user journeys/navigation documentation alongside the corresponding code. Significant architecture/API changes need their proper decision and tests; do not solve a missing contract with a fake control.
4. Keep both TR and EN complete, and verify applicable owner/manager/staff cases, account modes and state transitions during each feature migration.
5. Capture representative desktop/phone before-and-after states with fictional data. Update the coverage ledger as work is observed; never prefill pass results.
6. Preserve native links, deep links, query state, keyboard focus and Back behavior. Confirm unsaved changes where meaningful and retain input on failure.
7. Keep the credential-free demo and local assets functional. Do not make live Meta/model, waitlist, email or storage calls to prove a presentation change.
8. Use disposable databases and a dedicated local media root for destructive/reset tests. Do not reseed or delete the user's existing workspaces.
9. Session reports distinguish implementation, local/browser verification and human/external acceptance. Session 28 requires an actual phone walkthrough; emulation does not replace it.

### Verification commands

Run commands separately from `frontend/` as appropriate to changed code:

```powershell
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run i18n:check
npm.cmd run build
npm.cmd run e2e
```

Use focused test selections while migrating, then the required complete suites at Session 28. Existing E2E global setup resets its database; verify the dedicated target first. Use the production build for final browser acceptance and retain all configured Chromium/WebKit projects.

For changed `landing/` code run its existing typecheck and build, plus meaningful browser checks for waitlist and language/theme behavior. For backend/API changes, run affected backend, permission/isolation and generated-client checks and update the API documents. Final regression includes the backend and fake-evaluation checks currently required by CI, using [local-development.md](../../operations/local-development.md) and [testing strategy](../testing-strategy.md); do not substitute historical counts.

### Required session report

Create `sNN-report.md` only when that session is executed. Record:

- Assigned scope, actual branch/commit, unrelated changes preserved and upstream Phase 8 contracts used.
- Implemented behavior and source paths, screen/control IDs and decisions/deviations.
- Exact checks and observed outcomes, screenshots/artifact paths, role/language/browser/viewport and uncovered states.
- Acceptance IDs proved, failures, unavailable checks and explicitly pending external or human acceptance.
- Updated coverage-ledger rows and next-session handoff, including stable components/contracts and remaining dependencies.

During Session 01 create `screen-coverage.md` and a concise decision/baseline record in this directory. Do not create empty success reports for later sessions or a phase summary during planning.

### Session invocation

> Implement Phase 8.5 Session NN using `docs/implementation/phase-8.5-sessions/phase-8.5-sessions.md`, its canonical phase and UI specification. Inspect the current worktree, actual Phase 8 contracts and previous report. Complete that session's implementation and checks, update coverage and its report, then stop at the assigned boundary. Preserve unrelated work. Do not infer authorization for deployment, live account actions, paid evaluations, commit or push.

## Session briefs

### Session 01 — Inventory, baseline and design contracts

**Depends on:** current implemented frontend and available Phase 8 contracts. **Read:** router/navigation, all feature entry points, existing E2E, Phase 8 reports/ADR-025 and the retained concept source.

**Work:**
- Build the R01–R37 route/control inventory from actual source; enumerate each nested dialog, tab, editor, role-dependent action and fallback, including any newly added Phase 8 screens.
- Create `screen-coverage.md` with source path, session owner, state/role/language/layout dimensions and unverified status. Identify the entry points to otherwise hidden memory/task/comment views.
- Capture current representative screens, interaction costs and production asset/query baselines using fictional data; record exact environment and viewport.
- Map every proposed metric, trend, calendar item, assistant activity claim and navigation count to a current typed data source. Decide honest omission or a separately reviewed missing contract.
- Settle responsive shells, new view/tab URL policy, account selection, navigation/command-launcher boundaries, font/icon packaging and Phase 8 dependency ownership. Record default sequencing and file-conflict handling with concurrent hardening work.

**Verify and finish:** reconcile inventory with the actual router and component exports; record a current baseline check result and existing failures. Publish decisions, coverage and upstream dependencies. No broad UI implementation belongs here.

### Session 02 — Tokens, typography, icons and local assets

**Depends on:** 01. **Primary files:** `src/index.css`, existing Tailwind/Vite configuration, icons and bundled assets.

**Work:**
- Implement semantic color/surface/text/action/state/focus tokens, spacing, radii, type roles and motion rules from the specification.
- Package Manrope/Inter or the Session 01 approved equivalent locally with licenses and Turkish glyph coverage; remove any newly introduced runtime CDN requirement.
- Normalize the local icon family and product-mark treatment; retain brand identity unless its asset decision explicitly changes it.
- Provide reference specimens for headings, data, body/metadata, focus and state colors in a development-only harness or existing test setup.

**Verify and finish:** build and load with network egress disabled, inspect glyphs and layout shift, measure contrast on actual light/dark surfaces, and record font/asset size against baseline. Do not restyle every feature with raw colors.

### Session 03 — Shared components, forms and overlays

**Depends on:** 02. **Primary files:** `src/components/`, common field helpers and their meaningful interaction tests.

**Work:**
- Migrate Button, TextField, Card, EmptyState, ErrorMessage, FullScreenStatus, StatusBadge, SimulatedBadge and shared field variants.
- Add reusable page/panel headers, rows/tables, filters/tabs, pagination, skeletons and notices needed by the feature plan; avoid speculative unused abstractions.
- Rework sheets/dialogs/drawers/menus for focus entry/trap/return, Escape, backdrop behavior, background interaction, long-content scrolling and phone safe areas.
- Standardize inline validation, error summary, pending/disabled reasons, conflict/removed-source states and noncritical toasts. Keep canonical status mappings centralized.

**Verify and finish:** keyboard and screen-reader spot checks, automated scans on representative controls, no color-only states, mobile keyboard/zoom behavior and actual interaction tests. Publish component usage examples and migration notes.

### Session 04 — Responsive shell, navigation and route compatibility

**Depends on:** 03. **Primary files:** `AppShell`, navigation, `MorePage`, workspace switcher, shell status/banner and router integration.

**Work:**
- Implement expanded desktop sidebar, compact tablet adaptation, mobile five-tab navigation and grouped More destinations with role-aware utility links.
- Add consistent page context/breadcrumb and workspace selection. Expose Assistant, Knowledge and Reports on desktop without changing existing deep links.
- Consolidate repeated AI/demo explanations while preserving per-result provenance and urgent connection notices. Do not conflate connected with active assistant.
- Implement a destination launcher if selected in 01, clearly separated from effectful natural-language commands; no global data-search backend is implied.
- Define content-width variants and selected nested navigation; preserve query parameters, refresh and Back/Forward behavior.

**Verify and finish:** owner/manager/staff navigation, deleted/foreign membership, workspace changes with detail open, keyboard drawer/launcher, all initial route entry points, 360 px reflow and safe areas. Existing `/more` remains usable.

### Session 05 — Login, invite acceptance and workspace onboarding

**Depends on:** 04. **Primary files:** `features/auth`, `invites`, `workspaces` and public-shell fallbacks.

**Work:**
- Redesign login and account/invite entry with accessible field hierarchy, language control and responsive brand treatment.
- Cover pending/invalid/network/session-expired states; preserve password managers, autofill, paste and return-to routing.
- Redesign workspace picker, role/demo context, no-membership state and three-step creation wizard, retaining entered values when moving backward.
- Present category/market/language/timezone/currency and the existing readiness handoff clearly. Use delivered Phase 8 auth feedback where available; security/reset expansion is reconciled in 23.

**Verify and finish:** login/invite invalid-expired-consumed cases, wrong account, long workspace names, wizard defaults/validation, TR/EN and keyboard/phone forms. No new signup or role semantics.

### Session 06 — Today dashboard and commands

**Depends on:** 04–05 and Session 01 data map. **Primary files:** `features/home`, `features/commands`, report/readiness hooks.

**Work:**
- Build the wider Today composition: local date/greeting, authorized metrics, prioritized decisions, upcoming content and real assistant/legacy work.
- Show actionable setup/readiness when incomplete; reduce redundant static workspace metadata and all-zero decorative panels.
- Migrate command input, clarification, confirmations, fact-impact summary and result/error cards. Ensure the mobile command entry does not cover bottom navigation or content.
- Bind counts, activity and claims to existing records. Omit unsupported weekly percentages, trends, generic “working” animations and time-saving estimates.

**Verify and finish:** owner/staff metric scope, empty versus failed sources, connection failures, legacy/agent/paused/no-account states, a fact-update confirmation and report command in both languages. Capture the first complete redesigned daily-work screen.

### Session 07 — Inbox list and desktop workspace

**Depends on:** 06. **Primary files:** `InboxPage`, inbox hooks/labels and route-aware list/detail layout.

**Work:**
- Replace nested row cards with a readable conversation list, canonical filters, identity/time/preview/attention hierarchy and selected-row state.
- Introduce desktop list/detail structure without duplicating conversation mutation logic; retain focused phone routes.
- Preserve current filter/sort meaning, account/workspace scope and list position where possible. If search is included, document whether it covers a complete dataset or loaded records only.
- Handle long names, multilingual previews, expired windows, simulated results and no/partial/error records.

**Verify and finish:** each existing filter, selected/deleted/foreign conversation, direct detail URL/refresh/Back, long list pagination when supported and no horizontal overflow. Conversation interactions remain owned by 08.

### Session 08 — Conversation, grounded drafts and composer

**Depends on:** 07. **Primary files:** `ConversationPage`, `DraftCard`, `DraftParts`, `ReplyComposer` and embedded agent-work context.

**Work:**
- Migrate conversation header, message stream, attachments/redaction/native-reply presentation, takeover/release and safe context details.
- Build the grounded suggestion region with exact reply, reason chips, sources, approve/edit/reject and distinct needs-human path.
- Keep manual composer readable/reachable on phones; preserve unsent input on validation/network/conflict failures and existing text limits.
- Handle draft supersession, fact changes, role changes, expired windows, native replies and uncertain sends without premature success or automatic resend.

**Verify and finish:** seeded price reply, complaint handoff, manual response, double decision, changed draft/fact, unknown outcome and keyboard-visible composer. Verify the list/detail layout calls existing authoritative hooks once per required scope.

### Session 09 — Content library and state views

**Depends on:** 08. **Primary files:** `ContentPage`, `ContentCard`, generation entry and status helpers.

**Work:**
- Build image-led tiles/list treatment with actual uploaded thumbnails, readable title/type/state and meaningful dates.
- Preserve Drafts/Scheduled/Published/Problems membership, `tab`/`status` links and authorized AI/blank creation entry points.
- Design no-image, retained-media-deleted, generating, filtered-empty and failed/held cases; distinguish missing data from no content.
- Bound thumbnail fetching and provide stable image dimensions and truthful placeholders.

**Verify and finish:** each tab and relevant status, report links, long titles, mock/real provenance fixtures, empty library and media failures. Do not add cancelled items to an unintended view.

### Session 10 — Calendar/agenda and scheduling review

**Depends on:** 09 and a proven range-complete data contract. **Primary files:** content planning view, `ScheduleSheet`, scheduling helpers.

**Work:**
- Add the selected desktop calendar and phone agenda with date navigation, selected-day context and canonical state distinctions.
- Prove visible-range membership/pagination. If existing data is capped or incomplete, finish honest agenda/scheduling work and record the named contract dependency; never show incomplete empty days as complete.
- Redesign schedule review with account, exact content, date/time, workspace timezone, approval/role consequences and explicit final action.
- Preserve date bounds, staff lead-time/approval behavior and dirty/generation restrictions. No drag-and-drop mutation or new recurrence behavior.

**Verify and finish:** workspace-day boundaries, DST-observing timezone fixture, past/too-distant dates, no media, staff constraints and changed approval. Distinguish scheduled/publishing/retrying/checking/held/published visually and semantically.

### Session 11 — Content editor, media and exact preview

**Depends on:** 10. **Primary files:** `ContentDetailPage`, editor, upload, preview, validation, failure/on-hold/cancel controls.

**Work:**
- Create desktop editor/preview workspace and a phone edit/preview arrangement that retains form state and exposes save status.
- Migrate title, caption, visual notes, grounded values, image validation/progress/replacement and authenticated preview failure/removal.
- Render image feed and Story correctly; overlay suggestions must not look baked into the image or imply an unsupported caption.
- Cover generation pending/slow/failed, dirty saves, validation/claim blockers, schedule approval invalidation, readonly publication and supported failure/hold recovery.

**Verify and finish:** actual local media upload/replace, invalid image/aspect feedback, fact mismatch, failed save, readonly published item, retained-media removal and unknown publication. Ensure previews clean up resources and no media secret escapes.

### Session 12 — Approval queue, exact decision and history

**Depends on:** 08, 11. **Primary files:** `features/approvals`, command confirmations and shared status/action mappings.

**Work:**
- Redesign pending/history rows and desktop queue/detail versus phone focused decision, with action/person/subject/deadline/provenance.
- Migrate every existing approval body, including fact impact, reply, content publish/cancel and agent actions.
- Keep exact payload/version evidence visible; distinguish human decisions from delegated automatic outcomes and decision acceptance from completed effects.
- Handle expiry, stale/changed subject, double decision, denial, revoked access and failed partial detail loading while preserving queue context.

**Verify and finish:** one case for each subject type plus stale/double/expired decisions, browser direct-link selection policy, role restrictions and focus return. No bulk approval, optimistic sent/published labels or redesigned permission bypass.

### Session 13 — Assistant overview, owner tasks and progress

**Depends on:** 12. **Primary files:** `AgentPage`, task intake and `TaskPage`/task selection/thread summary.

**Work:**
- Split daily overview/tasks from configuration. Show actual account/controller/state, pending questions/approvals, recent actions and current work.
- Redesign owner-task composer/history, task detail/action progression and links to actual content or approvals.
- Migrate clarification plus paginated media/content choices; preserve current requester identity, expected question version and client request IDs.
- Handle no account, inactive/paused/legacy controller, waiting owner/customer/operation, failure and redacted data without invented activity.

**Verify and finish:** task submission, duplicate/request retry behavior, clarification conflict, authorized resource selection, partial results and real content/approval links on desktop/phone. A task or clarification never itself approves publication.

### Session 14 — Voice, permissions and controller/legacy controls

**Depends on:** 13. **Primary files:** personality/delegation forms, controller actions and `AutomationSettings`.

**Work:**
- Deliver focused Voice and Permissions sections with goals/tone/formality/length/emoji/DM-comment style and TR/EN examples.
- Clearly mark static voice preview as an example. Preserve save versions and show stale-form reload/review without dropping edits silently.
- Group all supported delegated actions with mode, limits, initiating source and capability constraints; show proposed changes and their real consequences.
- Preserve legacy automation and reviewed-readiness behavior; redesign cutover/pause/resume with explicit mode/account context and unresolved-operation explanations.

**Verify and finish:** owner/manager/staff edit boundaries, unavailable capability, version conflict, off/ask/automatic cases, pause/resume and legacy/agent transitions. No single long form for every daily and configuration task.

### Session 15 — Owner information questions and answer history

**Depends on:** 14. **Primary files:** question list/detail in `agent-work`, answer hooks and related notifications/deep links.

**Work:**
- Build a scannable question list and focused detail with question text, safe context, visibility, account/customer references, deadline and current state.
- Put the information-versus-approval distinction beside the answer composer. Separate owner/manager answers from staff proposals using the existing contract.
- Migrate reusable-knowledge opt-in/key validation, version/request behavior and paginated answer history without auto-verifying facts.
- Show pending/answered/expired/redacted/already-answered and inaccessible customer references with safe recovery.

**Verify and finish:** answer, staff proposal, stale/duplicate submission, expiry, reusable-knowledge consequence and current notification target. No answer implies permission for a send or moderation action.

### Session 16 — Public comments, thread context and moderation

**Depends on:** 15. **Primary files:** comments list/thread, manual moderation, operation history and public media context.

**Work:**
- Redesign account-scoped comments list and desktop thread context with readable public notice, authors, owner-native comments, time/state and actual media/caption when available.
- Preserve cursor pagination and thread destinations; design removed/private-unavailable media and deleted/redacted comment states.
- Migrate hide/unhide/delete controls and effect-specific confirmations with expected version, capability/role restrictions and actual operation history/outcome.
- Present supported reply/private-reply information without adding unregistered effect paths or leaking private DM/customer/owner data into the public view.

**Verify and finish:** real/mock capability fixtures, owner/staff limits, visible/hidden/deleted states, moderation unknown/failure/verified success, public-context isolation and direct thread refresh. Mock success does not close the live platform gate.

### Session 17 — Customer memory, sources and corrections

**Depends on:** 16. **Primary files:** `MemoryPage`, source/history controls and private conversation context links.

**Work:**
- Create a clear private customer/account header and grouped current memories with source/version/usability metadata.
- Redesign supported correction/removal forms and source/history drilldowns, including missing or erased source data and stale version handling.
- Make phone source review usable without nested sheets or losing unsaved corrections; retain account scope in links and pagination.
- Connect delivered Phase 8 rights entry points where available, without adding a broader identity-merge or CRM workflow.

**Verify and finish:** unauthorized role/customer/account, source deletion, correction conflict, removal and bounded history. Confirm the public comment UI does not fetch/render these private records.

### Session 18 — Knowledge overview, readiness and category browsing

**Depends on:** 17. **Primary files:** `KnowledgePage`, `CategoryPage`, `FactCard`, checklist, summaries and category labels.

**Work:**
- Build knowledge overview with meaningful readiness gaps, pending suggestions, extraction entry and compact completed readiness.
- Introduce desktop category/detail navigation and focused phone pages; migrate all fourteen current category keys without breaking their URLs.
- Emphasize fact label/value/status first, then evidence/version/source. Make missing, unverified and contested distinct from usable verified data.
- Preserve staff suggestion/owner verification boundaries, long localized values and unknown/partial template/fact errors.

**Verify and finish:** all category paths, empty/missing/contested/verified cases, readiness links, staff visibility, TR/EN and cross-category/back-navigation state. Typed editing and suggestion decisions are completed in 19.

### Session 19 — Every fact editor, extraction, suggestions and history

**Depends on:** 18. **Primary files:** `FactEditorSheet`, typed editors, `PasteExtractSheet`, `SuggestionsPage`, `HistorySheet`.

**Work:**
- Migrate money, weekly hours, text, localized text, phone, email, address, URL, boolean, enum and string-list editors using shared field/validation patterns.
- Cover units/currency/conditions, locale parsing, weekday ranges/closed days/exception handling and multi-language/list values. Keep large phone forms focused with save/cancel and dirty-state handling.
- Redesign paste/extract input, progress/failure with retained source, candidate/source review, discrepancy comparison and accept/reject/keep-current actions.
- Redesign immutable fact history and current-value changes, showing existing impact/approval requirements rather than silently rewriting scheduled content or past versions.

**Verify and finish:** representative valid/invalid values for each type, Turkish money, hours exceptions, extraction failure, candidate conflict, staff proposal and changed-fact consequences. Use meaningful value/transition tests rather than screenshot-only assertions.

### Session 20 — Approved-answer library

**Depends on:** 19. **Primary files:** `ApprovedAnswers` and save-as-answer entry from conversations.

**Work:**
- Redesign reusable answers as a readable library with title/question, intent/language, usable/stale status and grounded preview.
- Migrate create/archive and conversation save entry, with exact current role rules and template/fact-placeholder validation.
- Explain changed-fact review and separate reusable template approval from authority to send a future reply.
- Keep empty/filtered, validation/pending/error, long template and missing source states consistent with knowledge patterns.

**Verify and finish:** create, archive, save from sent conversation, unusable fact/template, changed price and staff restrictions in both languages. Do not add unsupported template editing or silent re-verification.

### Session 21 — Reports, metrics and saved evidence

**Depends on:** 20. **Primary files:** `DailyReport`, `MetricItems`, date/format helpers and report commands/links.

**Work:**
- Redesign daily date navigation, section summaries/metrics, partial/as-of states and authorized regenerate action.
- Give useful numbers emphasis with exact metric labels and valid evidence links; preserve snapshot/generation context on drilldown.
- Migrate record/duration evidence rows, pagination and missing/legacy/redacted evidence explanations. Never reinterpret a median as a row count.
- Add a chart only for an actually supported, defined complete data series. Retain a strong daily report if the concept's weekly series is unavailable.

**Verify and finish:** current versus historical snapshots, regeneration, no-data versus zero/partial failure, staff scope, timezone boundaries and deleted evidence. Command/report values must still agree on the same scope/time.

### Session 22 — Activity, notification center and bell

**Depends on:** 21. **Primary files:** `ActivityFeed`, notification center/bell/catalog/target mapping.

**Work:**
- Redesign activity timeline with local-day grouping, existing filters/pagination, actor/action/outcome and safe record links.
- Migrate notification center and optional small preview, unread/read handling, severity and authoritative counts.
- Preserve typed targets and current mark-read semantics; safely handle removed, inaccessible and stale destinations.
- Tune live regions and polling updates to avoid repeated announcements/focus jumps. Display simulation on applicable events and avoid exposing raw model/internal sensitive text.

**Verify and finish:** unread count transitions, critical reauth notification, pagination, duplicate polling, deleted/foreign targets, report/content/owner-question entry links and keyboard navigation.

### Session 23 — Settings, Phase 8 account security and privacy

**Depends on:** 22 and delivered Phase 8 auth/email/data-rights contracts. **Primary files:** settings/account/security/privacy/auth entry points plus typed Phase 8 clients.

**Work:**
- Deliver settings navigation, account identity, saved UI language and truthful workspace context, with role-aware security/privacy areas.
- Integrate session listing/current-device display, per-session/all-other revocation, password change and reset request/confirm with the owning Phase 8 rules.
- Integrate owner-only conversation/customer export/erasure and workspace deletion request/cancel/status, displaying exact scope and server-provided deadlines.
- Explain immediate redaction versus deferred final purge around unresolved operations; cancellation cannot imply accounts automatically resume.
- Reconcile every newly delivered Phase 8 UI route with the coverage ledger. If an upstream API is missing, finish independent controls, identify its owner and leave that acceptance row explicitly pending; no pretend functional substitute.

**Verify and finish:** wrong password, safe reset request, expired/used reset link, revoked session, permission loss, export isolation, erasure conflict/unknown outcomes and deletion grace/cancel/purge states. Use disposable data and email capture; expose no tokens in artifacts.

### Session 24 — Instagram connections, members and invitations

**Depends on:** 23. **Primary files:** `Connections`, OAuth result presentation, `Members`, invitation creation/QR and role/removal forms.

**Work:**
- Build readable real/mock account connection rows with health/error/capability context and current owner-only connect/reconnect/disconnect actions.
- Migrate OAuth return/error/pending states and disconnect/data-removal confirmation without changing callback/query contracts or reconciliation fences.
- Redesign team roster, role changes, owner constraints, member removal and current-user effects.
- Migrate invitations, one-time link/QR/copy feedback and delivered Phase 8 email state; offer resend/revoke only as supported. Distinguish requested delivery from confirmed delivery.

**Verify and finish:** OAuth denied/expired/wrong workspace, reconnect/degraded/unknown effect, owner/manager/staff permissions, last-owner rules, invite expiry/revocation and role change during an open decision. Preserve all acceptance links.

### Session 25 — Operational health, simulator and global fallbacks

**Depends on:** 24. **Primary files:** `SystemHealth`, `DevPanel`, global error/not-found/auth/workspace loading components.

**Work:**
- Group health by accounts, operations/jobs/webhooks and AI; integrate Phase 8 operational additions only from delivered authorized responses.
- Keep bounded technical IDs/error codes accessible without dominating owner-facing work; distinguish healthy, unknown, unavailable and not configured.
- Redesign scripted messages, failure injection, simulated publications, jobs/trace and demo reset into clearly scoped developer sections.
- Complete no-membership, deleted/foreign resource, auth expiry, unknown route, chunk/network failure and recoverable error presentation throughout both shells.

**Verify and finish:** developer tools absent under production-disabled configuration, simulator failure/reconciliation views, reset recreation/new workspace ID/cache behavior, restricted health, malformed URLs and global/workspace 404. Never run reset against data to preserve.

### Session 26 — Public landing, waitlist and transactional presentation

**Depends on:** 25 and existing approved content/delivery contracts. **Primary files:** `landing/src/`, delivered email/public-status templates and visual assets.

**Work:**
- Align brand, type, colors, buttons and product examples across every existing landing section; retain marketing composition while matching the finished app.
- Update illustrative knowledge/chat/content/report/phone frames to truthful current behavior, with clear example labels and capability limitations.
- Preserve TR/EN, existing theme controls, section links, FAQ and waitlist/contact fallback behavior; cover input/consent/pending/success/failure states.
- Align delivered invitation/reset/deletion/operator email and minimal status presentation without changing recipients, consent, token/secret behavior or reviewed legal language.
- Remove new external runtime font/image dependencies and retain asset source/license records. Do not publish a new feature claim because its concept screenshot exists.

**Verify and finish:** landing typecheck/build, phone/desktop language/theme/FAQ/navigation, mocked waitlist success/failure/no-endpoint paths and captured email rendering. No live submission, email delivery or landing deployment is implied.

### Session 27 — Whole-app accessibility, responsive, i18n and performance pass

**Depends on:** 01–26. **Primary files:** cross-cutting token/component corrections, affected features and meaningful regression coverage.

**Work:**
- Reconcile all route families against the coverage ledger and run the viewport/role/language/state matrix without taking an unnecessary Cartesian product.
- Fix contrast, keyboard order, focus restoration, menu/dialog behavior, accessible labels, live announcements, reduced motion, reflow and touch-target issues.
- Inspect 360/390 phone, 768/1024 tablet and 1440/1920 desktop layouts, including long Turkish text, 200% zoom, short-height/landscape and software-keyboard behavior.
- Verify offline fonts/assets, real/missing/deleted media, initial bundle/font cost, list pagination, duplicate queries and route timings against Session 01's measured baseline.
- Remove orphaned legacy styling/controls after final consumer migration. Keep one shared implementation for each effectful interaction.

**Verify and finish:** automated accessibility scans for representative patterns and critical states, manual keyboard/screen-reader/zoom evidence, i18n parity, overflow checks and documented performance differences. Unresolved findings have a concrete fix or explicitly pending acceptance; screenshots alone do not close them.

### Session 28 — Full regression, migration reconciliation and owner acceptance

**Depends on:** 27, integrated Phase 8 UI contracts and no required unresolved implementation rows.

**Work:**
- Run the required full frontend checks, production build and configured Chromium/WebKit E2E, plus current required backend/isolation/security/generated-client/fake-evaluation checks and changed landing checks.
- Reconcile source/router/component inventory with R01–R37 and all later additions. Ensure no screen, role-specific control, nested editor, token link or public fallback was omitted.
- Execute the daily-work walkthrough: login/switch workspace → readiness/knowledge → customer draft/complaint → explicit decision and verified outcome → create/upload/schedule/recover content → assistant task/question/comment/memory → report evidence → settings/security/privacy/team.
- Have the owner perform the walkthrough on Windows and an actual phone. Record device/OS/browser/language, observed usability problems and accepted fixes. If unavailable, finish independent regression work and report human acceptance pending.
- Update implemented user journeys, demo/operations notes, route mappings, coverage ledger and task status. Create the actual Phase 8.5 summary with UI-01 through UI-12 evidence, limitations and compatible frontend rollback instructions.

**Verify and finish:** clean required regression evidence, complete coverage ledger and recorded owner/device acceptance. Do not close Phase 8 production, legal, platform or real-model gates by passing UI tests. Stop at this phase boundary; deployment/commit/push follow the session's explicit authorization.
