# Glossary

**Purpose:** One meaning per term across all documents, code, database names and UI copy. Code identifiers in `backticks` are the canonical names to use in implementation.

| Term | Meaning | Code / table |
|---|---|---|
| **Workspace** | One business (tenant). All business data belongs to exactly one workspace. | `workspaces` |
| **Member** | A user's membership in a workspace with a role (`owner`, `manager`, `staff`). | `workspace_members` |
| **Owner** | The business owner role: full control of the workspace. In prose, "owner" also means "the human operating the business side" (owner or manager). | role `owner` |
| **Customer** | A person who messages the business on Instagram. *Not* a user of our product. | `conversations.customer_*` |
| **User** | A person who logs into our product (owner, manager, staff, or the founder as an invited member). | `users` |
| **Business fact** | A typed, versioned piece of business information (price, hours, address, policy…) with a verification status. | `business_facts`, `fact_versions` |
| **Fact key** | Stable namespaced identifier of a fact, e.g., `pricing.membership_monthly`. | `business_facts.key` |
| **Verified fact** | A fact whose current value was entered or confirmed by a member with `knowledge.verify` permission. | `status = 'verified'` |
| **Usable fact** | A verified fact that is not archived, not outside its validity window, and not *contested*. Only usable facts may appear in customer-facing or published text. | computed (`FactService.usable_facts`) |
| **Fact candidate** | A proposed value from a non-authoritative source (staff proposal, extraction from pasted text, Instagram profile). Never used until accepted. | `fact_candidates` |
| **Discrepancy** | A pending lower-priority candidate that differs from a verified fact. Informational; the fact remains usable. | candidate `relation = 'discrepancy'` |
| **Contested fact** | A verified fact with a pending conflicting candidate from a business member (staff). Not usable until resolved. | candidate `relation = 'contest'` |
| **Fact placeholder** | Token in LLM output, `{{fact:<key>}}`, replaced by code with the formatted verified value. | renderer |
| **Claim validator** | Deterministic check that rejects critical values in text that did not come from placeholders. | `app/knowledge/claims.py` |
| **Readiness** | Workspace status computed from required facts, account connection and policy review: `not_ready`, `ready_for_drafts`, `ready`. | `GET /readiness` |
| **Conversation** | The DM thread between the business's Instagram account and one customer. | `conversations` |
| **Message** | One message that actually exists in the Instagram thread (inbound received or outbound sent/echoed). | `messages` |
| **Reply draft** | A proposed outbound reply (AI-generated, approved answer, or owner-written) with a policy decision and status. Becomes a `message` only when sent. | `reply_drafts` |
| **Approved answer** | A reusable owner-approved reply text for a recurring question, with linked fact references. | `approved_answers` |
| **Messaging window** | The 24 hours after the customer's last inbound message during which the business may reply via API. | computed from `conversations.last_inbound_at` |
| **Human takeover** | Conversation mode in which automation stops drafting and the owner handles replies. | `conversations.handling_mode = 'human'` |
| **Intent** | Classified purpose of a customer message (e.g., `pricing`, `complaint`). | `reply_drafts.intent` |
| **Action class** | Policy grouping of actions for autonomy settings (e.g., `reply.pricing`, `content.publish`). | `automation_policies.action_class` |
| **Automation policy** | Per-workspace setting of `auto` / `approval` / `off` for an action class. | `automation_policies` |
| **Policy decision** | Deterministic outcome `auto`, `approval_required`, `human_required` or `blocked`, with reason codes. | `PolicyEngine` |
| **Approval** | A record that a specific action at a specific version may (or may not) happen. Kinds: `confirmation` (user confirms system's interpretation of their own command) and `authorization` (permission for a proposed action). | `approvals` |
| **Payload hash** | SHA-256 of the canonical JSON describing exactly what an approval authorises. | `approvals.payload_hash` |
| **Owner command** | A natural-language instruction from a user through an owner channel, interpreted into a typed command. | `owner_commands` |
| **Command type** | Member of the closed registry of supported commands, e.g., `knowledge.update_fact`. | `owner_commands.command_type` |
| **LLM task** | One of four bounded model calls: `interpret_command`, `draft_reply`, `draft_content`, `extract_fact_candidates`. | `app/ai/tasks/` |
| **Agent run** | Persisted record of one LLM task execution (inputs snapshot, output, model, tokens, outcome). | `agent_runs` |
| **Content item** | A planned Instagram publication (feed image or story image in MVP) with its own state machine. | `content_items` |
| **Media asset** | An uploaded, validated media file stored via `MediaStorage`. | `media_assets` |
| **On hold** | Content state when a referenced fact changed or the account became unavailable after approval. Requires review and re-approval. | `content_items.status = 'on_hold'` |
| **Operation** | Ledger record of one intended external side effect with an idempotency key and verifiable outcome. | `operations` |
| **Outcome unknown** | Operation state after an ambiguous failure (e.g., timeout) until reconciliation determines what happened. | `operations.status = 'outcome_unknown'` |
| **Reconciliation** | Checking provider state (container status, echoes, conversation lookup) to resolve an ambiguous operation. | `reconcile_*` jobs |
| **Job** | A unit of background work in the PostgreSQL queue. Only a trigger; domain tables hold user-visible state. | `jobs` |
| **Inbound event** | A raw, signature-checked, deduplicated webhook item stored before processing. | `inbound_events` |
| **Provider** | An external service adapter behind an interface: Instagram (`mock`/`meta`), LLM (`fake`/`openai`), storage (`local`/`s3`). | `app/integrations/` |
| **Provider kind** | Which implementation backs a connected account: `mock` or `meta`. | `social_accounts.provider_kind` |
| **Simulated** | Produced via a mock provider. Must be labelled in the UI and reports. | `is_simulated` |
| **Owner channel** | How users talk to the product: `web` (MVP), `telegram` (Phase 9), maybe `whatsapp`. Distinct from Instagram, which is a customer channel. | `owner_commands.channel` |
| **Notification** | Channel-neutral message to a user about something needing attention or a result. | `notifications` |
| **Audit log** | Append-only record of important state changes. Source of the owner's Activity view. | `audit_logs` |
| **Correlation ID** | ID propagated from a triggering event through all resulting jobs, runs, operations and audit entries. | `correlation_id` |
| **Demo workspace** | A workspace flagged `is_demo`, the only kind allowed to use mock providers in production configuration. | `workspaces.is_demo` |
