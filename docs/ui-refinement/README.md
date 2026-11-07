# UI refinement inventory

The implementation retains the existing semantic color palette, Inter/Manrope fonts, API calls, permissions, and routes. Shared conventions: plain page headers, restrained panel borders, 44px controls, clear primary/secondary actions, and desktop columns that stack on phones.

This inventory follows `frontend/src/app/router.tsx`. The separately packaged marketing site in `landing/` is unchanged.

## Route review

Workspace routes below are relative to `/w/:workspaceId`.

| Routes / variants | Decision and implementation | Browser journey |
| --- | --- | --- |
| `/login` | Quieter form, readable brand panel, touch-sized utility links | entry |
| `/reset-password`, `/reset-password/:token` | Consistent request/reset forms and success actions | public-pages + unit tests |
| `/invite/:token` | Retained focused invitation flow; shared public shell refined | entry |
| `/` | Refined workspace selection and link hierarchy | entry |
| `/workspaces/new` | Responsive category grid across wizard steps | entry |
| `/privacy`, `/data-deletion` | Retained reading measure; removed nested interactive controls, announced lookup feedback | public-pages + unit tests |
| Workspace index | Plain dated header; priority queue, metrics and upcoming/problem columns; readiness rail | today |
| `inbox` | Continuous wide conversation queue, compact guidance rail | inbox |
| `inbox/:conversationId` | Message/reply column beside assistant context and draft; mobile draft precedes composer | conversation |
| `content` library and all status tabs | Plain header, 44px filters, cohesive divided rows | content |
| `content?view=agenda` | Continuous dated groups with wrapping timezone label | agenda |
| `content/:id` | Editor and status/action columns; mobile status first | content-detail |
| `approvals` pending/history | Shared header, consistent tabs, cohesive decision queue | approvals |
| `more/agent` | Overview/capability columns; task/activity columns; voice and delegation form grids | agent-tasks, voice-delegation |
| `more/agent/questions`, `more/agent/questions/:questionId` | Shared back/title/account header; continuous queue; detail/response columns | questions |
| `more/agent/memory/:customerId` | Shared header, readable wrapping customer identifiers, consistent controls | memory |
| `more/agent/comments`, `more/agent/comments/:threadId` | Shared header, continuous queue, consistent thread controls | comments |
| `more/agent/tasks/:taskId` | Shared task header/account controls; retained task detail flow | agent-tasks |
| `more/knowledge` | Unified category list with readiness rail; readiness first on phones | knowledge |
| `more/knowledge/:category` | Plain header, responsive fact grid; retained editors and history dialogs | fact-editors |
| `more/knowledge/suggestions` | Shared header and responsive review layout | knowledge |
| `more/knowledge/answers` | Answer library beside composer; empty library gives composer full width | approved-answers |
| `more/automation` | Connection summary beside policy configuration | voice-delegation |
| `more/reports` | Header actions, date strip, real metric sections in columns; removed arbitrary comparison bars | reports |
| `more/reports/:date/:key` | Separated title/context and snapshot summary | reports |
| `more/activity` | Desktop date rail and cohesive event timeline | activity |
| `more/notifications` | Responsive message/action columns and pending feedback | activity |
| `more/settings` | Account/security beside workspace/management information | settings |
| `more/settings/connections` | Account and channel columns | connections |
| `more/settings/members` | Header invite action; member queue beside pending invitations | connections |
| `more/settings/system-health` | Responsive diagnostics grid and wrapping metrics | health-dev |
| `more/dev` | Two-column tools; separate full-width reset area | health-dev |
| `more` | Retained existing grouped navigation, shared shell/component refinements | shell |
| Unknown routes | Compact recovery inside the workspace shell; standalone recovery outside it; one main landmark in both cases | health-dev, public-pages, unit tests |

## Shared review

- Shell: visible desktop wordmark, semantic navigation colors, consistent rail width, more usable configuration-page width.
- Buttons: consistent typography, radius, spacing and restrained hierarchy; preserved disabled explanations, pending labels, focus outlines and native semantics.
- Panels/empty states: quieter borders, smaller radius and reduced visual nesting.
- Dialogs: wider desktop editing measure, coherent header/body/footer spacing; retained focus trap, restoration, dismissal and scroll containment.
- Forms: retained labeled native controls and validation association; grouped complex configuration into sections/grids.
- Tables: existing application data views are lists; retained the shared accessible scrolling table primitive.
- Mobile: fixed command bar offset above the five-tab navigation; retained safe-area spacing.
- Palette: all 28 existing hex color tokens were compared against HEAD and remain unchanged.

## Verification

`frontend/scripts/ui-refinement.mjs` reuses existing route-specific fixture journeys, redirects evidence here, and substitutes 1024px for their 360px scenario. Existing 390px, 768px and 1440px cases remain. Scenario labels inherited from the old scripts may still say `360`/`phone`; recorded viewport widths are authoritative. These are fixture checks, not live backend acceptance. Historical phase evidence is not overwritten.

Final commands and outcomes are recorded in `verification.md`. Per-suite logs and JSON evidence are under `checks/`.
