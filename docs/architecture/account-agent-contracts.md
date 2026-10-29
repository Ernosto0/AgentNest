# Account-agent contracts (Phase 7.5)

**Status:** Accepted target under [ADR-024](decisions/ADR-024-account-agent-and-delegated-autonomy.md); runtime implementation is staged in [Sessions 02–18](../implementation/phase-7.5-sessions/phase-7.5-sessions.md). The current Phase 1–7 paths remain active until an account is explicitly cut over. This document fixes names and ownership for those sessions; it is not evidence that the code exists.

## 1. Ownership and identity

- `account_agents` has exactly one row per `(workspace_id, social_account_id)`. `controller_mode` is `legacy` or `agent`, initially `legacy`; `state` is `inactive`, `active`, or `paused`, initially `inactive`. `controller_epoch bigint` starts at 0 and increases on activation, mode switch, pause/resume, disconnect and any account-wide controller change. The row is the serialization point for cutover. No migration enables an agent or grants an action.
- `agent_threads` is one logical unit of work per `(workspace_id, social_account_id, surface, source_ref)`. `surface` is `dm`, `comment`, or `owner_task`; `source_ref` is the existing conversation UUID for DMs, the account-scoped comment thread UUID for comments, or an owner-task UUID. A UUID string in this field is a routing key, never authority to read the referenced object. `dm_conversation_id uuid null` carries the composite FK to `conversations`; later owning sessions add typed comment/owner-task links. Resolve all referenced objects through workspace/account-scoped repositories. Each thread has `controller_epoch` (copied from the account at claim), `thread_version`, `event_cursor bigint`, `deletion_generation bigint`, `handling_mode` (`agent` or `human`), and `state` as defined below. Customer identity is nullable until verified. A display name or handle never links a public commenter to a private DM identity.
- `agent_events` is the durable, ordered inbox for an agent thread. Unique `(workspace_id, social_account_id, source_kind, source_key)` deduplicates deliveries; `(thread_id, cursor)` is unique. Allocate `cursor = thread.event_cursor + 1` while holding the thread row, then update the thread and enqueue the wake job in the **same transaction**. An event stores source IDs, source version, kind, safe routing metadata and timestamp; no customer body, credential, owner answer text or model context goes into a job or generic event payload. The domain that owns a message/comment/approval/operation writes its own record, then emits an event through the agent event service in that same transaction. The agent never recursively imports a domain from the domain's own code path.
- Inbound DM event identity is the already deduplicated `inbound_events.id`, native owner activity uses the persisted message ID, approvals use decision ID/version, operations use operation ID/status version, owner answers use answer ID/version, and scheduled tasks use a durable task ID/version. Replayed source identities return the existing event and do not enqueue another logical activation.

## 2. Core records for Session 02

All new tenant tables have `workspace_id NOT NULL`, `(workspace_id,id)` uniqueness and composite workspace FKs to tenant parents. Account relationships additionally validate the same `social_account_id` in the repository or through composite `(workspace_id,social_account_id,id)` keys where a child has an account; a foreign account/media/thread ID resolves to 404 at the API. Use UUID primary keys, UTC `Clock` timestamps, text `CHECK` enums, explicit unique/index names and additive migrations. Inspect the current Alembic head before assigning a revision; at this decision the head is `20261024_0018_general_business_categories`.

| Table / change | Required contract and uniqueness |
|---|---|
| `account_agents` | `(workspace_id, social_account_id)` unique; `controller_mode`, `state`, `controller_epoch`, `config_version`, `persona_version`, `goals`, `created_at`, `updated_at`. Empty goals/persona are non-authorizing. |
| `agent_delegations` | Immutable `(workspace_id, social_account_id, version)` unique; `grantor_user_id`, `policy` (schema-validated action modes/limits), `effective_at`, `revoked_at`, `policy_hash`, `created_at`. Only one current effective version; a new version revokes its predecessor atomically. No broad default grant. |
| `agent_threads` | Account/surface/source uniqueness as above; state, version/cursor/epoch/deletion generation, handling mode, nullable `dm_conversation_id`, customer identity ref, current goal and last activity. Index `(workspace_id,social_account_id,state,last_activity_at)`; DM conversation uses a composite FK in Session 02. |
| `agent_events` | Unique source identity and `(thread_id,cursor)`; `kind`, `source_id`, `source_version`, `created_at`. Index `(workspace_id,thread_id,cursor)`. A generic JSON body is forbidden. |
| `agent_sessions` | Durable goal/run: thread, initiating event cursor, `goal_key`, `status`, `version`, cumulative model/tool/token/cost counters and deadline, current wake condition and `created_at`/`completed_at`. Unique `(workspace_id,thread_id,goal_key)` and partial unique active session per thread (`queued`, `running`, all waiting states, `sleeping`). A replay resumes it. |
| `agent_steps` | Session, `sequence`, `status`, `claim_token`, lease expiry, captured event cursor/controller epoch/policy version/deletion generation, model/prompt/tool versions, input/output references, reserved and actual usage. Unique `(workspace_id,session_id,sequence)` and unique claim token. Store only bounded redacted context evidence; personal bodies stay in their domain tables. |
| `agent_actions` | Session, thread, `intent_key`, `action_type`, immutable payload/version/hash, target reference, initiation event/cursor, `status`, delegation version and policy grant evidence or approval ID, operation ID, execute deadline and outcome. Unique `(workspace_id,thread_id,intent_key)`. A new model call/tool-call ID or reworded text **cannot** create a new action for the same unresolved intent. |
| `agent_runs` | Task `account_agent_step` and nullable `(workspace_id,agent_step_id)` composite FK link one existing model-call evidence row to the durable step; legacy rows remain null. Existing run rows keep their semantics and retention. |
| `reply_drafts`, `content_items` | Nullable `(workspace_id,agent_action_id)` composite FK and explicit `origin = legacy | agent` where needed to distinguish controller ownership. Existing rows backfill to `legacy`; the send/publish executor remains the existing ledger path. An action link is not itself authorization. |

