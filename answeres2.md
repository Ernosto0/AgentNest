# Pilot Questions and Owner Answers

Date: 2026-11-19

This file records the owner's answers after reviewing Feature Phases 1–5. These are product decisions and pilot requirements; they do not establish that every requirement is implemented or live-verified.

## Context already confirmed

- Next step: a small assisted pilot with businesses.
- The owner confirmed that the prerequisites are ready and the app is live on Railway. This is owner-reported readiness; deployment and live acceptance were not independently verified during the review.

## 1. First businesses

**Question:** Which business types will participate, how many businesses, and when do you want to start?

**Answer:** Small local businesses in my area. The target is 10–15 businesses within a week.

## 2. Owner notifications

**Question:** Will the first owners use Web Push, Telegram, or WhatsApp? Which is the primary channel for day one?

**Initial answer:** Yes.

**Owner's clarification:** We want Telegram delivery. Users should be able to choose freely between Telegram, WhatsApp, or the app. Telegram is the most important channel for day one.

## 3. Assistant mode

**Question:** Will pilots use the Account Agent or the legacy reply flow?

**Answer:** They will use the Account Agent.

## 4. Languages

**Question:** Which languages do the first businesses need: Turkish/English only, or also Russian, German, and Arabic?

**Answer:** The app UI needs English and Turkish only. The Agent's customer-facing language support must also include Russian, German, Arabic, and other languages as needed.

**Still to define:** The additional languages covered by “other languages.” This answer does not restrict the Agent to Turkish and English.

## 5. Approval and automation policy

**Question:** Should every outgoing reply require approval initially, with follow-ups disabled?

**Answer:** No. We want semi-automation: full automation for basic questions and approval for more complex questions.

**Still to define:** The exact topics that qualify as basic versus complex. The answer does not separately specify whether follow-ups should be enabled.

## 6. Pilot terms and pricing

**Question:** Will the pilot be free or paid, for how long, and what pricing applies afterward?

**Answer:** Use the existing pricing document. The first local businesses will have a free first week or month.

**Pricing reference:** [Pricing Strategy and Unit Economics](docs/product/pricing-and-unit-economics.md), section 3.1, Assisted Pilot Programme.

The existing document records:

- A 30-day free assisted pilot for the first 10–15 businesses, with no credit card required.
- A founder package afterward at **990 TRY per month + KDV**, with the price locked for 12 months.
- Standard Türkiye monthly tiers in section 3.2: Starter **1,490 TRY**, Growth **2,490 TRY**, and Pro **4,490 TRY**.
- Assisted-pilot billing handled manually, as described in section 6.

These amounts are transcribed from the existing pricing document, not newly selected prices.

**Still to confirm:** Whether the free pilot lasts one week or one month. The existing document specifies 30 days; the latest answer leaves both options open.

## 7. Essential day-one features

**Question:** Which features must work on day one: DMs, publishing, comments, voice notes, bookings, or lead lists?

**Answer:** All of them.

All six listed areas are required for the pilot. They need to work with the selected Account Agent mode.

## 8. Pilot success

**Question:** What would make the pilot successful: faster replies, less owner work, more appointments, or another measurable outcome?

**Answer:** Everything.

Success should cover all the listed outcomes: faster replies, less owner work, and more appointments, together with the required features working reliably.

**Still to define:** Numeric targets and the period over which success will be measured.

## Confirmed priorities

1. Prepare an assisted pilot for 10–15 local businesses within a week.
2. Use the Account Agent.
3. Prioritize Telegram notification and approval delivery for day one, while preserving user choice of Telegram, WhatsApp, or the app.
4. Keep the app UI in Turkish and English; support customer replies in Russian, German, Arabic, and further languages as defined.
5. Automatically answer basic questions and require approval for complex questions.
6. Include DMs, publishing, comments, voice notes, bookings, and lead lists in pilot acceptance.
7. Use the existing pricing document, with the free-pilot duration still to be settled.

## Implementation implications from the review

These are follow-up requirements, not completed changes:

- Resolve and verify Telegram notification dispatch and approval delivery end to end.
- Close the Account Agent's documented language and voice/image coverage gaps for the required pilot journeys.
- Verify the required features using the Account Agent, since the existing practice chat uses the legacy reply pipeline.
- Define the basic-question automation topics and complex-question approval rules explicitly.
- Verify booking-related lead-list coverage on the Account Agent path; the review identified a gap for booking-only agent conversations.
- Record live acceptance results and update historical summary statements that still describe committed work as uncommitted.

---

# Implementation Plan: Account Agent Pilot Readiness

**Status:** Implemented across Sessions 00–10; offline verification passed; live verification cataloged and pending owner live probe execution.

