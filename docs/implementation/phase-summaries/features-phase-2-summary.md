# Feature Phase 2 Close-Out Summary: During Pilots

- **Phase:** Feature Phase 2 (F-03 voice and image understanding, F-04 story replies and mentions, D-02 approval-ladder suggestions, D-03 missed-customer report, D-05 visible learning loop, D-04 manage by chat)
- **Specification:** [features-phase-2-during-pilots/sessions.md](../features-phase-2-during-pilots/sessions.md), source [pre-launch-feature-recommendations.md](../../review/pre-launch-feature-recommendations.md) §4 step 2 plus D-04 and D-05
- **Sessions executed:** 01 to 08. Reports in [features-phase-2-during-pilots/](../features-phase-2-during-pilots/): [s01](../features-phase-2-during-pilots/s01-report.md), [s02](../features-phase-2-during-pilots/s02-report.md), [s03](../features-phase-2-during-pilots/s03-report.md), [s04](../features-phase-2-during-pilots/s04-report.md), [s05](../features-phase-2-during-pilots/s05-report.md), [s06](../features-phase-2-during-pilots/s06-report.md), [s07](../features-phase-2-during-pilots/s07-report.md), [merge-04-07](../features-phase-2-during-pilots/merge-04-07-report.md), [s08](../features-phase-2-during-pilots/s08-report.md). Sessions 01 to 03 ran in order in the main tree; 04 to 07 ran in parallel worktrees and were merged by hand; 08 was started by a Codex run and finished by Claude. Session order was not changed by pilot feedback (there was none yet).
- **Baseline Git commit:** `20a0551` (`main`). **Nothing is committed**: all eight sessions are uncommitted on `main` (see section 8).
- **Alembic migration head:** `20261117_0057_manage_by_chat.py` (revision `0057`). The next free migration is `0058`. Chain: `0048 -> 0049 (waitlist) -> 0050 (signup) -> 0051 (plans) -> 0052 (S01) -> 0053 (S03) -> 0054 (S04) -> 0055 (S05) -> 0056 (S07) -> 0057 (S08)`. `0049`-`0051` came from main (PRs #5-#7), which landed while this phase was built; on merging with main the phase's migrations were renumbered from `0049, 0050, 0052, 0053, 0055, 0056` to `0052`-`0057`. The session reports keep the numbers they were written with. `alembic heads` shows one head.
- **Status:** **Implemented and verified offline. Stopped for review.** Nothing was run against a real Instagram account, a real phone, a real Telegram bot or a real model. Everything that depends on those is listed in section 7 as pending.
- **Date:** 2026-11-17

> [!NOTE] Current Status (Date: 2026-11-19)
> The code for this feature phase was subsequently committed to `main` (`e1c9f13`). Its functionality has been integrated, verified offline, and extended to Account Agent pilot readiness in Sessions 00–10 of the `answeres2.md` plan. The original historical test records and offline verification below are preserved intact. Remaining live provider verifications (live voice/image quality, real Instagram payloads, OpenAI speech/vision APIs) are cataloged as pending live verification runbooks in Session 11 (`docs/implementation/account-agent-pilot-readiness/s11-report.md`).

---

## 1. Executive summary

The phase adds what pilots will ask for once the first owners are using the assistant, without loosening any safety rule: everything a customer sends is still untrusted data, every new reply path still ends at an owner approval, and every number in a report still comes from persisted records.

- **F-03, voice notes and images (Sessions 01 to 03).** A customer's voice note is downloaded, transcribed and stored as a separate, labelled record. The transcript is drafted like typed text, but a new deterministic rule (R18) forces approval for every transcript-based reply. A photo or screenshot gets a short "what the customer sent" description for the owner, and no automatic answer.
- **F-04, story replies and mentions (Session 04).** A reply to one of the business's own stories is drafted with that story's text as context. A plain story mention is answered only by an owner-written thank-you template, through the normal approval path.
- **D-02, approval ladder (Session 05).** A weekly job suggests, at most once a week, turning one reply topic to automatic when the owner has approved at least 20 of its drafts unchanged. The owner confirms through the existing delegation preview and apply, never through free text.
- **D-03, missed-customer report (Session 06).** A weekly report of after-hours DMs, unanswered conversations and first-reply time, with an estimate in lira from verified prices and a placeholder 5% conversion rate, and the formula shown.
- **D-05, learning loop (Session 07).** After the owner answers a question, one tap saves the answer as a verified fact (web and Telegram), and the Assistant page counts what the assistant learned this month.
- **D-04, manage by chat (Session 08).** Two new confirmed commands, "move tomorrow's story to 19:00" and "pause the assistant until tomorrow morning", in Turkish and English, and the command box now comes first on Today at phone width.

---

## 2. What changed, by feature

### 2.1 F-03 voice notes (Sessions 01 and 02)
- **Parsing and storage (S01):** `webhook_format.py` normalises attachment types and builds `audio_attachment`; table `message_transcripts` (migration `0052`, RLS forced; one row per message, `pending|succeeded|failed`, `reason_code`, `source = "transcript"`, text, language, provider, model, duration, `is_simulated`). Nothing is written to `messages.text`.
- **Job:** `transcribe_voice_note` (`{message_id}`, 3 attempts, backoff 10/60/300 s). Download and transcription run with no transaction open. A permanent failure is recorded and the job succeeds; a dead job stays visible.
- **Provider interface:** `app/integrations/transcription/` (own interface, not part of `LLMProvider`): `fake` (fixtures, refuses real audio), `openai` (`audio.transcriptions.create`, audio only), and `HttpsAudioFetcher` (https, port 443, Instagram/Facebook CDN host allowlist, public addresses only, no redirects, no Authorization header, size and type caps). Settings `TRANSCRIPTION_PROVIDER` (`auto|off|fake|openai`), `TRANSCRIPTION_MODEL` (`gpt-4o-mini-transcribe`), size, duration, timeout and a per-workspace daily cap (200).
- **Privacy:** the audio is never stored. The transcript follows message text: nulled at 365 days, erased on provider delete, conversation, customer and account erasure, included in the data-subject export. `sub-processor-register.md`, the privacy policy and the KVKK template were updated.
- **Reply path (S02):** transcripts enter `inbox/context.py` as `DraftMessage(source="transcript")` inside the untrusted-data section, are screened by `ai/injection.py`, and use prompt `draft_reply` v3 (v4 after the Session 04 merge). While a recent transcript is `pending`, drafting reschedules itself (30 s poll, 20 minute limit); the transcription job wakes drafting in the same transaction when it finishes. A failed transcript leaves the message on the old `ATTACHMENT_ONLY` person-handled path.
- **R18** (`policy/rules_reply.py`, reason `TRANSCRIPT_REQUIRES_APPROVAL`): a code-derived floor that makes a transcript-based reply at least `approval_required`; delegation, readiness and the model cannot lower it. The account-agent `dm.send` path asks a human when a finished transcript is among the newest 10 inbound messages.
- **UI:** "Transcript (automatic)" block with language chip and a machine-written warning in the inbox thread, the draft card and the approval view; 13 failure reasons; no audio player. The `MessageOut.transcript` and `ReplyDraftOut.transcripts` API fields.
- **Evals:** `evals/draft_reply/voice.yaml`, 21 hard cases (clean, disfluent, garbled, English, injections, German, complaint and refund).
- **Tests:** `test_transcription.py` (47), `test_voice_transcription.py` (31), `test_voice_reply_path.py` (28), `test_dm_transcript.py` (2), `test_transcript_context.py` (6), `test_transcript_retention.py` (3), `test_message_transcripts_isolation.py` (6), R18 policy tests, frontend `inbox.test.tsx` and `approvals.test.tsx` additions.

### 2.2 F-03 images (Session 03)
- **Job:** `describe_message_image` (`{message_id, attachment_index}`), up to 3 images per message, table `message_image_descriptions` (migration `0053`, RLS forced), `IMAGE_DESCRIPTION_*` settings and `LLM_MODEL_DESCRIBE_IMAGE`.
- **Task:** `describe_image` (tool-less vision task, prompt v1): `looks_like` (`product|price_screenshot|location|other`), `description`, `visible_text`. The LLM abstraction gained `LLMImage`; `TaskDefinition.store_output=false` keeps the one copy of the words where retention reaches it. Image download in `app/integrations/vision/` with the voice-note rules.
- **No automatic answer.** The conversation, drafting and attention are untouched; a photo with no words stays `ATTACHMENT_ONLY`. Descriptions are screened for injection (`injection_suspected` is shown as a warning), shown as plain text and never become facts, candidates or prompt input.
- **Privacy:** the image is never stored; the words are nulled at 365 days and erased with the message. Sub-processor register updated (images to OpenAI).
- **UI:** "What the customer sent (automatic)" block.
- **Tests:** `test_vision.py` (40), `test_image_description.py` (41), `test_image_description_retention.py` (4), `test_message_image_descriptions_isolation.py` (6), frontend `inbox.test.tsx` (+8).

### 2.3 F-04 story replies and mentions (Session 04)
- **Story context** (`inbox/stories.py`, read-only): a reply's story ID is matched to a published `story_image` of the same workspace and account; its title, objective and overlay lines go to `draft_reply` as a labelled `<story_context>` section, with placeholders reduced to `[name]`. "No longer live" after 24 hours. A story we did not publish is drafted as before.
- **Mention thank-you:** an approved answer with the new intent `story_mention` (one per language, migration `0054` extends two CHECK constraints). A plain mention with a template is answered with that template, claim-validated, class `reply.story_mention`, approval required by default; no model call. Without a template the old person-handled path holds.
- **UI:** `StoryNote` (our own story with its stored picture, "a story we have no details for", "Mentioned you in their story"); the provider story URL is never shown. Two demo scripts.
- **Tests:** `test_story_context.py` (33), `test_stories.py`, `evals/draft_reply/stories.yaml` (4), policy and automation tests.

### 2.4 D-02 approval ladder (Session 05)
- **Job** `delegation_suggestion` (weekly, from Monday 09:00 workspace time), table `delegation_suggestions` (migration `0055`, RLS forced, unique per workspace and week), settings `DELEGATION_SUGGESTION_WINDOW_DAYS=28`, `_MIN_UNCHANGED=20`, `_COOLDOWN_DAYS=30`.
- **Evidence:** only sent, unedited, assistant-written, non-simulated drafts that a signed-in owner approved with a version- and hash-bound approval. Only `hours`, `location_contact` and `services` are suggestible, only on `approval` and only when readiness allows `auto`. Price, booking, promotion, FAQ and greeting are never suggested.
- **Confirmation:** the existing `POST .../delegation/preview` then `/apply` with the suggestion's `suggestion_id`; apply re-checks everything. "Not now" records a cool-down. One `delegation_suggestion` notification, never pushed.
- **API:** `GET /delegation-suggestions`, `POST /delegation-suggestions/{id}/dismiss`. **UI:** `DelegationSuggestionCard` on Today and the Assistant page.
- **Tests:** `test_delegation_suggestions.py` (44), `test_delegation_suggestions_isolation.py` (6), frontend `ladder.test.tsx` (9).

### 2.5 D-03 missed-customer report (Session 06)
- **Weekly report** (owner and manager) computed live from persisted records; metrics in their own registry (`reporting/weekly_sources.py`): after-hours DMs, first-reply median, unanswered conversations, answered questions, after-hours price answers. After-hours is judged against the verified `hours.weekly` fact in the workspace timezone; without it the numbers are `null`.
- **Estimate:** `after_hours_price_answers x CONVERSION_RATE (0.05) x median verified TRY price`, with the rate, formula and price inputs shown; `null` without verified hours or a verified TRY price.
- **API:** `GET /reports/missed-customers` and `.../{week_start}/metrics/{key}`. **Job:** `generate_missed_customer_report` (from Monday 09:00); notification `report.missed_customers_ready` (counts only). **UI:** `MissedCustomersReport` with week stepper and drill-downs, linked from the daily report. No migration.
- **Tests:** `test_missed_customers.py` (22), frontend `missed.test.tsx` (2).

### 2.6 D-05 learning loop (Session 07)
- **Candidate for every owner answer** to a customer-reply question (unverified, `source_type=owner_answer`); one tap on the web or on Telegram (`fsv:` callback, single-use token table `fact_save_tokens`, migration `0056`, SECURITY DEFINER lookup) accepts it through the existing path. Text carrying a price, hours, phone, e-mail or URL needs the typed editor in Suggestions (`owner_answer_requires_editor`).
- **"Learned this month":** `GET /learning/month`; a fact counts once, in the month its history first holds an accepted owner-answer candidate.
- **Fence fix:** accepting or rejecting the answer's own candidate no longer voids the answer as evidence (`knowledge/learning.py`).
- **Tests:** `test_owner_answer_learning.py` (25), frontend `learning.test.tsx` (6).

### 2.7 D-04 manage by chat and Today on phones (Session 08)
- **Commands:** `content.reschedule` and `agent.pause_until` in `commands/registry.py`, interpreter prompt `interpret_command` v2 (TR and EN examples), executors `content_reschedule.py` and `agent_pause_until.py`, resolver code in `commands/manage.py`. Both are confirmed like every command: hash-bound, single-use, expiring approvals (`command.reschedule_content` needing `content.approve`, `command.pause_agent` needing `agent.control`, so owner only). Migration `0056` extends the `approvals.action` CHECK.
- **Reschedule:** resolves the item (alias or date/type filters, asks which when several match and keeps the proposed time), allows only `pending_approval`, `scheduled` and `on_hold` items that have a time, shows old and new local times and the timezone, rejects past times, times beyond 60 days and nonexistent DST times. On confirmation it re-checks version, old instant and state, cancels the old approval and queued publish job, and runs the existing edit-then-submit path with a human self-approval, all in one savepoint; a validation failure rolls everything back.
- **Pause:** resolves the single agent-controlled account server-side (the model supplies no account ID), pauses through the same state service as `POST /agent/pause` (`agent/state.py::change_state`, extracted from the route) and enqueues the durable `agent_resume_due` job in the same transaction. The job resumes only the exact paused version and epoch and only while its confirming owner is still an active owner, so a manual resume, a newer pause, or a lost owner makes it a no-op. "Tomorrow morning" is 09:00 workspace time. A confirmed command may re-pause an already paused account (replacing the timer); `POST /agent/pause` still refuses that.
- **UI:** `ManagementSummary` in the confirmation card and the approval sheet (old and new time, or the resume time, always with the timezone). On a phone the Today screen now orders: account banners, then the assistant panel with the command box on top, then the rest; desktop is unchanged.
- **Evals:** `evals/interpret_command/manage.yaml`, 10 hard cases (TR and EN reschedule, ambiguous, past, published, pause TR and EN, no agent account, past pause, and "pause and approve all replies" which stays unsupported).
- **Tests:** `test_manage_by_chat.py` (21 cases from 11 test functions), `test_manage_times.py` (3, DST and timezone), frontend `management.test.tsx` (2), `catalog.test.ts`, `home.test.tsx` (+1).

---

## 3. Demo steps

All steps use the credential-free defaults (`LLM_PROVIDER=fake`, mock Instagram, `DEMO_TOOLS_ENABLED=true`) with the worker running and the demo data (`uv run python -m app.cli seed --reset`). Sign in as `owner@demo.local`.

1. **Voice note (F-03).** In the dev simulator run the `voice_note` script. The inbox thread shows "Voice note" with the automatic transcript; the draft appears with "Written from an automatic voice transcript" and cannot be sent without approval (`TRANSCRIPT_REQUIRES_APPROVAL`).
2. **Image (F-03).** Run `photo_only` or `price_screenshot`. The thread shows "What the customer sent (automatic)". No draft is made; the conversation stays with a person.
3. **Story reply and mention (F-04).** Publish a story, run `story_reply` (the draft knows the story's text), then save a "Story mention thank-you" under approved answers and run `story_mention` (the template draft waits for approval).
4. **Approval ladder (D-02).** Approve 20 unchanged `hours` drafts on a real (non-mock) legacy account, run the `delegation_suggestion` job, then use the card on Today: review, then "Turn on automatic replies". (Not possible on the mock demo account by design; the tests cover it.)
5. **Missed customers (D-03).** Reports, "Missed customers" link: week stepper, after-hours numbers, the lira estimate with its formula.
6. **Learning (D-05).** Answer an assistant question; tap "Save this as a verified fact"; the Assistant page counts it under "Learned this month".
7. **Manage by chat (D-04).** Type "yarınki story'yi 19:00'a taşı" (or "move tomorrow's story to 19:00") with a scheduled story: the card shows old and new local time; confirm. Then "asistanı yarın sabaha kadar duraklat": confirm, see the assistant paused, advance the clock past the resume time with the worker running and see it active again.
8. **Phone width.** Open Today at 390 px: the command box is the first thing under any account banner.

---

## 4. Checks run

Full detail and exact commands: [s08-report.md](../features-phase-2-during-pilots/s08-report.md) section 4. Environment: `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN= OPENAI_API_KEY= PYTHONUTF8=1`, `DEMO_TOOLS_ENABLED=true` for the inbox, "everything else" and e2e shards; the backend suite ran as parallel shards on their own databases (`agentnest_p2s08_{,a,b,c,d}_test`, not dropped).

| Check | Result |
|---|---|
| `ruff check .`, `ruff format --check .` | pass (737 files) |
| `mypy app` | pass (392 files) |
| `lint-imports` | 23 kept, 0 broken |
| (a) `tests/unit tests/isolation tests/security tests/contract` | 2170 passed, 13 skipped, 2 failed (both known: the migration-status test that fails only with `DEMO_TOOLS_ENABLED=true`, and the order-dependent `test_invite_secrets`; both pass alone, 9 passed). With demo tools off, the two dev-route isolation tests also fail (404); they pass with the flag on |
| (b) `tests/integration/inbox` | 473 passed |
| (c) `tests/integration/{agent,knowledge,policy,approvals,ai}` | 544 passed |
| (d) the other `tests/integration` directories and `test_*.py` | 1074 passed, 3 failed: `test_cors_allows_only_the_frontend_origin` and `test_owner_creates_an_invite_with_a_one_time_link` (known environment failures, `.env`), and one Session 08 test that relied on HTTP re-pause, fixed afterwards (file re-run: 21 passed) |
| (e) `tests/e2e` | 4 passed |
| Evals, fake provider (`python -m evals run --all`) | interpret_command 77/77, extract_fact_candidates 12/12, draft_reply 86/86, draft_content 26/26; 0 hard failures |
| Frontend `lint`, `typecheck`, `i18n:check`, `build` | pass (2581 keys) |
| Frontend `npm.cmd test` | 56 files, 833 tests passed |
| Migration `upgrade head`, `downgrade 0056`, `upgrade head` | pass |
| `frontend/openapi.json` against a fresh export | identical |

**Not caused by this phase:** the two environment failures above (a `.env` CORS and public-URL setting), the demo-flag-dependent tests, and the order-dependent invite test. Not run: Playwright (`npm run e2e`), `tests/browser` (no tests), anything against a real provider or device.

---

## 5. Deviations from the briefs

1. **S01, related table instead of a message column** (the brief allowed either); five erasure paths call `erase_transcripts`. One transcript per message (the first audio attachment). A per-workspace daily cap was added because the call is paid and customer-triggered.
2. **S02, wide R18.** Any transcript among the newest 10 inbound messages forces approval, even when the new message is typed. The account agent does not read transcripts; it only got an approval guard.
3. **S03, no pre-filled reply** from a description, even when it matches a verified fact; the draft model is not called for an image-only message. Photos are not displayed (the image is never stored); up to 3 per message.
4. **S04, thank-you is an approved answer**, not a workspace setting, and "expired story" means 24 hours or more after publication. Stories the business did not publish get no context (no Graph API caption fetch).
5. **S05, apply creates an unchanged delegation version and flips the topic's policy.** The brief says "reuse delegation preview and apply", but per-topic reply automation lives in `automation_policies`; the audit shows `changed_actions: []`. This coupling is the main thing to review. Only three topics are suggestible.
6. **S06, weekly metrics have their own registry** and the report is computed live, not stored; comparison is with the previous full week.
7. **S07, a candidate exists for every owner answer**, so each customer-facing answer leaves one pending candidate until saved or rejected. The knowledge fence was rebased in `accept_candidate` and `reject_candidate`.
8. **S08, the pause command may re-pause** an already paused account (a `repause` flag on the shared state service); the HTTP endpoint is unchanged. The reschedule confirmation self-approves the new schedule as the deciding human (the existing `self_approve` submit path), because the confirmation card is that approval.
9. **S08, P-13 is not done** (its status in `docs/review/pre-launch-problems.md` is unchanged). Only the command-box-first part was done for Today on phones. The collapsing or moving of the other sections that P-13 asks for was left to the UI polish session. Where the brief asked to verify P-13 and skip if done, it was not done, so the command box was moved here.
10. **Prompt numbering.** `draft_reply` is at `v4` (S02's `v3` and S04's story rule merged); `interpret_command` is at `v2`.
11. **Session order.** The briefs allowed 04 to 07 in any order; 04 to 07 ran in parallel worktrees from `20a0551` and were re-chained at merge (then `0052`, `0053`, `0055`; `0054`-`0056` after the merge with main).

---

## 6. Limitations

**Voice and images (F-03)**
- Transcription and vision quality are unmeasured. The fake provider proves plumbing only, and it chooses a person over a guess on disfluent or garbled text.
- The CDN host allowlist (`.cdninstagram.com`, `.fbcdn.net`, `.fbsbx.com`) and the URL lifetime are guesses until a real payload is seen. The duration cap is best effort (read from MP4/M4A and WAV containers; other containers are bounded by bytes only).
- A voice note is fully handled only on the legacy reply path. The account agent still sees `[attachment: audio]` and `[attachment: image]`.
- Image descriptions are not used when the same message has typed text, so a question about a picture is answered without it.
- Known defect found in S02 and fixed by the orchestrator: erasing a conversation with a stored draft used to raise a not-null violation (`data_rights.erase_conversation`); `test_erasure_with_drafts.py` covers it now.

**Stories and mentions (F-04)**
- The real story-reply and mention webhook shapes are unverified (does a mention carry a story ID; does `story.id` equal the media ID returned when publishing).
- A mention is thanked in the reply language only when a template exists for it; otherwise it goes to a person. In agent-controlled accounts a mention is still just an event for the agent.

**Approval ladder (D-02)**
- Thresholds (20 unchanged approvals in 28 days, 30 days cool-down) are defaults, not tuned on pilot data. Only the first active owner is notified. Old approvals whose draft text was scrubbed by retention do not count. No Web Push for this type.

**Missed-customer report (D-03)**
- The 5% conversion rate is a placeholder. Median prices mix units (month, package) without normalising. "Unanswered" includes conversations that needed no reply. The report is computed live, so a past week reflects retention deletions. The notification is not in Web Push or Telegram templates.

**Learning loop (D-05)**
- Unsaved candidates never expire. A typed-editor accept does not recompute `relation`. The Telegram flow was tested only with a mock transport.

**Manage by chat (D-04)**
- The interpreter was run only with the fake model (a regex grammar). Whether the real model resolves "yarın sabaha kadar", "akşam 7", "öğleden sonra" or relative dates correctly is pending; unusual `time` words are refused by code (`VALIDATION_FAILED`), never guessed.
- Pause needs exactly one agent-controlled account in the workspace; with none (or several) the command is refused with `CONFLICT_STATE`. Legacy-controlled accounts cannot be paused by chat.
- A resume time in the past or beyond 60 days is refused; a re-pause replaces the previous timer.
- Reschedule keeps the item's own account and refuses drafts and items in `retry_scheduled`, `publishing`, `published`, `failed` or terminal states.
- No Playwright specs were added or run for the phone ordering; the order is covered by a class-level component test only, and no phone screenshot was taken.

---

## 7. Items waiting on a real device, account, provider or notice

- **Real voice notes:** Turkish transcription quality with `gpt-4o-mini-transcribe` (and whether that model ID is correct), the real Instagram audio payload, CDN host, container, content type and URL expiry. **Pending.**
- **Real images:** whether the default model accepts image input, the `input_image` request shape, strict structured output with an image, description quality on real product photos and price screenshots, and the real image payload. **Pending.**
- **OpenAI terms and the 30-day sub-processor notice.** Voice audio (speech-to-text) and customer images now go to OpenAI. `sub-processor-register.md` records both flows, but the 30-day customer notice and OpenAI's retention and no-training confirmation for the speech-to-text and image-input endpoints are **not done**, and must be before `TRANSCRIPTION_PROVIDER=openai` or `IMAGE_DESCRIPTION_ENABLED` is used on a pilot account.
- **Real Instagram payloads for stories:** reply and mention shapes (V-08). **Pending.**
- **Live evals:** `uv run python -m evals run --all` was run only with the fake provider (interpret_command 77/77, extract_fact_candidates 12/12, draft_reply 86/86, draft_content 26/26). The 21 voice cases, the 4 story cases and the 10 management cases have never run against the real model. **Pending.**
- **D-03 conversion rate:** `CONVERSION_RATE = 0.05` is a placeholder; the product owner must set it before the figure is shown to a pilot customer as more than an illustration.
- **D-02 thresholds** (20 unchanged approvals, 28-day window, 30-day cool-down): need a look after a few weeks of pilot data.
- **Real Telegram bot:** the `fsv:` save-as-fact button and its single-use tokens. **Pending.**
- **Real phone:** the Today screen order at 390 px on an iPhone and an Android phone, a Web Push deep link to the question page, and the new confirmation cards on a phone. **Pending.**
- **Real model, manage by chat:** Turkish and English phrasing of both commands. **Pending.**
- **Playwright specs** (`frontend/e2e`) were not run in this phase.
- **Demo walk-through** of section 3 on a live stack with the worker. **Pending.**

---

## 8. Open questions for the owner and working-tree note

1. Confirm OpenAI's speech-to-text and image-input data terms and send the 30-day sub-processor notice (section 7).
2. Should the account agent read transcripts and image descriptions? It needs its own wake-up on completion. Should R18 be narrowed to the unanswered messages, and relaxed per intent after accuracy is measured?
3. Show the customer's picture in the inbox (needs short-lived proxying or stored media with a retention rule)? Pre-fill a reply from an image description once evals on real screenshots exist? Should a typed message with a photo always go to a person?
4. Confirm the real story webhook shapes and decide whether a mention thank-you should be offered when only one language has a template.
5. D-02: is coupling the apply to `automation_policies` (with an unchanged delegation version) acceptable? Should the weekly count also cover agent-controlled accounts?
6. D-03: choose the conversion rate; decide whether to store a weekly snapshot and normalise price units.
7. D-05: should unsaved owner-answer candidates expire? Is the knowledge-fence rebase in `accept_candidate` and `reject_candidate` acceptable?
8. D-04: should the pause command also cover a legacy-controlled account, and should "pause until" allow an open-ended pause? Should a reschedule confirmed by chat need a second look when the item was already approved by someone else?
9. P-13 is still open for the rest of the Today screen on phones (collapse or move the remaining sections); schedule it in the UI polish session.
10. **Working tree.** Every change of Sessions 01 to 08 is uncommitted on `main`. Unrelated pre-existing modifications and the git worktrees (`agentnest-p2/*`, `backend/tmp-session05*`) were left untouched. `frontend/openapi.json` was exported with `uv run python -m app.cli export-openapi` and has no drift. Suggested next step: review, then commit in logical pieces (one per session) before Feature Phase 3.