An `intent_key` is server-built from the account, thread, durable goal, initiating customer/owner event or task, action kind, target and a stable semantic slot derived from the event's response obligation (for example, reply to inbound cursor range 12–14). The obligation/slot is persisted before the model call; the action kind and target complete the key after a proposal. It excludes generated wording, model tool-call IDs and retry count. An action with an unresolved or uncertain operation reserves that slot across restarts and replans. Only a new independently evidenced request, or a definitive terminal outcome plus explicit new goal, may allocate a new slot. External actions are written and authorized before operation enqueue; operation idempotency uses the stable action ID. A changed candidate payload before dispatch increments the action version and invalidates an existing approval; after dispatch it is immutable.

Migration `0019` stores `social_account_id` on `agent_actions` and requires it to match both the agent thread and linked operation through composite keys. Agent-origin content rows have an account-bound action FK. A reply draft and polymorphic approval have no direct account column; Sessions 07 and 03 respectively must verify their source conversation/subject resolves to the action's account before linking them.

## 3. States, jobs and transaction boundaries

`agent_sessions.status` and `agent_threads.state`: `queued`, `running`, `waiting_customer`, `waiting_owner`, `waiting_approval`, `waiting_operation`, `sleeping`, `completed`, `cancelled`, `failed`. `agent_steps.status`: `claimed`, `model_pending`, `model_done`, `dispatched`, `consumed`, `stale`, `abandoned`, `failed`. `agent_actions.status`: `proposed`, `waiting_approval`, `authorized`, `queued`, `in_progress`, `succeeded`, `failed`, `outcome_unknown`, `cancelled`. Changes use one transition module, compare-and-swap on version and expected state, and a same-transaction audit entry. A wait/sleep has a persisted condition or wake time; it holds no worker or DB lease. Completed/cancelled/failed sessions are terminal. A new customer event may create a new goal after the old one ends.

| Entity / from | Event and required guard | To / durable result |
|---|---|---|
| Session `queued` or runnable wait | `claim`: agent active, thread agent-owned, current epoch/policy and budget reserved | `running`; one claimed step and token |
| Session `running` | `wait_customer`, `wait_owner`, `wait_approval`, `wait_operation`, `sleep`: committed matching question/action/operation or scheduled task | Corresponding `waiting_*`/`sleeping`; condition/ref and optional `wake_at` saved; claim released |
| Session any active state | matching source event or due task with newer cursor, active controller and current policy | `queued`; condition cleared; one deduped wake |
| Session `running` | `complete`, `cancel` or exhausted/irrecoverable error | `completed`, `cancelled` or `failed`; terminal evidence and owner-visible reason |
| Step `claimed` | model input committed | `model_pending`; call occurs outside transaction |
| Step `model_pending` | result and captured cursor/epoch/policy/deletion generation still current | `model_done`; redacted result/usage persisted |
| Step `model_pending` or `model_done` | captured state changed or lease abandoned | `stale` or `abandoned`; result cannot dispatch; re-wake current thread |
| Step `model_done` | broker validated and created tool result or immutable action intent | `dispatched`; no effect until authorized/ledgered |
| Step `dispatched` | matching result event consumed once | `consumed`; checkpoint and next step/wait |
| Action `proposed` | `ask`/`automatic` deterministic decision | `waiting_approval` with exact pending approval / `authorized` with exact policy grant; `off` produces `cancelled` |
| Action `waiting_approval` | bound approval decided, current version/hash/policy and deadline | `authorized` or `cancelled`; information text never counts as decision |
| Action `authorized` or `queued` | executor rechecks current account, target, capability, policy and deadline; operation persisted | `in_progress` (via `queued` as needed); committed operation precedes provider call |
| Action `in_progress` | provider outcome or uncertainty, operation ID unchanged | `succeeded`, `failed` or `outcome_unknown`; the last waits for reconciliation |
| Action `outcome_unknown` | reconciler evidence for the same operation | `succeeded` or `failed`; absent proof remains unknown and blocks a replacement |

| Job | Payload (IDs only) | Trigger and outcome |
|---|---|---|
| `agent_wake` | `{thread_id}` | Dedup `agent_wake:{thread_id}`. Claims one thread/session under row lock, advances from queued/wait, reserves budget and makes a step. Duplicate/running wakeups coalesce by cursor; finalizer checks for a newer cursor and re-enqueues when needed. |
| `agent_continue` | `{session_id,step_id}` | Runs a validated broker result or resumes after a tool/operation result. Dispatches only an action admitted by the stable intent key. |
| `agent_wake_due` | `{session_id}` | Scheduled wake at `wake_at`; rechecks current cursor, controller, policy and provider conditions. Waiting on a person is not a retryable worker failure. |
| `agent_recover` | `{}` | Periodic scan of expired step claims, abandoned model calls and active sessions with no runnable job. Marks stale/abandoned evidence and re-enqueues safe work; unresolved effects stay with their reconciler. |

Stage 1 transaction: lock thread/agent, capture cursor/epoch/policy/deletion generation, reserve account/workspace quota and cumulative goal/activation budget, create step with unique claim token, then **commit**. Stage 2: call the model or read-only network tool outside a transaction. Stage 3: re-lock and compare captured values, takeover and account state; stale output becomes `stale`, with a new wake if needed. Stage 4: broker validates typed arguments and scoped references; internal writes commit with their event, while external intents/authorization/operation ledger are committed before any provider call. Stage 5: a typed result event is consumed once, checkpointed and either requeued or moved to a wait/terminal state. A crash at any boundary can repeat computation, but not admit a second action intent. The coordinator imports domain services; domains emit events via a narrow callback/event writer registered at startup. Only `operations/` calls side-effecting providers.

