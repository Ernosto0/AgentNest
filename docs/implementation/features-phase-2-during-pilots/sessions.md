# Feature Phase 2: During Pilots

**Status:** Sessions 01–08 implemented and verified offline; stopped for review (2026-11-17). See the [Session 08 report](s08-report.md) and the [phase summary](../phase-summaries/features-phase-2-summary.md) for checks, known environment failures and the live items that are still pending. Nothing committed.
**Source:** [pre-launch-feature-recommendations.md](../../review/pre-launch-feature-recommendations.md) §4, step 2, plus D-04 and D-05, which §4 left unplaced.
**Features:** F-03 (voice and image understanding), F-04 (story replies and mentions), D-02 (approval ladder), D-03 (missed-customer report), D-05 (learning loop), D-04 (manage by chat).
**Sessions:** 8. Sessions 01–03 are in order. Sessions 04–07 are independent and can run in any order once Feature Phase 1 is closed. Session 08 closes the phase.
**Gate:** [Feature Phase 1](../features-phase-1-before-first-pilot/sessions.md) is closed and reviewed. Pilot feedback can reorder sessions 04–08; record any reordering in the session report.

---

## 1. Plan

| Session | Feature | Scope | Main deliverables |
|:---:|---|---|---|
| 01 | F-03 | Voice transcription foundation | Audio fetch, transcription provider abstraction (fake and OpenAI), transcript stored on the message |
| 02 | F-03 | Voice in the reply path | Transcripts drafted like text, approval forced, transcript label in UI, eval cases |
| 03 | F-03 | Image description for the owner | "What the customer sent" description in the inbox; no automatic answer |
| 04 | F-04 | Story replies and mentions | Story context in drafting, owner-approved thank-you for mentions |
| 05 | D-02 | Approval ladder suggestions | Weekly job, one notification with confirm, reuses delegation preview and apply |
| 06 | D-03 | Missed-customer report in lira | Weekly summary with after-hours DMs, reply time and a TRY estimate from verified prices |
| 07 | D-05 | Visible learning loop | One-tap "save as verified fact" after an owner answer, "learned this month" count |
| 08 | D-04 | Manage by chat, and phase close-out | Reschedule and pause commands, command box first on phones, phase summary |

## 2. Starting state

- Confirm the migration head and the Feature Phase 1 summary before starting.
- An attachment-only DM becomes a person-handled message: `backend/app/inbox/drafting.py` (`attachment_only` branch, around line 242) and `backend/app/inbox/context.py`. Attachments are parsed in `backend/app/integrations/instagram/webhook_format.py` (`_attachments`). Story replies already arrive as an attachment of `type: "story_reply"` with the story URL and ID.
- The LLM abstraction (`backend/app/integrations/llm/base.py`) has `generate_structured` and `generate_step` only. There is no audio or vision method. The provider is OpenAI (see the memory note "OpenAI is the LLM provider"); `fake` is the offline default.
- Language detection is in `backend/app/inbox/language.py`. Only `tr` and `en` are supported.
- Delegation endpoints: `POST /agent/delegation/preview`, `POST /agent/delegation/apply`, `GET /agent/delegation`, `POST /agent/pause` and `POST /agent/resume` in `backend/app/agent/router.py`.
- Owner answers already create unverified fact candidates (`backend/app/owner_requests/service.py`, `propose_candidate`, `answer.candidate_id`).
- Command executors are in `backend/app/commands/executors/`. They include `update_fact` and `content_cancel`, but there is no reschedule and no pause.
- Reporting is in `backend/app/reporting/` (`definitions.py`, `metrics.py`, `summary.py`, `jobs.py`).

## 3. Common working rules

Before each session, read [CLAUDE.md](../../../CLAUDE.md), [invariants.md](../../invariants.md), this file's common rules and the session brief, and the previous report in this folder (for sessions 04–07, the latest report).

