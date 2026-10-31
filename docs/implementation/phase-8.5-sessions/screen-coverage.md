# Phase 8.5 screen and control coverage ledger

Inventory baseline: `main@641b1f5`, 2026-10-30, actual `frontend/src/app/router.tsx`, component exports/consumers and current typed hooks. Session01 inventories; later owners update observed rows, never infer passes from planned states. `W=/w/:workspaceId`; all source paths below are relative to `frontend/src/` unless prefixed otherwise.

## Reading the ledger

- **U**: source inventoried; redesign/browser acceptance unverified. **B**: original presentation captured with fictional API interception, not redesigned acceptance. **P**: upstream missing. No row is marked fully accepted in Session01.
- Every route/control inherits TR and EN, phone360/390, tablet768/1024, desktop1440/1920, keyboard/200% zoom/reduced motion checks where applicable. Use representative combinations rather than a Cartesian product. States listed are required future evidence, not observed passes.
- Authenticated rows inherit owner/manager/staff, lost membership/foreign workspace→safe404, workspace switching, initial pending/network failure; account-scoped rows also inherit `account` validity, no/disconnected/degraded/reauth, real/mock, legacy/agent/paused and capability restrictions. Public rows use anonymous/signed-in/wrong-account as applicable.
- Async collections inherit pending/empty/error/partial/filtered-empty where supported. Mutations inherit validation/pending/duplicate/stale-conflict/permission loss/success; external effects additionally checking/unknown/no automatic resend. Each session must record concrete fixture, language/browser/viewport, expected action, permission/provenance assertion, artifact and unresolved findings in its report/evidence.
- R34–R35 and parts of R37 are future integration obligations; they do not create guessed routes. R36 is a separate existing app. R33 owns two registered wildcard fallbacks.

## Router reconciliation and entry points

Actual router has **34 `path` declarations**: 31 concrete leaf page paths, the workspace gate path, and2 wildcards. The workspace index is1 additional concrete page. Thus32 concrete SPA page patterns map exactly to R01–R32; R33 maps both wildcard leaves. Including the pathless RequireAuth wrapper gives36 route objects. R34–R37 are obligations outside those32 pages, not four missing current SPA routes. Knowledge has14 category values under one pattern, not14 registered routes.

Hidden work entry points: `AgentPage` links account-scoped questions/comments; its task rows link task detail. `QuestionPage` and `ThreadSummary` link private memory with `?account=`; `ConversationAgentWork` embeds ThreadSummary in `ConversationPage`. Memory is not a free-standing customer directory. `CommentsPage` links thread detail; notification typed target mapper also reaches questions/tasks/comments. Report metric links preserve saved snapshot context. Inventory source: `features/agent/AgentPage.tsx`, `features/agent-work/WorkPages.tsx`, `features/inbox/ConversationPage.tsx`, `features/notifications/target.ts`, `features/reports/MetricItems.tsx`.

## Route families