Default engineering limits: 8 model steps, 12 tool calls and 120 seconds wall time per activation; 24 model steps per unresolved goal. Reserve quotas atomically before calls, count repair calls and actual usage, and retain cumulative counters through retries/restarts. Account provider quota and workspace spend limits are additional constraints. A budget exhaustion is a visible handoff. Unknown/restricted/invalid tools return bounded typed failures; repair at most once for schema errors, never for permission escalation. A repeated identical call has a fixed cap and produces a visible handoff. A pending human/operation wait does not consume ordinary job attempts.

## 4. Authority and visibility

Delegation action keys are exactly `dm.send`, `comment.reply`, `comment.private_reply`, `comment.hide`, `comment.unhide`, `comment.delete`, `content.prepare`, `content.schedule`, `content.publish`, `content.cancel`. Each has `automatic`, `ask`, or `off` plus typed scope/limits. Existing topic `automation_policies` remain the legacy controller's settings; they do not grant the agent authority. The account grant stores the owner's identity and immutable version. Manager may edit persona/goals under `agent.settings.edit`, but only owner with `agent.delegation.manage` can broaden action authority. Staff cannot grant authority. For a human-initiated agent task, effective authority is the intersection of delegation and the requester's current permission; for a customer event it is the account grant, never a customer role. `off` is blocked; `ask` creates an exact-payload approval; `automatic` creates a policy grant bound to the exact action/version/hash, delegation version, target, source event and deadline. Policy grants are **not** fake human approvals.

Approval action names: existing `reply.send` and `content.publish` are reused where their existing subject/executor fits; new comment actions use `comments.approve` with `agent_action` subject and action-specific summary. Internal content action requests use exact `content.prepare`, `content.schedule`, or `content.cancel` approval names with `agent_action` subject so an approval card never labels a different effect as publication. New operation types: `comment_reply`, `comment_private_reply`, `comment_hide`, `comment_unhide`, `comment_delete`; `dm.send` reuses `send_reply`, and publishing reuses `publish_content`. Session 03 extends closed DB constraints, subject callbacks and executor eligibility, and Session 11 adds comment executors. A human approval remains single-use and hash/version-bound to one operation. The executor rechecks delegation/policy version, grantor authority, account pause/disconnect, ownership epoch, target state, capability, quota and deadline immediately before dispatch. Revocation fences unsubmitted work; an in-flight unknown outcome stays under reconciliation and is never described as undone.

Broker capabilities separate `public_read`, `private_read`, `internal_write`, `external_effect`. A public-comment context can read that account's eligible media/comment thread and public business facts but cannot load DM turns, customer memory or private owner questions. A private DM context can read its evidenced customer identity/memory. A shared username, prompt instruction, retrieved text or model argument never upgrades visibility. Agent-facing references are server-issued aliases with a scope, version and expiry; the server resolves them again. A customer message or external document may cause a **proposal**, never change delegation, approve an action or invoke a command. Critical business claims still require verified usable fact versions or a permitted one-off owner answer; customer-attributed values are labelled and cannot become business promises.

## 5. API and privacy boundary

All paths below have the existing `/api/v1/workspaces/{workspace_id}` prefix, CSRF rules, typed problem errors and cursor pagination (default 20, max 100). Unknown/foreign IDs return 404. Config and grants start inactive; a requested agent cutover is an explicit owner action that increments `controller_epoch`, cancels unsubmitted legacy/agent work of the displaced controller and keeps in-flight ledger reconciliation active. Account pause stops all agent threads; thread takeover only fences that thread. Release requires a fresh epoch/check and never resurrects an old action. Status and action views show `is_simulated` and distinguish proposed, authorized, queued, verified, failed and unknown.

| Endpoint group | Access and request contract |
|---|---|
| `GET /accounts/{account_id}/agent`; `PATCH /accounts/{account_id}/agent/personality` | Any member can read safe settings/status; owner/manager edit persona with `expected_version`, TR/EN voice fields and audit. |
| `POST /accounts/{account_id}/agent/delegation/preview`; `POST /accounts/{account_id}/agent/delegation/apply` | Owner only; structured action-policy diff, expected config/delegation version, client request ID. Apply writes immutable version; no prose directly grants authority. |
| `POST /accounts/{account_id}/agent/activate`, `/pause`, `/resume`; `POST /agent/threads/{id}/takeover`, `/release` | Owner for account activation/pause; existing `conversation.takeover` for a thread. Expected version/epoch and idempotency. |
| `GET /accounts/{account_id}/agent/sessions`, `/actions`; `GET /agent/threads/{id}` | Paginated, scoped operational evidence. Never return raw hidden prompt/context or credentials. |
| `POST /accounts/{account_id}/agent/tasks` | `commands.use` plus action-specific requester permission; durable task ID and client request ID, no direct authority increase. |
| `GET /owner-questions`, `GET /owner-questions/{id}`, `POST /owner-questions/{id}/answer`, `/cancel` | Question visibility by role/thread; answer has `expected_version` and client request ID. Answer is information, never approval. |
| `GET /customers/{id}/memory`, `/sources`; `POST /customers/{id}/memory/{memory_id}/correct`, `/forget` | Account/customer scoped. Members inspect; owner/manager correct or forget, staff cannot authoritatively correct. Correction requires `expected_version`; UUID cursor pagination is bounded at 50. Generation fencing prevents erased data from returning. |
| `GET /accounts/{account_id}/comments`, `/comments/{id}`, `/comments/{id}/thread` | Paginated account/public context, with independent action endpoints through the operation ledger in Session 11. |