**Source of scope:** The owner's answers above. The pilot must use the Account Agent, provide semi-automation, prioritize Telegram, support five customer reply languages, and cover every requested feature.

**Delivery target:** Prepare for 10–15 local businesses within a week. This is the owner's target, not an engineering completion estimate. Sessions below are ordered units of work, not days. If required acceptance fails, report the gap rather than silently removing a requested feature or calling the pilot ready.

## A. Current code evidence

Reviewed against local commit `e1c9f13` on 2026-11-19. Re-check the baseline at execution time. No fresh test run or production verification was performed while writing this plan.

| Area | Observed starting point | Required result |
|---|---|---|
| Telegram delivery | `backend/app/notifications/service.py` dispatches Web Push and WhatsApp, but has no Telegram dispatch call. The Telegram adapter and delivery ledger already exist. | Real notifications reach eligible linked Telegram recipients through the existing ledger and worker. |
| Channel selection | `frontend/src/features/settings/Channels.tsx` supports linking Telegram and WhatsApp. Linking alone does not establish a complete per-channel notification preference contract. | Owners can choose their external channels or app-only delivery and see their actual delivery status. |
| Agent languages | `agent/context.py` filters to `tr`/`en`; `agent/grounding.py::ReplyValidationArgs` accepts only those languages; `agent/knowledge.py::answers_page` rejects others. | Agent replies, grounding, approved answers and server-written replies support `tr`, `en`, `ru`, `de`, `ar`. |
| Semi-automation | `agent/delegation.py` grants actions such as `dm.send` using `automatic`, `ask`, or `off`. Legacy topic policies are a separate authority system. | Basic versus complex reply handling is enforced on the Account Agent path without broadening the owner's action grant. |
| Voice and images | `agent/context.py` represents attachments without their transcript/description. `inbox/transcription.py::wake_drafting` returns early for agent-controlled accounts. `agent/dm.py` already forces human approval when recent transcripts are present. | Completed media processing wakes the agent safely; customer media becomes usable, labelled context with the existing approval protections. |
| Booking and leads | Agent calendar actions exist. `reporting/leads.py` qualifies agent leads through pricing facts, leaving booking-only agent enquiries uncovered. | Booking enquiries are recorded as enquiries; only evidenced appointments count as conversions. |
| Practice chat | `inbox/sandbox.py` uses legacy `DraftContext`/`DraftPlan` logic and isolated test-turn storage. | The practice experience truthfully represents the selected controller while preserving isolation. |
| Commercial setup | Pricing section 3.1 specifies 30 free days and the 990 TRY founder offer; the owner has not settled one week versus one month. Plan CLI commands exist; billing is manual. | Assisted onboarding records the agreed trial and package without inventing billing enforcement. |

## B. Decisions and working assumptions

Keep these separate from confirmed owner answers. Implementation can proceed on independent fixes while these choices remain open.

| Item | Proposed working approach | When it must be settled |
|---|---|---|
| Basic versus complex | Use the proposed policy matrix in Session 03. Treat ambiguous or mixed requests as requiring approval. | Before enabling automatic replies for a pilot workspace. |
| Free period | Make the onboarding record accept either 7 or 30 days. Keep the existing documented 30-day offer as a reference, not a newly confirmed decision. | Before communicating the offer to the first business. |
| Further Agent languages | Deliver the named five languages first. Keep a central supported-language registry; unsupported or uncertain languages go to a person. | Name any additional language before promising support for it. |
| Success targets | Record baseline and pilot measurements for response time, owner effort and linked appointments. Leave numeric business targets explicitly unset. | Agree targets and review period before evaluating pilot success. |
| Follow-ups | Preserve the existing opt-in setting and approval requirement. The owner's semi-automation answer does not authorize automatic follow-ups. | Before enabling follow-ups on an agent account or changing their policy. |
| Channel selection | In-app notifications remain available. External channels are explicit opt-ins, with support for selecting more than one. Show app-only as a valid choice. | Finalize the UX contract in Session 02; do not silently subscribe existing users to a newly added channel. |

## C. Execution rules

