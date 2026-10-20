# Functional Workflow Contracts

**Purpose:** Precise, implementation-ready contracts for the seven core workflows (A–G). For each one: trigger, preconditions, inputs, main steps (with transaction boundaries), state transitions, permissions, persistence effects, external side effects, failure paths, idempotency and acceptance tests.
**Related:** states in [state-machines.md](state-machines.md), tables in [data-model.md](data-model.md), endpoints in [api-design.md](api-design.md), LLM tasks in [agent-runtime.md](agent-runtime.md), UX in [user-journeys.md](../product/user-journeys.md).

Notation: **[T1]**, **[T2]** = separate committed DB transactions. "Enqueue" always happens inside the current transaction ([ADR-006](decisions/ADR-006-postgres-job-queue.md)). "Audit" = `audit.record(...)` inside the current transaction.

---

## A. Business onboarding

**Goal:** From workspace creation to verified facts and a readiness status.

| Aspect | Contract |
|---|---|
| Trigger | User creates a workspace (`POST /workspaces`) and works through the knowledge checklist. |
| Preconditions | Authenticated user. |
| Inputs | `name`, `business_category`, `market`, `default_locale`, `timezone`, `currency`. Then fact values, pasted text, mock or real account connection. |
| Permissions | Creator becomes `owner`. Fact entry: `knowledge.edit`. Verification: `knowledge.verify`. Connect account: `integrations.manage`. Automation settings: `automation.manage`. |

**Main steps**
1. **Create workspace** [T1]: insert `workspaces`, `workspace_members(owner)`. Audit `workspace.created`. The category template is *not* materialised as rows; missing items are computed by comparing template keys with existing facts.
2. **Enter facts** (sync, per fact) [T]: `knowledge.update_fact(...)` creates or updates `business_facts` + `fact_versions`. Status is `verified` if the actor has `knowledge.verify`, otherwise the input becomes a `fact_candidate (staff_proposal)`. Audit `fact.created` / `fact.updated` / `fact.verified`.
3. **Paste & extract** (async):
   - [T1] `POST /knowledge/extractions {text}` stores the request as a job payload reference: the text is stored in `agent_runs.input_snapshot` only (retention 30 days). Enqueue `extract_fact_candidates`. Return 202 with the run ID.
   - [T2] Job: run the LLM task with the template key catalog. Validate output. For each item, deterministically parse and normalise the value by type, compute `relation` and insert `fact_candidates (pasted_text)` with `source_excerpt`. Items whose excerpt is not a substring of the pasted text (normalised whitespace) are **dropped** (anti-hallucination check). Audit `fact_candidate.created` (count only).
4. **Resolve candidates** (sync): accept → `update_fact` (verified, `source_type = candidate_accepted`); reject → `rejected`. Audit.
5. **Automation review** (sync): the owner opens the automation screen, saves the policies (`PUT /automation-policies`, audit `policy.updated`) and confirms with "Bu ayarları inceledim" (`POST /automation-policies/review`). The first confirmation sets `settings.automation_reviewed_at` (server clock) and audits `policy.reviewed`; saving alone never does. The seed stamps it directly for the demo workspaces.
6. **Connect account**: mock — `POST /social-accounts/mock` (demo tools or `is_demo` workspace only) inserts `social_accounts(provider_kind=mock, status=connected)` with full capabilities. Meta — Phase 7 OAuth flow ([integrations.md §3.4](integrations.md)).
7. **Readiness** (computed on read, `GET /readiness`):
   - Requirements are judged on **usable** facts (verified, inside the validity window, not contested; [business-knowledge.md §1](business-knowledge.md)), so a contested or expired fact lowers readiness until it is resolved.
   - `not_ready` unless all of these are usable: `identity.business_name`; at least one of `contact.phone` / `contact.whatsapp` / `contact.email`; `location.address` or `location.online_only = true`; `hours.weekly`.
   - `ready_for_drafts` once the above holds.
   - `ready` when additionally: every template item marked `required_for_ready` is usable (pricing items, or `policy.price_disclosure = do_not_share`; ≥ 1 `service.*`; `booking.instructions`), an account is `connected`, and `automation_reviewed_at` is set.
   - The response lists each requirement with status and a deep link.

| State transitions | Facts: `unverified → verified`, candidates: `pending → accepted/rejected`, account: `→ connected`. |
|---|---|
| Persistence | `workspaces`, `workspace_members`, `business_facts`, `fact_versions`, `fact_candidates`, `agent_runs`, `social_accounts`, `audit_logs`. |
| External side effects | None in S1 (mock). OAuth in Phase 7. |
| Failure paths | Extraction LLM failure → run `failed`, UI keeps the pasted text and offers manual entry. Invalid value types → 422 with field errors. Timezone or currency invalid → 422. |
| Idempotency | Workspace slug unique. Fact updates use optimistic concurrency (`expected_version` in PATCH; mismatch → 409 `FACT_VERSION_CONFLICT`). Extraction requests carry `client_request_id`. Candidates with `relation = same` are auto-superseded, so re-running extraction does not spam. |
| Acceptance tests | AC-A1…A6. |

---

## B. Business fact update via natural language

**Goal:** "Aylık üyelik artık 7.000 TL" → interpreted, confirmed, versioned, propagated, audited.

| Aspect | Contract |
|---|---|
| Trigger | `POST /workspaces/{id}/commands {text, client_request_id}` from the web (or Telegram in Phase 9). |
| Preconditions | Member with `commands.use`. |
| Inputs | Raw text (≤ 1000 chars), channel, user locale, workspace context. |
| Permissions | Confirmation can be decided by the requester. Execution as a fact update requires `knowledge.verify` (owner, manager). Without it (staff), execution creates a `contest` candidate. |

