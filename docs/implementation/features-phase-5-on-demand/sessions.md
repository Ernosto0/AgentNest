# Feature Phase 5: On Demand

**Status:** Implemented and verified offline (2026-11-18). All 12 sessions across all five tracks are implemented and verified offline, stopped for review, nothing committed, live items pending. See the five track summaries: [Track A: WhatsApp](../phase-summaries/features-phase-5-whatsapp-summary.md), [Track B: Media](../phase-summaries/features-phase-5-media-summary.md), [Track C: Follow-up](../phase-summaries/features-phase-5-followup-summary.md), [Track D: Languages](../phase-summaries/features-phase-5-languages-summary.md), [Track E: Leads](../phase-summaries/features-phase-5-leads-summary.md).
**Source:** [pre-launch-feature-recommendations.md](../../review/pre-launch-feature-recommendations.md) §4, step 5.
**Features:** F-06 (WhatsApp owner channel), F-08 (carousels and Reels), F-10 (customer follow-up and the 7-day human reply), F-11 (more reply languages), F-12 (light lead list with export).
**Sessions:** 12 in five independent tracks. Do not start a track until its trigger is met. Within a track, run sessions in order. Some tracks may never be needed.

---

## 1. Plan

| Track | Trigger (from [mvp-scope.md](../../product/mvp-scope.md) §4) | Session | Scope |
|---|---|:---:|---|
| A. WhatsApp (F-06) | OQ-01 answered: pilot owners will not use Telegram or push | 01 | Policy decision, ADR, WhatsApp Cloud API client, account linking |
| | | 02 | Notifications and the daily summary through approved message templates |
| | | 03 | Approval buttons with action tokens, plus track close-out |
| B. Carousels and Reels (F-08) | Pilot demand | 04 | Carousel data model and validation |
| | | 05 | Carousel publishing and UI |
| | | 06 | Video upload, validation and storage for Reels |
| | | 07 | Reels publishing and UI, plus track close-out |
| C. Follow-up and late replies (F-10) | Pilot demand for late replies | 08 | One follow-up message inside the 24-hour window |
| | | 09 | Human Agent tag for manual replies up to 7 days |
| D. More languages (F-11) | OQ-11: the tourism segment starts | 10 | Language detection and claim-validator formats for ru, de, ar |
| | | 11 | Eval sets, workspace settings and RTL check, plus track close-out |
| E. Lead list (F-12) | Owners ask for a call-back list | 12 | Filtered view and CSV export |

**Close-out.** Each track's last session writes `docs/implementation/phase-summaries/features-phase-5-<track>-summary.md` and updates `roadmap.md`. There is no single phase close-out, because tracks run at different times.

## 2. Starting state

Check these again when a track starts, because the code will have moved since this file was written.

- Owner channels: `backend/app/integrations/channels/` (`base.py`, `registry.py`, `telegram/`), action tokens and the delivery policy from Phase 9, and Web Push from Feature Phase 1.
- Content types: `feed_image` and `story_image` in `backend/app/content/models.py`. Validation is in `content/validation.py` and `content/media.py`. Publishing goes through `backend/app/operations/publish.py`.
- Sending: `backend/app/operations/send.py`. The 24-hour window and reply workflow are in `backend/app/inbox/reply_workflow.py` and `expiry.py`.
- Languages: `backend/app/inbox/language.py` returns `UNSUPPORTED` for anything other than `tr` and `en`. The claim validator is in `backend/app/knowledge/claims.py`. Formatting is in `knowledge/formatting.py`.
- Customer memory: `backend/app/memory/`. Conversations and drafts: `backend/app/inbox/`.
- WhatsApp policy risk: [platform-capabilities.md](../../research/platform-capabilities.md) §2.

## 3. Common working rules

Before each session, read [CLAUDE.md](../../../CLAUDE.md), [invariants.md](../../invariants.md), this file's common rules and the session brief, and the previous report in this folder for the same track.

1. **Check the trigger first.** At the start of a track's first session, confirm with the user that the trigger is met, and update `mvp-scope.md` to move the item out of Deferred.
2. **Preserve unrelated work.** Check `git status`, the migration head and uncommitted changes. Do not use `git stash`.
3. **Follow the invariants.** RLS, 404 for foreign IDs, external effects only through the `operations` ledger, reconciliation before retry, no auto-resend of an ambiguous DM, no external calls in transactions, time from `Clock`, and secrets kept out of logs, payloads and responses.
4. **Keep the CI fixtures offline.** Every new provider has a mock or fake, and live harnesses are skipped without credentials.
5. **Update docs with contracts.**
6. **Ship both languages**, Turkish and English, for UI strings. Track D adds customer reply languages, not UI languages.
7. **Report truthfully.** Live results stay "pending" until recorded.
8. **Do not commit, push or send live messages** unless the user asks.