1. Read `CLAUDE.md`, `docs/invariants.md`, relevant architecture contracts and the previous session report before each session. Preserve unrelated work and the owner answers above.
2. Reuse the existing agent broker, delegation, approvals, notification delivery ledger, jobs and operations executors. Do not introduce a second authority system or a parallel send path.
3. Keep UI and owner-channel interface text in Turkish and English. Customer-facing replies have their own language setting.
4. Preserve workspace isolation, public/private context boundaries, current membership checks, source verification, payload-bound approval, injected time and provider constraints.
5. External notification sends use the existing delivery worker. Customer messages, calendar mutations and publications use their existing operation executors. Do not perform network calls inside database transactions.
6. Keep ambiguous effects under reconciliation; retries, worker recovery and repeated approval clicks must not duplicate customer sends, bookings or publications.
7. Any schema or authority change needs the matching contract/ADR update before its implementation. Inspect the current migration head; do not assume migration numbers are still available.
8. Keep ordinary tests offline. Live checks need controlled destinations and explicit authorization for the messages or publications involved. Planning this work does not itself send messages, deploy changes or change production configuration.
9. Write session reports under `docs/implementation/account-agent-pilot-readiness/sNN-report.md` when implementation begins. Record actual checks, remaining failures, migrations and evidence; do not prefill successful results.

## D. Ordered implementation sessions

### Session 00 — Establish the current baseline and acceptance inventory

**Work**

- Confirm Git status/commit, current migration head, actual agent controller settings and existing test commands. Check current CI evidence if available.
- Map each requirement to existing code and tests. Separate missing implementation, regression fixes, configuration work and unrecorded live evidence.
- Record deployment/version evidence read-only when access is available. Treat the owner's ready infrastructure as the starting context; do not redeploy merely to inventory it.
- Inventory live acceptance already completed by the owner so successful work is not repeated without a reason.

**Acceptance:** A dated baseline and requirement-to-test checklist exist, with every unknown labelled. No inference that old per-track test results prove the combined current commit.

### Session 01 — Restore Telegram notification delivery

**Primary files:** `backend/app/notifications/service.py`, `catalog.py`, `delivery_ledger.py`, `jobs.py`; `backend/app/integrations/channels/telegram/adapter.py`. Add a small Telegram dispatch service beside the existing push and WhatsApp dispatch services if needed.

**Work**

- Resolve the active workspace/user Telegram link and enqueue eligible notifications through `dispatch_channel_notification` in the notification's transaction.
- Define the supported notification types explicitly: approvals, owner questions, failures, quota warnings and existing report-ready notifications where supported. Do not equate a report-ready alert with a new scheduled summary feature.
- Reuse quiet-hours rules and existing single-use action tokens. Preserve the in-app notification if external dispatch fails.
- Trace alternate Telegram send paths first, then prevent duplicate dispatch for the same notification, recipient and channel.
- Recheck link status and membership when the job runs. Confirm simulated notifications cannot leak into real owner channels.
- Inspect delivery ambiguity handling. A timeout after a possible Telegram send must not be treated as a proven failure and blindly resent; document the adapter's actual guarantees and recovery state.

**Acceptance:** Notification creation produces the expected delivery/job; the worker sends outside a transaction; unlinking, replay, quiet hours, invalid membership, duplicate jobs and uncertain outcomes behave correctly. Reply, content and calendar approvals show an informed description and decide the existing approval exactly once. Free text never approves.

**Verification:** Extend notification integration/isolation tests and existing Telegram adapter/action-token tests. Include the complete notification-created → queued → delivered → button-decided path.

### Session 02 — Make notification-channel choice explicit

**Primary files:** `frontend/src/features/settings/Channels.tsx`, settings hooks and tests; `backend/app/api/v1/channels_router.py`, `backend/app/identity/channels.py`, notification dispatch services and preference schemas.

**Work**

- Design and document one per-workspace/per-user channel preference contract, reusing existing link and push preferences where possible. Add a migration only for missing persisted state.
- Offer Telegram, WhatsApp and app-only; retain Web Push controls as a separate device opt-in. Show connected, unconfigured, disabled and delivery-failure states truthfully.
- Keep Telegram prominent in assisted onboarding without making it mandatory. Respect the owner's choice to use WhatsApp or just the app.
- Define migration behavior for existing links/preferences without unsolicited new subscriptions. Preferences must affect queued delivery as well as new dispatch.
- Retain WhatsApp's notification/button-only boundary, approved-template behavior and current quiet-hours policy. Do not add free-text Agent commands to WhatsApp.

**Acceptance:** An owner can select and change channels, use multiple opt-ins, or select app-only. Deselected/unlinked channels stop delivering. A failure in one channel does not remove the in-app alert or break another selected channel. Foreign-workspace and unauthorized preference changes are rejected.

### Session 03 — Define and implement basic-versus-complex Agent reply policy

**Primary files:** `backend/app/agent/delegation.py`, `dm.py`, `grounding.py`, comment handlers, send-time revalidation and the Agent delegation UI. Update `docs/architecture/account-agent-contracts.md` and relevant policy documentation.

**Proposed policy matrix — subject to owner confirmation before activation**