| ID | Path/surface | Source | Owner session | Required state/control emphasis | Observed result / evidence / dependency |
|---|---|---|---|---|---|
| R01 | `/login` | `features/auth/LoginPage.tsx`, `RequireAuth.tsx` | 05 | Email/password/autofill; invalid/network/pending/expired; protected-route return incl query | Implemented in PublicShell; autofill/password metadata, returnDestination context retention, invalid email notice, error preservation. Unit tested in `login.test.tsx` and `returnTo.test.ts`. Chromium156/WebKit27.2 TR360/EN390/TR768/EN1440 browser captures and zero axe violations in [S05 report](s05-report.md). |
| R02 | `/invite/:token` | `features/invites/AcceptInvite.tsx` | 05 | Token consume, account/password form, signed-in/wrong account, invalid/expired/used | Implemented signed-in join, account creation, wrong-account logout and invalid token links; tested in `acceptInvite.test.tsx`. Browser fixtures verify signed-out presentation and zero axe violations under TR360–EN1440. |
| R03 | `/` | `features/workspaces/WorkspacePickerPage.tsx` | 05 | Membership roles/demo, long names, no memberships, create, language/logout | Implemented list with role/demo tags, long name word-wrap, empty-membership state, sign-out action and language save. Tested in `picker.test.tsx`. Browser fixtures verify no overflow on long names and zero axe violations. |
| R04 | `/workspaces/new` | `features/workspaces/CreateWorkspaceWizard.tsx`, `wizardDefaults.ts` | 05 | Three steps/back-retention; market/category/language/timezone/currency; defaults/validation/readiness handoff | Implemented 3-step wizard with step progress, category radio choices, market-driven defaults, Back input retention, dirty leave confirmation BottomSheet, and readiness handoff. Tested in `wizard.test.tsx`. Browser fixtures verify step progression and zero axe findings. |
| R05 | `W` index | `features/home/HomePage.tsx`, `Dashboard.tsx`, `ReadinessCard.tsx`, `features/commands/CommandBar.tsx` | 06 | Real authorized metrics, readiness, account status, command clarification/confirmation/outcome | B: [owner TR1440](evidence/s01/today-tr-desktop.png), [owner EN390](evidence/s01/today-en-phone.png), empty report/no account fixture |
| R06 | `W/inbox` | `features/inbox/InboxPage.tsx` | 07 | any/needs_approval/needs_human/failed, selected/deleted conversation, loading/long list | U; current filter is local state |
| R07 | `W/inbox/:conversationId` | `features/inbox/ConversationPage.tsx`, `DraftCard.tsx`, `DraftParts.tsx`, `ReplyComposer.tsx` | 08 | Takeover/release, draft decision/edit/reject, native replies, window expiry, source/attachment removal, unsent text | U |
| R08 | `W/content` | `features/content/ContentPage.tsx`, `ContentCard.tsx` | 09–10 | drafts/scheduled/published/problems, `tab` and legacy `status`, AI/blank creation, media fallback; agenda only if complete | U; range-complete calendar source pending10 |
| R09 | `W/content/:id` | `features/content/ContentDetailPage.tsx`, `ContentEditor.tsx`, `ContentPreview.tsx` | 11 | Dirty save, generation, upload/replace, claim validation, schedule, failure/hold/cancel, immutable published | U |
| R10 | `W/approvals` | `features/approvals/ApprovalsList.tsx`, `ApprovalDetailSheet.tsx` | 12 | Pending/history and every subject body, expiry/stale/double decisions, staff restrictions | U; tab/selection currently local |
| R11 | `W/more/agent` | `features/agent/AgentPage.tsx`, `PersonalityForm.tsx`, `DelegationForm.tsx` | 13–14 | Account selection, controller/version, tasks, actions, voice/delegation/preview/confirm | U |
| R12 | `W/more/automation` | `features/settings/AutomationSettings.tsx` | 14 | Legacy rules, account capabilities, reviewed readiness and agent-controller link | U |
| R13 | `W/more/agent/questions` | `features/agent-work/WorkPages.tsx` QuestionsPage/QuestionList | 15 | `account`, pagination, pending/answered/expired/redacted | U |
| R14 | `W/more/agent/questions/:questionId` | same QuestionPage/QuestionDetail | 15 | Answer vs staff proposal, knowledge reuse/key, history, expected version/request IDs | U |
| R15 | `W/more/agent/comments` | same CommentsPage/CommentList | 16 | Public scope, cursor, deleted/redacted author/text/media | U; never private memory data |
| R16 | `W/more/agent/comments/:threadId` | same CommentThreadPage/CommentThread | 16 | Thread/media, hide/unhide/delete, exact moderation, capability and operation outcome | U; live platform acceptance separate |
| R17 | `W/more/agent/memory/:customerId` | same MemoryPage/MemoryDetail | 17 | Private account/customer, memory correct/forget, sources/history, erased/conflict | U; reachable from questions/DM thread, not public comments |
| R18 | `W/more/agent/tasks/:taskId` | same TaskPage/TaskDetail | 13 | Progress/actions, clarification, version, media/content cursor choices, actual content/approval links | U |
| R19 | `W/more/knowledge` | `features/knowledge/KnowledgePage.tsx`, `ReadinessChecklist.tsx` | 18 | Real requirements, category summaries, suggestions/paste extraction, unknown sources | U |
| R20 | `W/more/knowledge/:category` | `features/knowledge/CategoryPage.tsx`, `FactCard.tsx`, `labels.ts` | 18–19 | All14 category keys, fact state/usability, create/edit/verify/restore/history, bad category404 | U; see K rows |
| R21 | `W/more/knowledge/suggestions` | `features/knowledge/SuggestionsPage.tsx` | 19 | Candidate relation/current/proposed/source, accept/reject/keep current; staff proposal | U |
| R22 | `W/more/knowledge/answers` | `features/knowledge/ApprovedAnswers.tsx` | 20 | Create/archive, language/intent/template placeholders, usable/stale, staff boundaries | U |
| R23 | `W/more/reports` | `features/reports/DailyReport.tsx` | 21 | Date/timezone, partial/as-of, regenerate permissions, missing vs zero, saved snapshot | U |
| R24 | `W/more/reports/:date/:key` | `features/reports/MetricItems.tsx` | 21 | Snapshot/date/key, cursor, duration vs count, legacy/redacted/unavailable evidence | U |
| R25 | `W/more/activity` | `features/activity/ActivityFeed.tsx` | 22 | Owner/manager entry; date/group filters, cursor, actor/action/severity, safe links | U |
| R26 | `W/more/notifications` | `features/notifications/NotificationCenter.tsx`, `NotificationBell.tsx`, `target.ts` | 22 | Unread/all, read/read-all, cursor/count, typed removed/foreign targets, polling focus/live regions | U |
| R27 | `W/more/settings` | `features/settings/SettingsPage.tsx` | 23 | Identity/language, readonly workspace, role-aware management links/logout; delivered security/privacy only | U |
| R28 | `W/more/settings/connections` | `features/settings/Connections.tsx`, `AccountStatusBadge.tsx` | 24 | Owner connect/reconnect/disconnect, mock/real availability, OAuth query result, unknown outcomes/removal | U |
| R29 | `W/more/settings/members` | `features/settings/Members.tsx` | 24 | Roster roles, owner-only changes/removal/invites, last-owner/current-user, one-time URL/QR/revoke | U |
| R30 | `W/more/settings/system-health` | `features/settings/SystemHealth.tsx` | 25 | Owner/manager; account/job/webhook/operation/AI, unknown/unconfigured/failed, bounded diagnostics | U; Phase8 additions only when delivered |
| R31 | `W/more/dev` | `features/dev/DevPanel.tsx` | 25 | Meta demo flag guard, scripts/failures/publications/jobs, reset confirmation/new workspace/cache | U; reset never run on data to preserve |
| R32 | `W/more` | `features/settings/MorePage.tsx` | 04 | Grouped role/demo destinations, workspace picker/create, logout | Implemented grouped semantic rows; owner/manager/staff and dev-disabled assertions, TR/EN phone/tablet/desktop Chromium/WebKit captures and zero axe violations in [S04 report](s04-report.md). Original [staff TR360](evidence/s01/more-staff-tr-phone.png) retained. Real-stack/human walkthrough remains pending. |
| R33 | Global `*`; `W/*` | `app/NotFoundPage.tsx`, `features/auth/RequireAuth.tsx`, `features/workspaces/WorkspaceGate.tsx`, `components/FullScreenStatus.tsx` | 25 (shared03/shell04) | Unknown/deleted/foreign safe404, network retry, auth/workspace loading, failed asset/chunk recovery | U |
| R34 | Undelivered security/reset/session surfaces | No current SPA source/typed UI contract | 23 + Phase8 auth owner | Session/device revoke, password change/reset request/consume/throttle | P; no guessed routes or pretend controls |
| R35 | Undelivered export/erase/workspace lifecycle/status surfaces | No current SPA source/typed UI contract | 23 + Phase8 data-rights owner | Owner scope/download/erase/unknown, deletion grace/cancel/deadline/purge | P; existing disconnect erase is R28 only |
| R36 | Existing public `landing/` | `landing/src/App.tsx`, `PhoneDemo.tsx`, `KnowledgePreview.tsx`, `OwnerChat.tsx`, `WaitlistForm.tsx`, `copy.ts`, `brand.ts` | 26 | Every section/demo, FAQ/theme/TR-EN, waitlist consent/pending/error/no endpoint/manual fallback | U; no live waitlist submission |
| R37 | Transactional/minimal public status | Current invite token entry R02; email/reset/deletion presentation not delivered in baseline | 26 + Phase8 email owner | Source-safe invite/reset/deletion/operator email, minimal public status, no token/identity leaks | P for undelivered templates; avoid inventing endpoints |