**Main steps**
1. [T1] Insert `owner_commands(status=interpreting, correlation_id=new)`. Enqueue `interpret_command(command_id)`. Audit `command.received`. Return 202.
2. [T2] Job `interpret_command`:
   1. Build the context: the fact catalog (keys, owner-facing labels, types, current values) for the workspace, the content catalog (the next 14 days and the last 14 days' failures as aliases `C1`..`Cn` with title, type, status and local schedule, never ids; [agent-runtime.md §3](agent-runtime.md)), the current local date and time, and the command registry description. The owner's own data is allowed in the prompt ([agent-runtime.md §8](agent-runtime.md)).
   2. Run `interpret_command` → `CommandInterpretation` (discriminated union).
   3. **Deterministic resolution:**
      - `fact_key` must exist in the catalog; otherwise use the top 3 similar keys by category/label → `needs_clarification`.
      - Re-parse the value from `raw_value_text` with the locale-aware parser. If it disagrees with the LLM's normalised value → `needs_clarification`.
      - Value equals the current value → `completed` with "already X".
   4. **Impact preview:** `knowledge.analyze_impact(fact_id)` returns counts of pending drafts, approved answers, and content items by status that reference the fact.
   5. Create the approval: `kind=confirmation`, `action=command.update_fact`, subject `owner_command` v1, payload `{fact_id, from_version, new_value, reason}`, summary `{label, old_formatted, new_formatted, impact_counts}`, `expires_at = now + 30 min`. Command → `awaiting_confirmation`. Link `agent_run_id`. Audit `command.interpreted`.
3. [T3] User confirms: `POST /approvals/{id}/decision {decision: approve, payload_hash}` → `approvals.decide` → callback `commands.on_approval_decided` in the **same transaction**:
   1. Re-check the binding (the payload stored with the command must still hash to `approvals.payload_hash`; otherwise `APPROVAL_STALE` and the decision rolls back). Lock the fact row. Check `current_version == from_version`; otherwise **do not raise**: the callback marks the command `failed (FACT_CHANGED_MEANWHILE)` and returns, so the decision stands (the approval stays `approved`, single-use) and nothing was overwritten. The owner repeats the command.
   2. Execution runs as the **human who decided** (INV-04), not necessarily the requester. Owner/manager: `update_fact` → new `fact_versions` row (`source_type=owner_command`, `source_ref=command_id`, `reason`), status `verified`, `last_verified_*`. Staff: `propose_candidate(staff_proposal)`, relation `contest`, notify verifiers. Stop here.
   3. Recompute `relation` of pending candidates for this key (a candidate equal to the new value → `superseded`; a different one → `discrepancy`).
   4. **Propagate (deterministic impact handling).** In the code this runs inside every fact update (UI edit, accepted candidate, command) through the `ReferrerHandler` registry in `knowledge/impact.py`, so all changes behave alike; Phase 3 registers no handler of its own, and Phases 4–5 add the referrers below:
      - `reply_drafts` in `pending_approval` / `needs_human` / `queued` referencing the fact → `superseded`, approvals cancelled (`FACT_CHANGED`). Enqueue `draft_reply(conversation_id)` for each conversation still within the window.
      - `content_items` (`content/impact_handlers.py`, P5-07) in `scheduled` / `retry_scheduled` referencing the fact → `on_hold (FACT_CHANGED)`: the queued `publish_content` job of the version is cancelled, a waiting operation (`pending` / `retry_wait`) is cancelled through the ledger hook, and `content.on_hold` (attention) goes to every `content.approve` holder **including the person who changed the fact** (G14; `knowledge.fact_changed` skips them). The item's approval is already `approved` and an approval never leaves that state, so it is not cancelled: it authorises nothing because the item left `scheduled` (the executor refuses by status and version, INV-16) and re-approval (step 7a) records a new one for version + 1.
      - `content_items` in `pending_approval` → `draft` (`withdraw`, `hold_reason=FACT_CHANGED`) and the pending approval is cancelled (`FACT_CHANGED`). In `draft` → `validation.stale = true`. No `content.on_hold` for these two: nothing was committed to go out.
      - A content item **references** the fact when it has a `fact_references` row for an older version of it, or when its caption or an overlay suggestion contains the fact's **old display string** (whole token, in either locale; only for money, hours, phone, email, address and URL values) even without a row: an owner may have typed the price by hand (G6). A text that already shows the new display is not held.
      - `publishing` is **not touched**: the provider call is in flight and cannot be recalled, and the ledger resolves its outcome (INV-05); holding it would hide a post that may be live. `published` is immutable (INV-17).
      - The confirmation card's `impact` (step 2.4) counts the same items by status (`content_item`: `draft`, `pending_approval`, `scheduled`, `retry_scheduled`).
      - `approved_answers` referencing the fact → `needs_review` (still usable, because answers render facts by placeholder at send time and re-validate).
      - Published content and sent messages are **not touched** ([INV-17](../invariants.md)).
   5. Notification `knowledge.fact_changed` to owners/managers with impact counts and links (dedup by fact and version).
   6. Command → `executing → completed` with result `{message_key: "command.fact_updated", params, links}`. Audit `fact.updated` (metadata: key, old/new formatted, version, command ID) and `command.executed`.
4. Downstream jobs (`draft_reply`) produce new drafts using the new value.

| State transitions | Command: `interpreting → awaiting_confirmation → executing → completed` (or clarification/expiry/cancel/fail). Approval: `pending → approved`. Fact: new version. Drafts: `→ superseded`. Content: `scheduled → on_hold`, `pending_approval → draft`. Answers: `active → needs_review`. |
|---|---|
| Persistence | `owner_commands`, `agent_runs`, `approvals`, `business_facts`, `fact_versions`, `fact_candidates`, `reply_drafts`, `content_items`, `approved_answers`, `notifications`, `audit_logs`, `jobs`. |
| External side effects | None (internal-only). |
| Failure paths | LLM transient error → job retry (max 3, backoff), then command `failed (LLM_UNAVAILABLE)`. Invalid output after one repair → `failed (LLM_OUTPUT_INVALID)`. Unsupported → `unsupported` with suggestions. Confirmation expires → `expired`, nothing changed. Concurrent fact change → `failed (FACT_CHANGED_MEANWHILE)`. |
| Idempotency | `unique (user_id, client_request_id)`: resubmitting returns the existing command. The approval decision is single-use. The fact update is guarded by the version check. Redraft jobs use dedup key `draft_reply:{conversation_id}`. |
| Acceptance tests | AC-C1…C7. |

### B.1 Content commands (Phase 5, P5-03b)

The same pipeline (`interpret_command` → deterministic resolution → answer, question or confirmation) with four more intents; the closed registry still has no approve, publish or send ([agent-runtime.md §3](agent-runtime.md)).

| Intent | Permission | Flow |
|---|---|---|
| `content.create_draft` ("Deneme dersi için bir story hazırla") | `content.edit` (all roles) | No confirmation: `interpreting → executing → completed` in one transaction. The executor calls `generation.stage_request` (draft v1, queued `agent_runs` row, `generate_content` job; workflow E step 1) with `client_request_id = command:{id}` and returns `command.draft_created` with a link to the draft. The draft still needs a time and an approval. |
| `content.cancel_scheduled` ("yarınki postu iptal et") | `content.approve` for the requester **and** for the person who decides | ContentRef resolution (alias, else local date, type and status; none → `REFERENCE_NOT_FOUND`, several → `command.clarify.which_content` with title and time options). Then a confirmation (`command.cancel_content`, payload `{content_id, content_version}`, 30 minutes). On approval, as the decider: `content.service.apply_cancel(expected_version)` = workflow E step 7 (the item's pending approval, its queued `publish_content` job and a waiting operation are cancelled; audit `content.cancelled`). An item that changed meanwhile is not cancelled: the command fails `VERSION_CONFLICT` / `CONFLICT_STATE` and the decision stands. |
| `query.content_status` | `commands.use` | `command.content_status`: the item's own state, local time, simulated flag. |
| `query.activity_summary` ("Bugün kaç DM geldi?", "Dün ne oldu?", "Son 7 gün") | `reports.view` (owner, manager) | No confirmation. Periods `today` (the local day so far), `yesterday` and `last_7_days` (the last seven local days up to now) come from `reporting.period_bounds` in the workspace timezone, and the numbers from `reporting.compute_metrics`, the very code behind the daily report, so the answer for today equals the report's `inbound_messages` at the same instant (AC-E4). Result `command.activity_summary`: `{period, inbound_messages, conversations, replies_sent, replies_auto, replies_approved, replies_by_owner, escalations, attention_now, is_simulated}` and a link `{target: report, date}` (yesterday's date for `yesterday`, today's otherwise). `attention_now` is a snapshot: as of now. The Phase 3 `command.activity_basic` is gone. |
| `query.explain_failure` ("son hata neydi?") | `commands.use` | `latest_failure` or a reference. `latest_failure` is the newest of a failed / on-hold / retrying content item and a `send_reply` operation that ended `failed` (including `OUTCOME_UNCONFIRMED`), both within the last 7 days (H6). A content item's `last_error_code` (or the held item's `hold_reason`) and a reply operation's `last_error_code` are explained from the error catalog (`errors.<CODE>`, with `operation.send_reply.<CODE>` texts where the shared text talks about posts), in the user's language: what happened, **when** (the local time, `d MMM HH:mm`, in the user's UI language) and the next step, with a link to the item (`command.content_failure`) or to the conversation (`command.reply_failure`: `{status, error_code, what, next, retryable, when, is_simulated}`). Nothing from the provider's own message is shown. |


---

## C. Incoming Instagram message

**Goal:** Webhook → stored, deduplicated → grounded draft → policy → approval or send → recorded result.

| Aspect | Contract |
|---|---|
| Trigger | `POST /webhooks/instagram` (real Meta) or `POST /webhooks/instagram/mock` (simulator; mounted only when the `mock` provider is enabled). Both use the same ingestion function; the **path** selects the provider kind and therefore the secret, so the signature is verified before any parsing. |
| Preconditions | The receiving account exists and is not `disconnected`. |
| Inputs | Raw body and headers. |
| Permissions | None (public endpoint). Trust comes from the signature. Workspace is resolved from the receiving account ID only. |

**Main steps**
1. **Ingest (API, < 500 ms)**:
   1. Read the raw body. Compute HMAC-SHA256 with the app secret of the path's provider kind (`META_APP_SECRET` for `/webhooks/instagram`, `MOCK_INSTAGRAM_APP_SECRET` for `/webhooks/instagram/mock`) and compare with `X-Hub-Signature-256` in constant time. Mismatch → 401, audit `webhook.signature_invalid` (system-level, no payload stored), counter incremented.
   2. Parse into normalised items (one per `entry[].messaging[]`). Unknown shapes → stored as `other` and ignored.
   3. [T1] For each item: resolve `social_account` by the recipient account ID (the business) **and** the path's provider kind (a mock-signed payload can never address a `meta` account, nor the reverse). No such account → `inbound_events(status=ignored, ignore_reason=UNKNOWN_ACCOUNT)`; a disconnected account → `ACCOUNT_DISCONNECTED`; an unsupported item shape → `UNSUPPORTED_EVENT` (stored, never processed). `is_simulated` of an ignored event comes from the path's provider kind. `INSERT … ON CONFLICT (dedup_key) DO NOTHING`. If inserted: enqueue `process_inbound_event(event_id)` with `correlation_id`.
   4. Return 200 (always 200 after a valid signature, even for ignored items, so Meta does not retry).
2. **Process event** (job `process_inbound_event`) [T2]:
   - `message` (from a customer): upsert `conversations` (unique by account + customer ID). Insert `messages(inbound, sender_kind=customer)`; unique `mid`, so duplicates become a no-op. Update `last_inbound_at = greatest(existing, provider_timestamp)` and `last_message_at`. If an open draft exists in `pending_approval`/`needs_human` → mark it `superseded` (`NEW_INBOUND`) and cancel its approval (a `queued`, `sending` or `outcome_unknown` draft is left alone). If `handling_mode = automatic`: enqueue `draft_reply(conversation_id)` with `dedup_key = draft_reply:{conversation_id}` and `run_at = now + DEBOUNCE` (default 8 s). If a job for the conversation is already queued or running, nothing is created and its `run_at` is not extended: one job per conversation. The job drafts for the newest inbound message when it runs, and a message that arrived during the run makes it reschedule itself (step 3, T3). If `handling_mode = human`: attention → `needs_human`, notify.
   - `echo` (a message sent from the business account): **first** offer it to the send machinery (a matcher that `operations` registers at startup): a send in `in_progress` or `outcome_unknown` for this account and recipient is matched by its stored provider message id, else by the SHA-256 of the recipient + text within `SEND_RECONCILE_WINDOW_MINUTES` (stored in `operations.provider_ref`); a match resolves `outcome_unknown` to `sent` and the echo is **not** a native reply. Otherwise, if `mid` is not already stored, it was typed in the native app: insert `messages(outbound, sender_kind=business_native)`, update `last_outbound_at`, retire the open draft (`pending_approval`/`needs_human` → `superseded`, `queued` → `cancelled`, both with reason `OWNER_REPLIED_NATIVELY`; a draft already being sent is left alone), attention → `none`.
   - `reaction` / `read` / `postback` / `other`: store and mark `processed` (no further action in MVP).
   - Event → `processed`. Audit `message.received` (IDs only).
3. **Draft reply** (job `draft_reply`) [T3, plus the LLM call outside any transaction]:
   1. Load the conversation. Abort (no-op) if `handling_mode = human`, if there are no unanswered inbound messages since the last outbound (owner already answered), or if an open draft newer than the last inbound exists.
   2. Collect unanswered inbound messages (`covers_through_message_id = latest`). Attachment-only → draft `needs_human (ATTACHMENT_ONLY)` without an LLM call.
   3. Deterministic pre-checks: language detection (simple classifier; unsupported → `needs_human (LANGUAGE_UNSUPPORTED)`), injection heuristics (flag), escalation keywords (flag).
   4. Build the context: **usable facts only** ([business-knowledge.md §6](business-knowledge.md)), active approved answers, brand voice, `policy.price_disclosure`, reply language, and the last 10 messages of the conversation as untrusted data (no usernames or IDs).
   5. Run `draft_reply` → `ReplyProposal {intent, flags[], can_answer, needs_human, approved_answer_id?, reply_template?, used_fact_keys[], language}`.
   6. **Render & validate**: if `approved_answer_id` is set, use that answer's template. Render placeholders from usable facts (unknown or unusable key → `FACT_NOT_USABLE`). Run the claim validator (critical patterns not from placeholders, URLs not from facts, byte length ≤ 1000 including the disclosure suffix). On failure, **one regeneration** with validator feedback; if it still fails → `human_required (GROUNDING_FAILED)` with `suggestion_text` (failed text with issues marked; not sendable as-is).
   7. **Policy** `evaluate_reply` (rules in §C.1) → decision + reasons.
   8. [T3] Under the conversation lock, if a newer inbound message than `covers_through_message_id` exists, discard the plan and raise `RescheduleJob(now + DEBOUNCE)`: the same job row runs again with its attempt given back ([background-jobs.md §3](background-jobs.md)). Otherwise insert `reply_drafts` with status by decision, `fact_references`, and for `approval_required`: `approvals.request(kind=authorization, action=reply.send, payload={social_account_id, conversation_id, recipient_id, text, draft_id, draft_version}, expires_at = min(window_end − 5 min, now + 24 h), execute_before = window_end − 60 s)`. The payload is recomputed from the draft (no payload column on `approvals`) by the executor, whose hash must equal the approved one. The approval `summary` carries ids and reasons, not the reply text; for `human_required` / `blocked` the text of a passing draft is kept as `suggestion_text` only. For `auto`: approval granted by policy (`approvals.grants.record_policy_grant`: `requested_by=system`, `decided_by=null`, `decision_channel=policy`, same `expires_at` / `execute_before`), the disclosure notice appended by code (`validation.suffix_span`), the draft `queued` and `send_reply` enqueued. Update conversation attention. Notifications for `approval_required` (`approval.requested`) and `human_required` (`conversation.needs_human`). Audit `reply_draft.created` (decision and reasons).
4. **Send** (job `send_reply`, see workflow D for the approval part) — `operations.execute_send_reply(draft_id)`:
   1. [T4] Lock the draft. Require `queued`. Require an executable approval (or a policy-auto record). Require the window open (`now < window_end − 60 s`). Require account `connected` with `messaging`. If the window is closed → draft `expired`. If the account is unavailable → stay `queued`, job retried later (until the window closes, then `expired`). Get or create `operations(send_reply:{draft_id})`. If it already `succeeded` → repair the draft to `sent` and exit. Operation `in_progress`, draft `sending`. Commit.
   2. Call `provider.send_text_message(recipient_id, text)` (no DB transaction open).
   3. [T5] Success → operation `succeeded (message_id)`; insert `messages(outbound, business_app, mid)`; draft `sent`; `last_outbound_at`; attention `none`; audit `reply.sent`. `ProviderOutcomeUnknown` → operation `outcome_unknown`, draft `outcome_unknown`, enqueue `reconcile_send(operation_id)` at +2 min (repeat until 10 min). Retryable pre-acceptance error → operation `retry_wait`, job retry. Permanent → `failed` + notification + account effects (workflow G).

### C.1 Reply policy rules (deterministic; all evaluated, most restrictive outcome wins: `blocked` > `human_required` > `approval_required` > `auto`)

| # | Condition | Outcome | Reason code |
|---|---|---|---|
| R1 | Account not `connected`, or lacks `messaging` capability | blocked | `ACCOUNT_NOT_CONNECTED` / `CAPABILITY_MISSING` |
| R2 | `now ≥ window_end − 5 min` | blocked | `MESSAGING_WINDOW_CLOSED` |
| R3 | Conversation `handling_mode = human` | human_required | `HUMAN_TAKEOVER` |
| R4 | Reply language not in `reply_languages` | human_required | `LANGUAGE_UNSUPPORTED` |
| R5 | Intent ∈ {`complaint`, `refund_request`, `discount_request`, `sensitive`} **or** any flag ∈ {`complaint`, `refund`, `discount`, `legal`, `health_safety`, `abusive`, `personal_data`} (from the LLM **or** from keyword detection) | human_required | `INTENT_<NAME>` / `FLAG_<NAME>` |
| R6 | Workspace escalation keyword matched | human_required | `ESCALATION_KEYWORD` |
| R7 | Model output `needs_human = true` or `can_answer = false` | human_required | `MODEL_REQUESTED_HUMAN` |
| R8 | A fact needed by the intent is not usable (missing, unverified, contested, expired) | human_required | `FACT_NOT_USABLE` |
| R9 | Claim validation failed after one regeneration | human_required | `GROUNDING_FAILED` |
| R10 | LLM unavailable / budget exceeded / output invalid | human_required | `LLM_UNAVAILABLE` / `LLM_BUDGET_EXCEEDED` / `LLM_OUTPUT_INVALID` |
| R11 | Attachment-only inbound | human_required | `ATTACHMENT_ONLY` |
| R12 | Injection heuristics matched | approval_required (at least) | `INJECTION_SUSPECTED` |
| R13 | Automation policy for the intent's action class = `off` | human_required | `AUTOMATION_OFF` |
| R14 | Automation policy = `approval` | approval_required | `POLICY_REQUIRES_APPROVAL` |
| R15 | Automation policy = `auto` but readiness ≠ `ready` | approval_required | `READINESS_NOT_READY` |
| R16 | ≥ 3 auto replies in this conversation in the last 60 min | approval_required | `AUTO_RATE_GUARD` |
| R17 | Intent `unknown`/`other` (no action class) | human_required | `INTENT_UNSUPPORTED` |
| — | None of the above restricts and policy = `auto` | auto | `POLICY_AUTO` |

**Invariant check ([INV-04](../invariants.md)):** rules R5 and R7 take the *union* of model flags and deterministic keyword flags. No model output can remove a reason.

**Details fixed in Phase 4:** (a) only the reasons of the *winning* outcome are reported (the chips explain why this level); (b) R10 also covers `LLM_REFUSED`; (c) R17 applies to the intent `other` (the model schema has no `unknown`); (d) R13 to R16 use the **effective mode**: the strictest mode among the intent's class and the classes of the facts the reply quotes (`pricing.*` is `reply.pricing`, and so on), so a price question labelled "faq" still needs the pricing policy; when the class that decided the mode is not the intent's own, R13 to R16 add a second reason `CONTAINS_<CLASS>` (`CONTAINS_PRICING`, `CONTAINS_HOURS`, `CONTAINS_LOCATION_CONTACT`, `CONTAINS_SERVICES`, `CONTAINS_BOOKING`, `CONTAINS_PROMOTIONS`, `CONTAINS_GENERAL_FAQ`) next to the rule's own reason, and the inbox shows it as a reason chip ("Fiyat içeriyor, fiyat ayarı geçerli"); on a tie the intent's own class wins, so the chip appears only when a quoted fact made the reply stricter (the strictest-class rule is kept, it is now explained); (e) a missing or unverified `policy.price_disclosure` counts as `do_not_share`; (f) R1 requires status `connected` exactly (the automatic `degraded` transition arrives in Phase 6).

| Aspect | Contract |
|---|---|
| State transitions | Inbound event `received → processed`; draft per §4 of state machines; approval per §1; operation per §6; conversation attention updated. |
| Persistence | `inbound_events`, `conversations`, `messages`, `reply_drafts`, `fact_references`, `approvals`, `operations`, `agent_runs`, `notifications`, `audit_logs`, `jobs`. |
| External side effects | One `send_text_message` per sent draft. Nothing else. |
| Failure paths | Invalid signature → 401. DB down during ingest → 5xx (Meta retries for 36 h; dedup protects us). LLM failure → `needs_human`. Send failures → workflow G. Window closed → `expired`/`blocked` with an explanation. Out-of-order events → `last_inbound_at` uses `greatest()`, and message ordering uses provider timestamps. |
| Idempotency | `inbound_events.dedup_key` unique; `messages.external_message_id` unique; `draft_reply` dedup key + no-op checks; one open draft per conversation (DB constraint); `operations.idempotency_key` per draft; no automatic resend on ambiguity. |
| Acceptance tests | AC-B1…B10, AC-G4, AC-G5. |

---

## D. Human approval

**Goal:** Create an approval, decide it with an authorised explicit action (or let it expire or be cancelled), and determine execution eligibility.

| Aspect | Contract |
|---|---|
| Trigger | A subject module calls `approvals.request(...)` (commands, reply drafts, content). |
| Preconditions | No other `pending` approval for the subject (DB constraint). The subject is in a state that awaits approval. |
| Inputs | kind, action, subject (type, ID, version), canonical payload, summary, required_permission, expires_at, execute_before. |
| Permissions | Decider must hold `required_permission` in the approval's workspace: `knowledge.verify` for fact commands, `reply.approve` for replies, `content.approve` for publishing. The requester may decide a `confirmation`. |

**Main steps**
1. **Request** (inside the subject's transaction): compute `payload_hash = sha256(canonical_json(payload))`. Insert `approvals(pending)`. Notify eligible users (`approval.requested`, dedup per approval). Audit `approval.requested`.
2. **Display**: `GET /approvals/{id}` returns `summary`, `payload_hash`, `expires_at`, `subject` link and `is_simulated`. The client must send back the `payload_hash` it displayed.
3. **Decide** (sync) [T]: `POST /approvals/{id}/decision {decision, payload_hash, note?}`:
   1. Load with `FOR UPDATE`. Membership and permission check (404 if the approval belongs to another workspace).
   2. `status == pending`, else 409 `APPROVAL_ALREADY_DECIDED`.
   3. `now < expires_at`, else mark `expired` (+ callback) and return 409 `APPROVAL_EXPIRED`.
   4. Hash matches and the subject version equals `subject_version`, else 409 `APPROVAL_STALE`.
   5. Set `approved`/`rejected`, `decided_by`, `decided_at`, `decision_channel`. Invoke the subject callback (same transaction). Audit `approval.approved` / `approval.rejected`.
4. **Expire**: periodic job `expire_approvals` (every minute) and lazy checks on read/decide → `expired` + callback + notify requester. Audit `approval.expired`.
5. **Cancel**: subject modules call `cancel_for_subject(reason)` on edit, supersede, fact change or withdrawal. Audit `approval.cancelled`.
6. **Execution eligibility**: executors call `assert_executable(approval_id, subject_version)`: status `approved`; version equal; `now < execute_before` (if set); `operation_id` null or equal to the current operation. Then they set `operation_id`.

| Aspect | Contract |
|---|---|
| State transitions | [state-machines.md §1](state-machines.md). |
| Persistence | `approvals`, `notifications`, `audit_logs`, subject tables via callbacks. |
| External side effects | None directly. Callbacks may enqueue jobs that cause effects later. |
| Failure paths | 403 (no permission), 404 (other workspace), 409 (already decided / expired / stale). Callback failure → the whole transaction rolls back and the approval stays pending (no half-states). |
| Idempotency | Conditional state update; replaying the same decision request returns 409 without effects. Messenger buttons carry single-use opaque tokens (Phase 9). |
| Acceptance tests | AC-B4, B5, B9, B10, AC-D4, D6, D8; unit tests per guard. |

---

## E. Content scheduling and publishing

**Goal:** Draft → validate → approve → schedule → execute → retry → confirm → report failure.

| Aspect | Contract |
|---|---|
| Trigger | Command `content.create_draft`, the "Ask for a draft" UI, or a manual new draft. Then submit with a schedule. |
| Preconditions | Account connected with the capability for the content type (checked at submit and at due time). |
| Inputs | Objective, format, media upload, caption or overlay text edits, schedule `{local_date, local_time}` or "now". |
| Permissions | Create/edit: `content.edit` (all roles). Submit: `content.edit`. Approve: `content.approve` (owner, manager). Cancel: `content.approve`; anyone else may only **withdraw their own submission** (step 7). |

**Main steps**
1. **Generate draft** (async, `POST /content-items/generate`, G7): [T1] in one transaction create `content_items(draft, version 1)` (`title` = the objective on one line, `objective`, `client_request_id`), an `agent_runs(status=queued)` row that holds the brief (`notes`) and is linked by `agent_run_id`, and the job `generate_content {content_id, version}` (dedup `generate_content:{content_id}`); audit `content.created` (`source: ai`). The same `client_request_id` by the same author returns the first draft and queues nothing. Job (`content/jobs.py`, `content/generation.py`), three phases, **no transaction open during the model call**: [T1, read-only] re-read the draft (it must still be a `draft` at the requested version, otherwise the run is closed as `failed CONTENT_CHANGED` and no model call is paid for) and the facts the model may quote: the usable ones except the internal categories and `policy.price_disclosure`, and without `pricing.*` unless the policy is `share` (an unknown policy counts as `do_not_share`, as for replies). [model] `run_task(draft_content)` on the queued run. [T3] lock the draft and re-check that it is still a `draft` at that version (an edit made meanwhile is a new version: the generation is **discarded**, the owner's text is never overwritten, the run is marked `discarded` in its snapshot, audit `content.generated` with `result: discarded`); **render** again against today's facts (`caption_template` / each overlay suggestion through `render`; a placeholder that cannot be rendered fails the whole generation with that error code, nothing half-grounded is saved); append the hashtags (code, letters only, at most 10); run the **claim validation** over the rendered texts (issues are stored inline, not a hard stop, because a human will review; every commercial claim of the model that no *rendered* fact backs adds a `CLAIM_UNBACKED` issue); store caption (feed) or overlay suggestions (story: no caption), `visual_notes` (if the owner has not written any), the title (if the owner has not renamed it), `validation`, and replace `fact_references` with the rendered facts plus every value that equals a verified fact; the save is the `edit` transition (`version + 1`, `content.updated`) and audit `content.generated` (`result: applied`). An LLM failure leaves the draft exactly as it was (a manual draft): the run is `failed` with the error code (`LLM_UNAVAILABLE` once the retries are used up, `LLM_REFUSED`, `LLM_OUTPUT_INVALID`, `LLM_BUDGET_EXCEEDED`) and the item's `generation` says so. A job replayed after a crash between the model and T3 stores the run's saved output without a second call.
2. **Edit** (sync): any payload change (caption, overlay suggestions, media) increments `version`, re-validates and replaces `fact_references` (references come from values that equal a verified fact; claim issues stay visible and block submission). **Resubmitting a refused or failed post (Q4):** on a `rejected` or `failed` item *any* change, a title or a note only included, counts as the edit (version + 1, back to `draft`), because the old version's approval, job and operation are spent and the next submission needs new ones; on other statuses a title or a note is saved in place. If the status was `pending_approval`/`scheduled`/`on_hold`/`rejected`/`failed` → `draft`, cancel a pending approval (`SUBJECT_EDITED`; an approval that was already `approved` stays so but is bound to the old version and is rejected as stale, INV-16) and cancel the queued publish job of the old version. `published` → `409`. Audit `content.updated`.
3. **Upload media** (sync): `POST /media` (multipart) → validate, convert and store ([ADR-015](decisions/ADR-015-media-storage.md)) → `media_assets(ready)`. Attach via edit.
4. **Submit** (sync) [T]: `POST /content-items/{id}/submit {schedule: {local_date, local_time} | "now", expected_version, self_approve: bool}`. Only a `draft` can be submitted (`CONFLICT_STATE` otherwise); `self_approve` without `content.approve` is `403` before anything is checked.
   1. **Validate everything** (`content/validation.py`, pure; every blocking item is listed at once). Failures → 422 `CONTENT_VALIDATION_FAILED` whose `errors` are the item codes of [observability.md §4.2](observability.md) (G17); the item stays `draft` and nothing is written. Warnings never block and are stored in `validation.warnings` of a submitted item.
      - *Media and text:* a story and a feed post both need a `ready` image (`CONTENT_MEDIA_REQUIRED`, `MEDIA_NOT_READY`); a feed image's ratio is 4:5 to 1.91:1 (`ASPECT_RATIO_OUT_OF_RANGE`; a story that is not about 9:16 only warns, `STORY_ASPECT_NOT_9_16`); a feed post needs a caption of at most 2200 characters (`CAPTION_REQUIRED`, `CAPTION_TOO_LONG`); a story is published **without** a caption (`CAPTION_NOT_ALLOWED`), and an overlay suggestion longer than 3 lines of 40 characters only warns (`OVERLAY_TOO_LONG`).
      - *Claims (INV-02):* the claim validator runs over the caption **and** every overlay suggestion, as plain text (a stored text has no rendered spans). A value that is the **current display of a verified, usable fact** (a whole-token match, case- and diacritic-insensitive: `500 ₺` is not in `6.500 ₺`) is **grounded**: it carries that fact's `fact_key` and `matches_verified`, is recorded in `fact_references`, and does not block, whether it came from a `{{fact:key}}` at generation or was typed by a person. Every other issue is `CLAIM_VALIDATION_FAILED` with the blocking issues: a value that matches no verified fact (invented, rounded, or the **old** price after a change), a model claim no fact backs (`CLAIM_UNBACKED`), and a `{{fact:key}}` still in the text (nothing renders on edit; it would be published as it stands: `PLACEHOLDER_UNRENDERED`). A discount word (`ücretsiz`, `free`, ...) is grounded only the way the validator grounds it in rendered text: the text must hold the whole display of a verified `promotion.*` fact. Submit and re-approval replace the item's `fact_references` with the facts the text states at that moment. See the limitation at the end of this section.
      - *Schedule (G13):* the local date and time are converted with the workspace timezone (`zoneinfo`) and must be within `now - 1 min <= t <= now + 60 days` (`SCHEDULE_IN_PAST`, `SCHEDULE_TOO_FAR`). A local time that does not exist (the hour skipped when clocks go forward) is `SCHEDULE_TIME_NONEXISTENT`; one that exists twice (the hour repeated when clocks go back) is the **earlier** instant, kept in `schedule_input.ambiguous` and shown back in `schedule_local`. `"now"` is the current instant. When the item will wait for an approver (everyone who does not `self_approve`, so always staff) the instant must also be at least 15 minutes ahead (`SCHEDULE_TOO_SOON_FOR_APPROVAL`): **nobody without the permission can publish now**.
      - *Account and capability:* submit **sets** `social_account_id`; the item has no other way to get one (create and patch do not accept it). It is the workspace's one active (non-disconnected) account, and it must be `connected` (`ACCOUNT_NOT_CONNECTED`) and hold `publish_feed_image` / `publish_story_image` for the type (`CAPABILITY_MISSING`).
      - *Quota forecast:* no rolling 24 h window around `t` may hold more than `PUBLISH_DAILY_LIMIT` posts (`PUBLISH_QUOTA_FORECAST_EXCEEDED`). The window counts the account's other items that are `scheduled`, `publishing` or `retry_scheduled` (by `scheduled_at`) and `published` ones (by `published_at`); items waiting for approval are not counted, because they are not committed to go out. A post leaves the window exactly 24 h after its time, like the mock's quota.
   2. **Payload** = `{content_id, version, content_type, social_account_id, caption, overlay_text, media_asset_id, media_sha256, scheduled_at}` (`content/payload.py`, hashed by `core.canonical`, so key order never matters). `overlay_text` is the list of overlay suggestions (G5): it binds what the approver saw, although a story publishes no text. A re-approval binds version + 1.
   3. `self_approve && has content.approve` → `record_policy_grant(self_approved=True)`: the approval is created and decided in the same transaction → `scheduled`. Else → `approvals.request(authorization, content.publish, required content.approve)` → `pending_approval`; it expires at `scheduled_at` and notifies the approvers (`approval.requested`). An approver who does not set `self_approve` takes this path too.
   4. On `scheduled`: set `scheduled_at`, `schedule_input`, `social_account_id` and `is_simulated` (from the account). `execute_before = scheduled_at + publish_max_delay_minutes` (G16: the workspace setting, default 1440 = 24 h, range 1 to 1440) is stored on the **approval** (`approvals.execute_before`, which `assert_executable` enforces), and the executor reads it there. Enqueue `publish_content(content_id, version)` with `run_at = scheduled_at`, `dedup_key = publish:{content_id}:v{version}`. Audit `content.scheduled` (self-approved) or `content.submitted` (pending), plus the approval's own entries.
5. **Approve later** (workflow D callback, `content/subject.py`, in the same transaction as the decision): the item must still be `pending_approval` at the approval's version, and the payload recomputed from the item must hash to the approval's `payload_hash`; otherwise `409 APPROVAL_STALE` and the approval stays pending. Approve → `pending_approval → scheduled` + enqueue as above. Reject → `rejected` with the decider's note. Expire → `draft (APPROVAL_EXPIRED)` with `scheduled_at` cleared (the owner picks a new time); the requester is notified by the approvals service (`approval.expired`), not by the callback.
6. **Execute** (job `publish_content` at `run_at`) — `operations.execute_publish(content_id, version)`:
   1. [T1] Lock the item. If the status is not `scheduled`/`retry_scheduled` or the version differs → no-op (job succeeds). Due-time checks ([state-machines.md §5](state-machines.md)); account unavailable → `on_hold (ACCOUNT_UNAVAILABLE)` + notify, stop. `now > execute_before` → `failed (PUBLISH_DEADLINE_PASSED)` (the state table has no `scheduled → failed`: the executor first takes the item `scheduled → publishing` inside T1 and then `publishing → failed`; nothing else may fail a `scheduled` item). Quota check (G8): `get_publishing_quota` is read **before** T1, with no transaction open (inside T1 it would hold the item lock during an external call); T1 then locks and re-checks everything that is in the database. Exhausted (`used >= limit`) → `retry_scheduled` (`scheduled → publishing → retry_scheduled` inside T1, the table has no direct edge) at the instant the oldest post that has to leave the window does (24 h after it was published; `PublishingQuota` carries no timestamps, so the times come from the account's `published` items, or now + 1 h if they do not cover the count) when that is before `execute_before`, otherwise `failed (PUBLISH_DEADLINE_PASSED)`. The operation goes to `retry_wait` (attempts untouched, `next_attempt_at` set) and the job is rescheduled to that instant without spending an attempt. An unreadable quota is ignored: the provider enforces it at publish time (`ProviderRateLimited`, retried as in step 6). The due-time checks run in this order: workspace active, `execute_before` (a past deadline is `failed` whatever the account state), the approval (`assert_executable`, payload hash), account `connected` with the capability for the type, media `ready`. Get or create `operations(publish:{id}:v{version})`; if `succeeded` → repair to `published` and exit. Set operation `in_progress`, item `publishing`. Commit.
   2. If there is no `provider_ref.container_id`: `create_media_container(spec with public_fetch_url(media, ttl))` → [T2] save `container_id`, commit.
   3. Poll `get_container_status` (every 10 s, up to 5 min, measured with the injected `Clock` and waited with an injected sleeper, `heartbeat()` after each wait, no transaction open; after 5 min the operation becomes `outcome_unknown` and `reconcile_publish` is enqueued at +1 min): `IN_PROGRESS` → keep waiting; `ERROR` → permanent failure `MEDIA_REJECTED`; `EXPIRED` → clear `container_id` and go to step 2; `PUBLISHED` → step 5 (already published, reconcile); `FINISHED` → step 4.
   4. `publish_container(container_id)` → `media_id`. `ProviderOutcomeUnknown` → operation `outcome_unknown`, enqueue `reconcile_publish` (+1 min) which re-reads the container status (`PUBLISHED` → step 5; `FINISHED` → retry step 4; else per step 3).
   5. `get_media(media_id)` for the permalink (best effort; a read **before** T3, never inside it; after a reconciliation the media id comes from `ContainerStatus.media_id`). [T3] Operation `succeeded`. Item `published` (`published_at`, `external_media_id`, `external_permalink`). Notification `content.published`. Audit `content.published`.
   6. Errors (a `ProviderOutcomeUnknown` or an unexpected error from `create_media_container` / `get_container_status` has had no visible effect and is retried like a transient one; the same from `publish_container`, or its `CONTAINER_PUBLISHED` / `CONTAINER_NOT_READY` / `CONTAINER_EXPIRED` answers, is an unknown outcome): retryable (`ProviderTransientError`, `ProviderRateLimited`) → operation `retry_wait`, item `retry_scheduled`, job re-enqueued at backoff (1, 5, 15, 30 min; `retry_after` respected) while `< execute_before` and attempts < 5. Otherwise → `failed` + notification `content.failed`. Permanent (`ProviderInvalidRequest`, `MEDIA_REJECTED`, `ProviderPermissionError`) → `failed` immediately. Auth → workflow G: `health.handle_auth_error`, the operation `failed ACCOUNT_NEEDS_REAUTH`, the item `publishing → on_hold (ACCOUNT_UNAVAILABLE)` + `content.on_hold`. A permission error clears the account's `publish_<type>` capability and fails with `CAPABILITY_MISSING`. The retry delay is `max(backoff[attempt], Retry-After)`; the item fails instead when `now + delay >= execute_before` or the 5th attempt failed, and `content.failed` carries the code. The executor refuses by the item's status and version, so an approval that stays `approved` after a cancel or an edit cannot publish anything.
7. **Cancel** (sync, `POST /content-items/{id}/cancel`; any member may call it, the service decides): owners and managers (`content.approve`) may cancel any item in a cancellable status. A user **without** `content.approve` may cancel only **their own pending submission**: the item is `pending_approval` and they created it (`created_by_user_id`) or submitted it (they are the requester of its current approval); anything else, including their own `draft` or `scheduled` item and other people's items, is `403 FORBIDDEN` (a foreign workspace's id stays `404`). The item response carries `can_cancel` (the viewer may cancel it now) so the UI shows the button only then. Allowed from `scheduled`, `retry_scheduled`, `on_hold`, `pending_approval`, `draft` → `cancelled`. Cancel the pending approval (`SUBJECT_CANCELLED`) and the queued job (`cancelled`). A `pending`/`retry_wait` operation → `cancelled` through the ledger hook (`content/hooks.py`). `publishing` (and `published`, `failed`, `rejected`, `cancelled`) → 409 `CONFLICT_STATE`, before anything is touched. An approval that was already `approved` stays so; the executor refuses by the item's status.
7a. **Re-approve** (sync, `POST /content-items/{id}/reapprove {schedule, expected_version}`, `content.approve`; G2): `on_hold` items only. The content is unchanged but **the version increases**, because the schedule is part of the approval payload: a new approval (recorded as decided, bound to version + 1), a new job and operation key `publish:{id}:v{n+1}`; the old ones can never fire. Everything of step 4.1 runs again, so a caption that still shows an old price fails and has to be edited first (which makes the item a draft that is submitted again).
8. **Fact change impact**: workflow B step 3.4.

| Aspect | Contract |
|---|---|
| State transitions | [state-machines.md §5–6](state-machines.md). |
| Persistence | `content_items`, `media_assets`, `fact_references`, `approvals`, `operations`, `jobs`, `agent_runs`, `notifications`, `audit_logs`; simulator: `sim_containers`, `sim_published_media`. |
| External side effects | `create_media_container` (no visible effect on Instagram) and `publish_container` (visible). At most one publish per container; at most one container in flight per operation. |
| Limitations | *Typed verified values (decided in P5-03a).* The stored caption is plain text (G6), so the claim validator has no rendered spans for it. Instead of spans, a value counts as grounded when it whole-token matches the **current** display of a verified fact (the matcher an owner's own reply uses, made strict): a generated caption that states the membership price, or a typed price equal to it, submits and is held by a later price change. The match is on the value, not on its meaning: `07:00` typed for Saturday is grounded if it appears in the verified hours. An edit still does not render `{{fact:key}}` (a placeholder left in the text is `PLACEHOLDER_UNRENDERED`). |
| Failure paths | As in step 6.6. Restart during any step → lease expires → job re-runs → ledger + container state make it safe. Approval expired before the due time → `draft (APPROVAL_EXPIRED)`. Deadline passed → `failed`. |
| Idempotency | Job dedup key per version; ledger key per version; container ID committed before the publish call; status reconciliation before any repeat; simulator enforces `unique(container_id)` on published media. |
| Acceptance tests | AC-D1…D8, AC-F1…F7, AC-C4. |

---

## F. Daily report

**Goal:** Deterministic aggregation of persisted records into a localised summary.

| Aspect | Contract |
|---|---|
| Trigger | (a) Scheduler at the workspace's `daily_report_hour` (setting, default 20:00) workspace-local time: job `generate_daily_report(workspace_id, local_date)` with `dedup_key=daily_report:{ws}:{date}`, one per workspace and local day. (b) On demand: `POST /reports/daily/generate {date}` (regenerate, overwrites) or `GET /reports/daily?date=` (H3 below). (c) Command `query.activity_summary`. |
| Preconditions | None. |
| Inputs | Workspace ID, local date (default today), timezone. |
| Permissions | `reports.view` (owner, manager; staff sees inbox-related metrics only). |

**Main steps**
1. Compute the period: `[local_date 00:00, local_date+1 00:00)` in the workspace timezone → UTC `period_start`, `period_end`. For "today" queries, `period_end = now`.
2. Run the metric queries below (pure SQL, read-only transaction).
3. Build `metrics` JSON + `has_simulated_data` (any contributing row simulated).
4. Upsert `daily_reports`. Notification `report.daily_ready` (scheduled runs only). Audit `report.generated`.
5. Render (on read): localised templated summary from backend catalogs. Sections with zero values are omitted. Every metric includes a `link` (the drill-down list `GET /reports/daily/{date}/metrics/{key}`) whose result count equals the metric (AC-E3).

**Today and stored days (H3).** `GET` computes **today** live (`period_end = now`, `is_partial`) and never stores it. A **past** day is the stored row if there is one, else it is computed, stored and returned; a later read returns that stored row unchanged (the records are the source, so `POST …/generate` recomputes it on request). The scheduled run for today stores what it sees at the run time (a 20:00 run is partial), announces it with `report.daily_ready` (info, every `reports.view` holder, dedup `report:{local_date}`, `is_simulated` from the report) and audits `report.generated` (workspace-level, resource `daily_report`, metadata `local_date`, `scheduled`, `definitions_version`, `is_partial`). Snapshot (`*_now`) metrics are as of the generation and are not recomputed when a stored day is read.

**Summary text (H4).** Sections Mesajlar, Onaylar, İçerik, Bilgi değişiklikleri, Sorunlar (`report.section.*`), each with one line per non-zero metric (`report.summary.<section>.<metric>`, a label and the number, so there is no plural form to get wrong). A section whose values are all zero or `null` is omitted; with nothing left the text is `report.summary.empty`. Rendered in the reader's UI language, from the stored numbers only (INV-08).

### F.1 Metric definitions (`definitions_version = "1"`)

| Key | Definition | Kind |
|---|---|---|
| `inbound_messages` | `messages` with `direction=inbound`, `is_deleted=false`, `provider_timestamp` in period | period |
| `conversations_with_inbound` | distinct `conversation_id` of the above | period |
| `new_conversations` | `conversations.created_at` in period | period |
| `replies_sent` | `messages` with `direction=outbound`, `sender_kind=business_app`, `provider_timestamp` in period | period |
| `replies_sent_auto` | subset of `replies_sent` whose `reply_drafts.decision = auto` | period |
| `replies_sent_approved` | subset whose draft `source ∈ {ai, approved_answer}` and decision `approval_required` | period |
| `replies_sent_by_owner` | subset whose draft `source = owner` | period |
| `native_replies` | `messages` with `sender_kind=business_native` in period | period |
| `escalations` | `reply_drafts` created in period with `decision = human_required` | period |
| `missed_conversations` | conversations whose window (`last_inbound_at + 24 h`) ended in the period with no outbound message after `last_inbound_at` | period |
| `median_first_response_minutes` | for each inbound burst in the period that received an outbound reply: minutes from the first unanswered inbound to the next outbound; median; null if none | period |
| `attention_now` | conversations with `attention ∈ {needs_human, needs_approval, failed}` | snapshot at generation |
| `unanswered_open_now` | conversations whose latest message is inbound and whose window is still open | snapshot |
| `pending_approvals_now` | `approvals` with `status=pending`, grouped by `action` | snapshot |
| `content_published` | `content_items.published_at` in period | period |
| `content_failed` | audit `content.failed` events in period (distinct content) | period |
| `content_scheduled_next_24h` | `status=scheduled` and `scheduled_at` in `[now, now+24h)` | snapshot |
| `content_on_hold_now` | `status=on_hold` | snapshot |
| `fact_changes` | audit `fact.updated` + `fact.verified` + `fact.archived` in period | period |
| `integration_errors` | operations that became `failed` in period + `inbound_events.status=failed` in period + account transitions to `needs_reauth`/`degraded` in period | period |

**Row-set rule (H1).** Every metric is defined once, in `reporting/definitions.py`, as a SQL **row set** over persisted records, and its value is computed from that set: the count of its rows (for `median_first_response_minutes` the median of the rows' `measure`). The drill-down list behind a number (`GET /reports/daily/{date}/metrics/{key}`) runs the same row set, so the count of its rows equals the number by construction (AC-E3). Every row set has the same seven columns: `subject_type`, `subject_id`, `occurred_at`, `is_simulated`, `link_id` (the record a link opens: the conversation for a message or draft, the content item, the approval), `measure` (minutes, median metric only) and `group_key` (the approval action, `pending_approvals_now` only, which also carries a `breakdown` per action). `has_simulated_data` is true when any row of any metric is simulated.

**Inbox keys (H2).** Staff (`reports.view_inbox_metrics`) see only: `inbound_messages`, `conversations_with_inbound`, `new_conversations`, `replies_sent`, `replies_sent_auto`, `replies_sent_approved`, `replies_sent_by_owner`, `native_replies`, `escalations`, `missed_conversations`, `median_first_response_minutes`, `attention_now`, `unanswered_open_now`. The other keys are dropped from their report and their drill-down is `403`.

**Details the table leaves open (decided in P6-01).**
- A period is `[start, end)`: a record stamped exactly at `end` belongs to the next period. For a live "today" (`end = now`) this means a record stamped at the same instant as `now` is not yet counted.
- `replies_sent_auto`, `replies_sent_approved` and `replies_sent_by_owner` join the message to its `reply_drafts` row through `messages.reply_draft_id`. A reply without a draft is in `replies_sent` only. The three subsets do not overlap.
- `missed_conversations` treats any outbound message after `last_inbound_at` as a reply, including one written in the Instagram app.
- `median_first_response_minutes`: a **burst** is a run of customer messages with no outbound message between them (deleted inbound messages are ignored; messages are ordered by `(provider_timestamp, id)`). It is **in the period** when its first message is. It counts only when it is **answered inside the period**: the next outbound message of the conversation, of any sender kind, is before `period_end`. The response time is the minutes from the burst's first message to that outbound message. The median of these is rounded to one decimal; with no answered burst it is `null`. A report for a day therefore does not change when it is generated later.
- `unanswered_open_now` uses the same test as the conversation attention logic: the last inbound message is newer than the last outbound one, and `last_inbound_at + 24 h` is after `now`.
- `content_failed` counts distinct content items, so an item that failed twice counts once. `fact_changes` counts audit entries, so an update followed by a verification counts twice.
- `integration_errors` counts a failed inbound event at `coalesce(processed_at, received_at)` and a failed operation at `completed_at`.

| Aspect | Contract |
|---|---|
| Persistence | `daily_reports`, `notifications`, `audit_logs`. |
| External side effects | None. |
| Failure paths | Query error → job retry. A report never contains estimated or model-generated numbers ([INV-08](../invariants.md)). |
| Idempotency | Upsert by `(workspace_id, local_date)`. Job dedup key. |
| Acceptance tests | AC-E1…E5. |

---

## G. Integration failure

**Goal:** Provider outage, invalid credentials, rate limiting, or webhook errors lead to retry or reauthorisation, with observability and user notification.

| Aspect | Contract |
|---|---|
| Trigger | A typed provider error raised in an executor, a token refresh failure, a webhook signature failure, or a health check failure. |
| Preconditions | — |
| Permissions | Reconnect: `integrations.manage` (owner). |

### G.1 Error mapping

| Provider error (adapter) | App error code | Retry? | Account effect | Subject effect | User notification |
|---|---|---|---|---|---|
| `ProviderTransientError` (5xx before acceptance, connection error) | `PROVIDER_UNAVAILABLE` | yes, backoff, within deadline | `consecutive_failures += 1`; ≥ 5 within 10 min → `degraded` (`degraded_until = now + 10 min`) | `retry_wait` / `retry_scheduled` | Only when it becomes `failed`, or the account becomes `degraded` |
| `ProviderRateLimited(retry_after)` | `PROVIDER_RATE_LIMITED` | yes, after `max(retry_after, backoff)` | none (not a health failure) | `retry_wait` | If deadline exceeded → `failed` |
| `ProviderAuthError` (token invalid, expired, revoked) | `ACCOUNT_NEEDS_REAUTH` | no | → `needs_reauth` | send: stays `queued` until the window closes; publish: `on_hold (ACCOUNT_UNAVAILABLE)` | `account.needs_reauth` (critical) + Home banner |
| `ProviderPermissionError` (scope missing) | `CAPABILITY_MISSING` | no | capability flag false | `failed` | `account.permission_missing` |
| `ProviderWindowClosed` | `MESSAGING_WINDOW_CLOSED` | no | none | draft `expired` | conversation attention `failed` |
| `ProviderInvalidRequest` (validation) | `PROVIDER_REJECTED` / `MEDIA_REJECTED` | no | none | `failed` | `content.failed` / `reply.failed` |
| `ProviderOutcomeUnknown` | `OUTCOME_UNKNOWN` | reconcile, not resend | none | `outcome_unknown` → resolved | Only if resolution = `OUTCOME_UNCONFIRMED` |

Any success resets `consecutive_failures` to 0.

### G.2 Flows
1. **Token refresh** (job `refresh_tokens`, daily, per `meta` account): if `token_refreshed_at < now − 24 h` and `token_expires_at < now + 20 days` → operation `refresh_token:{account}:{date}` → `refresh_token()` → store the new ciphertext and expiry. Auth error → `needs_reauth`. A token that expired without refresh → `needs_reauth` at the next use or scan.
2. **Reauthorisation**: the owner presses "Reconnect" → OAuth (Phase 7) → callback verifies the **same** `external_account_id` → token stored → `connected` → audit `account.reconnected` → enqueue `resume_account(account_id)`. That job re-enqueues `send_reply` for `queued` drafts still in their window, or expedites the queued job (`queue.expedite`). Phase 5 builds this for the mock provider (`POST /social-accounts/{id}/reconnect`, `operations/accounts.reconnect_mock`); the OAuth callback joins it in Phase 7. It does **not** auto-resume `on_hold` content: the owner re-approves, because the schedule may have passed.
3. **Degraded / circuit**: while `degraded_until > now`, executors do not call the provider. They reschedule after `degraded_until`. Job `account_health_check` (every 5 min for degraded accounts) calls `get_account_profile()`; success → `connected` and audit; failure → extend.
4. **Webhook problems**: invalid signature → 401 + system audit + counter (a "System health" panel shows the count over 24 h; ≥ 10 per hour logs an `ERROR`). Processing failure (bug, unexpected shape) → event `failed` with `error_code`, job dead after 3 attempts, visible in system health. Re-processing is possible via a dev/admin action.
5. **Missing webhooks** (cannot be detected directly): Phase 7 adds an optional periodic `poll_conversations` (Conversations API, rate-limited at 2 calls/s) for accounts with no events in 24 h. Deferred in S1.
6. **LLM provider outage**: tasks fail → work routed to humans (`LLM_UNAVAILABLE`). Account health is unaffected. System health shows the agent run failure rate.

| Aspect | Contract |
|---|---|
| Persistence | `social_accounts` status and counters, `operations`, subject tables, `notifications`, `audit_logs` (`social_account.needs_reauth` / `social_account.degraded`, `operation.failed`). |
| External side effects | Refresh calls and health checks (read-only). |
| Idempotency | Refresh operation key per day. Notifications deduped per account and status (`account:{id}:{status}`). |
| Acceptance tests | AC-G1…G5, AC-F2, AC-F6. |