**Checks.** Backend: `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run lint-imports && uv run pytest <paths>`. Frontend: `npm.cmd run lint && npm.cmd run typecheck && npm.cmd test && npm.cmd run i18n:check && npm.cmd run build`.

**Report.** Each session writes `sNN-report.md` in this folder.

---

## 4. Session briefs and prompts

### Track A: WhatsApp owner channel (F-06)

#### Session 01: Policy decision, ADR, client and linking

**Work**
- Confirm OQ-01's answer with the user. Read WhatsApp Business policy on AI assistants and record the reading with sources in `platform-capabilities.md`. Write ADR-027 (check that this is the next number): notifications and buttons only, with no free-text commands on WhatsApp, explaining why.
- Add a WhatsApp Cloud API client (send template message, send interactive buttons, webhook verification) with a mock transport. Put credentials in settings, and document them.
- Add account linking through the existing channel-link flow (one-time code). Extend the channel check constraints with a migration.
- Import-linter contract: core modules never import the adapter.

```text
Implement Feature Phase 5, Session 01 (WhatsApp policy, ADR, client and linking) from docs/implementation/features-phase-5-on-demand/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's starting state and common rules, the Track A notes, ADR-012 and docs/research/platform-capabilities.md §2 first. Confirm with me that OQ-01 is answered before writing code. Then update mvp-scope.md, record the WhatsApp AI policy reading with sources, write the next ADR (notifications and buttons only, no free-text commands), add a WhatsApp Cloud API client with a mock transport, extend the channel-link flow and constraints, and add an import-linter contract.

Run the checks, write s01-report.md in the same folder, and stop. Preserve unrelated work. Do not commit, push or send live messages.
```

#### Session 02: Notifications and daily summary

**Work**
- Implement `WhatsAppChannel` against `OwnerChannel`, using the delivery ledger and quiet hours. Outside the 24-hour customer-service window, only approved templates may be sent. Define the template texts (TR and EN) and document the template submission steps.
- Deliver the daily summary and the same notification types as Web Push. Track the cost per message in the delivery metadata, because WhatsApp charges per conversation.
- Tests: template versus session message selection, quiet hours, failures and isolation.

```text
Implement Feature Phase 5, Session 02 (WhatsApp notifications and daily summary) from docs/implementation/features-phase-5-on-demand/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 02 brief and s01-report.md first. Implement WhatsAppChannel on the delivery ledger and quiet-hours policy, use approved templates outside the 24-hour window, deliver the daily summary and notification types, record per-message cost metadata, and document template submission.

Run the checks, write s02-report.md in the same folder, and stop. Preserve unrelated work. Do not commit, push or send live messages.
```

#### Session 03: Approval buttons, plus track close-out

**Work**
- Add interactive approve and reject buttons that carry single-use, hashed, expiring action tokens, reusing the Phase 9 implementation. Replay and stale approvals show the current state. Free text never decides.
- Add the P9-05-style edge-case tests: forwarded buttons, replay, expiry, unlinked user, duplicate webhook.
- Add a live probe harness (skipped without credentials).
- Track close-out: write `features-phase-5-whatsapp-summary.md` and update `roadmap.md`.

```text
Implement Feature Phase 5, Session 03 (WhatsApp approval buttons and track close-out) from docs/implementation/features-phase-5-on-demand/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 03 brief, s02-report.md and the Phase 9 action-token code first. Add approve and reject buttons that use single-use, hashed, expiring action tokens, add replay, forwarding, expiry, unlinked-user and duplicate-webhook tests, and add a skipped-by-default live harness.

Run all checks, write s03-report.md and docs/implementation/phase-summaries/features-phase-5-whatsapp-summary.md, update roadmap.md, and stop for review. Preserve unrelated work. Do not commit, push or send live messages.
```

---

### Track B: Carousels and Reels (F-08)

#### Session 04: Carousel data model and validation

**Work**
- Update `mvp-scope.md`. Add a `feed_carousel` content type with an ordered list of 2–10 media items (a migration for the content type check and an ordered child table, with RLS), each validated with the existing image rules and a shared aspect ratio.
- Update the state machine docs, approval payload hashing (the media order is part of the hash), and the price-change hold (any item using a fact).
- Tests: ordering, limits, mixed aspect ratios rejected, approval invalidated when the order changes, isolation.

