# Phase 4: Inbox and Reply Approvals

## Objective
Deliver the incoming-message workflow (C) end to end against the stateful mock Instagram provider: signed webhooks, deduplication, conversations, debounced grounded drafts, the deterministic policy engine, reply approvals bound to the messaging window, the operations ledger for sends with reconciliation, human takeover, approved answers, and the developer simulator.

## Read first
[workflows.md §C, §D, §G](../../architecture/workflows.md) · [state-machines.md §4, §6, §7](../../architecture/state-machines.md) · [integrations.md §3](../../architecture/integrations.md) · [agent-runtime.md §4, §7](../../architecture/agent-runtime.md) · [data-model.md §3.5, §3.7, §3.9](../../architecture/data-model.md) · [api-design.md §2.6, §2.9, §2.10](../../architecture/api-design.md) · ADRs [010](../../architecture/decisions/ADR-010-instagram-provider-adapter.md), [011](../../architecture/decisions/ADR-011-external-operations-ledger.md), [014](../../architecture/decisions/ADR-014-approval-and-policy-model.md) · [user-journeys.md J2](../../product/user-journeys.md)

## Scope
**In:** `social_accounts` + mock connect; `InstagramProvider` protocol, types and errors; `MockInstagramProvider` messaging subset (send, window, echoes, profile, `find_recent_outbound`, failure rules for send); webhook builder and signer; ingestion endpoint (GET handshake + POST); `inbound_events`, `conversations`, `messages`, `reply_drafts`, `operations`, `automation_policies`, `approved_answers`; `process_inbound_event`, `draft_reply`, `send_reply`, `reconcile_send` jobs; the `draft_reply` task (prompt v1, fake); language detection, injection heuristics and escalation keywords; policy engine for replies; owner manual replies, draft edit and cancel, takeover/release; impact handlers for drafts and approved answers; account health counters (basic); the dev simulator (API, CLI, UI panel); inbox, approvals and automation UI; `draft_reply` eval datasets.
**Out:** content publishing (Phase 5), circuit breaker UX and reauth UX (Phase 6), the real Meta adapter (Phase 7), comments.

## Prerequisites
Phase 3 accepted.

## Files and modules expected to change
```
backend/app/integrations/instagram/{base.py, errors.py, mock.py, webhook_format.py, registry.py}, models (social_accounts, sim_*)
backend/app/inbox/{models.py, ingest.py, processing.py, drafting.py, language.py, service.py, router.py, webhooks_router.py, jobs.py, schemas.py}
backend/app/ai/{prompts/draft_reply/v1.md, tasks/draft_reply.py, injection.py}
backend/app/policy/{models.py, engine.py, rules_reply.py, service.py, router.py}
backend/app/operations/{models.py, send.py, reconcile.py, health.py, jobs.py}
backend/app/knowledge/{approved_answers.py, impact_handlers.py}
backend/app/demo/{simulator.py, scripts/customer_messages.yaml, dev_router.py}, app/cli.py (simulate commands)
backend/evals/draft_reply/*.yaml
frontend/src/features/inbox/{ConversationList, ConversationView, DraftCard, ReplyComposer, WindowTimer, FactChip, ReasonChips}.tsx
frontend/src/features/settings/AutomationSettings.tsx, features/knowledge/ApprovedAnswers.tsx
frontend/src/features/dev/DevPanel.tsx
frontend/e2e/scenario-b.spec.ts
```

## Key interfaces and contracts
- `InstagramProvider` ([integrations.md §3.1](../../architecture/integrations.md)). Implement the methods needed for messaging. Container methods may raise `NotImplementedError` in the mock until Phase 5.
- `inbox.ingest_webhook(session, clock, settings, provider_kind, raw_body: bytes, headers) -> IngestResult` (shared by HTTP and simulator).
- `policy.evaluate_reply(ctx, ReplyPolicyInput) -> Decision{outcome, reasons}` (rules R1–R17).
- `operations.execute_send_reply(draft_id)`, `operations.reconcile(operation_id)`.
- Approval payload for replies: `{conversation_id, recipient_id, text, draft_id, draft_version}`.
- Config added: `INSTAGRAM_ENABLED_PROVIDERS` (default `mock`), `MOCK_INSTAGRAM_APP_SECRET`, `ALLOW_SIMULATED_WORKSPACES`, `REPLY_DEBOUNCE_SECONDS` (default 8), `SEND_RECONCILE_WINDOW_MINUTES` (default 10).

## Tasks (in order)