**Session 03 implementation boundary.** `POST /delegation/preview` and `/apply` accept a complete, closed set of the ten action rules (`mode`, optional `max_per_day`, and allowed `customer`/`owner_task` sources), expected account configuration/delegation versions and a UUID client request ID. Apply stores the request ID uniquely per account, revokes the old immutable policy version and increments the account configuration/controller epoch. Replaying the same request ID and policy returns the original version; a reused ID with different policy conflicts. It does not activate the agent. `GET /delegation` returns the current scoped version. Owner-only `/pause` and `/resume` use expected configuration version. A policy change or pause makes unsubmitted agent approvals and queued effects stale at decision/executor time; Session 05 adds a durable cleanup wake to close their visible pending states without racing the approval service's lock order. Activation/cutover remains Session 07 work once the coordinator and DM path exist.

The Session 03 decision service reads current membership for human-task requesters and the grantor, account state/capability, action-scoped facts and limits. `automatic` stores a policy grant on `agent_actions` with exact hash, target, action/version, delegation/version/grantor and controller epoch; `ask` creates a single-use `agent_action` approval whose hash equals the exact effect payload hash. The two are distinguishable. A projected automatic DM or publish subject obtains a policy-channel approval only through `record_effect_grant`, which verifies action type, subject type, required permission and exact payload hash. The existing send/publish executors additionally call `fence_action` for agent-origin subjects before creating an operation. They retain their own provider capability, window/media/quota and exact subject checks. Session 07 owns DM projection and Session 13 owns content projection; neither may bypass these checks. Existing legacy automation/approvals retain their original behavior.

Session 08 owns **agent memory and derived summary** inspection, correction, forgetting and account-disconnect/retention erasure. It must expose an internal, customer-scoped export/erase service for its own records that Phase 8 P8-05 can call; no existing general customer export/deletion route is claimed. The current code has only `data.export`/`data.delete` permission constants. Phase 8 owns the general data-subject export/deletion API, cross-domain orchestration and Meta callbacks. Session 08 tests its service and ensures that memory never survives an existing disconnect-erasure request or source deletion. A Session 08 report must state any Phase 8 dependency honestly rather than claiming full data-rights acceptance from a memory table alone. Personal source bodies, memory, summaries and prompt snapshots follow explicit retention/erasure rules; only minimal content-free action/operation evidence can survive an unresolved side effect until reconciliation ends.

## Session 06 runtime boundary: context, voice and grounding

Migration `0022` follows `0021`: steps capture `captured_persona_version`, and sessions
persist `validation_failures`. A persona edit fences an in-flight model result without
changing thread ownership. `GET /accounts/{account_id}/agent/personality` is member-readable;
`PATCH` requires `agent.settings.edit` (owner/manager), `expected_version`, and a closed
personality object. The response is `{version, personality}`. Tone, formality, length,
emoji and DM/comment styles are enums; TR/EN examples are at most two strings per language,
160 characters each. Updates increment persona/configuration versions and audit only
version metadata. Examples are delimited untrusted data, never delegation or fact authority.

The actual coordinator calls `app.agent.context.assemble`: at most eight non-deleted DM
turns, four relevant visible facts and two active approved answers, current persona and
server-selected TR/EN language. Public contexts do not query DM turns. All owner/customer
and retrieved text is neutralized inside an untrusted section; a separate server-generated
source table supplies fact IDs/versions/placeholders. Summaries remain absent until Session 08.
Knowledge relevance is a bounded lexical key/label/title search, not a semantic search guarantee.

`knowledge.read` v1 retains `{limit:1..20,cursor:fact_key|null}` but now uses scoped SQL
usability/visibility predicates and `LIMIT limit+1` before materialization. The cursor is a
keyset bound. Internal escalation/brand/schedule categories and the price-disclosure control
fact are withheld; missing/unusable disclosure defaults to no money/pricing values. Pending
contests, validity dates in workspace time, archives and unverified facts are excluded in SQL.
Each item includes ID, version, placeholder, validity and `public_business` visibility.
`knowledge.answers` v1 uses `{limit:1..10,cursor:uuid|null,language:tr|en}`. Only active,
current usable/visible dependency versions pass its SQL predicate; each bounded page also
re-renders and claim-validates templates with at most 20 dependencies. Malformed legacy
rows can underfill a page; callers follow its scan cursor. No raw customer example questions
are returned. The result carries answer and fact source IDs/versions. Neither path loads the
legacy all-facts/all-answers collection.

`reply.validate` v1 and `validate_reply` are the shared pre-send contract for Session 07:
`{template,language,fact_sources:[{id,version}],customer_clarification:null|{message_id,start,end,kind}}`.
Exact currently visible fact versions must match every placeholder. Literal critical values
still fail the existing renderer/claim validator. A customer date/time clarification requires
an empty business template and no fact sources, a current same-thread inbound source span,
and a closed date/time value. Code constructs the entire attributed question; arbitrary model
prose cannot surround an exempt numeric span. Public surfaces cannot use this private source.
The validator returns `{valid,text,errors,facts,customer_source}` and never sends or grants
authority. The coordinator permits one invalid validation result to be repaired; a second
persists `AGENT_GROUNDING_REJECTED`. Session 07 must persist the exact proposal in domain
storage and re-run this path before dispatch, preserving fact references and current source
deletion checks. One-off owner-answer evidence stays closed until Session 09 provides its
persisted scoped authority/visibility service. Customer values never update business facts.

## 6. Five transition examples

