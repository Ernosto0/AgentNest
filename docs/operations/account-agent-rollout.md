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
| Comments | Real-account private replies require the opt-in rollout below. Public replies and moderation remain off. Public context cannot read private memory. |
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

## Real-account comment-to-DM rollout (Feature Phase 3)

**Live evidence: pending.** Offline fixtures establish implementation behaviour only. Complete the live evidence gate before a customer rollout. No subscription is automatic.

1. Apply migration **0059** (parent 0058). Enable the `meta` provider in deployment configuration. Keep every account's `comment_automation_enabled=false` initially. Verify consent returned `instagram_business_manage_comments` (`comments_permission=true`); reconnect from Connections when missing. `META_REQUEST_COMMENT_SCOPE=true` requests it; false requests the original four scopes only, in the same order.
2. Confirm app Live mode, appropriate Advanced Access/App Review and webhook configuration. Standard Access role-account delivery remains pending. Manually subscribe using the account token, outside application code: `POST https://graph.instagram.com/<version>/<ig-user-id>/subscribed_apps?subscribed_fields=comments`; read back with `GET https://graph.instagram.com/<version>/<ig-user-id>/subscribed_apps`. Keep existing message subscriptions. Whether this app accepts `comments` as a value is **pending**; do not assume a successful handshake proves delivery. Never put tokens in command history, reports or screenshots.
3. An owner turns on **Comment-to-DM (private replies)** in Settings → Connections. The API is `PUT /api/v1/workspaces/{workspace_id}/accounts/{account_id}/comment-automation`, `{ "enabled": true }`. Scope plus flag derive only `comment_read` and `comment_private_reply`; `comment_reply` and `comment_moderate` remain false. Non-owners see read-only state. Reconnect preserves opt-in but revoked scope disables capabilities. Fresh connection or disconnected-row reuse resets opt-in.
4. Activate the account agent using the cutover procedure above. Keep *Reply privately to comments* at **Ask** (the default). Prepare a usable verified price fact. The existing tool validates `{{fact:key}}` placeholders and exact evidence; an unverified or bare price must not dispatch. Automatic mode requires a real owner's delegation and its exact policy grant.
5. From a disposable customer, add a new top-level comment on recent owned non-Live media. In Inbox → Comments verify one source event/thread, inspect the private reply, approve the exact draft and observe the ledger outcome. Check the customer's Instagram Inbox/Requests independently. Do not mistake approval for delivery. Confirm no normal DM follow-up can send until the customer actually responds.
6. Watch inbound ignore reasons, approval expiry, delegation/capability changes, jobs, operations and account health. Verify flag-off during pending work causes `CAPABILITY_MISSING`. Flag-off accounts retain no inbound comment text. Native comment deletion/moderation webhook semantics and recipient/commenter/DM identity equivalence remain pending.

| Rule | Reason code / behaviour |
|---|---|
| Age strictly below 7 days minus 10 minutes; future/missing timestamp refused | `PRIVATE_REPLY_WINDOW_EXPIRED`; provider readback uses `PRIVATE_REPLY_EXPIRED` |
| One opportunity per comment | `PRIVATE_REPLY_COMMENT_ALREADY_USED` |
| One private reply per commenter per account, ever (ASSUMED-strict) | `PRIVATE_REPLY_COMMENTER_LIMIT`; live count semantics pending |
| Missing author | `PRIVATE_REPLY_COMMENTER_UNKNOWN` |
| Any reply with a parent | `PRIVATE_REPLY_NOT_TOP_LEVEL`; eligibility undocumented |
| Owner's own, hidden/deleted comment, invisible/unowned media | Existing ineligible/stale checks |
| No remote proof after ambiguous send | `outcome_unknown`, reservation held, never auto-resend |

`COMMENT_PRIVATE_REPLY_LIMIT_SCOPE=commenter` is the default. Only after recorded platform evidence and rollout review may operators select `comment` to relax the commenter-wide rule; the per-comment uniqueness remains. Active reserved (not expired), succeeded and outcome-unknown opportunities count; failed/cancelled do not. Admission serializes on the account; eligibility is checked again before dispatch. Provider reads happen after the write-ahead ledger transaction commits.

**Rollback:** turn the Connections flag off (`{ "enabled": false }`), then pause the agent if a broader stop is needed. Pending private replies recheck capability before dispatch. A dispatched operation cannot be undone. Keep unresolved evidence; never resend or release an `outcome_unknown` reply based on missing readback. Public reply/hide/unhide/delete remain disabled.

**Probe and evidence:** `pytest -m meta_comments_live tests/contract/test_meta_comments_live.py` is skipped without explicit inputs and always skipped in CI. Run read-only subscription and comment ownership probes first. Mutations require exact target, `META_LIVE_COMMENT_EFFECT=private_reply` and `META_LIVE_COMMENT_SEND=YES_SEND_REAL_MESSAGE`; second-message probes additionally require `META_LIVE_COMMENT_LIMIT_PROBES=YES_SEND_REAL_MESSAGE`. Run the first send once, then the repeat probe separately on that already-used comment. The second-comment target must be independently confirmed as the same customer. A direct probe bypasses the product ledger and is not application acceptance.

Record sanitized HTTP status, error code/subcode, subscription counts, timestamp/ownership booleans and hashed recipient ID via `META_LIVE_PROBE_RECORD`. Compare hashed recipient with the later DM sender offline without retaining raw identity or names. Retain application ledger IDs, capability/delegation versions and final outcomes separately. Subscription acceptance, authentic webhook shape, first send, repeat denial, same-commenter limit, identity comparison and device walkthrough are all **pending**.
