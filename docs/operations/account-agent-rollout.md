# Account agent operation and rollback

**Status:** Offline procedure. New real comment capabilities and the Phase 7.5 real-model,
founder-account and phone gates remain pending. Do not enable a real account based only on
this procedure.

## Before an account cutover

1. Apply additive migrations through the current Alembic head on a backed-up, disposable
   rehearsal database first. Existing accounts must show `controller_mode=legacy` and
   `state=inactive`. Never downgrade a database containing agent evidence: migration 0019
   refuses it, and later memory/comment/question records also require preservation.
2. Check the account's provider capabilities and health, delegation/action modes, verified
   business facts, persona, budget limits, owner role, worker health and recent dead jobs.
   Set a real-model budget and measure quality/latency before any real account enablement.
3. Select one named account and a small set of disposable conversations and comments.
   Record the account ID, owner, current `config_version`, `controller_epoch`, policy
   version, capability inventory and intended rollback owner. Confirm no unresolved
   `outcome_unknown` operation is being mistaken for a failed send.
4. The owner activates through the account's Agent settings. The API is
   `POST /api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/activate` with
   `expected_config_version`, a fresh `client_request_id` and `mode=agent`. The
   service increments the controller epoch, adopts threads, fences old steps and queues
   cleanup. Repeating the same request ID is idempotent; use a new one for a new change.
5. Verify the selected account is active and every other account retains its prior mode.
   Inspect activity, pending questions/approvals, queued jobs, action/operation counts and
   actual provider outcomes. A UI request success is not a sent/published outcome.

## Pause, rollback and recovery

1. For an immediate stop, the owner uses Agent settings **Pause**. The API
   `POST /api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/pause` requires the current
   `expected_config_version`. Pause increments the epoch, invalidates claimed steps and
   queues cleanup. Do not assume an already dispatched provider operation was undone.
2. The owner switches controller to `mode=legacy` through the same activate endpoint with
   a fresh request ID and current config version. This is an account-scoped, atomic
   controller change. It increments `controller_epoch` and `cutover_generation`, adopts
   existing threads and schedules cleanup of stale drafts/approvals. New eligible inbound
   work follows legacy handling; old agent jobs fail their epoch/authority checks.
3. Let the cleanup and recovery workers run. Confirm pending agent approvals and unexecuted
   drafts are cancelled, and no stale agent send/publish/moderation dispatch occurs.
   Keep memory, owner questions, action history, audit and operation evidence. Do not
   remove agent tables or attempt to undo a remote comment deletion.
4. Review every `outcome_unknown` operation with its ledger ID. Use the existing
   reconciliation path and actual provider evidence before any new action. An ambiguous DM
   must never be automatically reworded or resent. If reconciliation cannot establish an
   outcome, leave it visibly unresolved and assign a human owner.
5. Check native/manual owner activity and any waiting customer/owner thread. Resume an
   agent controller only after correcting the cause; resume is a new epoch, not a replay of
   old action grants. Recheck delegation, capabilities, facts, budget and current owner
   membership. Never reuse a stale approval or previously issued policy grant.

## Routine owner and operator checks

| Surface | Check and action |
|---|---|
| Questions | Answer from a verified owner/manager account. An information answer resumes the scoped conversation; it grants no action permission. Staff proposals and free text do not approve actions. |
| Approvals | Inspect the exact subject, payload, expiry and simulated badge before deciding. A changed action needs a new decision. |
| Comments | Keep real read/reply/moderation/private-reply capabilities off until R75 research, authentic fixtures and application-ledger founder tests pass. Public context cannot read private memory. |
| Memory | Use the scoped correction/forget flow for inaccurate customer memory. Verify derived summaries and source links are updated. Existing account disconnect erasure must fence in-flight model results; Phase 8 owns the general data-rights API. |
| Budgets | Inspect durable step/cost limits, retries, dead jobs and the visible failure state. Changing a model setting does not enlarge delegation or provider capability. |
| Disconnect | Stop new work, preserve unresolved operation evidence for reconciliation, run account-scoped erasure and verify no old wake can dispatch. Do not reconnect to a different account identity. |

## Evidence to retain for a real trial

Record sanitized account/capability identifiers, migration head, model and prompt versions,
policy version, exact test actions, operation IDs and final provider outcomes. Test DM,
public reply, eligible private reply and customer continuation, owner answer/resume,
memory continuity, hide/unhide/delete, content publish if enabled, pause, native activity,
reconnect/capability loss and uncertain outcomes through the application. Keep secrets and
personal message bodies out of logs and reports. A direct adapter probe does not count as
an application operation. Complete the Windows and real-phone Turkish/English walkthrough
separately from browser automation.