| Trigger | State and evidence | Authority/deadline | Recovery |
|---|---|---|---|
| Customer DM | Signed/deduped inbound message → `agent_event` → thread cursor → queued session/step → `dm.send` action → existing `ReplyDraft`/`send_reply` operation | Account `dm.send` grant or `reply.send` approval; verify messaging window, exact text and facts at dispatch | Replayed webhook returns existing event; uncertain send blocks a reworded second intent and reconciles |
| Owner information needed | Tool creates versioned owner question and `waiting_owner`; notification commits with question | Owner/manager answer is scoped information, no action grant; no worker lease while waiting | Answer writes event and one wake; stale answer/takeover/policy/closed window causes replan or safe stop |
| Autonomous comment deletion | Signed comment event → public thread/action `comment.delete` → policy grant → `comment_delete` operation | Explicit current `automatic` delegation and manage-comments capability; target ownership/version and deadline | Unknown delete outcome reconciles; pause cannot claim a remote delete was undone |
| Private reply from comment | Eligible comment action `comment.private_reply` → reservation/operation | Explicit grant or `comments.approve`; verified one-shot/window/recipient rule and source comment; no ordinary DM entitlement | Ambiguous outcome holds reservation and reconciles, never sends a second private reply blindly |
| Unknown operation | Executor records `outcome_unknown` and emits result event only when evidence changes | Existing exact action/operation identity remains reserved | Reconciler may mark succeeded/failed or terminal unconfirmed; coordinator waits and presents truthful status |

The mock may exercise provisional comment/private-reply shapes but must label them simulated. Real Meta action flags remain disabled until R75 research, authentic account evidence and capability-specific acceptance are complete.

Session 12 implements `comment.private_reply` as a separate broker/provider action and
`comment_private_reply` ledger effect. The provisional mock permits one private reply per
visible, verified-synthetic source comment for seven days after its provider timestamp;
this is an explicit simulator fixture, not a Meta limit. A unique account/comment
`private_reply_opportunities` row binds the exact action, source/media versions, proposal,
deadline and operation. An unknown outcome retains the reservation. Positive keyed mock
readback can settle it; absence or failed lookup cannot permit resend. The real adapter
rejects mutation and lookup until R75-04/05 are verified.

The mock provider may return a recipient identifier with the reply result. This is stored
as provider evidence, without merging the public author with a DM identity. Only a new
inbound DM from that exact account-scoped recipient binds the public source to its private
conversation. A prior conversation, duplicate webhook, unknown private reply, missing
recipient, or ambiguous multiple pending matches creates no link. The private DM context
may then include a bounded public source excerpt; public context has no path to private
turns or memory. The private reply itself does not update `last_inbound_at`, establish a
normal messaging window, or authorize `dm.send`. Normal continuation still uses the
independently received customer message and existing DM send checks.

## Session 07 implementation: controller-owned DMs

Migration `0023` adds account `cutover_generation`, thread `ownership_generation`, step `captured_ownership_generation` and action `ownership_generation`. A mode switch advances both controller epoch and cutover generation; policy/pause changes advance the agent epoch without invalidating ordinary legacy authority merely because an inactive agent policy was edited. Legacy plans/drafts capture cutover generation. Agent steps/actions additionally bind thread ownership, so takeover followed by release cannot make an old result or grant fresh again.

Owner-only `POST /accounts/{id}/agent/activate` accepts `expected_config_version`, UUID `client_request_id` and `mode=agent|legacy`, returning state/mode/configuration version/epoch. The latest identical request replays without a second change; stale older versions conflict. No migration activates accounts. Cutover fences queued work and defers approval/draft retirement until after commit. Existing agent threads are adopted/replanned after epoch changes with cumulative budgets intact; historical legacy inquiries are not automatically sent on initial activation.

`dm.send` accepts Session 06's exact `ReplyValidationArgs`, validates and persists the proposal only on its `ReplyDraft`, then admits a stable customer-event response obligation and reuses the existing send job/ledger. A latest control/result event cannot authorize a new send. The original ask approval is preserved as a real human `agent_action` decision and exact payload binding; automatic mode projects the policy grant to the existing draft executor. Ask approvals also reserve the delegation's UTC authorization-day quota under the account lock. The executor re-runs the same source/claim/language validation and checks cursor/ownership/policy before dispatch. Closed customer date/time questions have no global numeric exemption.

Response coverage resolves the captured customer event's scoped message ID rather than choosing a maximum random UUID when provider timestamps tie. Release compares bounded inbound/outbound message records using provider timestamp, persisted arrival time and ID; a new human-mode inbound produces one durable eligible event on release, while an already answered native obligation stops. An unresolved send continues reserving its slot despite that conversational stop. Context/thread history uses persisted arrival time before ID for tied provider timestamps.

After enqueue, the coordinator enters an action-ID-backed `waiting_operation` even if an operation ID does not yet exist. An approval decision can transition `waiting_approval -> waiting_operation`; it does not imply delivery. Recovery resolves action -> draft -> operation state, including a crash after ledger result commit but before a wake. Pending/unknown actions block a new reworded intent. Only a verified terminal result permits a completed goal; unknown results keep reconciliation ownership. Result observations are reconstructed from domain records rather than stored personal tool output in generic steps.

Executor admission locks approval first, then attempts the account lock without waiting, then obtains draft/domain locks. Contention yields a retry and releases its transaction. Deferred cleanup matches approval -> account -> draft ordering; thread change keys include ownership generation. Takeover/native replies fence claims immediately, while in-flight/unknown ledger effects are preserved. Disconnect erasure unlinks thread conversation FKs and advances deletion generation before deleting personal conversation records. Session 08 extends proposal/source redaction to memory and summaries; Session 09 owns explicit owner-answer continuation obligations.

## Session 05 implemented coordinator (migration 0021)

The coordinator uses short account -> thread -> session locks, a unique claim token and a
90-second step lease. It rechecks cursor, account/thread epoch, current delegation version,
deletion generation, handling mode and the 120-second activation deadline before dispatch.
A model call holds no transaction. Broker handlers may only read local data or create durable
domain intents in that transaction; network effects remain operations jobs.

Event wake keys are now `agent_wake:{thread_id}:{event_cursor}`. This intentionally replaces
the earlier thread-only job dedup contract: a new event committed while an older wake is
running must own a durable queued row even if the earlier handler has returned but its worker
has not finalized the job. Account/thread claims still coalesce computation. Recovery wake keys
include the minute and continuation keys include the durable step ID. Recovery scans only
runnable/due/resolved waits, rotates eligible rows by updated time, and excludes terminal and
indefinite human/customer waits from its bounded batch.