1. **Preserve unrelated work.** Check `git status`, the migration head and uncommitted changes first. Do not use `git stash`. Do not reset shared databases.
2. **Follow the invariants.** New tenant tables get RLS (enabled and forced), and foreign IDs return 404. There are no external calls inside a DB transaction, including media downloads and transcription calls. Time comes from `Clock`. No secrets go in logs or payloads.
3. **LLM output is a proposal.** New model tasks have no tools. Prices, hours, contacts and URLs still come only from `{{fact:key}}` placeholders and pass the claim validator. Customer content, including transcripts and image descriptions, is untrusted input and goes through the existing injection handling (`backend/app/ai/injection.py`).
4. **Keep the CI fixtures offline.** Every new provider call has a fake implementation, and tests never need a real key.
5. **Update docs with contracts.** That includes `docs/architecture/` for schemas, jobs and endpoints, `docs/legal/sub-processor-register.md` if a new data flow goes to a provider, and `mvp-scope.md` when a deferred item becomes in scope.
6. **Ship both languages**, Turkish and English, for all UI and notification strings.
7. **Report truthfully.** Live-provider quality, such as transcription accuracy on real Turkish voice notes, is "pending" until measured.
8. **Do not commit or push** unless the user asks.

**Checks.** Backend: `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run lint-imports && uv run pytest <paths>`. Frontend: `npm.cmd run lint && npm.cmd run typecheck && npm.cmd test && npm.cmd run i18n:check && npm.cmd run build`.

**Report.** Each session writes `sNN-report.md` in this folder: status, baseline commit, migration head, files, contracts, test commands and results, invariant notes, open questions and handoff.

---

## 4. Session briefs and prompts

### Session 01: Voice transcription foundation (F-03, part 1)

**Goal.** An Instagram voice note is downloaded and transcribed, and the transcript is stored on the message.

**Work**
- Update `mvp-scope.md` to add voice and image understanding to the in-scope list, with the "approval mandatory for transcript-based replies" rule.
- Identify how audio attachments arrive in real and mock webhooks (type, URL, expiry of the CDN URL). Extend `webhook_format.py` and the mock provider to produce audio attachments.
- Add a `transcribe_audio` capability behind a provider protocol, either next to the LLM provider or as its own small interface. Implement `fake` (deterministic transcript from a fixture) and `openai`. Read the model ID and size or duration limits from settings, and document them in `environment-variables.md`.
- Add a job: download the audio (outside the transaction, size and duration capped, content type checked), transcribe it, then store the transcript in a new column or a related row, with `source: "transcript"`, language, model and duration. Do not keep the raw audio longer than the existing media retention rules allow, and check `backend/app/retention/`.
- Handle failures (download expired, too long, provider error): the message stays a person-handled attachment, as it is today, with a reason code.
- Update `sub-processor-register.md` and the privacy notes, because audio goes to the transcription provider.
- Tests: webhook parsing, job success and failure paths, size cap, retention, isolation, and no external call inside a transaction.

**Out of scope.** Drafting from the transcript (Session 02). UI.

```text
Implement Feature Phase 2, Session 01 (voice transcription foundation) from docs/implementation/features-phase-2-during-pilots/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's starting state and common rules, and the Session 01 brief first. Update mvp-scope.md, parse audio attachments from real and mock webhooks, add a transcription provider interface with fake and OpenAI implementations, and add a job that downloads (capped, outside transactions), transcribes and stores the transcript with its metadata. Keep failures on the existing human path, and update the sub-processor register.

Run the backend checks, write s01-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

---

### Session 02: Voice in the reply path (F-03, part 2)

**Goal.** A transcribed voice note gets a draft like a text message, but the draft always needs approval, and the owner can see that it came from a transcript.

**Depends on.** Session 01.

**Work**
- Feed the transcript into `inbox/context.py` and `drafting.py` as the customer's text, marked as a transcript in the prompt context. The model must be told that the text may contain transcription errors.
- Add a policy rule in `backend/app/policy/` that forces at least `approval_required` for transcript-based drafts, whatever delegation says. Make it a deterministic rule with a reason code, not a model flag. Add tests showing that delegation cannot override it.
- Inbox UI: show the voice note player (if the media is kept), the transcript labelled "Transcript (automatic)", and the transcript language. In the approval view, show the same label.
- Add 10–15 eval cases with Turkish transcripts, including disfluent and misspelled ones, to the existing eval set. Record the results from the fake provider. List the live eval run as pending.

```text
Implement Feature Phase 2, Session 02 (voice in the reply path) from docs/implementation/features-phase-2-during-pilots/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 02 brief and s01-report.md first. Route transcripts into the normal draft path as labelled customer text, add a deterministic policy rule that always requires approval for transcript-based drafts (delegation cannot override it), show the transcript label in the inbox and approval views, and add Turkish transcript eval cases.