```text
Implement Feature Phase 5, Session 04 (carousel data model and validation) from docs/implementation/features-phase-5-on-demand/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules and the Track B notes first. Confirm with me that pilot demand triggers this track. Then update mvp-scope.md, add a feed_carousel content type with an ordered, RLS-protected list of 2–10 validated images, include media order in the approval hash, extend the price-change hold, and update the state-machine and data-model docs.

Run the checks, write s04-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

#### Session 05: Carousel publishing and UI

**Work**
- Publish through the operations ledger: one child container per item, then the carousel container, then publish. Reconcile each step before retry. Mock provider support is required. The Meta implementation follows the documented container flow.
- UI: multi-select upload, drag to reorder, preview, and the per-item caption rules Instagram allows.
- Tests: partial container failure and reconciliation, and no duplicate publish.

```text
Implement Feature Phase 5, Session 05 (carousel publishing and UI) from docs/implementation/features-phase-5-on-demand/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 05 brief, s04-report.md and backend/app/operations/publish.py first. Publish carousels through the operations ledger (child containers, carousel container, publish) with reconciliation before any retry, in both the mock and Meta providers, and add multi-upload, reorder and preview UI. Test partial failure and duplicate prevention.

Run the backend and frontend checks, write s05-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

#### Session 06: Video upload, validation and storage for Reels

**Work**
- Add video media: upload limits (size, duration, resolution, codec) from Meta's Reels requirements (record the source), server-side probing (for example `ffprobe` from a pinned dependency, documented in deployment), thumbnail extraction, storage on the existing backends, and retention.
- Do not transcode at first: reject unsupported files with a clear reason.
- Update deployment docs for the new binary, and the storage cost notes.

```text
Implement Feature Phase 5, Session 06 (video upload and validation for Reels) from docs/implementation/features-phase-5-on-demand/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 06 brief and s05-report.md first. Add video media with limits taken from Meta's documented Reels requirements (cite them), server-side probing with a pinned tool, thumbnail extraction, storage and retention, and clear rejection reasons (no transcoding). Update the deployment docs for any new binary.

Run the checks, write s06-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

#### Session 07: Reels publishing and UI, plus track close-out

**Work**
- Add a `reel` content type and publish through the ledger. Container processing takes longer, so poll status with backoff as a job and never block a request.
- UI: video upload with progress, cover selection, preview, and the processing state.
- Track close-out: write `features-phase-5-media-summary.md` and update `roadmap.md`.

```text
Implement Feature Phase 5, Session 07 (Reels publishing and track close-out) from docs/implementation/features-phase-5-on-demand/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 07 brief and s06-report.md first. Add a reel content type published through the operations ledger with container status polled as a backoff job, plus upload-progress, cover and processing-state UI.

Run all checks, write s07-report.md and docs/implementation/phase-summaries/features-phase-5-media-summary.md, update roadmap.md, and stop for review. Preserve unrelated work. Do not commit or push.
```

---

### Track C: Follow-up and late replies (F-10)

#### Session 08: One follow-up message inside the 24-hour window

**Work**
- Update `mvp-scope.md`. Add a rule: when a customer asked about a price or booking, got an answer, and went quiet for X hours (configurable, default off), create one follow-up draft. It requires owner approval by default. Allow at most one per conversation, and never once the 24-hour window has closed. The window check is deterministic at send time as well as at draft time.
- The follow-up text uses facts through placeholders like any reply.
- Settings toggle, report metric, tests (window boundary, one per conversation, customer replies in between cancels it, isolation).

```text
Implement Feature Phase 5, Session 08 (single customer follow-up) from docs/implementation/features-phase-5-on-demand/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Track C notes and backend/app/inbox/reply_workflow.py first. Confirm with me that pilot demand triggers this track. Then update mvp-scope.md and add an opt-in rule that creates at most one owner-approved follow-up draft per quiet price or booking conversation, rechecks the 24-hour window at send time, and cancels if the customer writes again. Add a setting, a report metric and boundary tests.

Run the checks, write s08-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

#### Session 09: Human Agent tag, plus track close-out