| ID | Task | Details | Size |
|---|---|---|---|
| P4-01 | Social accounts | Model + migration (constraints incl. one active per workspace); registry; `POST /social-accounts/mock` (allowed if `mock` is enabled and the workspace is demo, or in non-production); list API without secret fields; readiness now reads the connection. Seed connects a mock account to each demo workspace and sets `automation_reviewed_at`, so demo readiness becomes `ready`. | S |
| P4-02 | Provider contract + mock (messaging) | Types and errors; mock send with window enforcement, byte limit, `sim_sent_messages`, simulated echo via the `demo_emit_echo` job; profile; `find_recent_outbound`; `sim_failure_rules` for `send`/`profile`; webhook payload builder and signer. Contract tests for the messaging subset. | M |
| P4-03 | Webhook ingestion | `GET /webhooks/instagram` handshake (using `META_WEBHOOK_VERIFY_TOKEN`, introduced now with a dev default); `POST /webhooks/instagram/mock` (mounted only when `mock` is enabled) and `POST /webhooks/instagram` (Meta, wired fully in Phase 7) share one ingestion function; the path selects provider kind and secret, and the raw-body signature is verified before parsing; account resolution also requires a matching `provider_kind`; parse; account resolution; dedup insert; enqueue; always 200 after a valid signature. System-level audit for invalid signatures; counter. | M |
| P4-04 | Inbound processing | Conversation upsert, message insert (unique `mid`), `greatest()` for `last_inbound_at`, echo handling (reconcile vs native reply), supersede open drafts, attention updates, debounced `draft_reply` enqueue, human mode handling. | M |
| P4-05 | Drafting | Language detection (tr/en heuristics; unsupported → `needs_human`); injection heuristics; escalation keywords (built-in + workspace fact); context builder (usable facts, price disclosure handling, approved answers, brand voice, last 10 messages); `draft_reply` task + prompt v1 + fake implementation; render → validate → one regeneration → `GROUNDING_FAILED` path with `suggestion_text`; disclosure suffix for `auto`. | L |
| P4-06 | Policy engine | `automation_policies` model + API; rules R1–R17 as small pure functions; most-restrictive aggregation; table-driven tests including adversarial model output. | M |
| P4-07 | Reply drafts and approvals | `reply_drafts` model with the open-draft constraint; status transitions per the state machine; approval request with window-bound expiry; decided-callbacks (approve → queued + enqueue send; reject; expire); notifications (`approval.requested`, `conversation.needs_human`). | M |
| P4-08 | Operations ledger and send | `operations` model; `execute_send_reply` (two-transaction pattern, re-checks, window, account); typed error handling; `outcome_unknown` → `reconcile_send` (echo match by message ID, or recipient + text hash within the window; then `find_recent_outbound`; then `OUTCOME_UNCONFIRMED`); account `consecutive_failures` update (circuit UX in Phase 6). | L |
| P4-09 | Human actions and approved answers | Manual reply (owner source, validator warnings, queued + self-approval record); edit pending draft (version, re-validate, new approval); cancel queued; takeover/release; approved answers CRUD + "save from sent reply" (values → placeholders); impact handlers for drafts (supersede + redraft) and answers (`needs_review`). | M |
| P4-10 | Simulator and dev tools | Dev API (§2.10) for customer messages (scripted list: price, hours, location, trial, complaint, refund, discount, injection, English tourist, Russian message, photo-only), native owner reply, failure rules, run-due jobs, jobs list. CLI equivalents (`simulate-message`, `run-due-jobs`). Dev panel UI. | M |
| P4-11 | Frontend inbox | Conversation list with filters and simulated badges; conversation view with message bubbles, window timer, draft card (rendered fact chips with source popovers, reason chips, validation issues), approve / edit / reject, manual composer with warnings, takeover toggle, "suggest reply"; approvals list includes reply approvals; automation settings screen (sets `automation_reviewed_at`); approved answers screen. | L |
| P4-12 | Evals | `draft_reply` datasets (≥ 40 cases tr/en) per [testing-strategy.md §6](../testing-strategy.md); CI runs them with `fake`. | M |
| P4-13 | Tests | See below. | M |

## Tests to add
- **Contract (mock):** messaging subset.
- **Integration:** AC-B1 to AC-B10; AC-C3 and AC-C5 (price change → new draft uses 7.000; pending draft superseded); AC-G4; AC-G5; out-of-order events; bursts debounced into one draft; owner native reply supersedes the draft; human mode skips drafting; auto mode sends without approval only for allowed classes when `ready`; rate guard; disclosure suffix included in the byte limit; the simulation flag on every produced row (AC-X2 partial).
- **Adversarial (scripted fake):** complaint labelled pricing with `needs_human=false` → human; invented price in the template → regenerate → human (`GROUNDING_FAILED`); unknown fact key → `FACT_NOT_USABLE`; language switch → rejected by the post-validator.
- **Isolation:** the harness covers new routes. A webhook for workspace B's account never creates rows in A.
- **E2E:** `scenario-b.spec.ts` (simulate DM → approve → sent (simulated) badge; complaint → "needs you"; window expiry with a dev clock is not possible in E2E and is covered by integration tests).

## Acceptance criteria
- AC-B1…B10, AC-C3, AC-C5, AC-G4 and AC-G5 pass.
- Eval hard assertions pass with `fake`.
- INV-05, INV-06, INV-09, INV-15 tests for sends pass (import-linter: only `operations` calls `send_text_message`).

## Demo scenario
Dev panel → "Ayşe: Aylık üyelik ne kadar?" → within seconds the Inbox shows *Onay bekliyor* with draft "…aylık üyelik ücretimiz **6.000 ₺**…" and the chip "Kaynak: Aylık üyelik, doğrulandı" → Onayla ve gönder → *Gönderildi · SİMÜLASYON*. Send the complaint script → *Size devredildi* with reasons. Change the price by command (Phase 3) → send another price question → the draft shows 7.000 ₺. Inject `timeout_after_success` → approve → *Kontrol ediliyor…* → echo arrives → *Gönderildi*.

## Known risks
- Echo-based reconciliation depends on V-02 for the real provider. The mock models the documented behaviour; Phase 7 may need the lookup fallback.
- Fake drafting quality is template-like. Acceptable for the demo; the real provider is optional.

## Explicitly excluded
Content publishing, comments, attachments analysis, the Human Agent tag, Telegram.