Run the backend and frontend checks, write s02-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

---

### Session 03: Image description for the owner (F-03, part 3)

**Goal.** When a customer sends a photo or screenshot, the owner sees a short description and any visible text. The assistant does not answer automatically.

**Work**
- Add a `describe_image` vision task (fake and OpenAI), with no tools and a structured output: short description, visible text, and whether it looks like a product, a price screenshot, a location, or other.
- Run it as a job for image attachments, with size limits, outside transactions and with retention respected.
- The conversation stays `human_required`. Show the description in the inbox under the image as "What the customer sent (automatic)". Optionally pre-fill a suggested reply, which stays a draft that requires approval, only when the description matches an existing verified fact. Decide this in the session, and record the decision.
- Treat visible text in the image as untrusted. It goes through injection handling and is never used as a fact.
- Update the sub-processor register. Add tests and TR and EN strings.

```text
Implement Feature Phase 2, Session 03 (image description for the owner) from docs/implementation/features-phase-2-during-pilots/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 03 brief and s02-report.md first. Add a tool-less describe_image vision task (fake and OpenAI) run as a capped job, store a structured description, and show it in the inbox for the owner. The conversation stays human_required, image text is treated as untrusted, and no automatic answer is sent. Update the sub-processor register.

Run the backend and frontend checks, write s03-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

---

### Session 04: Story replies and story mentions (F-04)

**Goal.** A reply to the business's story is drafted with the story as context. A story mention gets an owner-approved thank-you.

**Work**
- Find where `story_reply` attachments currently force `human_required`. Instead, fetch the story's caption or overlay text where the API allows it. If the story is one Pivoris published, use its stored content record. Pass it to drafting as "Customer is replying to this story: ...". If the story context cannot be found, keep today's behaviour.
- Add story mention ingestion (webhook format, mock provider). Create a mention item that offers a single owner-configured thank-you template. It is approval-required by default, and the delegation ladder can later make it automatic.
- Show the story thumbnail or text in the conversation view.
- Tests: story with known content, unknown story, expired story, mention with template, mention with no template configured.
- Update `docs/architecture/integrations.md` (webhook fields) and `docs/research/platform-capabilities.md` if you confirm new API facts. Mark anything unverified as unverified.

```text
Implement Feature Phase 2, Session 04 (story replies and story mentions) from docs/implementation/features-phase-2-during-pilots/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 04 brief and the latest report in that folder first. Replace the blanket human_required for story replies with drafting that uses the story's caption or our stored content as context, keeping the old behaviour when the context is missing. Add story-mention ingestion with a single owner-approved thank-you template, show story context in the conversation view, and update the integration docs.

Run the backend and frontend checks, write s04-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

---

### Session 05: Approval ladder suggestions (D-02)

**Goal.** The product proposes the next step of automation from the owner's own behaviour.

**Work**
- Add a weekly job that counts, per workspace and per intent, approvals in the last N days that were approved without edits, and any edits, rejections or failures. Put the thresholds (for example 20 unchanged and 0 edited) in settings or the policy config.
- Only suggest intents that delegation allows to be automatic (low-risk intents in the existing policy). Never suggest price-, booking- or complaint-type intents if policy forbids them.
- Create one notification per workspace per week at most, with a confirm button. Confirming opens the existing delegation preview (`POST /agent/delegation/preview`) and then applies it (`POST /agent/delegation/apply`). Free text never applies it. Dismissing records a cool-down.
- Audit both the suggestion and the decision.
- Add the notification type to `notifications/catalog.py`, and add a UI card on the Today screen and the Assistant page.
- Tests: threshold logic, forbidden intents never suggested, cool-down, isolation, and a single notification per week.

