# Phase 4 summary: Inbox and reply approvals

**Status:** implemented and verified locally; **waiting for review** (per [roadmap.md §5](../roadmap.md)). Phase 5 has not been started.
**Scope reference:** [phase-04-inbox-and-approvals.md](../phases/phase-04-inbox-and-approvals.md). All tasks P4-01 … P4-13 are done (P4-06 before the draft job, see D22).
**Branch:** `phase-04-inbox-and-approvals`, created from `phase-03-command-system` at `8be82e5` (the Phase 3 commit, still waiting for review). One commit per task group, nothing pushed. If Phase 3 changes in review, rebase this branch onto it; the Phase 3 files Phase 4 touches are listed in §6.

## 1. What changed

| Area | Contents |
|---|---|
| Social accounts (P4-01) | `integrations/instagram`: `SocialAccount` + `sim_*` models, the pure account state machine, read-only queries (imports only `core`, enforced). `operations/accounts`: connect (mock; allowed if `mock` is enabled and not production, or a demo workspace with `ALLOW_SIMULATED_WORKSPACES`), disconnect, the only function that changes an account state (audited). `GET/POST …/social-accounts`. Settings and production checks for the Instagram variables. Readiness reads the connection. The seed connects a simulated account to both studios, sets `reply_languages` and the automation review, so both are `ready` |
| Provider + mock (P4-02) | `InstagramProvider` protocol, typed errors with the ambiguity rule, Meta-format webhook builder/signer/parser (`WebhookCodec`), `MockInstagramProvider` (24 h window from `sim_inbound_messages`, 1000-byte limit, one stored message per accepted send, `find_recent_outbound`, scripted failures including `timeout_after_success`). 48 contract tests |
| Webhooks (P4-03) | `inbound_events`; `ingest_webhook` verifies the HMAC of the **raw body** before parsing, resolves the account by (kind, receiving id), `ON CONFLICT (dedup_key) DO NOTHING`, enqueues only new items; invalid signature → 401 + system audit, no payload. Routes outside `/api/v1`, mounted only for enabled kinds |
| Processing (P4-04) | `conversations`, `messages` (unique per account + provider id), `reply_drafts` (one open draft per conversation); processing under a conversation row lock; `greatest()` timestamps; supersession of drafts waiting for a person; native-reply echoes; human mode; the single pure draft state machine and the attention rules |
| Drafting (P4-05) | `draft_reply` task (strict schema, prompt v1, snapshot without the customer's words), tr/en fake, language detection (unsupported languages recognised), escalation keywords, injection heuristics, context builder (usable facts only), pipeline: model proposes → code renders → claim validator → one regeneration → `GROUNDING_FAILED`/`FACT_NOT_USABLE`; the disclosure notice is budgeted into the 1000-byte limit |
| Policy (P4-06) | `policy`: rules R1–R17 as pure functions, most restrictive outcome wins; `automation_policies`; `GET/PUT /automation-policies` (saving is the owner's review); `auto` only when everything for `ready` is in place |
| Reply approvals (P4-07) | The `draft_reply` job (three phases, model outside any transaction), approvals bound to `{account, conversation, recipient, text, draft id/version}` expiring at window end − 5 min, policy grants for `auto`, the `reply_draft` approval subject, window-close expiry, a draft for a person when the model stays unavailable |
| Operations (P4-08) | `operations` ledger and the send in two transactions; reconciliation by echo / lookup / `OUTCOME_UNCONFIRMED`, never a resend; stuck-operation sweep; account health; the INV-15 source scan and import contracts |
| Human actions (P4-09) | Conversations API, takeover/release/suggest, manual replies (self-approved or requested), edits with a fresh approval, cancel; approved answers (no literal values, placeholders only), save-from-sent-reply; impact handlers for drafts and answers |
| Simulator (P4-10) | Scripts, signed customer messages and native-reply echoes through the real ingestion path, failure rules, run-due, CLI commands; dev routes only with `DEMO_TOOLS_ENABLED` |
| Frontend (P4-11) | Inbox list/filters, conversation view with the draft card (source chips, reason chips, warnings, approve/edit/reject with the displayed payload hash), composer, takeover/suggest; automation and connection screen; approved answers; developer panel; reply body in the approvals sheet; bell and readiness links |
| Evals (P4-12) | 61 `draft_reply` cases (tr/en) through the real pipeline, hard assertions on every case; CI already runs all tasks in strict mode |
| Tests (P4-13) | See §2. `scenario-b.spec.ts` |
| Schema | Migrations `0004` (accounts, simulator, events, conversations, messages, drafts), `0005` (approved answers), `0006` (automation policies), `0007` (operations ledger and its foreign keys) |
| Docs | Updated in the same changes: `data-model`, `api-design`, `workflows` (§C, §C.1), `state-machines` (§4), `integrations`, `agent-runtime` (§4), `background-jobs`, `component-design`, `environment-variables`, `local-development`, `.env.example` |

## 2. Test results

@@RESULTS@@

## 3. Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| AC-B1 | One DM → one event, one message, after the debounce one draft | `inbox/test_reply_workflow.py::test_ac_b1_…` |
| AC-B2 | The same webhook 3× → one message, one draft | `inbox/test_webhook_ingest.py::test_the_same_webhook_three_times_…` |
| AC-B3 | The draft carries the verified price as `6.000 ₺`, references the current fact version, validation passed | `test_reply_workflow.py::test_a_price_question_becomes_a_grounded_draft_…`; `test_drafting_pipeline.py` |
| AC-B4 | Default policy → `approval_required` / `POLICY_REQUIRES_APPROVAL`, approval expiring ≤ window end − 5 min | `test_reply_workflow.py::test_the_approval_is_bound_to_the_exact_text_…`; `unit/policy/test_reply_rules.py` |
| AC-B5 | Approve with the shown hash → queued → sending → sent; one outbound simulated message; audit | `inbox/test_send.py::test_ac_b5_…`; E2E `B5` |
| AC-B6 | A complaint is `human_required` even if the scripted model says `needs_human=false` | `unit/policy/test_reply_rules.py::test_ac_b6_…`; `test_reply_workflow.py::test_ac_b6_…`; E2E `B6` |
| AC-B7 | An injection attempt never yields a sendable discount | `test_reply_workflow.py::test_ac_b7_…`; evals (`injection` cases, hard); E2E `B7` |
| AC-B8 | Unverified/contested price → `human_required` / `FACT_NOT_USABLE`, no price in any text | `test_reply_workflow.py::test_ac_b8_…`; `test_drafting_pipeline.py`; evals `grounding` |
| AC-B9 | A second approval attempt → 409 and still one simulator message | `test_send.py::test_ac_b9_…`; `test_reply_workflow.py::test_ac_b9_…` |
| AC-B10 | A decision after the window → 409 `APPROVAL_EXPIRED`, nothing sent | `test_reply_workflow.py::test_ac_b10_…` |
| AC-C3 | The next price question uses the new price | `test_approved_answers_and_impact.py::test_ac_c5_…` (the redraft carries 7.000 ₺), `test_simulator.py::test_demo_a_price_change_…` |
| AC-C5 | A pending draft is superseded and redrafted; a sent message is unchanged | `test_approved_answers_and_impact.py::test_ac_c5_…` (both) |
| AC-G4 | Invalid signature → 401, no event stored, failure counted | `test_webhook_ingest.py::test_an_invalid_signature_…` |
| AC-G5 | `timeout_after_success` → `outcome_unknown`; echo → `sent`; no echo in 10 min → `OUTCOME_UNCONFIRMED` + notification; never resent | `test_reconcile.py::test_ac_g5_…` (both branches) |
| AC-X2 (partial) | Everything via the mock is `is_simulated`, with a badge in the UI | `test_send.py::test_every_row_a_simulated_send_…`; UI tests; E2E |
| INV-05 | An ambiguous send is reconciled, never repeated | `unit/operations/test_operation_state_machine.py` (`outcome_unknown → in_progress` forbidden), `test_reconcile.py`, `test_send.py` |
| INV-06 | Duplicate webhooks/jobs → one remote effect | `test_send.py::test_ac_b9_…`, `…_repaired_without_sending_again`, unique keys in the schema |
| INV-09 | Simulated data labelled everywhere | as AC-X2 |
| INV-15 | Only `operations` calls side-effecting provider methods; the ledger row is committed first | `unit/test_side_effect_calls.py`, import contracts, `test_send.py::test_inv15_…` (another connection sees `in_progress` during the call) |

## 4. Demo steps (verified in the E2E scenario)

1. `docker compose up -d postgres`; `cd backend`; `uv run alembic upgrade head`; `uv run python -m app.cli seed --reset`; start the API, **the worker** and `npm run dev`.
2. Sign in as `owner@demo.local`, open *Gölkent Fitness & Pilates*. More → Geliştirici araçları → **Fiyat sorusu** (Ayşe).
3. Gelen kutusu → Ayşe → *Onay bekliyor*: "…aylık üyelik ücretimiz **6.000 ₺ / ay**." with the chip "Kaynak: Aylık üyelik, doğrulandı" and the reason "Otomatik gönderim kapalı" → **Onayla ve gönder** → *Gönderildi* with *SİMÜLASYON*.
4. **Şikayet** → the conversation shows *Size gerek var* with reasons; there is nothing to approve. **Talimat enjeksiyonu** → handed to you, no discount anywhere.
5. Home: "Aylık üyelik artık 7.000 TL" → confirm → send **Fiyat sorusu** again → the draft shows 7.000 ₺ (and a draft waiting for approval at the time of the change is replaced).
6. Dev panel → failure rule *send → timeout_after_success* → approve a reply → *Kontrol ediliyor…* → the echo arrives → *Gönderildi*; one message in the simulator.
7. More → Otomasyon ve Instagram: set *Fiyatlar* to automatic (allowed because the studio is `ready`) → the next price question is answered without asking, with the automatic-reply notice added by code.

## 5. Deviations from the docs (and why)

The planning-time resolutions (G1–G26 in the plan) are written into the documents named in each row; this table is the list to review.

| # | Deviation | Reason / where recorded |
|---|---|---|
| D1 | The account **service** (connect, disconnect, state changes) is in `operations/accounts.py`, not in `integrations/instagram`; only models, the state machine and read-only queries stay there | Integrations import only `core` (no audit). `component-design.md` |
| D2 | The accounts API calls the expiry `connection_expires_at`, not `token_expires_at` | The response-field secret scan forbids names containing `token`. `api-design.md` |
| D3 | `NormalizedInboundEvent` has `account_id` / `customer_id` (not `recipient_account_id` / `sender_id`); `AccountRef` carries `workspace_id`; `AccountProfile`, `OutboundMessageInfo` defined | An echo swaps sender and recipient; the simulator tables are tenant-scoped. `integrations.md` |
| D4 | `ingest_webhook(session, clock, settings, provider_kind, raw_body, headers)`; a `WebhookCodec` does verify/parse without a provider instance | Testable in a request's transaction and from the simulator. `component-design.md`, phase doc |
| D5 | `inbound_events.payload` is nullable; the stored payload is the single item | The retention job nulls it after 30 days. `data-model.md` |
| D6 | `messages` is unique on `(social_account_id, external_message_id)` and carries `social_account_id` | INV-06 wins over the per-workspace key in the table. `data-model.md` |
| D7 | `reply_drafts.failure_code` is the reason of **any** terminal state except `sent` (superseded, cancelled, expired, failed) | One column for the reason chips. `data-model.md` |
| D8 | `draft_reply` jobs are keyed **per inbound message** (`draft_reply:{conv}:{message}`) and proceed only if their message is still the newest | A trailing-edge debounce; with a single key a message arriving during a running job would be swallowed. `background-jobs.md`, `workflows.md` |
| D9 | The task post-validator checks structure only; unknown fact keys are caught by the renderer (`FACT_NOT_USABLE`) after one regeneration | Gives the documented reason and the regeneration. `agent-runtime.md` §4 |
| D10 | R13–R16 use the **effective mode**: the strictest of the intent's class and the classes of the facts the reply quotes; only the reasons of the winning outcome are shown; R10 covers `LLM_REFUSED`; R17 is for `other`; an unknown price policy counts as `do_not_share`; R1 requires `connected` exactly | A price question labelled "hours" must still follow the pricing policy (INV-04). `workflows.md` §C.1 |
| D11 | R8 also reports `FACT_NOT_USABLE` when the model could not answer and a fact of that kind exists but is unverified/contested; the fake never substitutes another product's price | AC-B8. `public knowledge.service.unusable_fact_keys` |
| D12 | The approval payload is `{social_account_id, conversation_id, recipient_id, text, draft_id, draft_version}`; the approval summary carries ids and reasons, never the text | ADR-014 target account; keeps message text out of notifications. `workflows.md` |
| D13 | Saving the automation policies stamps `automation_reviewed_at` and **replaces the temporary Phase 2 PATCH** (`settings.automation_reviewed`), which is removed with its tests | Phase 2 D4 said "temporary until Phase 4". `api-design.md` |
| D14 | Draft transitions `sending → queued` (retry) and `sending → expired` (provider says the window closed) added | A pre-acceptance error needs a way back; `workflows.md` §G says "draft expired". `state-machines.md` §4 |
| D15 | A person who may approve and sends their own reply gets a recorded **self-approval** (`approvals.grants`); anyone else a pending request | ADR-014 (self-approval needs the permission). `api-design.md` |
| D16 | A late echo after `OUTCOME_UNCONFIRMED` is recorded as our message (`reply.late_confirmation`); the draft keeps its terminal state | The message was delivered; it must not be misread as a native reply. `background-jobs.md` |
| D17 | Failure-rule operations also include `lookup` and `echo`; the echo of a simulated send is a `demo_emit_echo` job in `operations` (mock accounts only) | Reconciliation and the no-echo path must be demonstrable. `integrations.md` |
| D18 | Mock window state is a new `sim_inbound_messages` table | The mock must not read application tables. `data-model.md` |
| D19 | `approved_answers` API: `LITERAL_VALUE` / `UNKNOWN_FACT` validation; `from-message` lives in `inbox` (it needs messages); permission `knowledge.verify` for writes | INV-02. `api-design.md` |
| D20 | Migrations are split `0004`–`0007`, not one `0004` | They were added task by task; `alembic check` is clean and upgrade/downgrade round-trips |
| D21 | Error codes `MESSAGING_WINDOW_CLOSED`, `ACCOUNT_NOT_CONNECTED` added (backend and frontend texts) | New API errors |
| D22 | The `draft_reply` **job** is built in P4-07 (with approvals), after the policy engine (P4-06); P4-05 delivers the pipeline | The job needs the decision and the approval request |
| D23 | Tooling: `E2E_API_PORT` / `E2E_WEB_PORT` override the E2E and Vite proxy ports; `tests/conftest.py` loads all handlers once | A second stack beside another checkout; registry snapshots must not drop registrations |
| D24 | The reply approvals sheet and inbox components differ in file names from the phase list (`DraftParts.tsx`, `InboxPage`/`ConversationPage`, `labels.ts`) | Smaller, cohesive files |

## 6. Phase 3 files this branch touches (for a rebase)

Backend: `app/handlers.py`, `app/main.py`, `app/api/router.py`, `app/core/{config,errors}.py`, `app/core/i18n/{en,tr}.json`, `app/approvals/models.py` (operation FK), `app/knowledge/{models,constants,readiness,service,approved_answers}.py`, `app/identity/{schemas,service}.py`, `app/demo/{seed,…}.py`, `app/cli.py`, `migrations/env.py`, `pyproject.toml`, `evals/{runner,loader}.py`, `tests/conftest.py`, `tests/isolation/conftest.py`, `tests/unit/core/test_settings_safety.py`, `tests/integration/test_seed.py`. Frontend: `app/router.tsx`, `i18n/index.ts`, `api/types.ts`, `features/{approvals/ApprovalDetailSheet,notifications/*,knowledge/readinessLinks,settings/MorePage}`, the generated `openapi.json` / `schema.d.ts` (regenerate, never merge), `e2e/playwright.config.ts`, `vite.config.ts`.

## 7. Known limitations

- **Reconnecting an account does not re-send queued replies.** A reply that waits for a re-authorisation stays `queued` (the job retries every 5 minutes, then the expiry sweep ends it at the window end). The reconnection UX and `resume_account` are Phase 6.
- No automatic `degraded` state and no circuit breaker: Phase 4 counts consecutive failures and reacts to an invalid token (`needs_reauth` + a critical notification) and a missing permission (messaging capability off). Phase 6.
- The Meta adapter does not exist: `POST /webhooks/instagram` and the handshake are mounted only if `meta` is enabled, and the registry refuses to build a Meta provider ("arrives in Phase 7"). Echo matching by text hash and the lookup fallback depend on the platform checks V-02.
- The fake drafting is template-like and keyword-based (documented demo phrases); exploratory typing is better with the real provider. The real provider has not been run against `draft_reply` (no key here): the prompt and strict schema are tested offline only.
- Messages are not paginated (the last 100 are shown); the conversation list returns 50.
- Notifications and conversations poll (4–30 s); no push.
- Attachment analysis, comments, the Human Agent tag and Telegram are out of scope as planned.
- The real iOS Safari, a LAN phone test and GitHub CI have still not run (carried over).

## 8. Questions for review

- **Q1 (D1/D4):** Is it acceptable that `ingest_webhook` takes a session (not a session factory) and that the account service lives in `operations`?
- **Q2 (D8):** One draft job per inbound message (a trailing-edge debounce) instead of the documented single dedup key: confirm, or prefer a different mechanism?
- **Q3 (D10):** The strictest-of-intent-and-facts rule means a pending `reply.general_faq` automation never applies to a reply quoting a price. Confirm that is the intent of ADR-014.
- **Q4 (D13):** The automation screen requires everything for `ready` (account, facts) before `auto` can be chosen; the first save is the review. Is "Ask me first" the right default presentation?
- **Q5 (D15):** A staff member's manual reply needs an owner/manager approval (as decided at planning). Should staff also see the approval state in their inbox view (today: "An owner or manager has to approve this reply")?
- **Q6 (§7):** Re-enqueueing `send_reply` for queued drafts on reconnection: Phase 4 follow-up or Phase 6 as planned?
- **Q7:** Phases 1–3 questions (merge strategy of the stacked branches, OpenAI model ID, accessibility tests) are still open.