| Request/action | Proposed handling |
|---|---|
| Greeting; verified hours, location/contact, service descriptions | Automatic when the owner grants that action and all existing checks pass. |
| Standard verified price question | Automatic only when price disclosure is allowed and the requested price is verified and usable. |
| Mixed topics or unclear request; missing/stale/conflicting information | Clarify safely or require approval/owner input; never guess a business value. |
| Custom quote, exception, discount or negotiation | Owner approval/input. |
| Complaint, refund, legal/health-sensitive request, suspected injection | Preserve the applicable human-handoff or block rule; approval is not a way around a blocked action. |
| Voice-derived reply | Approval required under the existing transcript rule. |
| Booking, rescheduling, cancellation; content publication; destructive moderation | Retain the separately configured action authority; propose approval for pilot mutations rather than treating them as basic FAQ replies. |

**Work**

- Add the smallest versioned Agent policy extension needed to express the confirmed topic restrictions. Legacy `automation_policies` must not become an implicit Agent grant.
- A reply is automatic only when the action grant permits it AND the server admits the topic/evidence AND every existing safety check passes. A topic rule can restrict an action grant, never broaden it.
- Do not trust a model-provided `basic` or `safe` flag as authorization. Persist classification evidence and reason codes, validate against source messages/facts, and send unrecognized or conflicting classifications for human review.
- Apply the policy to relevant DM and comment reply paths. Public comments still respect price-disclosure and public/private visibility restrictions.
- Recheck current policy at approval decision and immediately before execution. Configuration changes invalidate unexecuted grants as required by the existing contracts.
- Make the owner-facing configuration show examples of what auto-sends and what needs approval, in both UI languages.

**Acceptance:** Basic verified questions auto-send with a valid grant; complex/mixed requests cannot auto-send merely because `dm.send` is automatic. Revocation, takeover, stale facts, quota exhaustion, closed windows and transcript approval floors still win. Unknown outcomes still reserve the response slot.

### Session 04 — Extend all Account Agent reply paths to five languages

**Primary files:** `backend/app/core/reply_languages.py`, `agent/context.py`, `agent/grounding.py`, `agent/knowledge.py`, `agent/calendar.py`, tool input schemas, relevant owner-answer/clarification renderers, and approved-answer editor controls.

**Work**

- Replace Agent-only `tr`/`en` restrictions with the shared supported reply-language contract for `tr`, `en`, `ru`, `de`, `ar`. Audit tool schemas and generated API types, not just the prompt.
- Use the existing detection, claim-validation and value-formatting support for the additional languages. Keep uncertain language detection on the human path.
- Localize server-written calendar outcomes, availability responses, clarification questions, owner-answer wrappers and automatic-reply notices. Do not silently send English booking confirmations to Arabic-speaking customers.
- Allow approved answers in each supported customer language. Keep UI labels in Turkish/English and define the existing fact-label fallback explicitly.
- Preserve Arabic RTL rendering, byte limits, source spans, verified fact versions and escalation/injection handling in all five languages.

**Acceptance:** Each language works through Agent context → tool schema → grounding → policy → approval/automatic grant → final send, including calendar and owner-answer variants. Unsupported languages do not become sendable by prompt alone. TR/EN UI coverage remains complete.

**Verification:** Extend `test_agent_language_failclosed.py`, grounding/calendar/approved-answer tests and language eval datasets. Add multilingual Agent journeys; real-model results are recorded later in Session 11.

### Session 05 — Make voice notes and image descriptions usable by the Agent

**Primary files:** `backend/app/inbox/transcription.py`, `image_description.py`, `backend/app/agent/context.py`, existing Agent event/wake handling, `grounding.py`, `dm.py`, and `backend/app/policy/transcripts.py`.

**Work**

- On completion/failure of media processing, emit the existing style of scoped durable Agent event and wake the correct thread in the same transaction. Do not also wake the legacy controller for that account.
- Include successful transcripts and relevant image descriptions as bounded, source-linked, untrusted customer context. Typed text accompanying an image must not cause the image context to be silently ignored.
- Handle pending, failed, deleted and erased media without stale replies, busy polling loops or duplicate actions. Respect takeover, pause, controller epoch and deletion generation.
- Preserve the transcript approval floor; do not relax it as part of semi-automation. Image descriptions cannot establish verified business prices, hours, inventory or other promises. Ambiguous visual interpretation goes to a person.
- Where clarification needs customer media evidence, extend the typed evidence contract explicitly; do not copy generated descriptions into verified facts or trust arbitrary source spans.
- Maintain retention/export/erasure behavior for derived text and avoid introducing stored raw media without an explicit retention design.