```text
Implement Feature Phase 2, Session 05 (approval ladder suggestions) from docs/implementation/features-phase-2-during-pilots/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 05 brief, the latest report in that folder, and backend/app/agent/delegation.py first. Add a weekly job that counts unchanged approvals per intent, suggests automation only for intents policy allows, sends at most one notification a week with a confirm button that goes through the existing delegation preview and apply endpoints, records dismissals with a cool-down, and audits everything.

Run the backend and frontend checks, write s05-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

---

### Session 06: Missed-customer report in lira (D-03)

**Goal.** A weekly report that shows the owner what the assistant saved them, in TRY.

**Work**
- Add metrics in `reporting/definitions.py` and `metrics.py`: DMs that arrived outside opening hours (from the verified hours fact), median time to first reply this week compared with the four weeks before activation or the previous period, conversations left unanswered, and price or booking questions answered.
- Estimate: "price questions answered outside hours × a conservative conversion rate × the median verified price". Show the formula and its inputs in the report. Never show a lira amount without its basis. If there is no verified price, show counts only.
- Exclude simulated data.
- Add a weekly job, a report page section, a summary in the daily or weekly notification, and a drill-down for each number, reusing `drilldown.py`.
- Tests: hours boundaries in the workspace timezone, missing hours fact, missing prices, no data, and isolation.

```text
Implement Feature Phase 2, Session 06 (missed-customer report in lira) from docs/implementation/features-phase-2-during-pilots/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 06 brief, the latest report in that folder, and backend/app/reporting/ first. Add weekly metrics for after-hours DMs, time to first reply, unanswered conversations and answered price questions, and a TRY estimate whose formula and inputs are shown and which comes only from verified prices (counts only when none exist). Exclude simulated data, add drill-downs, a weekly job and the report UI.

Run the backend and frontend checks, write s06-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

---

### Session 07: Visible learning loop (D-05)

**Goal.** Owners see the knowledge base grow from their daily answers.

**Work**
- After the owner answers an assistant question (web, Telegram or Web Push deep link), show "Save this as a verified fact?" with one tap. This accepts the candidate that `owner_requests/service.py` already creates, through the existing candidate accept endpoint. Free text never verifies it. Structured facts (prices, hours) still go through their typed editor if the value needs normalising.
- On Telegram, add an inline button using the existing action-token pattern. It is single-use and expiring.
- On the Assistant page, show "Learned N things from you this month", with a list linking to each fact. Count only facts verified from owner answers.
- Tests: accepting through web and Telegram, replay of the button, a structured fact that needs the editor, and the monthly count boundaries.

```text
Implement Feature Phase 2, Session 07 (visible learning loop) from docs/implementation/features-phase-2-during-pilots/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 07 brief, the latest report in that folder, and backend/app/owner_requests/service.py first. After an owner answers an assistant question, offer a one-tap "save as verified fact" on web and on Telegram (single-use action token), going through the existing candidate accept path, and add a "learned this month" count and list on the Assistant page.

Run the backend and frontend checks, write s07-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

---

### Session 08: Manage by chat, and phase close-out (D-04)

**Goal.** Common tasks have a command, the command box comes first on phones, and the phase is closed.

**Work**
- Add command executors in `backend/app/commands/executors/`:
  - `content_reschedule`: "move tomorrow's story to 19:00". Resolve the content, preview old and new times, and confirm before applying. Respect content state transitions.
  - `agent_pause_until`: "pause the assistant until tomorrow morning". Use the existing pause and resume endpoints, add an automatic resume time as a job, and confirm before applying.
- Register both in `registry.py` with interpreter examples in Turkish and English, and add eval cases for the interpreter.
- Move the command box to the top of the Today screen at phone widths (`frontend/src/features/home`). Coordinate with P-13 in [docs/review/sessions.md](../../review/sessions.md) (UI polish); if it is already done, verify and skip.
- Phase close-out: run all checks, write `docs/implementation/phase-summaries/features-phase-2-summary.md` (changes, tests per feature, demo steps, deviations, live items pending such as real voice-note quality) and update `roadmap.md`.

```text
Implement Feature Phase 2, Session 08 (manage by chat and phase close-out) from docs/implementation/features-phase-2-during-pilots/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 08 brief, all earlier reports in that folder, and backend/app/commands/registry.py first. Add confirmed content_reschedule and agent_pause_until commands with TR and EN interpreter examples and eval cases, and put the command box first on the Today screen at phone width (skip if P-13 already did it).

Then close the phase: run all backend and frontend checks, write s08-report.md and docs/implementation/phase-summaries/features-phase-2-summary.md, update roadmap.md, and stop for review. Preserve unrelated work. Do not commit or push.
```