Migration 0021 adds activation cursor/start/step/tool counters, cumulative token reservation
and a content-free outcome code on sessions, plus a built-in-read checkpoint on steps.
Defaults remain 8 provider calls (repairs included), 12 tool dispatches, 120 seconds per
activation and 24 calls per unresolved goal. Each model step conservatively reserves 40,000
tokens for its original/repair calls; the unresolved goal cap is 960,000 reserved tokens.
Requests are capped at 16,000 UTF-8 bytes of context/schema, with 800 output tokens per call;
reservations never refund on restart. Actual available usage is reconciled from AgentRun,
including stale output and a restart after run evidence was committed. Unknown usage remains
unknown in AgentRun; reservations still charge it. No dollar-price assumption is introduced.

An activation resets on an eligible newly received event or an actually resolved wait/scheduled
wake, never on an ordinary job retry. Three identical dispatched tool requests are allowed;
the fourth hands off with `AGENT_LOOP_LIMIT`. Exhaustion/final errors persist failed session
state and outcome code; dead jobs remain in the existing job-health surface.

Built-in knowledge/thread reads save only successfully validated read routing arguments.
A non-null fact cursor must match an existing scoped fact key before checkpointing. Read
results and customer bodies are reloaded from current scoped domain storage on restart;
they never enter the generic step row. Later write/effect tools must reconstruct results from
their durable domain/action references and retain stable intent admission.

Customer waits require a later non-echo inbound message event. Approval and operation waits
require matching actions in the same session and resume only after persisted approval/ledger
resolution. `sleep_until` is the server-owned scheduling entry point. Owner-question wait
validation is intentionally closed until Session 09 supplies its durable question service.
Own-message/echo/outbound events are rejected by the conversational event writer.

Policy/pause transactions enqueue `agent_cleanup_approvals` after advancing the epoch and
never lock pending approvals. Decision callbacks and cleanup use approval -> account -> action
ordering; authorization/executor paths use account -> action. Cleanup cancels stale pending
approvals after the policy transaction, preserves ledger outcomes, and does not acquire an
approval lock while holding an account lock. Approval decisions enqueue a durable wake;
recovery also detects persisted approval/operation resolution without relying on callbacks.

## Session 08 implemented memory contract

Migration `0024` adds account-scoped `customer_identities`, `customer_memories`,
`customer_memory_versions`, `customer_memory_sources`, `customer_summary_versions` and
`customer_source_fences`. Identity evidence is the provider-scoped DM participant ID from
the authoritative conversation, stored as a digest; handles never establish continuity.
No public/comment path resolves or retrieves private identity/memory.

Private tools `memory.read`/`memory.write` v1 consume server-bound scope. Writes accept an
exact bounded self-reported source quote and closed useful business topic/kind, never a
verified fact or authority update. The coordinator binds identity generation in the
server claim. Memory changes invalidate relevant summary generations and projected DM
proposals; executor validation binds thread deletion generation as well as ownership/cursor.
Explicit privacy changes retain content-free source tombstones to prevent old source replay.
Summaries are bounded deterministic customer-context snapshots with identity revision,
thread source cursor and versions, never critical-fact authority.

Members inspect paginated memory and source metadata; owner/manager may authoritatively
correct/forget (`memory.correct`/`memory.forget`), staff cannot. Corrections require the
expected version and record user/version provenance. Owner-only internal
`memory.service.export_customer`/`erase_customer` implement the memory-domain rights hook
under `data.export`/`data.delete`; general DSAR orchestration remains Phase 8.

Memory defaults to 365-day retention. Correction/forget/source erasure clears derived
summary/history/proposal caches and fences late models and queued sends. Ordinary correction
preserves historical sent business text. Explicit erasure immediately removes memory even
while an old send is uncertain; only existing minimal reconciliation evidence may wait.
Personal proposal caches and API bodies are hidden immediately, reconciliation never recreates
an erased body, and definitive resolution clears retained draft text. Source fences retain
only scoped provider-source hashes; invalidated summary query digests are cleared.

Memory invalidation touches only agent-origin/explicit agent proposal caches, not human/manual
drafts. Linked unsubmitted actions/drafts cancel atomically and immediately make their approval
cards/decisions stale; deferred cleanup uses the existing approval-first lock ordering and a
customer-generation-specific job key. Historical sent business message bodies remain outside
memory-only forget/erase scope; account conversation erasure retains its explicit wider scope.
Configured memory retention controls stored write/correction deadlines and effective read/API
expiry, including shorter policy changes before the next retention sweep.

## Session 09 implemented private owner-information contract

Migration `0025` follows `0024`. `owner_questions` bind workspace/account/thread/customer,
the unresolved session, original customer message/hash/cursor, ownership/deletion generations,
closed required-information slot, visibility, expiry and a server-owned continuation key.
Deduplication hashes thread + session + source event + required slot, never model wording.
`owner_answers` are versioned information decisions/proposals with author role/user,
UUID request id/hash and expiry. Composite FKs bind question answers to that exact question,
holding actions to its account and reusable candidates to its workspace. Neither record is
an action grant. Existing accounts remain legacy until explicit owner activation.

Private `owner.ask` v1 accepts `{question,required_info,visibility,holding_response:false}`.
Required slots are `availability|exception|service_detail|business_policy|other`; visibility
is `customer_reply|private_business`. Its result is
`{question_id,state,version,wait_for:"owner",approval_id:null}`. A pending result immediately
ends the activation in a question-ID-backed `waiting_owner`, with a consumed step and no
retained worker/DB transaction. Optional holding text is server-written, tracked once by
`holding_action_id`, and goes through the same delegation, stable intent and send ledger.
Uncertain effects continue reserving the thread slot. `approval.request` v1 instead accepts
the closed reply proposal and creates an exact `agent_action` human approval through the
existing Session 03/07 path, even under an automatic rule. It still cannot override `off`.

