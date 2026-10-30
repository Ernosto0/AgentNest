# Session 18: Rollout and close-out

**Task:** P7.5-18. **Status:** Offline rehearsal and docs complete; founder/phone acceptance pending. **Prerequisite:** Session 17; real rollout also requires G7.5-C/D and the relevant existing gates. See [report](s18-report.md).
Read the [common session rules](phase-7.5-sessions.md) and phase sections 3, 13-14.

## Goal

Validate upgrade/cutover/rollback, complete authorized founder-account acceptance and leave an accurate operating guide and phase summary.

## Offline work

1. Rehearse additive upgrade with populated legacy accounts, deliberately enable one agent account and verify other accounts remain legacy. Exercise the atomic controller epoch switch with queued jobs, waiting questions, approved actions and an uncertain send.
2. Drill pause and rollback to legacy. Preserve reconciliations, memory and immutable action history; no automatic downgrade or attempt to undo remote deletion. Verify abandoned agent jobs cannot dispatch after rollback.
3. Finish operator documentation for configuration, memory correction/retention, questions, approval, moderation, unknown outcomes, budgets, disconnect and recovery. Update Phase 8/9 handoff contracts and checklists for new surfaces/data.
4. Run final required checks after any fixes; link Session 17 evidence when no changes require a repeat. Write a provisional phase summary that clearly states externally pending items.

## Authorized founder trial

After explicit authorization for the target account and named actions, verify actual grants/webhooks and run the application workflow for DM conversation, public reply, eligible private reply and customer response, owner question/resume, memory continuity, hide/unhide and deletion of an agreed test comment. Verify delegated content publishing with a selected test asset if enabled. Capture sanitized provider/outcome evidence; never collect credentials in chat or logs.

Exercise pause, native owner activity, reconnect/capability loss and uncertain-action handling as the supported test environment permits. Complete an owner Windows and real-phone TR/EN walkthrough. Record unavailable behavior as pending rather than fabricating a provider outcome. Live access limitations cannot be removed by a model setting.

## Done when and report

Create `s18-report.md` and `docs/implementation/phase-summaries/phase-7.5-summary.md` with every AC75 row, migrations, versions, release/rollback instructions and exact automated/model/manual/live evidence. Full phase completion requires G7.5-A through E. Otherwise report **offline complete, live/model/manual pending** with enabled/disabled capability inventory and the next concrete prerequisite.

Update the session index/roadmap status only to what evidence supports. Do not start Phase 8 implementation, deploy, submit App Review, commit or push as an implied part of close-out.