## Shared controls and nested surfaces

These rows supplement route families and inherit the same dimensions. They enumerate existing control exports/consumers, including inline confirmations that are easy to miss when looking only for dialogs. All rows are U until their owning session records observed evidence.

| Control ID / parent | Source and control | Owner | Required states / expected next action and assertion | Evidence / status |
|---|---|---|---|---|
| S01 | `components/Button.tsx` primary/secondary/ghost/danger/block | 03 | Hover/focus/disabled/pending, semantic submit; duplicate prevention | Semantic migration; `controls.test.tsx` proves native type, pending duplicate prevention and visible linked disabled reason. Four TR360/EN1440 Chromium/WebKit specimens; [S03 report](s03-report.md). Feature-specific pending reasons remain with later owners. |
| S02 | `components/TextField.tsx`, `FormFields.tsx`, `Field.tsx`, `fieldIds.ts` + compatibility knowledge exports | 03 | Label/help/error/required/read-only; mobile16px, descriptions and validation | `controls.test.tsx` proves supplied/generated IDs, merged descriptions, validation/error removal, retained input, native select/textarea/radio/checkbox and summary focus. Browser fixtures validate summary-to-field and retained values. Software keyboard/actual phone and every typed-editor state remain pending. |
| S03 | `components/Card.tsx`, `Layout.tsx`, `Pagination.tsx` | 03 | Semantic panel vs generic div, layout dimensions, long content | Surface/border panel; DEV specimen consumes headers/filter/row/table/pagination. Four browser fixtures have no page scroll overflow and zero axe findings; cursor callbacks tested. Feature layout/selection migrations remain with owners. |
| S04 | `components/BottomSheet.tsx`, `modalFocus.ts` all existing consumers | 03 | Initial focus/trap/return, Escape/backdrop, background interaction, scroll, safe area, removed trigger | `BottomSheet.test.tsx` proves nesting/topmost Escape, trap/return, exact background/scroll restoration, nondismissible/backdrop/latest callback, detached opener fallback. Chromium156/WebKit27.2 TR360/EN1440 fixtures prove explicit opener and default prior-focus restoration, long sheet footer and contained bounds. [JSON](evidence/s03/components.json); viewport sheet captures/report. Dirty editors and software keyboard remain with later owners. |
| S05 | `components/EmptyState.tsx`, `ErrorMessage.tsx`, `FullScreenStatus.tsx`, `Feedback.tsx` | 03 | Loading vs missing vs error; localized recovery, restrained live regions | Distinct semantic empty/error/loading; Notice defaults static, Toast is noncritical and dismissible; validation summary links and status behavior tested. Representative static/async states scanned in four browser specimens. Actual screen-reader and feature-specific conflict/removed-source transitions remain pending. |
| S06 | `components/StatusBadge.tsx`, `status.ts`, `SimulatedBadge.tsx` | 03 | Canonical statuses incl unknown/checking; readable label/icon, per-result provenance | Semantic tokens only; canonical keys/labels/icons unchanged. Existing `StatusBadge.test.tsx` verifies all states, distinct TR/EN labels, checking never success and per-result simulation. All statuses rendered in four zero-violation axe specimens. Real workflow outcomes remain with feature owners. |
| S07 | `components/LanguageSwitch.tsx`, `app/LanguageSync.tsx` | 03/05 | TR/EN saved preference/error, anonymous language; Turkish glyphs | LanguageSwitch semantic styling; existing interaction tests remain passing in full S03 suite. TR/EN shared specimens render translated labels/local fonts. Saved preference/network and auth integration remain owned by05/23; LanguageSync behavior unchanged. |
| S08 | `components/icons.tsx`, `index.css`, local fonts | 02 | Single local stroke family, decorative aria, type roles, offline/glyph/contrast/reduced motion | Implemented foundation; [S02 report](s02-report.md), [asset observations](evidence/s02/assets.json), [TR390](evidence/s02/reference-tr-phone.png), [EN1440](evidence/s02/reference-en-desktop.png). Fictional dev specimens and anonymous production login; Chromium156, browser external requests blocked, local fonts/glyphs/contrast/focus/reduced motion passed. Existing local decorative stroke family and wordmark retained. Shared/feature adoption, WebKit, screen-reader and actual-phone acceptance remain unverified. |
| S09 | `app/layout/AppShell.tsx`, `navigation.ts`, `SimulationBanner.tsx` | 04 | Sidebar/tablet/five tabs, skip/main, active nested route, compact provenance/urgent notices | 768px compact rail/expand labels, 1200px expanded sidebar, five phone tabs, page context/widths and static demo/offline disclosure implemented. Route-manifest test retains all32 concrete entry points and2 fallbacks; selection/membership/role tests pass. Twelve TR/EN Chromium/WebKit360–1920 fixture captures and shell/launcher axe scans pass; [observations](evidence/s04/shell.json). Feature screens/urgent connection behavior remain authoritative and receive later migration evidence. |
| S10 | `features/workspaces/WorkspaceSwitcher.tsx` | 04 | Accessible workspace selection, long names, change with detail open; clear old workspace detail | Explicit safe-section/filter whitelist drops tenant detail/account/cursor/snapshot IDs. Eleven mapping cases, actual switch/history/query and revoked/foreign membership tests pass; twelve long-name browser scenarios preserve refresh/Back/Forward and clear unsafe IDs. Physical-device/dirty feature forms remain pending. |
| S11 | `features/notifications/NotificationBell.tsx` | 04/22 | Authoritative unread count, keyboard link, no duplicate poll/focus announcements | Semantic bell keeps existing query/unread_count/name contract. Fixture count12 displays9+; existing content notification navigation/mark-read/provenance test passes after scoping bell vs desktop link. Polling/read-state/target redesign remains owned by22. No new query or live-region added. |
| S12 | `app/layout/DestinationLauncher.tsx` | 04 | Local destination filtering only, Escape/keyboard/focus return, role/demo; no command execution | Implemented local locale-aware native destination links; Ctrl/Cmd+K, arrow/Enter/Tab, text input Escape, shared modal focus/background handling. Pointer opener and shortcut prior-focus return pass unit and all twelve browser fixtures; role/demo filtering and no command/API mutation tested. [S04 report](s04-report.md); manual screen-reader/actual phone pending. |
| A01 / R01 | `LoginPage` email/password/language/submit | 05 | Password manager/paste, pending/invalid/network, preserve input, safe return incl query | Implemented responsive PublicShell, input retention on 401, email validation check, safe return routing; tested in `login.test.tsx` and `returnTo.test.ts`. Zero axe findings on Chromium and WebKit. |
| A02 / R02 | `AcceptInvite` display-name/password/existing-account acceptance | 05 | Invalid/expired/consumed/wrong-account; signup semantics unchanged; no token artifacts | Implemented signed-in join, account creation form, conflict email-taken note, wrong account sign-out; tested in `acceptInvite.test.tsx`. Zero axe findings. |
| A03 / R03 | Picker role/demo row, language/logout/create/no membership | 05 | Long names wrap, correct role, removal recovery, no membership empty | Implemented semantic membership row cards, empty state, word break on long names, sign out action; tested in `picker.test.tsx`. Zero axe findings. |
| A04 / R04 | Wizard step1 business name | 05 | Required name, long names, Back retention | Implemented step 1 with validation, hint, Back value retention; tested in `wizard.test.tsx`. |
| A05 / R04 | Wizard step2 business category | 05 | Category choice, required selection, retained edits on Back | Implemented 9 category radio cards, selection validation, Back value retention; tested in `wizard.test.tsx`. |
| A06 / R04 | Wizard step3 market/languages/timezone/currency/create | 05 | Defaults/override rules, reply vs UI locale, pending/error retained values, server-created workspace/readiness destination | Implemented market-driven defaults, overrides, next-steps notice, dirty leave sheet, readiness handoff; tested in `wizard.test.tsx` and `ui-entry.mjs`. |
| H01 / R05 | `Dashboard` status/Banners/Attention/Upcoming/Failures/Numbers | 06 | Pending/error not zero; owner/staff metrics; reauth owner link; result simulation | U |
| H02 / R05 | `ReadinessCard` + `ReadinessChecklist` open-requirement links | 06/18 | Real missing requirements, permissions, bad/partial readiness sources | U |
| H03 / R05 | `commands/CommandBar`, `ClarificationChips` | 06 | Max text, interpret/clarify, no free-text approval, retain failed input | U |
| H04 / R05 | `ConfirmationCard`, `CommandResultCard`, `messages.ts` link mapper | 06 | Exact fact impact/action binding, expiry/conflict, actual result links/state | U |
| I01 / R06 | Inbox filters/rows/WindowTimer | 07 | Any/needs approval/human/failed, localized customer/preview, expiry/simulation, selection/deleted | U |
| I02 / R07 | Conversation header/handling mode/suggest | 08 | Takeover/release/suggest pending and authority changes, native reply | U |
| I03 / R07 | `DraftCard`, `DraftParts` grounded sources/parts/windows/reasons | 08 | Approve/edit/reject/needs human/superseded, stale facts, queued/sending/sent/unknown | U |
| I04 / R07 | `ReplyComposer` manual/send-again warning | 08 | Limits, validation, failed unsent text retained, unknown outcome never auto-resend | U |
| I05 / R07 | Message attachments/redacted body/save-as-answer + `ConversationAgentWork` | 08/20 | Missing media, sent-only save, private thread/memory links account scope | U |
| C01 / R08 | `GenerateSheet` AI/blank, GenerationProgress | 09/11 | Type/account/brief, pending/slow/fail, retained input/open actual draft, fake badge | U |
| C02 / R08 | `ContentCard` title/status/time/thumbnail | 09 | All tab memberships, no-image/deleted media, bounded thumbnails | U |
| C03 / R09 | `ContentEditor` body/caption/overlay/save/validate | 11 | Dirty/save conflict, claim issues by field, readonly published, no overlay→caption invention | U |
| C04 / R09 | `MediaUpload`, `ContentPreview` | 11 | Upload/replace/type/aspect/size error, authenticated blob cleanup, missing/redacted | U |
| C05 / R09 | `ScheduleSheet` date/time/account/checks/review/submit | 10 | Workspace timezone/DST/leadtime, role submission vs approval, errors preserve input | U |
| C06 / R09 | `CancelAction` inline confirmation | 11 | Exact subject and consequence, pending/in-progress reconciliation, safe cancel | U |
| C07 / R09 | `FailureDetail`, `OnHoldActions` inline retry/reapprove/reschedule | 11 | Failure classification, permission, held validity/fact changes, unknown outcome | U |
| C08 / R09 | `ContentStatusPanel` publication/status/outcome URL | 11 | Actual persisted state, safe URL, no premature success, removed media | U |
| P01 / R10 | `ApprovalDetailSheet` decision/back/expiry + `ExtraFields` | 12 | Trap/return, explicit bound approve/deny, owner/manager/staff, double/stale/expired | U |
| P02 / R10 | `ChangeSummary`, `ImpactSummary`, `CancelContentSummary` | 12 | Fact change/cancel exact values and affected counts, immutable evidence | U |
| P03 / R10 | `ReplyApprovalBody` | 12 | Exact reply/recipient/facts/version, stale or deleted subject; accepted≠sent | U |
| P04 / R10 | `ContentApprovalBody` | 12 | Exact content/preview/schedule/cancel evidence; accepted≠published | U |
| P05 / R10 | `AgentApprovalBody` exact-action fetch | 12 | Policy/action IDs, redaction, public/private scope, state/outcome distinction | U |
| G01 / R11 | Agent account select + AccountAgent overview/state/action history | 13 | Account valid/no account, controller/paused, truthful session counts and current work | U |
| G02 / R11 | Task composer/history | 13 | Request ID/retry/duplicate, disabled reason, actual task and content/approval links | U |
| G03 / R18 | Task clarification + TaskSelection media/content choices | 13 | Expected question version, required selection, pagination, removed/foreign resources | U |
| G04 / R11 | `PersonalityForm` goals/tone/formality/length/emoji/DM-comment style | 14 | Example labelled static, save version/conflict, owner vs readonly | U |
| G05 / R11 | `DelegationForm` action modes/limits/preview/apply confirmation | 14 | Off/ask/auto, real capability matrix, expected version, no model-enlarged authority | U |
| G06 / R11 | Controller activate/pause/resume/return-legacy confirmation | 14 | Owner-only, readiness warning, unresolved operations, connected≠active | U |
| G07 / R12 | Legacy policy form/review readiness | 14 | Capability unavailable/staff readonly, canonical policy values, controller navigation | U |
| Q01 / R13–14 | WorkFrame account/back, question list/cursor and detail context | 15 | Question visibility, removed customer/context, account query retained | U |
| Q02 / R14 | Answer/proposal textarea, reuse opt-in/key, history cursor | 15 | Owner/manager answer vs staff proposal, max lengths/key, stale/expired/duplicate | U |
| M01 / R17 | Memory current rows/correct/forget and sources cursor | 17 | Owner/manager/staff API rules, source deletion, stale version, safe cache invalidation | U |
| T01 / R15–16 | Public comment/media/context and ThreadSummary | 16 | Public-only data, cursor, hidden/deleted/redacted/media unavailable; no memory fetch | U |
| T02 / R16 | ManualActions effect selection/confirm + operation history | 16 | hide/unhide/delete, role/capability, exact request/version, unknown/fail/verified | U |
| T03 / R07/R16 | ThreadControl takeover/release | 08/16 | Version conflicts and current authority, context-local control, no stale private text | U |
| K01 / R19 | Readiness checklist, summaries, suggestions and extraction entries | 18 | Complete/missing/contested/unknown partial; links to correct category/key | U |
| K02 / R20 | All categories via `labels.ts` CATEGORY_ORDER | 18 | identity/contact/location/hours/service/pricing/promotion/booking/policy/schedule/faq/brand/escalation/custom | U;14 source keys reconciled |
| K03 / R20 | `FactCard`, `FactStatusChip` edit/verify/restore/history | 18/19 | Verified/unverified/contested/missing/unusable, staff proposes not verifies | U |
| K04 / R20 | `FactEditorSheet` create/edit/form validation/impact | 19 | Current version/save, label/key/type, staff candidate, failure retains values | U |
| K05 / R20 | `MoneyEditor` | 19 | Turkish parsing/decimal/currency/unit, disclosure/conditions, invalid ranges | U |
| K06 / R20 | `HoursEditor` and RangeInputs | 19 | Weekdays/open/closed/ranges, exceptions/date/remove, overnight/invalid feedback | U |
| K07 / R20 | `SimpleEditors.TextEditor` | 19 | Required/long text, draft retention, readonly | U |
| K08 / R20 | `LocalizedTextEditor` | 19 | TR/EN values/add/remove language, empty/long values | U |
| K09 / R20 | `PhoneEditor` | 19 | Phone format/required, mobile input, invalid/error | U |
| K10 / R20 | `EmailEditor` | 19 | Email semantics/validation, preserve paste/autofill | U |
| K11 / R20 | `AddressEditor` | 19 | Multiline structured address fields, empty/long localized data | U |
| K12 / R20 | `UrlEditor` | 19 | URL format/safe source, long URL wraps, validation | U |
| K13 / R20 | `BooleanEditor` | 19 | Labelled yes/no, false distinct missing, keyboard | U |
| K14 / R20 | `EnumEditor` | 19 | Allowed-values labels, invalid/removed option, keyboard | U |
| K15 / R20 | `StringListEditor` | 19 | Add/edit/remove entries, empty and repeated items, focus | U |
| K16 / R19/21 | `PasteExtractSheet` source/progress/candidate results | 19 | Source retained on failure, excerpt review, never auto-verifies | U |
| K17 / R21 | Suggestions accept/reject/keep-current/discrepancy | 19 | Staff proposal vs owner verify, changed fact/candidate conflict | U |
| K18 / R20 | `HistorySheet` | 19 | Immutable versions/source/time, bounded history, missing/redacted source | U |
| K19 / R22/R07 | Approved-answer create/archive + conversation save entry | 20 | Intent/language/template/fact placeholders, stale facts, role rules, pending/error | U |
| E01 / R23 | DailyReport date navigation/regenerate/metrics/summary | 21 | Local dates/partial/as-of/zero/error, staff metric scope, actual snapshot | U |
| E02 / R24 | MetricItems pagination and record links | 21 | Duration vs count, historical snapshot membership, deleted/foreign/redacted evidence | U |
| E03 / R25 | Activity filters/date/group/pagination/link mapper | 22 | Actor/action/outcome/simulation, scope and removed link fallback | U |
| E04 / R26 | Notification filters/read-all/row targets | 22 | Authoritative unread transitions, stale target, no repeated poll announcement | U |
| U01 / R27 | Account/language/context/logout/settings links | 23 | Saved locale failure, identity versus workspace, role-aware destinations | U |
| U02 / R28 | OAuthBanner query parsing/dismiss | 24 | Accepted/denied/expired/wrong workspace/unknown code; preserve unrelated params | U |
| U03 / R28 | AccountCard connect/reconnect/health/capabilities | 24 | Owner-only effect, mockAllowed/metaAllowed, disconnected/reauth/degraded | U |
| U04 / R28 | Disconnect BottomSheet/remove-data checkbox | 24 | Exact account/operation uncertainty, checkbox resets false, erase may wait | U |
| U05 / R29 | Member role select, RemoveSheet | 24 | Last owner/current member/owner-only, stale permission, exact subject safe cancel | U |
| U06 / R29 | InviteSheet role/create/link/QR/copy | 24 | One-time secret not retained in artifacts; actual clipboard result; pending/error | U |
| U07 / R29 | PendingInvites revoke/expiry | 24 | Actual pending membership invitation scope, expiry/revocation, delivery only if delivered | U |
| U08 / R30 | Health sections/rows/diagnostics | 25 | Missing vs zero vs unavailable, no secrets/raw model text, bounded IDs | U |
| U09 / R31 | Scripts/run, failure operation/mode/clear, simulated publication list | 25 | Explicit simulator scope, metadata flag guard, pending/failure safe retry | U |
| U10 / R31 | Due jobs/run and reset BottomSheet | 25 | Dedicated disposable DB/media only, changed workspace ID/cache cleared | U |
| L01 / R36 | Header/hero/comparison/controls/onboarding/FAQ/theme/language | 26 | TR/EN, saved theme, navigation and truthful examples, keyboard/phone | U |
| L02 / R36 | OwnerChat/PhoneDemo/KnowledgePreview/content/report frames | 26 | Clearly fictional examples, current actual capability limits, local assets | U |
| L03 / R36 | WaitlistForm consent/email/message/manual WhatsApp fallback | 26 | Validation/pending/success/error/no endpoint, no live request during checks | U |