All routes below use `/workspaces/{workspace_id}/accounts/{account_id}/owner-questions`:

| Route | Contract |
|---|---|
| `GET /`, `GET /{id}` | Member inspection; bounded UUID pagination (`limit=1..50`, `cursor`), optional customer filter; foreign persisted account/customer/question IDs return 404. |
| `GET /{id}/answers` | Version/proposal history with the same pagination bounds; private bodies never enter public tools/context. |
| `POST /{id}/answer` | `{expected_version,client_request_id,body,kind:"answer"|"proposal",reusable_knowledge:null}`. Owner/manager authoritatively answer; staff may propose while pending. A proposal after an authoritative answer rejects without changing its version. |
| `POST /{id}/cancel` | Owner/manager only; `{expected_version,client_request_id}`. Cancellation is versioned and idempotent. |

Information decisions lock account -> thread -> question, never approval. Answer + event +
cursor advancement + durable wake commit in one caller transaction; duplicate identical
requests replay the same record, conflicting retries/version races return 409. Expired or
cancelled questions reject late answers. Replacements retain version history, invalidate old
proposals and emit a new wake. The existing periodic recovery finds the exact persisted
question referenced by owner waits and independently expires a bounded oldest-deadline batch.
Unanswered people do not consume model/failure attempts or precede resolved waits in the scan.
Recovery can find a committed answer after a worker dies before processing its wake.

The closed reply evidence is `owner_answer:{id,version}` with empty `template`, no fact
sources and no customer clarification. The server renders the **entire** attributed reply
from the persisted answer. Arbitrary model prose cannot borrow its authority, and an answer
ID is never a BusinessFact ID or a numeric/span exemption. Dispatch repeats exact question,
thread/customer, current answer, visibility, expiry, original message hash, current author
membership, knowledge-generation digest and ownership/deletion checks. Existing critical
fact render/claim validators remain unchanged. The independently evidenced DM obligation
guard admits only the matching `owner_answer` event (or a current customer event using valid
answer evidence); generic control/result wakes cannot mint another DM intent.

The coordinator rereads current messages/facts/delegation/takeover before continuation and
the executor still checks provider capability, messaging window and the exact payload grant.
A closed window retains valid information, creates a deduplicated in-app notification and
waits for a customer interaction, with no background send/delivery claim. Reopening is
deliberately conservative: only an exact repeat of the original request can reuse the
still-valid answer automatically; a changed request must be clarified/replanned. A workspace
knowledge aggregate digest conservatively invalidates answers after any fact/candidate
change. Its output is bounded but its database aggregate scans the workspace; performance
at large knowledge volume remains an optimization dependency.

Cancellation/replacement/expiry immediately cancel linked **unsubmitted** actions/drafts and
make approval cards stale. Deferred cleanup alone takes approval locks in the existing
approval-first order. In-flight/unknown outcomes keep their reservations and reconciliation
evidence; sent messages/manual drafts are preserved. Between-claim tool observations are
cleared when either customer memory generation or thread event cursor changes.

Explicit reusable knowledge accepts only `{key:"custom.<slug>",text}` and creates an
unverified typed text candidate with `source_type=owner_answer` and persisted
`owner_answer_id`; normal knowledge verification remains mandatory. Private-business answers
cannot create reusable candidates. Question/answer bodies and linked proposal caches redact
on linked source removal, disconnect erasure and expiry; memory-only correction/forget does
not rewrite historical business messages. The broader conversation/data-subject erasure API
remains the separate owner `data.delete`/Phase 8 workflow. Jobs, events, notifications, audit
and generic model runs contain IDs/counters/state, never question/answer bodies.


### Session 10 public ingestion/context implementation

Only the mock webhook codec accepts `synthetic_comments` using the explicitly provisional
`synthetic-comment-v1` schema. HMAC verification of raw bytes precedes parsing. The actual
inbound receipt/dedup/job pipeline persists and processes comments; R75-01/02 remain open,
and the real Meta codec and comment capabilities remain disabled. Developer-only
`POST /api/v1/dev/workspaces/{workspace_id}/simulate/comment` records mock state and signs
the payload before passing it through this same ingestion path. Its fields explicitly
include root/parent IDs, stable optional author, state/revision/time and synthetic post
metadata; there is no username-based identity inference.

Member permission `comments.view` permits bounded account comment lists, detail and thread
reads under `/accounts/{account_id}/comments`, plus media/detail/thread pages. Page limits
are 1-50 with UUID cursors; foreign workspace/account/media/thread IDs return 404.
`public.thread` is a read-only comment-surface broker tool (1-8 comments) exposing only the
current post/thread, source IDs/versions, unknown/ownership states and simulation provenance.
Private DM, memory and owner-question tools remain unavailable. No public reply, moderation
or private-reply effect is registered in Session 10.

Actual model context pins the current scoped event's exact comment source/version, even
when it is beyond the first page, with at most five public turns and a bounded post caption.
Language and knowledge relevance use that current eligible customer comment. Native owner
sources update context and ownership fencing without becoming customer-comment obligations.
Each source change advances its thread cursor; captured media versions fence post changes
across sibling threads, and carried observations are discarded across either generation.
Durable public read checkpoints contain validated routing arguments only and are reread
on restart. No public/customer body is stored in jobs, generic agent events or audit metadata.


A historical/unlinked comment scaffold with no `public_thread_id` receives empty public
context and no private turns. It cannot use the strict public-thread tool or establish a
public source obligation. This retains the earlier adversarial surface-switch privacy
checks while real ingestion always creates the scoped public link.