**Acceptance:** A voice-only enquiry yields a useful Agent draft that requires approval. A text-plus-photo enquiry uses the relevant description safely. Completion retries, customer replies during processing, deletion, takeover and worker restart cause no duplicate or stale customer effect.

**Verification:** Extend `test_dm_transcript.py`, transcript/image integration and erasure tests; add Agent wake/context tests and multilingual media journeys.

### Session 06 — Close booking and lead-list coverage gaps

**Primary files:** `backend/app/agent/calendar.py`, Agent enquiry/evidence storage, `backend/app/reporting/leads.py`, `leads_csv.py`, `leads_router.py`, relevant calendar services and lead-list UI.

**Work**

- Trace booking enquiry → availability → proposed booking → approval → verified calendar result → customer confirmation. Repair Account Agent integration failures rather than building a new booking subsystem.
- Record a scoped enquiry signal for Agent pricing/booking questions, including booking-only enquiries that never reach a `ReplyDraft`. Select the minimal persisted contract after inspecting existing event/action evidence; document any schema change and RLS.
- Treat enquiry classification as reporting evidence, never proof of a sale or appointment. Do not infer conversion from an Agent's prose or a human reply.
- Count conversion only from an eligible linked appointment using the existing documented time/status rules. Ensure supported Agent booking paths populate conversation/customer links correctly.
- Preserve CSV escaping, export auditing, row caps, permissions, timezone boundaries and exclusions for simulated/deleted data. Do not expand this into a CRM.

**Acceptance:** Booking-only Agent enquiries appear before conversion, including abandoned or failed booking attempts with persisted enquiry evidence. A confirmed linked appointment removes the lead according to the contract; pending approval or a failed provider call does not. Cancellation behavior matches the documented conversion rule. Replayed booking calls cannot create duplicate appointments.

**Verification:** Extend `test_calendar_agent.py`, `test_leads.py`, lead isolation/CSV tests and Agent-to-calendar integration tests, including stale availability and uncertain provider outcomes.

### Session 07 — Make practice chat truthful for the selected controller

**Primary files:** `backend/app/inbox/sandbox.py`, `sandbox_router.py`, `backend/app/agent/` context/grounding/policy helpers, and `frontend/src/features/test-chat/`.

**Work**

- Record the dry-run design before implementation: reuse production Agent proposal, grounding and policy logic with isolated test storage and simulated tool outcomes. Avoid a separate imitation of Agent behavior.
- Do not run a real Agent loop against production write tools and rely on rollback. A sandbox effect boundary must prevent real sends, calendar mutations, publications, customer memory writes, approvals and external owner notifications.
- Show the selected controller and simulation status. Simulate tool results for booking/content actions and clearly distinguish those from verified remote outcomes.
- Define behavior for a workspace with no account/controller and for incomplete knowledge. Preserve test-chat rate limits, retention and the existing no-report/no-customer-usage semantics; actual model spend limits still apply.

**Acceptance:** An agent-configured workspace practices the same relevant language, policy and grounding decisions as production. Tests prove real customer tables, send/publish/calendar operations, customer memory, report counts and external notification queues remain unaffected.

**Verification:** Extend `test_assistant_test_chat.py`, isolation tests and frontend test-chat tests. Cover attempts to invoke real effects, not just a visible SIMULATED badge.

### Session 08 — Verify all requested features together on Account Agent accounts

**Work**

- Run combined offline acceptance on a fresh workspace using the Account Agent, real broker/executor paths, fake models and mock providers.
- Cover DMs; public comment and comment-to-DM flows; voice/image enquiries; booking/reschedule/cancel; lead list/export; feed/Story/template-image/carousel/Reel publishing; owner questions and approvals through selected channels.
- Include Instagram/website fact import → owner verification → Agent answer. Include a price change that invalidates a draft and holds affected scheduled content.
- Exercise Arabic layouts, both UI languages, phone-width workflows and owner/manager/staff permissions.
- Verify native-app echoes, takeover/release, duplicate webhooks, expired approvals, quota pauses, worker recovery and reconnect behavior. Keep Human Agent tagged replies human-written; this plan does not extend AI replies beyond their permitted window.
- If follow-ups are included in the pilot setup, explicitly implement and test an Agent-compatible path first; preserve opt-in, one-follow-up limit, approval and send-time window checks. Otherwise record follow-ups as disabled, without silently excluding any of the six required feature areas.

**Acceptance:** Every required feature passes in the selected controller mode. A successful legacy-only test cannot substitute for an Account Agent acceptance result. Each failure has a fix and rerun or is reported as an unresolved pilot blocker.

### Session 09 — Align assisted onboarding, pilot terms and measurement

