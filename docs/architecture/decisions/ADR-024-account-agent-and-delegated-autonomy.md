# ADR-024: Account agent with memory and delegated autonomy

- **Status:** Accepted target architecture (2026-10-26); staged implementation pending
- **Date:** 2026-10-25
- **Product direction:** Requested by the owner: a conversational Instagram agent that manages DMs and comments, remembers context, maintains a tone, asks questions, requests help when necessary, and chooses actions independently within delegated account authority.
- **Supersession:** ADR-007's prohibition on autonomous orchestration; the no-tool restriction in ADR-009; ADR-014's topic-first agent authority and fixed publication approval requirement. Legacy bounded tasks, legacy topic policies and exact human approval mechanics remain active until an account is explicitly cut over. All unrelated decisions remain in force. [Account-agent contracts](../account-agent-contracts.md) fix the implementation names and boundaries.

## Context

The current system is a set of deterministic workflows containing single LLM proposal calls. It is not the intended conversational account agent. Changing all topic dropdowns to `auto` cannot supply durable memory, goal tracking, information requests to the owner, tool selection, or comment moderation.

The target product is a business representative that runs conversations and chooses supported Instagram actions. Opening hours, pricing, services and offers are knowledge domains, not the limits of its conversational ability. A request outside those labels must not automatically end the conversation.

This is a product and architecture pivot. It is not permission to claim unsupported Instagram capabilities or to bypass the existing execution ledger.

## Decision

### 1. An account agent owns coordination

One logical agent identity per connected Instagram account has business goals, personality, a versioned delegation policy and access to scoped memory. It processes DMs, comment threads, owner instructions, owner answers, approval decisions, tool results and scheduled wakeups through the same runtime.

The model chooses the next step, including tools. It is not restricted to selecting a reply category. The runtime is a durable loop:

1. Load the event, current thread state, relevant memory, business knowledge, delegation policy and available capabilities.
2. Ask the model for the next typed action or tool request.
3. Validate the request and resolve targets in server code. Authorize it against the owner's delegation and current account capabilities.
4. Run a read, persist an internal update, create a question/approval request, or dispatch a side effect through the operations executor.
5. Observe the actual result, update state, and continue or yield.

Structured action schemas validate arguments; they do not prescribe a canned conversation. A reasoning step can decide to ask a customer a question, answer several subjects together, retrieve more context, or stop because no reply is useful.

One logical coordinator does not mean one account-wide blocking worker. Thread-scoped leases and state versions serialize conflicting work. Independent threads may proceed concurrently, with account-wide limits enforced at execution. No lease or database transaction remains open while waiting for an owner or external service.

### 2. Autonomy comes from owner delegation, not a permission per subject

Primary settings describe what the agent may do: converse in DMs, reply publicly, send eligible private replies, hide/unhide comments, delete comments, and prepare/schedule/publish content as delegated. Each capability may be automatic, require approval, or be disabled, with optional scope and limits.

The owner may delegate broad moderation authority, including autonomous deletion. The model then chooses whether a particular comment merits deletion under that instruction. A human does not have to approve every deletion. A workspace can instead choose hiding, narrower moderation criteria, or approval for deletion; these are owner choices, not mandatory defaults imposed on every workspace.

Business commitments are distinct from discussing a subject. The agent may explain an existing offer or acknowledge a complaint without thereby acquiring authority to invent a discount or issue compensation. The current unconditional topic escalations must be replaced by action-level rules and explicit exceptions.

Natural-language owner guidance is part of the experience. Security-relevant instructions are resolved into a versioned, inspectable delegation policy. Changing that policy requires the existing owner permission; a customer message, tool output or model inference cannot modify it. Tone instructions cannot grant authority.

Deterministic enforcement still decides whether the selected action is within delegation. Model confidence alone never grants permission. Provider constraints, account ownership, recipient eligibility, data visibility and current authorization are checked in code.

### 3. Tools are mediated capabilities

Initial tool families, with names illustrative until API contracts are implemented:

| Family | Capabilities |
|---|---|
| Knowledge | Search verified business knowledge; retrieve relevant supporting material |
| Context | Read scoped conversation history, customer memory, post context and comment threads |
| Conversation | Send a DM, reply publicly, send an eligible private reply to a comment |
| Moderation | Hide, unhide or delete a comment under delegated authority |
| Owner collaboration | Ask a business question, request an action approval, hand over a conversation |
| Memory | Propose scoped memory updates, update a conversation summary and track pending work |
| Content | Prepare, schedule or publish through the content subsystem as capabilities and delegation allow |

These are target capabilities, not assertions that the current adapter implements them. Booking transactions, refunds or other integrations require their own tools and contracts before the agent may claim to perform them.

The broker supplies workspace/account identity and resolves server-side object references. The model never chooses an arbitrary workspace or receives provider credentials. Tool arguments are untrusted proposals. Only authorized tool handlers access data, and only operations executors perform external effects.

An ordinary agent action needs no human tap when an applicable delegation exists. The broker records an exact-payload policy grant with the policy version and reason; the executor rechecks current eligibility. Owner-required actions use the existing explicit, bound approval mechanism. Revoking delegation stops unexecuted actions; an old run or queued grant cannot override the revocation.

### 4. Memory and personality are first-class

