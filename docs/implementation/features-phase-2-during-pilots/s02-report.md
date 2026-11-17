# Feature Phase 2, Session 02: Voice in the reply path (F-03, part 2)

**Status:** Implemented and verified offline (backend and frontend checks, section 5). Not committed. Stopped for review.
**Baseline:** `main` at `20a0551`, plus the uncommitted Session 01 work and the unrelated `backend/pyproject.toml` D-01 line, all left intact.
**Migration:** none. Head stays `0049`; the next free revision is `0050`.
**Live provider / real device:** none used. No key, no network. Transcription quality on real Turkish voice notes and the live draft quality on transcripts are **pending** (section 7).

## 1. What was built

### Transcripts enter the normal draft path (`inbox/context.py`, `inbox/drafting.py`)
- `prepare` loads the `message_transcripts` rows of the unanswered messages and of the 10 history messages (workspace-scoped, one query). A message's words are its typed text plus its `succeeded` transcript (collapsed to one line, so a transcript cannot open a fake `business:` line). `customer_text` (what every pre-check scans: injection heuristics, keyword flags, escalation words, language choice) now includes transcripts, so a transcript goes through `ai/injection.py` like any message. `attachment_only` is true only when there is nothing to read.
- In the model input a transcript is a `DraftMessage(role="customer", source="transcript")`; its prompt line reads `customer (voice note, automatic transcript, may contain transcription errors): <text>`, inside the same neutralised `<untrusted_customer_messages>` section. **Prompt `draft_reply` v3** (new `prompts/draft_reply/v3.md`, v2 kept) tells the model a transcript is ordinary untrusted customer data that may contain misheard, missing or run-together words, and that an unclear name, number or time is a reason to set `can_answer=false` and `needs_human=true`. The `agent_runs` snapshot keeps only `transcript_count`.
- A failed (or stuck) transcript is simply ignored: the voice note stays attachment-only, `ATTACHMENT_ONLY`, as before. The failure reason stays on the transcript row and is shown in the inbox.

