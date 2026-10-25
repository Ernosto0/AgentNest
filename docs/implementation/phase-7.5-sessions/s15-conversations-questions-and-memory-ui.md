# Session 15: Conversations, questions and memory UI

**Task:** P7.5-15. **Status:** Planned. **Prerequisite:** Session 14.
Read the [common session rules](phase-7.5-sessions.md) and phase sections 9, 11, 13.

## Goal

Let the owner inspect and guide real agent work: conversations, comments, memory, information requests and action approvals.

## Read first

Existing inbox/draft/approval/content/reporting/notification components and metrics contracts; new thread/comment/question/memory APIs; activity projection conventions.

## Build

1. Extend inbox detail for agent/human ownership, goal/state, pending work and verified outcomes. Add comment thread view with media context, public/private surface indicators, moderation state and native/agent activity.
2. Build business-question list/detail and answer UI. Separate an information answer from approval of an exact action. Show stale/expired/answered-by-someone-else states and optional reusable knowledge candidate creation.
3. Add customer memory/source inspection, authorized correction/forget and visible retention behavior. Do not leak hidden private data in comment views, notifications or previews.
4. Expose takeover/release and manual comment actions through the shared backend operation path. Display queued/failed/unknown results honestly; refresh related views after changes.
5. Extend activity and reporting projections with persisted agent actions, owner interruptions and outcomes. Preserve definitions and historical report snapshots; introduce versioned new metrics instead of rewriting old numbers. Add resumable owner-task progress and clarification UI.

## Verify and done when

Test answer-versus-approval controls and permissions, duplicate submit, expired question, late answer, unknown moderation outcome, memory correction and takeover. Browser-test comment-to-DM -> owner question -> answer -> customer continuation using the real application with mock Instagram. Verify TR/EN, screen-reader labels, no horizontal overflow, cache clearing after erasure and stable historical report drill-down.

## Handoff

Write `s15-report.md` with a complete offline owner walkthrough and API/UI evidence. Map AC75-06/07/10/18/20/24; automated browser checks are not the final manual phone acceptance.
