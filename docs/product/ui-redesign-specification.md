# Application UI Redesign Specification

**Status:** Core experience implemented, 2026-11-07; see [verification and before/after evidence](../ui-core-redesign/verification-report.md). The wider Phase 8.5 specification remains a reference for secondary workflows and historical scope. This core change does not assert whole-phase, live-platform, owner or actual-device acceptance.
**Reference:** [Interactive concept](https://agentnest-style-preview.woollyhero2.chatgpt.site) and [local concept source](../../design-preview/agentnest-today/README.md).
**Current behavior:** [User journeys](user-journeys.md). The core navigation and workflows below are implemented and documented there. Wider secondary-screen targets remain reference scope rather than an assertion of whole-phase acceptance.

## 1. Design intent and reference boundary

AgentNest should feel calm, competent and approachable to a business owner checking Instagram between real-world tasks. Use the concept's charcoal-green sidebar, warm canvas, white surfaces, deep teal primary actions, sage assistant areas, image-led content and clear separation between daily work and configuration.

The concept establishes composition and visual direction. It does not establish backend behavior, available metrics, permanent assistant branding, legal wording, per-account authority or production asset policy. Its fictional studio, prices, names, photos, numbers and in-memory actions must not become runtime defaults. Adopt the layout and improve text sizes/contrast for production.

### Design rules

1. Give each page one clear purpose, one main heading and a visible next action.
2. Use rows and dividers for related records. Use panels for distinct work areas. Avoid cards inside cards inside cards.
3. Put the proposed action and decision context before diagnostic metadata. Make source evidence reachable without losing the task.
4. Spend desktop width on related work: list/detail, editor/preview, queue/decision. Keep prose readable within wider layouts.
5. Keep the mobile primary action reachable above the keyboard and safe area. Long forms belong on focused pages, not tiny nested sheets.
6. Use warm supporting language, but explicit verbs for approvals, sending, publishing, erasure, access and recovery.
7. Show what the system knows. Unknown, unavailable, incomplete and zero are distinct values.
8. All interactive affordances must work, have an explained unavailable state, or be omitted. Never copy the concept's modal-only sidebar destinations as the production information architecture.

## 2. Design system

### 2.1 Semantic palette

Token names below are target semantics, to be mapped into the existing Tailwind/CSS setup in Session 02. Do not scatter raw values through feature components.

| Token/purpose | Starting value | Usage |
|---|---|---|
| Canvas | `#F7F8F3` | Application background |
| Surface | `#FFFFFF` | Editors, lists, neutral work panels |
| Surface subtle | `#F1F4EB` | Selected groups, quiet background regions |
| Navigation | `#253B31` | Desktop sidebar and mobile navigation drawer |
| Navigation text | `#E0E8DC` | Readable labels on dark background |
| Navigation selected | `#D1E4B7` | Selected entry, with dark readable text |
| Text primary | `#293B32` | Headings and main content |
| Text secondary | `#5D6B54` | Supporting content; check actual surface contrast |
| Action primary | `#31664C` | Primary action with white label |
| Action hover | `#24583E` | Hover/pressed primary action |
| Assistant surface | `#EAF0E3` | Assistant activity and grounded suggestions |
| Border | `#E1E6DB` | Nonessential surface divisions |
| Control border | `#7A886E` | When a visible boundary identifies an input/control |
| Focus | `#557344` | High-contrast visible outline; verify on both shells |
| Success | `#315C3F` / `#EDF4E9` | Verified successful outcome, text + icon |
| Attention | `#75603A` / `#F4EBD5` | Awaiting a decision, text + icon |
| Danger | `#A13732` / `#FCF0EE` | Failures/destructive actions, text + icon |
| Informational | `#315F78` / `#EAF1F5` | Scheduled, queued and checking states |
| Simulation | `#69478C` / `#F4EDF9` | Per-result simulation modifier |

Final values must meet measured contrast on each used background. A subtle panel border need not identify a control; a control's affordance must meet the non-text contrast target. Do not brighten semantic text merely to imitate a faint screenshot.

### 2.2 Type, rhythm and sizing

- **Headings:** Manrope, with system sans-serif fallbacks. **UI/body:** Inter, with system fallbacks. Bundle required Latin and Turkish glyphs and font licenses locally; no runtime font CDN.
- **Page heading:** desktop 30 px; phone 26 px; weight 600–700, restrained negative tracking, natural line wrapping.
- **Section heading:** 18 px; label hierarchy must remain clear without uppercase everywhere.
- **Working body:** default 14 px on desktop; 16 px for mobile forms and substantial message/editor text. Short list metadata may be 12–13 px. Do not use the concept's 8–10 px metadata as the production standard.
- **Numbers:** 28–36 px, tabular numerals for metrics/times where useful. Large counts are links only when their scope and destination are clear.
- **Line height:** 1.45–1.65 for body, 1.3–1.4 for headings. Support text expansion and browser text sizing.
- **Spacing scale:** 4, 8, 12, 16, 20, 24, 32, 40, 48 px. Page gutters: 16–20 px phone; 24 px tablet; 32–40 px desktop.
- **Corners:** controls 6–8 px, panels 10–12 px, large modal 12–16 px. Reserve pill shapes for statuses, counts and small identity elements.
- **Elevation:** borders and tone establish hierarchy. A modest shadow is appropriate for floating menus/dialogs, not every list row.
- **Icons:** one stroke-based SVG family. Extend existing local icon components where practical; decorative icons are hidden from assistive technology and icon-only controls have localized accessible names.
- **Motion:** 120–200 ms for subtle feedback. Respect reduced motion. No decorative animated assistant implies that work is actually running.
- **Targets:** primary touch controls at least 44 by 44 CSS px. Desktop may use a compact visual treatment while retaining an adequate hit area. Do not shrink mobile filters to fit a row.

### 2.3 Component inventory and required variants

| Family | Components/variants | Required behavior |
|---|---|---|
| Actions | Primary, secondary, ghost, danger, icon button, link action, split action only if needed | Default/hover/focus/pressed/disabled/pending; no icon-only ambiguity; preserve pending request behavior |
| Inputs | Text/email/password, textarea, number/money, URL/phone, select, checkbox/radio, date/time, file upload | Label/help/error, required/read-only/disabled, invalid/pending/conflict; preserve user input |
| Navigation | Sidebar item/group, bottom tab, workspace/account selector, breadcrumb, settings/category nav | Current location, unread/attention counts, role filtering, keyboard and deep-link state |
| Collections | List row, dense table, content tile, pagination, filter bar, search field, tabs/segmented view | Loading, empty, filtered-empty, partial data, error, selected row; preserve list position |
| Information | Status badge, simulation badge, identity/avatar, source chip, timeline event, metric | Canonical state and provenance; readable labels; unknown/missing variants |
| Feedback | Inline validation, error summary, notice/banner, toast, skeleton, empty state, full-page fallback | Severity and recovery action; live-region restraint; no toast as sole evidence of a critical outcome |
| Overlays | Menu, popover, tooltip, dialog, desktop drawer, phone sheet/full-screen editor | Focus entry/trap/return, Escape/backdrop behavior, dirty state, safe-area and scroll containment |
| Layout | Public shell, app shell, page header, panel header, list/detail workspace, editor/preview, detail/evidence region | Content-driven width; nested context; stable loading dimensions; correct reading order |

Avoid building a separate design system application or adopting a new UI framework solely for the redesign. A small development-only reference view or test harness can show components and states without adding a public product feature.

## 3. Navigation and responsive behavior

### 3.1 Desktop information architecture

| Group | Entry | Existing destination/behavior |
|---|---|---|
| Brand/workspace | Product identity and workspace switcher | Existing picker and workspace context; account selector only on account-scoped screens |
| Daily work | Today / Bugün | Workspace index; replaces the visible Home label |
| Daily work | Inbox / Gelen kutusu | Inbox and active conversation |
| Daily work | Content / İçerik | Library and calendar/agenda views |
| Daily work | Approvals / Onaylar | Pending/history; permission-aware count |
| Assistant | Assistant / Asistan | Overview, Voice, Permissions, History; requests are in Overview |
| Business | Business knowledge / İşletme bilgileri | Categories, suggestions and approved answers |
| Business | Reports / Raporlar | Daily report and evidence; no new analytics metric implied |
| Utility | Activity / Etkinlik | Existing activity feed |
| Header | Notifications / Bildirimler | Bell and retained notification-center route; no duplicate sidebar item |
| Utility | Settings / Ayarlar | Account/workspace settings, connections, members and health; developer entry only when enabled |

Use the retained brand identity; any new nesting mark remains a proposed asset until checked against existing product/landing branding. A fictional permanent assistant name from the concept is not required. Do not duplicate notifications, settings and account identity across several competing headers.

### 3.2 Phone and tablet

- **Under 768 px:** Today, Inbox, Content, Approvals and More bottom tabs. More becomes a grouped destination page; its drawer equivalent may be an additional shell affordance but must not remove the existing `/more` route.
- **768–1199 px:** compact navigation with expanded labels available; use list/detail only when both panes stay usable. Prefer a list followed by detail at narrow tablet widths.
- **1200 px and above:** expanded 224–248 px sidebar; fluid content with a suitable maximum working width around 1440 px. Do not impose the existing global `max-w-3xl` on dashboards, inboxes or editors.
- **Readable forms:** keep prose/form columns approximately 560–760 px within a wider settings/editor layout. Wider does not mean every input spans the screen.
- **Details:** at 1200 px and above a 320 px list remains beside the selected detail. The Inbox splits earlier, from 1024 px (300 px list, 340 px from 1280 px), because its rows and detail were verified at that width beside the collapsed rail. On phones, opening a record shows its own page with a back destination; return restores filter and position where possible.
- **Phone overlays:** brief confirmations can use sheets; long fact editors, scheduling detail or permission forms use full-height layouts with reachable save/cancel controls.
- **Keyboard:** input focus, mobile keyboard, safe areas and 200% text must not hide the composer or decision footer. Bottom navigation and command entry must not stack over the active task.

Session 01 confirms breakpoints against Turkish content and real data. Verify 360, 390, 768, 1024, 1440 and 1920 px, including representative short-height and landscape views.

### 3.3 Route and query compatibility

`W` below means `/w/:workspaceId`. Preserve every current path. Inbox uses `section=messages|comments|questions` (Messages by default); old question/comment URLs select their matching tab. Assistant uses `panel=overview|voice|permissions|history` (Overview by default). Record IDs remain in paths. New visual groupings do not require route churn. Existing `account`, `tab`, `status`, report date/snapshot and notification-target parameters retain their meaning.

| Screen ID | Existing route/surface | Target area | Session |
|---|---|---|---|
| R01 | `/login` | Branded public/auth shell | 05 |
| R02 | `/invite/:token` | Invite acceptance and error states | 05 |
| R03 | `/` | Workspace picker | 05 |
| R04 | `/workspaces/new` | Three-step workspace wizard | 05 |
| R05 | `W` | Today | 06 |
| R06 | `W/inbox` | Conversation list/workspace | 07 |
| R07 | `W/inbox/:conversationId` | Conversation detail and composer | 08 |
| R08 | `W/content` | Library + planning views and state filters | 09–10 |
| R09 | `W/content/:id` | Content editor or immutable published detail | 11 |
| R10 | `W/approvals` | Pending/history queue and selected decision | 12 |
| R11 | `W/more/agent` | Assistant overview/tasks/voice/permissions | 13–14 |
| R12 | `W/more/automation` | Legacy automation or link to the current controller view | 14 |
| R13 | `W/more/agent/questions` | Questions list | 15 |
| R14 | `W/more/agent/questions/:questionId` | Question answer/proposal and history | 15 |
| R15 | `W/more/agent/comments` | Public comments list | 16 |
| R16 | `W/more/agent/comments/:threadId` | Public thread and moderation | 16 |
| R17 | `W/more/agent/memory/:customerId` | Private customer memory | 17 |
| R18 | `W/more/agent/tasks/:taskId` | Task detail and clarification | 13 |
| R19 | `W/more/knowledge` | Knowledge overview | 18 |
| R20 | `W/more/knowledge/:category` | All supported categories | 18–19 |
| R21 | `W/more/knowledge/suggestions` | Suggested/discrepant facts | 19 |
| R22 | `W/more/knowledge/answers` | Approved-answer library | 20 |
| R23 | `W/more/reports` | Daily report | 21 |
| R24 | `W/more/reports/:date/:key` | Saved metric evidence | 21 |
| R25 | `W/more/activity` | Activity timeline | 22 |
| R26 | `W/more/notifications` | Notification center | 22 |
| R27 | `W/more/settings` | Account/workspace settings | 23 |
| R28 | `W/more/settings/connections` | Instagram account connections | 24 |
| R29 | `W/more/settings/members` | Members, invitations and roles | 24 |
| R30 | `W/more/settings/system-health` | Operational health | 25 |
| R31 | `W/more/dev` | Development-only simulator/tools | 25 |
| R32 | `W/more` | Grouped secondary navigation | 04 |
| R33 | Workspace and global `*` | Permission-safe not-found/recovery | 25 |
| R34 | Phase 8 account-security/reset UI | Use delivered route contracts; no guessed URL contract | 23 |
| R35 | Phase 8 export/erase/workspace deletion/status UI | Use delivered permission/lifecycle contracts | 23 |
| R36 | Existing `landing/` application | Public landing, demos, FAQ and waitlist states | 26 |
| R37 | Existing transactional/public status presentation | Invite/reset/deletion messages; minimal safe status where delivered | 26 |

Session 01 enumerates new routes added after this snapshot and records them with the same fields. Do not claim R34–R35 implemented because a mock modal exists. Provider callback APIs stay APIs unless their owning Phase 8 contract defines a browser page; any public deletion status remains minimal and privacy-safe.

## 4. Screen specifications

Every section below inherits the state, role, privacy, responsive and verification rules in sections 5–7.

### 4.1 Login, invites, workspaces and onboarding — R01–R04

- Login uses a quiet branded composition: readable form, language selection, clear primary action; desktop may have a restrained brand/message region. Phones show the form first.
- Retain autocomplete, paste/password-manager support and the existing return-to destination. Include invalid credentials, pending, network failure, session expiration and Phase 8 throttle feedback without exposing account existence.
- Invite acceptance shows workspace, intended role and account state only when authorized by the token contract. Cover invalid, expired, consumed and wrong-account cases; no usable token in a reusable screenshot.
- Workspace picker uses distinct workspace rows/tiles, role and demo information, a clear create action, empty membership and revoked-access recovery.
- Workspace creation retains name, business category, market, language, timezone and currency steps. Back preserves input; validation is inline; market changes keep the documented defaults and explicit override behavior.
- After creation, guide owners into the current knowledge/readiness flow. Do not invent self-service registration, billing, business metadata editing or automatic Instagram connection.

### 4.2 Today and existing commands — R05

- Desktop order: account-blocking notices and a compact strip of today's period numbers span the page (each number links to its evidence; a comparison with yesterday appears only when the value changed, never as a percentage from a zero base). Below them, two independent columns keep their natural heights, so no card is stretched to match its neighbour: the main column holds the assistant panel (per-account state and pause/resume, inline request entry, the latest agent activity) and upcoming content (seven-day calendar plus a capped visual preview of the next scheduled items); the side column holds Needs your attention, appointments, incomplete readiness and, while readiness is complete, Instagram performance. With open readiness requirements, performance moves to a full-width band below. Phones show Needs your attention first, then the numbers, then the assistant. New content actions stay in the page header.
- Attention rows are whole-row targets whose accessible name is the concrete next action: connection recovery, recent failed posts, pending approvals, business questions, conversations needing a person, held content, drafts and unanswered comments, most urgent first; review work (drafts, comments) follows a divider. The total appears only when every count is known.
- Upcoming content has one empty state for the whole plan. A day without a story offers to draft one; scheduled counts derive from the fetched scheduled page and show "+" when that page is full.
- Current report counts remain distinct from period metrics. Failed and upcoming posts are labelled capped previews; their lengths are never totals. Missing or failed data never establishes a quiet state.
- Business-question counts come from account-agent overviews. Staff see only server-authorized report metrics. Simulation remains visible on affected results.
- Readiness disappears when complete. Open requirements come first; completed requirements are collapsed.
- Request entry stays inline at every width. Existing command interpretation, clarification, confirmation and result semantics are retained.

### 4.3 Inbox and conversations — R06–R07

- Inbox has Messages, Comments and Questions navigation. Old public/comment/question routes stay valid and mount the matching workspace. Desktop: conversation list with current filters beside the active conversation; an optional context region can show verified source links, current thread/task and authorized private memory. Narrow layouts progress list → detail → context.
- List rows: identity/initials with fallback, message preview, meaningful time, attention reason, handling mode, reply window and simulation marker. Never create unread semantics from an unrelated attention flag.
- Preserve current filters (`any`, `needs_approval`, `needs_human`, `failed`) and sorting semantics. Add a search field only when its scope and data completeness are defined; label loaded-items search honestly if used.
- Conversation header: customer identity, current handling mode, takeover/release, suggest reply and actionable window/connection state.
- Message stream: clear inbound/outbound/native-business distinctions; localized timestamps, attachments, removed/redacted content and loading older records where supported. Avoid forced scroll jumps when a draft refreshes.
- Draft region: actual proposed text, grounding/source chips, why approval is needed, validation, edit/reject/approve, and a different needs-human path for complaints or unsupported content.
- Composer: preserve input on failure, show applicable limits, pending/disabled reasons and verified outcome after sending. Manual replies and AI approval are separate actions.
- Cover new inbound message superseding a draft, changed facts, stale approvals, expired windows, duplicate decisions, role changes, takeover, native Instagram replies and outcome unknown.
- As built: the section tabs are a segmented control under the page title with a per-section intro line. Comments shows the unanswered-comment total (`home/attention`) and Questions the pending business-question total across connected accounts (agent overviews); Messages shows no count because its list is a capped recent preview. Counts appear only when known and non-zero. Filter pills wrap rather than scroll a filter out of view; an empty filter offers "show all". Attention reasons have distinct tones: awaiting approval uses the assistant tone, needs-you uses attention, problems uses danger. With nothing selected, the detail pane explains the three reasons. The list ends with a "most recent conversations" note instead of a total. The detail is one surface: header, day-grouped thread (scrolls in place from 1024 px and follows new messages only when already at the bottom), the assistant's draft, then the composer. A closed reply window is explained above the composer. Export/erase sit in an owner-only overflow menu.
- Export/erase entry points use Phase 8's owner-only contracts, explicit scope and consequences. A UI refresh must not retain removed customer's private text in a new local cache.

### 4.4 Content library, planning and editing — R08–R09

- Layout: page header with the Library/Agenda switch; one composer (assistant tone) is the page's creation entry — a typed brief opens the existing draft sheet prefilled with brief and format (nothing is generated until the owner sends it), and a quieter blank-draft action sits beside it. The library shows the four status tabs as tiles with counts derived from each tab's fetched page ("50+" when the page is full; lists request `limit=50` explicitly) and one line of context (pending approvals, next scheduled time, latest publication, problems), then a search/format filter over the loaded page and a visual card grid. Each tab has its own empty state with a real next step; an account with no content at all sees a three-step "idea → schedule → follow" orientation.
- Library: real thumbnails, title, format, status, meaningful scheduled/published/updated time and a clear AI-draft/blank-draft entry. Placeholder artwork says there is no image; it never masquerades as uploaded media. Images keep their own ratio inside a uniform 4:5 frame (contained on a blurred copy of themselves). Cards in Problems state the hold/failure/rejection reason.
- Agenda: a Monday-to-Sunday week on the workspace clock (rows on phones, seven columns from 1024 px) with week navigation from the current week forward, plus a list layout of everything scheduled. Items scheduled before the current week (late or retrying) are listed above it. When the scheduled page is full, days after its last item read "not loaded", never free.
- Preserve Drafts, Scheduled, Published and Problems membership from the existing status helpers, including `tab`/`status` links from reports. Cancelled items do not acquire a new tab membership accidentally.
- Planning: desktop week/month or agenda views, phone agenda by default; show only API-backed scheduled items in the selected workspace timezone. Differentiate scheduling, publishing, retry, held and verified publication.
- Calendar requires complete date-range data. Define pagination/range coverage in Session 01/10; no fabricated empty day or client-only reschedule. Drag-to-reschedule is excluded from this phase.
- Editor: publishing account and fixed existing format, image, caption/structured controls, then optional internal title/image notes. At 1200 px and above a persistent approximate preview displays the authoritative account, stored image and current local caption. The existing submission contract chooses the workspace’s single active account; the UI does not offer an account choice it cannot apply. Phones expose Preview/Edit without losing form state. Existing content types remain image feed and image Story.
- Media: file selection, image loading/upload/validation, replace/remove when supported, aspect guidance, failure/retry and missing/deleted media. Use authenticated preview access and cleanup of object URLs; no provider secrets in image URLs.
- Keep Story overlay suggestions distinct from the image itself. Show that text is not baked into the uploaded bitmap and not sent as a caption. The preview cannot imply compositing or publishing behavior that does not exist.
- Grounded facts, visual notes, caption length and pre-publication validation remain visible at the relevant field. Dirty edits, save failure, generation delay/failure and lost approval are explicit.
- Scheduling review: exact content, account, date/time/timezone, relevant authority and expiry; explicit approve/schedule/publish action with current role constraints. Never infer that saving a calendar date approved publication.
- Published content is immutable. On-hold/failed/rejected/checking states offer only the recovery actions the current state machine permits; show retention-deleted media honestly.

### 4.5 Approvals and decision history — R10

- Queue rows identify action type, subject/person, key change, requested time and expiry, current state and provenance. Pending and History remain distinct views.
- Selection retains the queue and opens the existing accessible decision sheet; pending/history and selected approval are stored in the URL. Contextual thread approvals reuse the same summary and decision sheet. Direct subject links and refresh restore selection without guessing private IDs.
- All existing bodies are redesigned: reply send, content publish/schedule/cancel, business-fact change/impact and account-agent actions. Use exact backend summary/version/hash evidence.
- Show proposed text/image, old/new values, affected records and relevant source/permission explanation before the primary decision. Critical content cannot hide behind a tooltip.
- Distinguish human approval from an automatic policy grant in history. Approval accepted is followed by actual queued/sending/checking/sent or publishing outcomes, not an immediate success badge.
- Cover expired, cancelled, rejected, stale, already-decided, changed subject, partial load and permission loss. No bulk approve feature is added.

### 4.6 Assistant overview, tasks, voice and permissions — R11–R12, R18

- The route-aware tabs are **Overview, Voice, Permissions, History**. Questions and Comments live inside Inbox. Account changes preserve the active panel.
- Overview: current account, controller mode, actual active/paused/legacy state, waiting counts, current work and recent verified action outcomes. A connected account alone does not mean the assistant is running.
- Overview starts with existing authenticated owner-task composer and current requests, followed by account status and recent outcomes. History shows existing action records. Requests retain read-only progress, action status, linked content/approval, clarification and media/content selection. Keep existing pagination and requester authority.
- Task detail separates requested goal, question awaiting an answer, pending external outcome and completed action. Choosing a media/content reference does not change permissions or approve publishing.
- Voice: goals, tone, formality, length, emoji, DM/comment styles, TR/EN examples and sample preview. Clearly distinguish a static example from a real model run. Preserve expected-version saves and stale-form recovery.
- Permissions: Messaging, Comments and Content groups retain an independent off/ask/automatic mode per action. Daily limits and request sources are initially collapsed under Advanced settings. Explain unavailable combinations before saving; show exact proposed changes for review.
- Pause/resume and controller cutover are deliberate controls with consequences. Pause never claims to retract already sent work or settle unknown operations.
- Legacy automation remains reachable and truthful for accounts still using it; do not show both controllers as independently active. A shell link can lead to the correct controller-specific view without inventing an automatic migration.
- As built: tabs are a segmented control beside the title with a per-tab intro; the account picker appears only with more than one account. Overview opens with an assistant-tone band: account identity, state (Active / Paused / Inactive / Previous automation), a sentence that says "working on N" only when the overview reports running sessions, pause/resume or enable with the pause warning beside it, a reconnect notice, then "Waiting for you" (action approvals, information requests, each linking to where it is handled) and "Assistant work" (in progress = running, queued, verifying, waiting for customer, waiting until due; all-time completed and failed). Below, a main column holds the request composer (Ctrl/⌘+Enter, counter, visible reason when requests are blocked, suggestion chips that only fill the field, a three-step "what happens next"), Your requests (open first, five shown; named by their first action because the list carries no request text; clarification shown with an Answer link; per-action result and content/approval links) and the five latest actions as a timeline (linked to the owner's request when one produced it). A side column holds capabilities grouped as Messaging, Comments and Publishing (unknown keys under Other) with provider availability and the assistant's delegation mode, flagging a mode that the connection cannot use; the Google Calendar connection with real status and booking modes; and Control (controller, Instagram connection, owner-only return to previous automation under Advanced settings). Voice uses segmented choices with a sticky summary and the static sample preview. Permissions keeps per-action off/ask/automatic as segmented controls with a mode legend, notes actions the connection or a missing calendar cannot perform (explanatory only), counts changed actions in a sticky bar, and still applies only the exact previewed policy. History groups loaded requests and recorded actions by workspace day with filters (needs you, in progress, completed, failed, cancelled) and labels its scope (latest 20 requests, latest 10 actions).

### 4.7 Owner information questions — R13–R14

- List pending and answered/expired states using actual list/query capabilities; rows show the question, why input is needed, visibility, account/thread context and deadline.
- Detail puts the question and relevant safe context before the answer/proposal composer. The prominent explanation says this is information, not approval.
- Owner/manager answers, staff proposals, reusable-knowledge opt-in, expected-version conflicts and answer history retain their existing contracts.
- Use “Information needed” and “Save for future answers.” Generate `custom.owner_answer_<question UUID without hyphens>` internally. The candidate remains unverified until the existing knowledge review; the owner never enters a technical key.
- Contextual private questions use the optional scoped `thread_id` API filter before pagination. Public comments never request private questions or memory.
- Show removed content and expired/already-answered questions. Do not silently verify reusable business knowledge or dispatch an Instagram action after a free-text answer.

### 4.8 Public comments and moderation — R15–R16

- Desktop list/thread layout with post context; phone list → thread. Respect provider pagination, account selection and public-thread provenance.
- Display public post caption/media where delivered, comment author/content/time/state, native-owner comments and visible/hidden/deleted/removed states.
- Keep the public-context notice readable. Private customer memory, DMs and owner-only answers are not prefetched into this view or inserted into a reply context panel.
- Reuse current public reply/private reply availability only where the API exposes a supported path. Do not create a new arbitrary manual reply API as visual polish.
- Hide/unhide/delete use permission/capability-aware controls, explicit effect-specific confirmation, current version and actual operation status/history. A queued delete is not already deleted.
- Show unknown moderation outcomes, unavailable permissions and lost source content. Do not assert real comment capability acceptance from mock demonstrations.

### 4.9 Private customer memory — R17

- Customer/account identity and scope are visible at the top. Match existing source/identity linkage; shared names never establish a merge.
- Group active memories with source, version, confidence/type where supplied and current usability. Provide supported correction/removal actions and source drilldowns in an adjacent drawer or focused mobile view.
- Historical/derived summaries must retain evidence and removed-source states. A stale source is not displayed as verified business knowledge.
- Explain owner/staff availability and Phase 8 export/erase boundaries. Never add a broader CRM or public-memory panel.

### 4.10 Business knowledge — R19–R21

- Overview: readiness and actionable gaps first, pending suggestions and clear paste/extract entry, then category summaries. Compact the fully complete checklist rather than spending an entire page on it.
- Desktop category navigation beside fact rows/details; phone grouped category list and focused category pages. Preserve exact category keys and deep links.
- Cover every current category: `identity`, `contact`, `location`, `hours`, `service`, `pricing`, `promotion`, `booking`, `policy`, `schedule`, `faq`, `brand`, `escalation`, `custom`.
- Fact browsing emphasizes label and formatted value, then verified/unverified/contested/missing status, source and last meaningful verification/version metadata. Do not use vague green dots for fact usability.
- Edit/create includes all current value types: money, weekly hours, text, localized text, phone, email, address, URL, boolean, enum and string list. Include currency/unit/conditions, weekday ranges/closed days/exceptions, per-language values and correct list editing.
- Suggestions/extraction: supplied source text, extraction pending/error, candidate comparison, discrepancy, accept/reject/keep-current and staff proposal. Keep pasted input on failure; extraction never silently verifies facts.
- History: immutable versions and source/actor/time; changing a current fact creates a new version. Show impact on pending drafts, scheduled posts and approved answers using existing services.
- Large editors use full-screen phone layouts with explicit save/cancel, validation and dirty-state protection; no nested modal inside a modal.

- As built: the overview opens with a strip of four counts (verified facts in use; facts to review = unverified, contested or expired; pending suggestions, linking to them; template items not added yet, with how many block setup). There is no percentage, because optional items are not gaps. "Needs your attention" lists, in order: open knowledge readiness requirements (an unverified fact that would satisfy one is shown with its value), pending suggestions, contested facts (to the suggestion), unverified facts and expired ones. Five are shown, the rest behind "Show more". Unverified facts can be verified there by an owner or manager with the same version-bound call as on the category page. Categories appear as tiles in three groups (business basics, what you offer, how to answer), each with worded counts. A search over fact names (both languages) and values, and over names of items not added yet, replaces the tiles and deep-links to `…/knowledge/<category>#fact-<key>` or `#item-<identifier>`. A side column (two columns below 1280 px, after the attention list on phones) holds the paste-and-extract entry with its three steps, assistant setup and approved answers. Setup shows the server's readiness split into drafts and automation. Knowledge requirements there point to the attention list instead of repeating it, finished stages collapse to one row, and a note says optional facts never block setup. "Needed" comes only from readiness `missing_keys`: a template item that readiness is not waiting for (WhatsApp once a phone exists, preset prices, the price answer when prices are shared) is "Not added", never "Missing". Contact-style groups say "One of these is needed". The category page has a grouped category rail from 1024 px (a scrolling strip on smaller screens), fact rows (label, value, quiet "Verified" or a pill for any state that needs action, provenance, notes; Verify is the primary action only for unverified facts), a "Not added yet" list and archived facts collapsed. Suggestions show "in use now" beside "suggested", their source (pasted text or a team member) and the excerpt.
### 4.11 Approved answers — R22

- A browsable answer library with intent, language, question/title, template preview and current usability. Only expose supported filtering/search scopes.
- Creation preserves title, intent, question, TR/EN choice, grounded template/placeholders and validation feedback. Explain usable fact references in owner language.
- Archive follows the existing action; a price change requiring review remains visible. “Approved answer” is a reusable template, not an approval to bypass current policy for a new message.
- Preserve save-as-approved-answer from conversation context; staff/owner restrictions remain explicit.

### 4.12 Reports and evidence — R23–R24

- Reports retain local-day navigation, partial/as-of status, simulation indicators, existing sections and regenerate permissions. Numbers get readable emphasis and direct evidence links.
- Evidence pages identify selected day, metric definition and saved snapshot/generation. Preserve historical membership even when live records change or have been erased.
- Median response-time rows remain duration evidence, not a count of messages. Missing/legacy evidence receives an honest explanation.
- Trends and charts are optional presentations of defined existing records, never invented metrics. If historical series are unavailable, ship a strong daily report instead of a sample weekly chart.
- Empty/zero, partial failure, stale evidence, regenerated report and restricted-role cases must be designed.

### 4.13 Activity and notifications — R25–R26 plus bell

- Activity uses a scannable timeline grouped by appropriate local date, with existing group/date filters, pagination, actor, action, subject link, severity and simulation where applicable.
- Distinguish operational explanations from raw model internals. Expose only already approved safe diagnostic data; no chain-of-thought, secrets or new customer-text logging.
- As built (Activity): a "Last 7 days" strip of server counts over the whole history (key events with the number of technical entries left out, completed, warnings, failed); each count filters the feed by that outcome. Filters (type chips that scroll on phones, an outcome select, a workspace-local day, a "Technical entries" switch that is off by default) all run on the server and live in the URL; an active-filter line offers one reset. The feed is grouped by local day (date column from 1024 px). Rows show an icon for the kind of event on a tile toned by level, the headline, the related record link, the actor, workspace-clock time and a pill only for failures and warnings. Within a day, three or more entries with the same server `collapse_key` (an alert condition, the same action on the same record) fold into one row at the newest entry with its count, time range and worst level, labelled "Similar entries grouped". It expands to every entry, and each entry expands to its details: full time and zone, actor kind, type, outcome, record, whitelisted details, reference ID and action. "Show related activity" opens all entries of the same flow (correlation), technical ones included. Counts that may continue on the next page read "N+". Loading older activity keeps the loaded entries on a failed page and offers a retry.
- Notification center retains current read/unread and mark-read behavior, severity, timestamps and typed destination mapping. A small popover may preview authorized results but does not replace the full center.
- Deleted/foreign/stale targets lead to safe current context or a clear unavailable state. Read/unread changes and badge counts use the server's contract; announcements do not repeat on every poll.

### 4.14 Settings, security and privacy — R27, R34–R35

- Settings uses section navigation: Account, Language, Workspace context, Connections, Members, Security, Privacy/data and System health as permissions and delivered contracts permit. Do not add editable business fields without an API.
- Account identity, saved language, timezone/currency context and sign-out are clear. UI language and business reply language remain separate concepts.
- Phase 8 security: session listing/current-device marker, single/all-other revocation, password change, reset request/confirm, throttling and invalid/expired/used reset link. Use backend invalidation rules and privacy-safe request responses.
- Phase 8 data rights: conversation/customer scope selection, owner-only export download, pending/error outcomes and erasure confirmation. Explain redaction versus final purge when unresolved operations remain; never promise instant total deletion.
- Workspace deletion: clear workspace identity and consequences, server-provided scheduled date/deadline, grace/cancellation states and the fact that cancellation does not automatically reconnect/resume accounts. Keep destructive actions separate from routine saves.
- Token links, download responses and public status views follow current auth/privacy contracts. Public deletion confirmation must not reveal customer, account or workspace identity.
- These rows remain named upstream dependencies until Phase 8 delivers them. Never replace them with nonfunctional settings toggles.
- As built: one page with in-page section navigation (a sticky list from 1024 px, a scrolling chip strip below; the highlight follows the scroll and the hash is kept): Account, Workspace, Security, Connections, Privacy & data. Account shows identity with sign-out, an editable display name (`PATCH /auth/me`), the role, and the interface language as a radio segmented control saved to the account, with a note that customer replies use the workspace's reply languages. Workspace shows friendly details (business type, region, currency name, time zone as "City (GMT±hh:mm)", reply languages, created date); only the owner can edit name and time zone (`PATCH /workspaces/{id}`, `workspace.manage`), and a time-zone change shows its consequence before saving. Team members (with a member count) and System health (owner/manager) are navigation rows, not integrations. Security has the password form (show/hide toggles, client checks for length and confirmation, a wrong current password and the server's `too_short`/`too_common` mapped to their fields, a note that other devices are signed out) and signed-in devices named from the stored User-Agent by a conservative parser (`features/settings/deviceLabel.ts`: browser, OS and device type, or "Unknown browser"; the raw string is never shown), this device first, last activity, sign-in date and IP. Signing out one device or all other devices asks for confirmation and uses the existing server revocation endpoints. Connections summarises Instagram and Google Calendar with their real status, simulation badge and a Connect/Reconnect/Manage (owner) or View link to the connections page. Privacy & data points to where data rights actually live: per-conversation export/erasure in the Inbox (owner), optional history deletion when disconnecting Instagram, and the privacy policy. The owner-only deletion panel summarises the consequences; the dialog lists what happens right away, during the 7-day window (cancellation does not reconnect Instagram, resume automation or restore cancelled items) and afterwards, and requires typing the exact workspace name. While deleting, the panel shows the scheduled date in the workspace time zone, days left, and Cancel deletion until `can_cancel` is false; every member sees a banner. Copy says data is "scheduled for permanent deletion" because no job runs `purge_workspace` yet (see ADR-025 §3.3). The deletion email's cancel link opens `/w/{id}/more/settings#danger-zone`.

### 4.15 Connections, team and invitations — R28–R29

- Connection list: account identity, real/mock provider, state, meaningful health timestamp/error and actual capabilities. Distinguish OAuth permission availability from configured agent delegation.
- Connect/reconnect/OAuth return: pending navigation, accepted/denied/expired/error and retry with an explicit valid next step. Preserve callback/query contracts and account/workspace scoping.
- Disconnect: show scope, paused future effects and any optional data-removal consequence; preserve unknown-operation reconciliation and current confirmation API.
- Team: member identity/role, permitted role changes/removal, owner constraints and current-user consequences. Staff do not gain hidden management controls.
- Invites: role choice, pending/revoked/accepted/expired state, allowed resend/delivery behavior, one-time URL/QR/copy feedback where still supported, and acceptance details. Do not display a sent-email success before the delivery contract confirms that outcome.

### 4.16 System health, developer tooling and global fallback — R30–R33

- Health: grouped account, operation, job/webhook and AI sections with period/as-of context. Phase 8 backup/alerts/runtime-role information appears only when delivered and authorized.
- Technical diagnostics remain useful for operators without dominating ordinary owner screens. Use code formatting for bounded IDs/error codes, accessible tables and honest unknown/not-configured values.
- Developer panel retains scripted messages, failure rules, published simulator state, jobs, trace entry points and demo reset. Group tools with clear simulator scope; destructive reset includes confirmation and handles the recreated workspace ID/cache invalidation.
- Developer entry and routes stay unavailable when `demo_tools_enabled` is false. The redesign cannot make them production features.
- Global fallback: auth/workspace loading, 401/403 handling under current contracts, not found, deleted record, no membership, offline/network, failed chunks/assets and recoverable page errors. Avoid leaking foreign-workspace record existence.

### 4.17 Landing, waitlist and transactional presentation — R36–R37

- Align retained brand mark, color/typography roles, buttons, sample product frames and navigation with the finished app. Marketing may use larger display type and editorial space; it does not copy the authenticated sidebar.
- Cover every existing landing section: hero, comparison, owner-chat example, knowledge, conversation demo, content planning, escalation, reports, controls, onboarding steps, FAQ and pilot/waitlist.
- Demo phone frames and illustrative screenshots match implemented app behavior and carry example labels. Do not advertise deferred owner channels, real comment capabilities or unsupported autonomy as available.
- Preserve language/theme controls, section links and actual waitlist/WhatsApp fallback configuration. Cover input validation, consent wording, submission pending/success/failure and no-endpoint/manual-contact paths.
- Reuse approved legal/disclosure content. Align existing invite/reset/deletion/operator-email templates and minimal browser status presentation where delivered without changing recipients, consent, token lifetime or delivery mechanics.
- Deployment of the landing page, transactional delivery and live submissions remain separately authorized work. Local/offline tests must not contact a real waitlist endpoint.

## 5. Shared interaction and state contract

| State family | Required presentation and behavior |
|---|---|
| Initial loading | Stable shell and meaningful skeleton; do not briefly show no account/no records before data resolves |
| Empty | Explain what belongs here and give the permitted next step; avoid celebratory “all done” for missing/error data |
| Filtered empty | Identify active filter and offer clear/reset; preserve scope |
| Partial/unavailable | Keep usable regions visible; identify which data failed or is incomplete; no fabricated zero |
| Mutation pending | Stable target, duplicate submission protection, relevant progress; retain form input |
| Field validation | Inline label-linked feedback plus summary when useful; keyboard focus on actionable error |
| Stale/conflict | Explain changed version/permissions, fetch current state and allow deliberate review; no silent overwriting |
| Success | Persisted state drives status. Toast can supplement but not replace record-level evidence |
| Ambiguous effect | “Checking”/current known state; explain safe next step. No one-click resend that bypasses reconciliation |
| Destructive action | Exact subject, effect and consequence; safe cancel/default; explicit action label |
| Dirty navigation | Warn for unsaved substantive edits; preserve input on save failure; do not warn for read-only navigation |
| Access change | Clear sensitive current data and restore safe context when user/account/workspace authority changes |
| Removed/redacted source | Privacy-safe placeholder and valid navigation; never restore old text from stale UI state |
| Offline/transient error | Preserve task context/input and offer safe retry; never manufacture a pending external operation |

Tab/filter/view state and selected records must survive direct URLs, refresh and browser Back according to a documented route policy. Sensitive draft text is not placed in URLs. UI-only search/launcher must distinguish destination navigation from effectful command execution.

## 6. Accessibility, internationalization and performance

- Target WCAG 2.2 AA behavior: normal text at least 4.5:1, large text at least 3:1; required control/focus boundaries at least 3:1 on their actual adjacent surfaces. Measure actual states rather than approving a palette in isolation.
- Keyboard reaches every control in logical order. Use semantic links for navigation and buttons for actions, appropriate tabs where present, visible focus, one main landmark and correctly nested headings.
- Menus/dialogs/drawers have localized names, Escape behavior, appropriate modal focus handling and return focus. A search field's native Escape-clears-text behavior must not trap an open command dialog.
- Use polite status announcements for async work and assertive ones sparingly for blocking failures. Never announce an entire conversation on each background refresh.
- Verify 200% zoom/text, 320 CSS px reflow where applicable, reduced motion, long names and message wrapping, phone safe areas and software keyboard. Tables may scroll within labelled containers without overflowing the whole document.
- Turkish/English parity includes errors, reasons, tooltips, badges, empty states, alt text, calendar labels, a11y labels and plurals. Test `İ/ı/Ğ/ğ/Ş/ş/Ö/ö/Ü/ü/Ç/ç`, long translated labels and locale-aware search/sorting where used.
- Use existing workspace-timezone/currency helpers; do not infer time from the host clock or UI language. Business reply language stays independent of interface locale.
- Self-host necessary assets and use real authenticated media previews. Lazy-load noncritical thumbnails, bound long lists via existing pagination and avoid loading all private contexts for a public thread.
- Session 01 records production JS/CSS/font sizes, representative initial/subsequent route timings, query counts and image payloads. Investigate regressions exceeding 15% of a measured route baseline or 50 KiB gzip added to initial JS; document whether justified. These are review triggers, not invented measured results.
- Shared presentation refactors must not refetch a full workspace for every drawer/tab. Query invalidation and workspace switching clear the same authoritative scope as before.

## 7. Coverage and evidence matrix

Create `docs/implementation/phase-8.5-sessions/screen-coverage.md` during Session 01 from the actual router and component inventory. Include one row per route family, nested editor/overlay and applicable state; add rows for newly delivered Phase 8 UI. This document is the target inventory, not a completed ledger.

Each evidence row records: screen ID, path/control, source file, session owner, role/account/controller, data fixture, state, language, viewport/browser, expected next action, permission/provenance assertion, screenshot/test path, observed result and unresolved dependency.

| Coverage dimension | Required scope |
|---|---|
| Routes | Every R01–R37 row and later additions has a recorded disposition; runtime inventory diff explains any change |
| Layout | All route families load at phone width without page overflow; representative task layouts captured at 360/390, tablet 768/1024 and desktop 1440/1920 |
| Languages | Every route has TR/EN text coverage; all major layouts and critical dialogs have captures in both languages |
| Roles | Owner, manager, staff, revoked membership and foreign IDs on affected areas; do not multiply irrelevant public/login combinations |
| Accounts | Real/mock presentation using fixtures, no account, disconnected/degraded/reauth, legacy/agent/paused, unavailable capability |
| States | Applicable loading, empty, filtered empty, partial/error, validation, pending, success, stale, expired, checking and redacted cases |
| Critical workflows | DM draft → approve → actual outcome; complaint handoff; fact update/impact; content upload/schedule/publish/recovery; task clarification; owner answer; moderation; privacy/security flows |
| Navigation | Direct URL, refresh, Back/Forward, open notification/report target, change workspace/account with detail open |
| Accessibility | Automated scans on shared layout and each distinct critical interaction pattern; keyboard, screen-reader spot checks, zoom and phone keyboard checks |
| Offline | Core demo and browser tests run without external credentials/egress; fonts and assets still render |
| Human acceptance | Windows desktop and actual phone walkthrough with device/OS/browser, language, findings and owner result recorded |

Do not execute a Cartesian product of every dimension. Cover every route, every critical state/role distinction and every shared interaction pattern with representative combinations and explicit traceability. A beautiful dashboard alone is not whole-app completion.