Public model/tool display budgets are measured after neutralisation and JSON escaping,
including the extra encoding layer in the model request: comment preview 280 bytes and
post caption 320 bytes. Opaque author IDs are emitted exactly only if their display fits
100 bytes and needs no neutralisation; otherwise `author_id` is null with
`author_id_omitted: true`. Author identity in domain records, UUID source references and
versions remain exact. Full bodies remain available through scoped member APIs. These
previews may omit the suffix of a long source; full-topic/model-quality evaluation is
pending Session 17. Maximum eight-comment Unicode/escaping observations are tested through
the actual second model request against the existing 16,000-byte request envelope.

## Session 11 offline public effects

`comment.reply` and `comment.moderate` are comment-surface broker tools. The latter accepts
only `hide`, `unhide`, or `delete`; both require a scoped comment UUID and exact local version.
Reply text is rendered by `reply.validate` from current verified fact versions. The target
must be a non-owner comment on a synthetically verified post, in the correct state; the
source event must be the current customer-comment obligation. A conflicting pending or
unknown action for that comment reserves the target. A succeeded reply reserves its target
permanently against reworded replans. A model may complete with no action.

`public_comment_actions` binds the action, target, local comment version, shared media
version, effect, reply payload and hash. An exact `agent_action` approval is required for
`ask`; `automatic` uses the versioned delegation grant. Queued jobs carry only the action ID.
The worker rechecks approval or grant, account state, delegation, capability, ownership,
source/media versions and grounded reply before committing one `comment_*` operation.
Only then does the mock provider perform the effect outside a database transaction.
`GET /accounts/{account_id}/agent/actions/{action_id}` and the existing operation detail
expose queued, performed, failed, and unknown states without reply bodies.

The mock's `sim_comment_effects` gives positive readback by operation key. A lost response
becomes `outcome_unknown`; a repeated job never calls the provider again. Positive readback
can resolve it. Missing effect evidence, including an absent comment/404, remains unknown
and blocks duplicates. Source erasure and retention remove pending reply bodies from action
and mock evidence; audit and operation metadata contain IDs and status only. Real Meta
comment mutations and readback reject calls until R75-03/06 and Session 16 verification.

## Session 13: authenticated owner tasks and image content

`POST /accounts/{account_id}/agent/tasks` accepts `text`, UUID `client_request_id`
and optional exact `media_asset_id` / `content_id` selections. It returns a durable task
ID (202); the same requester/account/request ID and input return the original task,
including after a pause. Reusing the ID with different text or selections conflicts.
The account must belong to the authenticated workspace and have an active agent for a
new task. No customer ingestion path invokes this API. Staff may submit tasks, but
each requested effect independently checks their current role. Claim, broker dispatch,
approval execution and scheduled publication reconstruct membership rather than trusting
the stored requester role.

GET list/detail are requester-only; foreign accounts/tasks/cursors return 404. Lists
use a descending UUID cursor with a bounded `limit` and `next_cursor`. Responses include
`clarification`, `question_version` and typed content action results, including the
actual content status and simulation provenance. `POST /tasks/{id}/answers` takes the
original task shape plus required `expected_version` matching `question_version`;
answers have independent request IDs. It records at most eight clarification answers
and atomically emits a wake. Replays are idempotent; stale/different answers conflict.
Answers are information only and cannot approve publication.

Migration `0029` stores owner tasks. Additive `0030` stores bounded read/selection receipts,
clarifications/answers, and durable content intents on actions. No migrated account is
activated or given new grants. Existing manual submission/self-approval remains the
legacy path; explicitly resubmitting or reapproving an agent item manually establishes
a new legacy approval. It cannot reuse an old agent grant.

All tools below are `v1`, restricted to `owner_task` source/surface, and reject extra
arguments. Bodies remain in domain records; jobs, audit metadata and step checkpoints
contain routing IDs/hashes rather than caption or request bodies.

| Tool | Arguments and behavior |
|---|---|
| `content.read` | `kind: content/media`, nullable UUID `cursor`, `limit` 1–10. Returns scoped content/version or ready-media/hash receipts. No foreign-account content or storage URLs. |
| `content.prepare` | `content_type: feed_image/story_image`, `title`, nullable `media_asset_id`, nullable grounded `caption` proposal. Requires a seen ready asset; captions use exact fact-source evidence. Stories have no caption. No customer/private-answer evidence or new media generation. |
| `content.schedule` | `content_id`, `expected_version`, workspace-local ISO `local_date` and `HH:MM local_time`. Authorizes scheduling separately, then proposes publication under its own rule. |
| `content.publish` | `content_id`, `expected_version`. Proposes the current draft for now; queued/scheduled is not published. |
| `content.cancel` | `content_id`, `expected_version`. Separate cancellation delegation; uses existing cancellation rules. Cannot cancel an uncertain/in-flight publish. |
| `task.clarify` | `question` (1–500 characters). Persists one pending requester question and pauses the goal until a versioned answer. |

Selections must have been read and remain current. With multiple possible records the
requester must select the exact ID in intake/answer (or supply that ID in their text);
the model cannot resolve ambiguity by guessing an unseen alias. A single available
record is unambiguous. Missing imagery/details return a clarification requirement.
Drafting does not imply permission to schedule or publish. Automatic, ask and off apply
independently to all four effects. Publication `ask` uses an explicit single-use
`agent_action` approval; automatic publication projects its policy grant to the existing
content executor. Both bind content/media/account/instant and sorted fact versions.
The action version equals the bound content version, including edited drafts.

The original content validation, fact holds, media fences, quota, ledger and reconciliation
remain authoritative. Scheduled grants expire at the scheduled instant plus the workspace
publish delay, rather than the generic 24-hour action lifetime. Pending human decisions
expire by the earlier of 24 hours and the requested future instant (for “now”, the publish
deadline). The executor checks current delegation, requester membership, pause, exact
payload and fact versions. Unknown publish outcomes retain the same operation/container;
revocation does not prevent positive reconciliation of an effect that already happened.
Task action results reconstruct scheduled/published/unknown states from persisted records.