## Observed baseline runs and remaining matrix

Full raw environment/request/asset/timing results: [evidence/s01/baseline.json](evidence/s01/baseline.json). Fixture suite: Chromium156.0.8078.4, Windows, Node26.4.0, TR/EN, Europe/Istanbul, height900. The six B rows have0 page errors, no external-origin attempts and document width equal viewport. They establish before states only. Current unit suite passes516 tests in33 files; test results are baseline regression evidence, not proof of every state listed above.

Still unverified: all redesigned states, role-transition/foreign-ID browser cases, account/controller fixtures, critical mutation transitions, WebKit, tablet/1920 layouts, 200% zoom, software keyboard, screen reader, live/integrated APIs, representative image payload/timing, actual phone/human acceptance. Shared states and changes are verified in 02–05; feature-specific gaps remain with their owner sessions, final reconciliation27–28.

## Evidence append format for implementation sessions

Session03 observed append: **S01–S07 | fictional local specimen; no role/account/API data | validation/pending/disabled/loading/empty/error/checking/simulated; long/nested modal | TR/EN | Chromium156.0.8078.4 + WebKit27.2,360/1440×900 | retain input, navigate native controls, close topmost sheet and restore focus | canonical status/provenance unchanged; no authority added | [components.json](evidence/s03/components.json), `components/{controls,BottomSheet,StatusBadge,LanguageSwitch}.test.tsx`, [report/captures](s03-report.md) | four scenarios and eight axe scans pass;0 API/external requests/page errors | feature matrices, screen-reader, software keyboard and actual phone remain pending**. Baseline captures stay frozen; no route family is declared redesigned by shared-control adoption alone.

Append only observed results using: `control ID | fixture/role/account/controller | state | TR/EN | browser/viewport | expected next action | permission/provenance assertion | test/screenshot | observed result | dependency`. Each report links its updated rows and distinguishes source coverage, implementation, browser checks and external/human acceptance. Preserve all baseline artifacts when creating after captures.