| Layer | Scope and purpose |
|---|---|
| Business knowledge | Workspace knowledge with provenance, verification, validity and versioning; source for critical business claims |
| Personality | Business voice, language preferences, examples, conversational style and goals; persistent and owner-editable |
| Customer memory | Account-scoped customer preferences and relevant interaction history, with provenance, correction and retention |
| Thread state | Goal, collected details, summary, open questions, pending approvals, pending tool work and next step |
| Run history | Events, selected actions, tool results and outcomes needed for audit and recovery; no private chain-of-thought requirement |

Customer statements may establish that customer's preferences or claims, not verified business policy. A customer saying a price changed never changes the price used for other customers. An owner answer may resolve the current question; persisting it as reusable business knowledge follows the appropriate knowledge permission and validation rules. A one-off exception does not silently become a standing offer.

Public and private contexts have explicit visibility. Remembering information from a DM does not authorize publishing it in a comment. Comment-to-DM identity linking requires provider-supported identity evidence; matching display names or usernames alone is insufficient. New customer memory needs retention/export/deletion rules consistent with ADR-022 before real use.

Critical business values still come from usable knowledge. Free conversation, empathy, clarifying questions and recommendations do not require a predefined FAQ entry, but unsupported business promises remain disallowed. The validator needs source-aware treatment of customer-provided values, so asking "Did you mean Tuesday?" is not mistaken for promising business availability.

### 5. Questions, approvals and takeover are different

- **Customer clarification:** the agent asks the customer and waits for their response. It need not notify the owner.
- **Owner information request:** the agent asks an authorized business member for missing information and stores the waiting conversation, question, visibility and continuation. An answer wakes the agent; it does not automatically authorize an unrelated action.
- **Owner action approval:** the agent presents the exact proposed action through an explicit decision control. Approval binds only that action, version and payload.
- **Takeover:** staff or owner takes control. Unsent automatic work is stopped; background wakeups cannot silently reclaim the conversation.

The agent may send a truthful interim reply when it is useful and allowed. It cannot promise a follow-up that the platform will not permit. On resumption it rechecks new customer messages, takeover, facts, policy, target state and provider eligibility. A late owner answer cannot cause a stale send.

### 6. Instagram comments are a full event surface

Add persisted media/comment/thread context and normalized comment events. A comment can lead to no action, a public reply, an eligible private reply, moderation, an owner question, or a combination chosen by the agent.

Public replies, private replies, hide/unhide and deletion are separate operations with their own result verification and duplicate prevention. A private reply is not treated as an ordinary DM or as permission for unlimited follow-up. Capability flags reflect actual granted access, not requested scopes.

Comment targets must belong to media managed by the connected account. This design does not assert an API capability to comment on arbitrary third-party posts or perform every action available in the Instagram mobile app.

Platform facts remain owned by [platform-capabilities.md](../../research/platform-capabilities.md). The fresh official-page check on 2026-10-25 was inconclusive: the comment-moderation page could not be fetched and the private-replies page returned HTTP 429. Existing recorded documentation is not new live verification. Exact scopes, access levels, event shapes, private-reply eligibility and limits, and moderation outcome semantics must be refreshed and tested before real rollout.

### 7. Reliability bounds apply to runs, not conversational vocabulary

Each wakeup has step, time, token and tool-call budgets. An unfinished task checkpoints or yields; it does not run forever. Conversation progress persists across worker restarts. Tool/network calls happen outside database transactions.

Event deduplication, thread versions and idempotency keys prevent duplicate actions. An uncertain side effect goes to reconciliation before retry. The agent must not reword a timed-out message or create a new action to evade an unresolved operation.

Pause, disconnect, takeover and delegation changes are effective at the executor boundary. Content/media changes invalidate dependent actions. Reporting distinguishes chosen, authorized, queued, executed, verified, failed and uncertain outcomes.

## What remains and what changes

Retain the modular monolith, PostgreSQL jobs, tenant isolation, provider adapters, encrypted credentials, operations ledger, audit, exact-action approvals, fact provenance, simulated-result labels and honest outcome reporting.

Replace the single-call-only conversation controller, fixed intent coverage as an autonomy boundary, mandatory human handling based solely on topic, and per-topic settings as the main product experience. Extend the LLM abstraction, not the vendor SDK throughout business code. Existing bounded extraction/content tasks may remain useful tools behind the coordinator.

Session 01 records the scoped ADR supersession, amends INV-03/04/16 and the product/runtime/data/workflow target contracts in [account-agent-contracts.md](../account-agent-contracts.md). Existing bounded tasks retain their no-tool behavior until an account is explicitly switched. Implementation sessions must add the specified enforcement and tests before enabling the new controller. No invariant is weakened silently by this target document.

## Trade-offs

The runtime and evals become more complex, and multi-step interactions can use more tokens and time. Memory needs relevance selection and privacy controls. An autonomous agent can make a poor choice within its authority; the owner needs inspectable actions, editable delegation and immediate pause/takeover.

The benefit is the requested product: the agent can converse, gather information, remember context and decide useful next actions without repeated approval of routine work.

## Implementation

The canonical delivery plan is [Phase 7.5](../../implementation/phases/phase-7.5.md), with [18 implementation sessions](../../implementation/phase-7.5-sessions/phase-7.5-sessions.md). It defines data/runtime contracts, migration, research dependencies, acceptance scenarios and rollout evidence. The original migration outline now redirects there. This ADR changes no running behavior or live account permissions by itself.