**Primary documents:** `docs/operations/pilot-onboarding-checklist.md`, `docs/product/pricing-and-unit-economics.md`, relevant product scope/workflow docs, and this file's decision status.

**Work**

- Update the assisted runbook for the 10–15-business target, Account Agent activation, channel choice and confirmed semi-automation policy. Owner activation/delegation remains explicit.
- Add an onboarding record for business, verified facts, supported languages, channel checks, trial start/end, agreed package, assigned operator and acceptance evidence. Store no credentials in the record.
- Once selected, align the free period and founder package wording with the pricing document. Keep manual billing; do not interpret plan period extension as trial-expiry or payment enforcement. No automated charge at trial end.
- Reconcile outdated pricing feature claims with delivered functionality and actual commercial restrictions. Do not silently change tier prices or make WhatsApp compulsory.
- Define measurements from persisted records for first-response time, reply/approval workload, linked appointments and failure/unknown outcomes. Record owner-reported time saved separately from computed metrics.
- Keep the 5% money estimate explicitly illustrative or hide it from pilot success reporting until a measured basis is agreed. Do not present it as earned revenue.
- Agree numeric success targets and review dates with the owner; their absence does not block unrelated engineering fixes.

**Acceptance:** An operator can follow the documented setup with an owner, record the agreed offer, choose channels, verify facts, configure policy and identify how pilot outcomes will be measured. No unsupported CLI commands, invented billing controls or unverified success claims appear.

### Session 10 — Complete combined regression and release preparation

**Work**

- Run relevant targeted tests after each implementation session. At this boundary run the combined backend, frontend and browser acceptance checks for the final change set.
- Verify one migration head; apply migrations and exercise supported downgrade/re-upgrade behavior on a disposable database. Document any data-dependent rollback restriction.
- Regenerate OpenAPI/client types and notification catalogs if changed. Check import contracts, TR/EN UI strings and clean production builds.
- Record remaining baseline/environment failures accurately. A failed required check is not cleared by calling it pre-existing.
- Prepare a release note and recovery procedure for new preferences, Agent policy, language/media behavior and enquiry evidence. State which queued work becomes stale on policy change and how unknown effects remain under reconciliation.

**Checks to select from the current repository scripts**

```text
# backend/
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run lint-imports
uv run pytest
uv run alembic heads

# frontend/
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run i18n:check
npm.cmd test
npm.cmd run build
npm.cmd run e2e
```

Use isolated test databases and the repository's documented offline environment. Confirm commands and environment requirements during Session 00; do not run migrations or destructive fixtures against the live pilot database. Build/type-check the landing app if its copy or configuration changes.

**Acceptance:** Required checks pass for the combined implementation, or the release remains explicitly incomplete with the exact failing checks. Release/version and migration evidence are recorded.

### Session 11 — Record live acceptance and close out pilot readiness

**Work**

- First use already recorded live results where applicable. On a controlled account, run only the missing checks after confirming destinations and scope with the owner.
- Verify Telegram delivery and informed approval clicks end to end on a phone. Test app-only and WhatsApp choices as configured; use existing harnesses and provider constraints.
- Run real-model Agent journeys in the five named languages, plus voice transcription and image-description quality checks. Record provider/model identifiers actually used, failure cases, token/cost evidence and review results. Do not assume old model availability or pricing figures are current.
- Verify genuine signed webhook shapes, DM delivery, native-app echo supersession, comments/private replies, supported publication formats, calendar provider outcomes, revoke/reconnect and lead-list conversion behavior.
- Check worker execution, media-fetch reachability, error visibility, backup/restore evidence and release version on the live environment. Missing connection access is a verification gap, not a reason to redeploy or assert failure.
- Use sanitized fixtures and evidence links; exclude credentials and unnecessary customer data. Update capability records with observed results and dates.
- Add dated current-status notes to historical summaries, preserving their original test results and historical limitations. Update the roadmap and open questions with confirmed answers rather than rewriting history as though live checks happened earlier.

**Acceptance:** The matrix below has evidence for every required row. Remaining unverified permissions/provider capabilities or failing journeys remain explicit blockers for the corresponding promised feature. The final close-out distinguishes code complete, offline accepted, live accepted and owner decisions still pending.

## E. Pilot acceptance matrix

Completed status across Sessions 00–10 implementation and offline acceptance, with live verification cataloged and pending owner live probe execution.