**Work**
- Research the Human Agent tag's permission and rules. Record them with sources in `platform-capabilities.md`, and update the App Review package.
- Allow manual replies (typed by a person in the inbox, never drafted and auto-sent) up to 7 days after the customer's last message, using the tag. The API and policy reject any automated path from using it. Add a capability flag that depends on the granted permission.
- Show the window state clearly in the conversation view.
- Track close-out: write `features-phase-5-followup-summary.md` and update `roadmap.md`.

```text
Implement Feature Phase 5, Session 09 (Human Agent tag and track close-out) from docs/implementation/features-phase-5-on-demand/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 09 brief and s08-report.md first. Record the Human Agent tag's permission and rules with sources, update the App Review package, and allow only human-typed manual replies up to 7 days using the tag behind a permission-dependent capability flag. Policy must reject any automated use. Show the window state in the conversation view.

Run all checks, write s09-report.md and docs/implementation/phase-summaries/features-phase-5-followup-summary.md, update roadmap.md, and stop for review. Preserve unrelated work. Do not commit, push or send live messages.
```

---

### Track D: More reply languages (F-11)

#### Session 10: Detection and validator formats for ru, de, ar

**Work**
- Update `mvp-scope.md`. Extend `inbox/language.py` to detect `ru`, `de` and `ar`, with confidence thresholds. Mixed or low-confidence messages still escalate.
- Extend `reply_languages` validation to accept the new codes.
- Extend `knowledge/formatting.py` and `claims.py` for number, currency, date and time formats in each language, including Arabic-Indic digits and RTL marks. The claim validator must catch a wrong price in every supported language.
- Tests per language: detection, formatting, and the validator catching invented numbers.

```text
Implement Feature Phase 5, Session 10 (language detection and validator formats for ru, de, ar) from docs/implementation/features-phase-5-on-demand/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Track D notes, backend/app/inbox/language.py, backend/app/knowledge/claims.py and formatting.py first. Confirm with me that the tourism segment triggers this track. Then update mvp-scope.md, add ru, de and ar detection with confidence thresholds, accept them in reply_languages, and extend number, currency and date formatting and the claim validator (including Arabic-Indic digits) with per-language tests proving invented values are caught.

Run the checks, write s10-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

#### Session 11: Eval sets, settings and RTL, plus track close-out

**Work**
- Add 15–20 eval cases per new language (prices, hours, booking, out-of-scope, injection attempts). Run them with the fake provider, and list the live run as pending.
- Workspace settings UI to choose reply languages, with a warning that eval coverage exists only for the listed languages.
- Show Arabic customer messages and drafts in the inbox with correct RTL direction (`dir="auto"`), and check phone width.
- Track close-out: write `features-phase-5-languages-summary.md` and update `roadmap.md`.

```text
Implement Feature Phase 5, Session 11 (language eval sets, settings, RTL and track close-out) from docs/implementation/features-phase-5-on-demand/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 11 brief and s10-report.md first. Add 15–20 eval cases per new language, a reply-language setting with a coverage warning, and correct RTL display for Arabic in the inbox and approval views.

Run all checks, write s11-report.md and docs/implementation/phase-summaries/features-phase-5-languages-summary.md, update roadmap.md, and stop for review. Preserve unrelated work. Do not commit or push.
```

---

### Track E: Lead list (F-12)

#### Session 12: Filtered lead view and CSV export, plus track close-out

**Work**
- Update `mvp-scope.md` to make it explicit that this is a filtered view, not a CRM. There are no pipelines, stages or custom fields.
- Add an endpoint that lists conversations where the customer asked about a price or booking in the period and did not convert (no booking or calendar event, no "done" marker), using existing conversation, intent and memory data. Exclude simulated data.
- CSV export with KVKK in mind: only the customer handle, the last question, the date and a conversation link. It is restricted to owners and managers, audited, and formula injection is escaped.
- A UI list with a period filter and an export button.
- Track close-out: write `features-phase-5-leads-summary.md` and update `roadmap.md`.

```text
Implement Feature Phase 5, Session 12 (lead list with CSV export and track close-out) from docs/implementation/features-phase-5-on-demand/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Track E notes and docs/legal/kvkk-aydinlatma-metni-template.md first. Confirm with me that owners asked for this. Then update mvp-scope.md (a view, not a CRM), add an endpoint and UI listing price or booking conversations that did not convert, excluding simulated data, and add a minimal, audited, role-restricted CSV export with formula-injection escaping.

Run all checks, write s12-report.md and docs/implementation/phase-summaries/features-phase-5-leads-summary.md, update roadmap.md, and stop for review. Preserve unrelated work. Do not commit or push.
```