### The draft/transcript race (orchestrator decision), handled deterministically
- **While a transcript is `pending`** (and younger than `TRANSCRIPT_WAIT_LIMIT` = 20 min, measured from the row's `created_at`, which is now set from the injected `Clock`), `prepare` returns `DraftSkip("transcript_pending")` and the `draft_reply` job raises `RescheduleJob(now + 30 s)`: no draft, no attempt consumed, same job row and dedup key. It does not hand the message to a person.
- **When the transcription job finishes** (success, permanent failure, and the `on_dead` path after exhausted retries; `VOICE_SOURCE_GONE` aside) it calls `wake_drafting` **in the same transaction** as the row's new state: enqueue `draft_reply` with the existing dedup key at `run_at = now`, and pull an already queued job (the 8 s debounce or the 30 s wait) forward to now. A job that is *running* then owns the key, and has either read the final row or reschedules itself within 30 s. Skipped for echoes, deleted messages, agent-controlled accounts, and conversations in human mode (an explicit "suggest reply" job, key `...:requested`, is still woken).
- **Stuck `pending`:** the job's `on_dead` already marks the row failed (and now wakes drafting). If the job itself were lost, drafting stops waiting after 20 minutes and the voice note falls back to `ATTACHMENT_ONLY`; a transcript that lands later finds a draft already covering the message and changes nothing (tested).

### Deterministic approval rule: R18 (`policy/rules_reply.py`)
`r18_transcript`: if `ReplyPolicyInput.transcript_based` then finding `approval_required` with reason **`TRANSCRIPT_REQUIRES_APPROVAL`**. `transcript_based` comes from `DraftContext.transcript_message_ids`, set by code from stored rows (transcripts among the unanswered or the 10 history messages, so a typed follow-up after a voice note is still approved by a person). Nothing in the model output reads or clears it. It is a floor: an automatic mode, readiness, intent or delegation cannot lift it, and stricter rules (human_required, blocked) still win and show their own reasons. The draft records `validation.transcript_message_ids`, and the `reply_draft.created` audit entry carries `transcript_based` (never the text).

**Account agent path (Phase 7.5 delegation).** `agent/dm.py::send` now passes `require_human=True` to `authorize_action` when `policy/transcripts.py::recent_transcript_present` finds a customer voice note with a finished transcript among the conversation's newest 10 inbound messages, so an `automatic` `dm.send` delegation becomes `ask`. The agent does not read transcripts today (it sees `[attachment: audio]`), so this is a guard for the day it does.

### API (patched into `frontend/openapi.json`; `schema.d.ts` regenerated)
- `MessageOut.transcript: TranscriptOut | null` where `TranscriptOut = {status: pending|succeeded|failed, text|null, language|null, reason_code|null, duration_seconds|null}`. `text` only when succeeded and not erased.
- `ReplyDraftOut.transcripts: DraftTranscriptOut[]` = `{message_id, text|null, language|null}`; empty unless the reply came from a transcript. Used by both the inbox draft card and the approval view (`GET /reply-drafts/{id}`).
- No audio field, no audio endpoint. Only `MessageOut`, `ReplyDraftOut`, `TranscriptOut`, `DraftTranscriptOut` changed (123 added lines in `openapi.json`, 39 in `schema.d.ts`; no path changed).
- An owner's edit of a draft keeps `transcript_message_ids`, so the label survives.

### UI (Turkish and English)
- Inbox thread: an audio message shows "Voice note" (not "Photo or file") and, under it, a `TranscriptBlock`: **"Transcript (automatic)"** (tr: "Yazıya çeviri (otomatik)"), the language chip (Turkish / English / Another language), the text in a dashed block with `lang` set, "Written by a machine, so it can contain mistakes. You can listen to the voice note in Instagram." Pending shows "Transcribing the voice note…"; failed shows a message with the reason (13 reason strings); an erased transcript says so. **No audio player and no audio storage.**
- Draft card and approval view (`ReplyApprovalBody`): `DraftTranscripts` shows the same labelled block(s) above the draft text with "Written from an automatic voice transcript. Check it before you approve." The reason chip `TRANSCRIPT_REQUIRES_APPROVAL` has tr/en text.

### Evals
- New dataset `evals/draft_reply/voice.yaml` (`draft_reply_voice`, 21 hard cases; harness input key `transcript`): clean, no-diacritics, disfluent ("Şey ıı merhaba yani randevu almak istiyordum da ııı ..."), garbled ("merhba ayluk uyelik fyatı ne kdar"), filler-only, English, delegated-automatic (pricing, hours, location, phone, promotion, booking, English), complaint, refund, escalation keyword, two injections, German (unsupported), price-not-shared, unusable hours, unverified price. The runner builds the transcript context exactly as `prepare` does, and a new hard invariant fails any case whose reply would be `auto` while transcript-based.
- **Fake-provider results (recorded):** `python -m evals run --all` gave interpret_command 67/67, extract_fact_candidates 12/12, **draft_reply 82/82 (61 existing + 21 voice), 0 hard failures**, draft_content 26/26. Report: `backend/evals/reports/20261116T125309Z-fake.{md,json}`. The fake model matches words, so it cannot read through filler words: `voice_disfluent_price_tr` and `voice_garbled_price_tr` expect "approval or human, never auto" and the fake chooses human (the safe direction). **The live (OpenAI) eval run is pending**; so is any accuracy claim on real transcripts.

## 2. New contracts

- **Policy rule:** R18, reason code `TRANSCRIPT_REQUIRES_APPROVAL`, outcome at least `approval_required`.
- **Prompt:** `draft_reply` `v3` (v2 file kept); `DraftMessage.source: message|transcript` (default `message`); `agent_runs` snapshot `transcript_count`.
- **API fields:** above. **Audit:** `reply_draft.created` metadata gains `transcript_based`. **Stored:** `reply_drafts.validation.transcript_message_ids` (JSON, no migration).
- **Job behaviour:** `draft_reply` reschedules +30 s while a recent transcript is pending; `transcribe_voice_note` wakes drafting in its final transaction.
- **Constants:** `TRANSCRIPT_WAIT_LIMIT` 20 min, `TRANSCRIPT_POLL_SECONDS` 30 (`inbox/context.py`). No new setting or env var.
- `MessageTranscript.created_at` is now set from the injected `Clock` at request time.

## 3. Files

Backend, new: `app/policy/transcripts.py`, `app/ai/prompts/draft_reply/v3.md`, `evals/draft_reply/voice.yaml`, `tests/integration/inbox/test_voice_reply_path.py`, `tests/integration/agent/test_dm_transcript.py`, `tests/unit/inbox/test_transcript_context.py`.
Backend, changed: `app/inbox/{context,drafting,jobs,reply_workflow,transcription,schemas,views,router,service}.py`, `app/ai/schemas.py`, `app/ai/tasks/draft_reply.py`, `app/policy/rules_reply.py`, `app/agent/dm.py`, `evals/{loader,runner}.py`; `evals/reports/20261116T125309Z-fake.*` generated.
Backend tests, changed: `tests/unit/policy/test_reply_rules.py` (R18, 18 rules), `tests/unit/ai/test_draft_reply_task.py`, `tests/unit/evals/{test_draft_reply_evals,test_eval_harness}.py` (voice dataset; prompt v3 allowed), `tests/integration/inbox/test_voice_transcription.py` (the Session 01 "attachment-only draft" test now asserts the new behaviour; the erasure test removes the draft first, see section 6), `tests/isolation/test_message_transcripts_isolation.py` (+1).
Frontend: new `src/features/inbox/TranscriptBlock.tsx`; changed `openapi.json`, `src/api/schema.d.ts`, `src/components/icons.tsx` (MicIcon), `src/features/inbox/{ConversationPage,DraftCard}.tsx`, `src/features/approvals/ReplyApprovalBody.tsx`, `src/i18n/locales/{en,tr}/inbox.json`, `src/features/inbox/inbox.test.tsx` (+5), `src/features/approvals/approvals.test.tsx` (+1).
Docs: `architecture/{workflows,background-jobs,data-model,api-design,agent-runtime,observability}.md`, `product/mvp-scope.md`, `legal/sub-processor-register.md`, this report.

## 4. Invariant notes

- **INV-01:** no new table; all new reads filter on `workspace_id` (isolation test calls the three read helpers with a foreign workspace; foreign IDs on the changed routes already 404).
- **INV-03:** the transcript is untrusted, labelled in its prompt line, neutralised, screened by the injection heuristics and keyword scan, never a fact, never written to `messages.text`.
- **INV-04:** R18 is code-derived and cannot be lowered by the model or by delegation (unit tests over every automatic intent, every model output combination, and the evals; agent-path test with an `automatic` delegation).
- **INV-02:** values still come only from `{{fact:...}}`; the voice evals include grounding cases.
- **INV-06/07:** one draft job per conversation (dedup key kept); the wait is a reschedule of the same row, durable in Postgres.
- **INV-19 / Clock:** the wait limit uses the transcript row's `created_at` from `Clock`; no wall-clock reads. **No external call inside a transaction:** unchanged (Session 01 test still passes).

## 5. Checks (exact)

Environment for backend runs: `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN= OPENAI_API_KEY=` and `TEST_DATABASE_URL` = the `.env` value with the database swapped to `agentnest_p2s02_{a,b,c,d,e}_test` (parallel shards; **dropped at the end**). `.env` has `DEMO_TOOLS_ENABLED=false`; tests that call `/dev/*` routes were run with `DEMO_TOOLS_ENABLED=true`, everything else with the `.env` value.

| Command (from `backend/` unless noted) | Result |
|---|---|
| `uv run ruff check .` / `uv run ruff format --check .` | All checks passed / 699 files already formatted |
| `uv run mypy app` | Success, 370 source files |
| `uv run lint-imports` | 23 kept, 0 broken |
| New and changed tests (db a): `pytest tests/integration/inbox/test_voice_reply_path.py tests/integration/inbox/test_voice_transcription.py tests/integration/agent/test_dm_transcript.py tests/unit/inbox/test_transcript_context.py tests/unit/policy tests/unit/ai/test_draft_reply_task.py tests/unit/evals tests/isolation/test_message_transcripts_isolation.py` | **285 passed** (of which new: 28 voice reply path, 2 agent guard, 6 context, 1 isolation, 5 task, 7 policy R18, 3 eval) |
| Shard B (db b): `DEMO_TOOLS_ENABLED=true pytest tests/integration/inbox` | **394 passed** |
| Shard C (db c): `pytest tests/unit tests/isolation tests/security tests/contract` | 2091 passed, 13 skipped, **3 failed**, all environment (see section 6): two dev-route isolation tests (pass with `DEMO_TOOLS_ENABLED=true`: 2 passed) and the invite-secret log test (passes alone) |
| Shard D (db d): `pytest tests/integration/{policy,approvals,agent,ai,retention,jobs,activity,operations,demo}` | 559 passed, 4 failed (`demo/test_reset.py`, dev routes); `DEMO_TOOLS_ENABLED=true pytest tests/integration/demo`: **14 passed** |
| Shard E (db e): `DEMO_TOOLS_ENABLED=true pytest tests/e2e tests/integration/{notifications,integrations,knowledge} tests/integration/test_*.py` | 315 passed, **1 failed**: `test_health_and_errors.py::test_cors_allows_only_the_frontend_origin` (known, pre-existing) |
| `python -m evals run --all` (fake) | 67/67, 12/12, **82/82**, 26/26; 0 hard failures |
| `npm.cmd run lint` / `typecheck` / `i18n:check` / `build` (from PowerShell) | pass (i18n: en, tr, 2460 keys) / pass / pass / built |
| `npm.cmd test` (PowerShell) | **52 files, 791 tests passed** (new: 5 inbox, 1 approvals) |

Earlier in the session, before the last small test additions, the inbox shard and the simulator tests were also run separately (`tests/integration/inbox/test_simulator*.py` with `DEMO_TOOLS_ENABLED=true`: 39 passed). The five test databases were dropped at the end.

## 6. Deviations, findings and limitations

- **Pre-existing defect found (not fixed, owner decision needed):** `data_rights.erase_conversation` (and the workspace-wide variant) does `UPDATE reply_drafts SET covers_through_message_id = NULL`, but the column is `NOT NULL`, so erasing any conversation that has a stored draft raises `NotNullViolation`. Reproduced with a plain typed message and draft at HEAD logic; the unit tests mock the session, so it was never hit. Since a voice note now gets a draft at once, the Session 01 test `test_the_data_subject_export_includes_the_transcript_and_erasure_removes_it` deletes the drafts before erasing (commented in the test).
- **Agent path:** the account agent does not read transcripts (it still sees `[attachment: audio]`) and has no transcript wait. I added only the approval guard. Feeding transcripts to the agent (with its own wake-up on transcript completion) is a later change; open question below.
- **No audio player**, by decision: the audio is never stored.
- **Conservative scope of R18:** a transcript anywhere in the 10 history messages forces approval, even if the new message is typed. Easy to narrow to unanswered messages if the owner finds it noisy.
- **Transcripts of a draft are read live:** the approval/inbox views show the current transcript text (null after retention erasure); the draft only stores the message ids.
- **Test-environment notes:** `test_dev_job_listing_of_a_never_shows_the_jobs_of_b`, `test_the_simulator_listing_of_a_never_shows_what_b_published` and the `/dev/*` simulator tests need `DEMO_TOOLS_ENABLED=true` (they pass with it); `tests/security/test_invite_secrets.py::test_the_invite_token_is_never_logged_audited_notified_or_queued` fails inside the combined unit+isolation+security+contract run (log-capture order dependence, same as in the Session 01 report) and passes alone and with `-k invite` together with `tests/unit`. Known: `tests/integration/test_health_and_errors.py::test_cors_allows_only_the_frontend_origin` (pre-existing).
- **Not run:** `tests/browser`, Playwright e2e, the full ~3,600-test suite serially.
- **Unverified / pending:** live transcription quality on real Turkish voice notes; live LLM behaviour on transcripts (prompt v3 untested against a real model); the live eval run; everything listed in the Session 01 report section 6 (real Instagram payload and CDN hosts, model ID, OpenAI speech-to-text terms, 30-day sub-processor notice).

## 7. Open questions for the owner

1. Should the account agent (controller `agent`) read transcripts? That needs a wake-up on transcript completion like the legacy path.
2. Keep R18's wide scope (any transcript in the last 10 messages) or narrow it to the unanswered messages?
3. Fix `erase_conversation` (delete the drafts, or make `covers_through_message_id` nullable)? It is independent of this feature but now easy to hit.
4. After pilot measurements of transcription accuracy, may R18 be relaxed for some intents? Today it is unconditional.
5. Is a 20-minute wait limit (and 30 s poll) acceptable?
