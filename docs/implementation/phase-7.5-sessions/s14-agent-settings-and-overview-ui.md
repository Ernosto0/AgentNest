# Session 14: Agent settings and overview UI

**Task:** P7.5-14. **Status:** Planned. **Prerequisite:** Session 13.
Read the [common session rules](phase-7.5-sessions.md) and phase section 11.

## Goal

Replace the topic-dropdown experience for agent accounts with understandable goals, personality, delegation and visible control.

## Read first

Existing `frontend/src/features/{settings,home,workspaces,notifications}`; routing/navigation, API generation, component/i18n conventions; new configuration/status/task APIs.

## Build

1. Add agent overview and configuration screens with task status, waiting questions/approvals, verified recent actions and account capability status. Keep simulated provenance visible.
2. Add editable goals/personality, channel voice preferences and representative conversation preview. A preview never sends to Instagram and accurately labels simulated/real-model output and cost authorization where applicable.
3. Build action-level automatic/ask/off controls, moderation/publication scopes and a versioned delegation-change preview. Explain what the agent may do in ordinary business language. Avoid exposing internal tool names as primary labels.
4. Implement pause/resume and controller enablement with backend epoch/policy outcomes. Show in-flight activity honestly; pause cannot promise to undo an already sent action. Apply role-based controls and clear readiness/capability reasons.
5. Preserve the old settings path for legacy accounts, with deliberate migration to the agent experience. Refresh affected caches after settings, pause, reconnect and controller changes. Add owner-task composer/progress entry using Session 13 APIs.

## Verify and done when

Component-test owner/manager/staff views, failed/stale configuration saves, policy previews, capability loss, pending effects at pause and controller migration. Test TR/EN key parity, keyboard/accessibility and narrow layout. Regenerate client types from current OpenAPI and run frontend checks/build. Add focused browser coverage using the actual backend for configuration and state transitions, not only mocked UI routes.

## Handoff

Write `s14-report.md` with routes, screenshots/visual checks, role behavior and demo instructions. AC75-03/17/20 has UI evidence; questions/comment/memory task detail follows in Session 15.