| Area | Required proof | Implemented Work & Contracts | Offline Verification Evidence | Live Verification Status & Evidence | Remaining Decisions or Blocked Checks |
|---|---|---|---|---|---|
| **Basic DM** | Verified basic answer auto-sends through the Account Agent under an owner grant; exactly one customer effect. | Session 03 semi-automation policy in `agent/delegation.py`, `agent/dm.py`, and grounding validator. Basic topics: greeting, business hours, studio address, services, verified pricing. Under `ActionRule(mode="automatic")`, policy grant executes autonomously with verified fact substitution. | `tests/unit/agent/test_agent_policy_matrix_unit.py` (81 tests) and `tests/unit/agent/test_account_agent_pilot_acceptance_unit.py` (35 tests) prove basic FAQ queries execute automatically with exactly 1 operation ledger entry (`INV-05`, `INV-06`). | **Pending Live Verification** (Runbook 2). Requires live Meta Instagram DM webhook and live send execution on connected Instagram business account. | Topic classifications confirmed; no blocked checks offline. |
| **Complex DM** | Complex/mixed enquiry waits for approval or owner input; Telegram decision affects the exact current payload once. | Session 01 resolved Telegram notification dispatch in `notifications/service.py` and action token buttons `act:<token>` in `TelegramChannel`. Session 03 enforced mandatory `ask` approval for complaints, custom quotes, refunds, mixed/unclear queries, and cancellations. Version-bound and single-use (`INV-16`). | `tests/unit/integrations/channels/test_telegram_delivery_unit.py` (13 tests), `tests/unit/approvals/test_telegram_action_tokens.py` (8 tests), and Session 08 combined acceptance prove `ask` approvals dispatch to Telegram, button tap decides once, and stale/replayed tokens reject with `EXPIRED_OR_STALE`. | **Pending Live Verification** (Runbook 1). Requires live Telegram bot message and tap on mobile phone. | None offline; pending owner live probe execution. |
| **Channel choice** | Telegram, WhatsApp and app-only choices behave as configured; opt-out/unlink stops delivery. | Session 02 created `channel_preferences` table (migration `0101`), preference APIs (`channels_router.py`), and frontend multi-channel preference matrix (`Channels.tsx`). Delivery service evaluates preferences per recipient before dispatching. | `tests/unit/identity/test_channel_preferences_unit.py` (24 tests), Vitest `settings.test.tsx`, OpenAPI synchronized. | **Pending Live Verification** (Runbooks 1 & 7). UI toggles verified; pending live phone delivery check across toggled states. | Resolved OQ-01. |
| **Languages** | TR/EN/RU/DE/AR work through full Agent reply and booking flows; app UI remains TR/EN. | Session 04 centralized 5 languages in `app/core/reply_languages.py`, updated `agent/context.py`, `grounding.py`, `calendar.py`, `knowledge.py`, localized templates in TR/EN/RU/DE/AR, Arabic RTL support with Western digits. | `tests/unit/agent/test_agent_languages_unit.py` (82 tests), `test_claims_ru_de_ar.py` (37 tests), `test_formatting_ru_de_ar.py` (52 tests), and eval harness (146/146 fake evals passed). | **Pending Live Verification** (Runbook 5). Real-model evaluation run with OpenAI (`gpt-6-luna` or production model) across the 5 languages on live API. | Additional languages beyond the 5 named deferred to future roadmap. |
| **Media** | Voice completion wakes the Agent and produces an approval-required reply; image-plus-text context is handled safely. | Session 05 updated `inbox/transcription.py` and `image_description.py` to emit durable agent wake events. `agent/context.py` ingests transcripts/descriptions as untrusted labelled context. Mandatory human approval (`ask`) enforced for voice-derived replies. | `tests/unit/agent/test_agent_media_unit.py` (30 tests), `tests/unit/test_dm_transcript.py`, Session 08 combined acceptance. | **Pending Live Verification** (Runbook 5). Real voice note audio webhook, OpenAI Whisper transcription, and vision model on live Meta connection. | Sub-processor privacy notice (30-day KVKK) before real customer audio processing. |
| **Comments** | Eligible public/private replies respect capability, disclosure, window and authority rules; a later DM links correctly. | Feature Phase 3 and Session 08 integrated `comment.reply`, `comment.private_reply`, `comment.hide/unhide/delete` into Account Agent delegation. Enforces 7-day window, 1 private reply per comment, price-disclosure rules. | Session 08 combined acceptance (`test_account_agent_pilot_acceptance_unit.py`). | **Pending Live Verification** (Runbook 3). Requires Meta App Review / Advanced Access for `comments` webhook on production Instagram accounts. | Advanced Access required from Meta for non-tester accounts. |
| **Publishing** | Feed, Story, template image, carousel and Reel use the correct approval/media/polling paths and produce one publication. | Feature Phase 3 (template images, Pillow renderer) and Feature Phase 5 Track B (carousels, Reels, ffmpeg prober) integrated with Account Agent `content.prepare/schedule/publish/cancel` in Session 08. | `tests/unit/content/` (188 tests), Session 08 combined acceptance. | **Pending Live Verification** (Runbook 4). Real Graph API two-step container creation and publishing to live Instagram test account. | Meta 50-post/24h rate limit guard enforced. |
| **Bookings** | Availability is evidenced; book/reschedule/cancel follows configured authority and confirms only verified outcomes. | Session 06 and Session 08 verified `calendar.book/reschedule/cancel` on Account Agent. Slot enquiry -> proposed booking -> owner approval -> verified booking in `calendar_appointments`, localized 5-language responses, timezone handling. | `tests/unit/reporting/test_leads_agent_unit.py`, `tests/unit/agent/test_agent_languages_unit.py`, Session 08 acceptance suite. | **Pending Live Verification** (Runbook 6). Real Google Calendar OAuth connection and calendar event creation. | Google Calendar OAuth client credentials on production. |
| **Leads** | Agent pricing and booking-only enquiries appear; only eligible confirmed linked appointments count as conversion. | Feature Phase 5 Track E and Session 06 unified lead tracking: Agent booking enquiries persist in `lead_enquiries` even without price quotes, confirmed appointments in `calendar_appointments` deduct converted leads, CSV export formula escaping. | `tests/unit/reporting/test_leads_agent_unit.py` (7 tests), `tests/unit/reporting/test_leads_csv.py` (14 tests). | **Pending Live Verification** (Runbook 7). Production UI download and row inspection with live conversation data. | None; reporting logic is pure SQL aggregation. |
| **Knowledge** | Import yields suggestions; only owner-verified usable facts are quoted; changed prices invalidate affected work. | Feature Phase 4 (Instagram bio/captions import, SSRF-safe website fetcher) and Session 08 fact-change holds. Verified facts quote placeholders `{{fact:key}}`, claim validator verifies grounded values, price change sets `FACT_CHANGED` on affected drafts and holds scheduled content. | Session 08 combined acceptance, `tests/unit/knowledge/` tests. | **Pending Live Verification** (Runbook 7). Live import on owner website and Instagram bio. | None; suggestions are strictly owner-approved before becoming usable facts. |
| **Practice** | Selected-controller language/policy behavior is represented; no real effects, customer memory or report contamination. | Session 07 updated `inbox/sandbox.py` to support `controller_mode="agent"`. Reuses production coordinator prompt, policy matrix, and grounding validator with sandboxed test storage. SIMULATED badge shown; zero external side effects or report contamination (`INV-09`). | `tests/unit/inbox/test_sandbox_agent_unit.py` (18 tests), Vitest `testChat.test.tsx` (31 tests). | **Completed Live Verification (Offline & Production Safe)**. Practice chat operates entirely in sandbox storage by design (`INV-09`, `INV-14`); verified clean in production web build. | None. |
| **Recovery** | Duplicate events/jobs/clicks, worker restart, takeover, revoked access and uncertain effects remain safe and visible. | Core write-ahead ledger `operations` (`INV-05`, `INV-15`), dedup keys (`INV-06`), approval hash binding (`INV-16`), worker lease recovery, disconnect erasure (`INV-17`), Alembic migration rollback runbook (Session 10). | Session 08 combined acceptance, Session 10 migration & rollback inspection. | **Pending Live Verification** (Runbook 7). Live worker restart and reconciliation check under transient network interruption. | None. |
| **Pilot terms/outcomes** | Agreed free period/package is recorded; response time, owner effort and linked appointments can be reviewed without invented ROI. | Session 09 updated `docs/operations/pilot-onboarding-checklist.md` with structured onboarding record template, 30-day/1-week free trial parameter, 990 TRY/mo + KDV founder package, SQL-persisted metrics for FRT, workload, appointments, illustrative money metric disclaimers. | Session 09 documentation and schema audits. | **Pending Live Verification** (Runbook 7). Owner executes onboarding interview with first pilot business and files onboarding record. | Confirm 1-week vs 30-day free trial duration with first pilot cohort. |

## F. Completion and first implementation task

The pilot is ready when all six owner-required feature areas pass on Account Agent accounts, Telegram delivery works end to end, channel choice is respected, five-language behavior and semi-automation are verified, the offer is agreed, and the acceptance evidence is recorded. Any missing item must be named explicitly.

**Start with Session 00, then Session 01.** Telegram is the highest-priority production fix. Continue through channel choice, Agent policy/languages/media, booking/leads and practice parity before combined acceptance. This plan does not authorize commits, pushes, deployment changes or live sends by itself.
