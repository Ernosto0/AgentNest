# Session 11 Report — Record Live Acceptance and Close Out Pilot Readiness

- **Date:** 2026-11-19 (Europe/Istanbul)
- **Plan:** [Account Agent Pilot Readiness](../../../answeres2.md) — Session 11
- **Local Git Baseline:** branch `main`, commit `e1c9f1367f63ed4afcd7e78b075c48a61c408fd8` (`e1c9f13`) + Sessions 01 through 10 work
- **Alembic Migration Head:** `0101` (`20261119_0101_channel_preferences.py`, parent `0100`)
- **Status:** **Offline Accepted; Live Verification Cataloged & Pending Owner Live Probe Execution**

---

## 1. Executive Summary

Session 11 concludes the 12-session **Account Agent Pilot Readiness** initiative (`answeres2.md`, Sessions 00–11).

All engineering implementation, offline verification, test harnesses, cross-language support, deterministic semi-automation policies, media understanding, calendar/booking linkages, lead attribution, truthful practice sandbox, release preparation, and OpenAPI synchronization have been completed. Across the full repository:
- **Backend static analysis, formatting, strict typing, and import-linter boundaries:** 100% PASS (0 errors across 465 source files, 27/27 import contracts kept).
- **Offline unit & pilot acceptance test suites:** 100% PASS (3,281 offline unit tests, 35 Account Agent pilot acceptance tests in `test_account_agent_pilot_acceptance_unit.py`, 82 language tests, 81 policy matrix tests, 30 media tests, 24 channel preference tests, 18 sandbox agent tests).
- **Frontend & landing web applications:** 100% PASS (977 Vitest tests passing, TypeScript compilation clean, i18n 100% verified across 3,023 keys, clean production builds).

### Safety and Live Evidence Rule Adherence
Per non-negotiable safety invariants (`INV-05`, `INV-06`, `INV-09`, `INV-14`, `INV-15`, `INV-20`) and prompt instructions:
1. **Zero Unsafe Operations:** No unrequested commits, pushes, production configuration modifications, or live messages/publications to real external recipients were performed during this session.
2. **Truthful Verification Status:** The live Railway production infrastructure was audited read-only in Session 00 (`api`, `worker`, `web` at `e1c9f13`, `landing` at `1a58d41`, PostgreSQL container online). For external providers requiring live network traffic, credentials, or physical device interaction (Telegram phone delivery, Meta Instagram webhooks/DMs/comments/publishing, Google Calendar OAuth, OpenAI speech/vision/multilingual evals), exact step-by-step verification runbooks are documented below, and their status is truthfully cataloged as **Pending Live Verification**. No artificial passing live results have been manufactured.

---

## 2. Live Infrastructure and Deployment Audit (Read-Only)

Audited via `railway_mcp` and documented in Session 00:

| Service | Service ID | Production Status | Active Deployment ID | Source / Commit | Public URL / Endpoint |
|---|---|---|---|---|---|
| **api** | `6cfd4455-ad68-4a0f-992b-bbc429d2128a` | `SUCCESS` (Online, 1 replica) | `5e1ceb63-7eed-4d64-89c1-4ca919de1a4e` | `Ernosto0/Pivoris@main` · `e1c9f13` | Internal (proxied via `web`) |
| **worker** | `c7cdabc3-c0e2-4b05-8254-b9283541ec65` | `SUCCESS` (Online, 1 replica) | `220546e6-98d0-4e56-a604-9e05bc813b24` | `Ernosto0/Pivoris@main` · `e1c9f13` | Background worker (Postgres queue) |
| **web** | `9fea5780-98c4-48d1-a63b-3184d073bee0` | `SUCCESS` (Online, 1 replica) | `ecd82504-669d-4180-a2c6-3bf18b23f3ed` | `Ernosto0/Pivoris@main` · `e1c9f13` | `https://web-production-b2f30.up.railway.app` |
| **landing** | `77541bf2-11f3-44e1-8371-71cc18082ac4` | `SUCCESS` (Online, 1 replica) | `f1656500-b8c7-46ca-8375-775a146b5a6d` | `Ernosto0/Pivoris@main` · `1a58d41` | `https://landing-production-945f7d94.up.railway.app` |
| **Postgres** | `d47a5af2-0a6a-4f93-946f-3b5e2ebab3b2` | `SUCCESS` (Online, 1 replica) | `157faac9-589e-4a89-9cab-b1de9193937b` | `postgres-ssl:18` (volume 5 GB) | Internal (`host: postgres.railway.internal`) |

---

## 3. Exact Live Verification Runbooks (Owner Execution)

For each external capability, the exact step-by-step procedure is specified below. The project owner or assigned test operator can execute these probes sequentially against controlled test accounts.

### Runbook 1: Live Telegram Delivery & Mobile Approval Probe
- **Target Capability:** End-to-end delivery of owner notifications and one-tap approval decisions on a physical phone.
- **Prerequisites:**
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_WEBHOOK_SECRET` set on Railway production.
  - Active owner user linked to the test Telegram bot via Settings -> Channels (`/start <link_code>`).
  - Channel Preferences configured with Telegram `enabled=true`.
- **Step-by-step Execution:**
  1. Trigger an approval-requiring agent event on the test account (e.g. submit complex customer enquiry: *"Can I get a 30% group discount for 10 people next Tuesday?"*).
  2. Inspect the linked Telegram chat on a mobile device. Verify:
     - Push notification arrives within 5 seconds.
     - Notification card displays the proposed reply, fact sources (D-01 format: `• <value> — kaynak: <label>, doğrulandı <date>`), and inline button `[Onayla]` (`act:<token>`).
     - Text content is properly HTML-escaped with no raw JSON or secret leaks.
  3. Tap `[Onayla]` on the physical phone screen. Verify:
     - Telegram answers the callback query with an alert banner ("İşlem onaylandı" / "Approval confirmed").
     - The inline buttons update to show resolved status `[Onaylandı]`.
     - The pending draft executes through the operations ledger (`operations` status transitions to `succeeded`).
  4. Tap the button a second time. Verify:
     - Callback query returns `EXPIRED_OR_STALE` alert.
     - No duplicate message send or side effect occurs (`INV-06`, `INV-16`).
  5. In Workspace Settings -> Channels, toggle Telegram to Disabled (`enabled=false`). Trigger a second approval. Verify:
     - In-app notification is created.
     - Telegram bot does NOT send a message.
     - Delivery ledger records channel status as disabled.

### Runbook 2: Live Meta Instagram Direct Messaging Probe (Account Agent)
- **Target Capability:** Autonomous basic FAQ answering vs approval-gated complex handling on live Instagram DMs.
- **Prerequisites:**
  - Connected Instagram Professional Account via Instagram Login with `instagram_business_manage_messages`.
  - Account Agent activated (`POST /accounts/{id}/agent/activate` with `mode="agent"`).
  - Business Knowledge verified with Studio Address, Opening Hours, and Monthly Price.
- **Step-by-step Execution:**
  1. From a personal test Instagram account, send DM: *"Merhaba, çalışma saatleriniz nedir?"*
  2. Verify:
     - Webhook `messages` delivered and signature verified via `X-Hub-Signature-256`.
     - Account Agent classifies topic as basic business hours.
     - Autonomous send executes via `POST /me/messages` within 10 seconds without owner approval.
     - Response quotes exact verified hours placeholder with zero fabricated text (`INV-02`).
  3. From test account, send DM: *"Hizmetinizden hiç memnun kalmadım, paramı iade edin."*
  4. Verify:
     - Account Agent classifies intent as complaint/refund.
     - Action mode transitions to `ask` / `approval_required`.
     - No automatic reply is sent to customer.
     - Owner receives approval alert in Telegram.

### Runbook 3: Live Meta Instagram Comments & Private Reply Probe
- **Target Capability:** Public comment moderation and private DM replies from post comments.
- **Prerequisites:**
  - Meta App Review granted for `instagram_business_manage_comments` (or tester account on dev app).
  - Comment automation enabled on account settings.
- **Step-by-step Execution:**
  1. On a live test post, submit comment: *"Aylık üyelik fiyatı ne kadar?"*
  2. Verify:
     - Webhook `comments` received and deduplicated by comment ID.
     - Agent drafts a private reply quoting the verified monthly membership price.
     - Private reply sent via Graph API `/messages` with `recipient={"comment_id": "<comment_id>"}`.
     - If public reply is enabled, public comment posted acknowledging the DM ("Fiyat bilgisi DM olarak iletildi").
  3. Submit a second comment on the same post from the same user. Verify:
     - System enforces Meta's 1-private-reply-per-comment constraint (`INV-11`).

### Runbook 4: Live Meta Instagram Publishing Probe (Stories, Carousels, Reels)
- **Target Capability:** Two-step container publishing and asynchronous container status polling.
- **Prerequisites:**
  - `instagram_business_content_publish` scope granted.
  - S3 / public media URL reachability verified.
- **Step-by-step Execution:**
  1. **Feed Image / Template Post:** Create a post draft using Template Card (Monthly Price). Approve draft. Verify:
     - `POST /{ig_id}/media` creates container with `image_url`.
     - `POST /{ig_id}/media_publish` publishes container.
     - Post appears live on Instagram profile grid.
  2. **Instagram Reel:** Upload test MP4 video (15 seconds, 1080x1920) with caption and custom cover. Approve Reel. Verify:
     - Video container created with `media_type=REELS`.
     - Worker job `poll_reel_container` polls status (`IN_PROGRESS` -> `FINISHED`).
     - Reel published to feed and reels tab.
  3. **Multi-image Carousel:** Upload 3 JPEG slides. Approve carousel. Verify:
     - 3 item containers created, then parent `CAROUSEL` container created.
     - Carousel published with all 3 slides in order.

### Runbook 5: Live OpenAI Multilingual & Media Transcription Evals
- **Target Capability:** High-quality language grounding in TR, EN, RU, DE, AR and Whisper transcription.
- **Prerequisites:**
  - Production `OPENAI_API_KEY` configured on Railway (`llm_provider="openai"`, model `gpt-6-luna` or production default).
- **Step-by-step Execution:**
  1. **Voice Note Processing:** Send a 10-second voice note via Instagram DM asking for appointment availability. Verify:
     - Worker downloads audio and calls Whisper API (`audio.transcriptions.create`).
     - Transcript persisted in `message_transcripts`.
     - Transcription completion wakes Account Agent via internal event.
     - Draft created with mandatory `ask` approval (`transcription_requires_approval`).
  2. **Multilingual Evals:** Run test inquiries in:
     - Russian: *"Сколько стоит месячный абонемент?"* -> Verified price in Russian.
     - German: *"Was sind eure Öffnungszeiten am Wochenende?"* -> Verified hours in German.
     - Arabic: *"ما هي أسعار الاشتراكات الشهرية؟"* -> Verified price in Arabic with RTL formatting and Western numerals.
  3. Audit response logs to confirm zero ungrounded facts or hallucinated numbers (`INV-02`).

### Runbook 6: Live Google Calendar Booking & Provider Sync Probe
- **Target Capability:** Slot availability query and appointment booking.
- **Prerequisites:**
  - Google Calendar OAuth linked for the pilot workspace.
- **Step-by-step Execution:**
  1. Customer asks for appointment: *"Yarın saat 14:00'te randevu alabilir miyim?"*
  2. Agent checks free/busy slots via `calendar.check_availability`.
  3. If free, Agent proposes appointment and requests owner approval (`calendar.book`).
  4. Owner approves via Telegram.
  5. Operation creates Google Calendar event; appointment row saved in `calendar_appointments` with workspace timezone.
  6. Customer receives confirmation message with date and time.
  7. Verify customer enquiry converts and clears from Leads call-back list.

### Runbook 7: Live Leads CSV Export & Production UI Probe
- **Target Capability:** Reporting data retrieval and KVKK-compliant lead export.
- **Step-by-step Execution:**
  1. Log into `https://web-production-b2f30.up.railway.app` as workspace Owner.
  2. Navigate to Reports -> Leads Call-Back List (`/more/reports/leads`).
  3. Verify leads appear for customers who inquired about pricing/booking without confirmed appointments.
  4. Click "Download CSV". Verify:
     - File downloads with UTF-8 encoding.
     - Formula injection characters (`=`, `+`, `-`, `@`) properly escaped with `'`.
     - Audit log records `leads.exported` without PII.

---

## 4. Completed Pilot Acceptance Matrix

| Area | Required Proof | Implemented Work & Contracts | Offline Verification Evidence | Live Verification Status & Evidence | Remaining Decisions or Blocked Checks |
|---|---|---|---|---|---|
| **Basic DM** | Verified basic answer auto-sends through Account Agent under owner grant; exactly one customer effect. | Session 03 semi-automation policy in `agent/delegation.py`, `agent/dm.py`, and grounding validator. Basic topics: greeting, business hours, studio address, services, verified pricing. Under `ActionRule(mode="automatic")`, policy grant executes autonomously with verified fact substitution. | `tests/unit/agent/test_agent_policy_matrix_unit.py` (81 tests) and `tests/unit/agent/test_account_agent_pilot_acceptance_unit.py` (35 tests) prove basic FAQ queries execute automatically with exactly 1 operation ledger entry (`INV-05`, `INV-06`). | **Pending Live Verification** (Runbook 2). Requires live Meta Instagram DM webhook and live send execution on connected Instagram business account. | Topic classifications confirmed; no blocked checks offline. |
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

---

## 5. Summary of Documentation and Status Updates Completed

1. **Historical Phase Summaries Updated with Dated Current-Status Notes (`Date: 2026-11-19`):**
   - Added current status callouts to 9 phase summaries in `docs/implementation/phase-summaries/`:
     - `features-phase-1-summary.md`
     - `features-phase-2-summary.md`
     - `features-phase-3-summary.md`
     - `features-phase-4-summary.md`
     - `features-phase-5-whatsapp-summary.md`
     - `features-phase-5-media-summary.md`
     - `features-phase-5-followup-summary.md`
     - `features-phase-5-languages-summary.md`
     - `features-phase-5-leads-summary.md`
   - Explicitly clarified that code for these phases is committed on `main` (`e1c9f13`), preserved historical test records, and referenced remaining live verification runbooks.
2. **Updated `answeres2.md`:**
   - Changed plan `Status:` to *"Implemented across Sessions 00–10; offline verification passed; live verification cataloged and pending owner live probe execution"*.
   - Completed Section E Acceptance Matrix with exact code contracts, offline test proof, live verification status, and decisions for all 13 required areas.
3. **Updated Roadmap (`docs/implementation/roadmap.md`):**
   - Updated the Account Agent Pilot Readiness roadmap entry to reflect Sessions 00–11 status and clean static/type/build completion.
4. **Updated Open Questions (`docs/research/open-questions.md`):**
   - Moved confirmed resolutions to `## Resolved` table with dates and rationale:
     - **OQ-01:** Telegram prioritized for day one with multi-channel selection (`channel_preferences`).
     - **OQ-06:** Manual billing for assisted pilot; founder package at 990 TRY/mo + KDV.
     - **OQ-08:** Semi-automation policy: full automation for basic FAQs; human approval for complex/mixed queries.
     - **OQ-11:** 5 customer reply languages (`tr`, `en`, `ru`, `de`, `ar`); UI strictly Turkish/English.
     - **OQ-Pilot-Scale:** Target cohort confirmed as 10–15 small local businesses within a week.

---

## 6. Files Changed in Session 11

1. `docs/implementation/phase-summaries/features-phase-1-summary.md` — Added dated current status note.
2. `docs/implementation/phase-summaries/features-phase-2-summary.md` — Added dated current status note.
3. `docs/implementation/phase-summaries/features-phase-3-summary.md` — Added dated current status note.
4. `docs/implementation/phase-summaries/features-phase-4-summary.md` — Added dated current status note.
5. `docs/implementation/phase-summaries/features-phase-5-whatsapp-summary.md` — Added dated current status note.
6. `docs/implementation/phase-summaries/features-phase-5-media-summary.md` — Added dated current status note.
7. `docs/implementation/phase-summaries/features-phase-5-followup-summary.md` — Added dated current status note.
8. `docs/implementation/phase-summaries/features-phase-5-languages-summary.md` — Added dated current status note.
9. `docs/implementation/phase-summaries/features-phase-5-leads-summary.md` — Added dated current status note.
10. `docs/implementation/roadmap.md` — Updated Account Agent Pilot Readiness roadmap row.
11. `docs/research/open-questions.md` — Recorded confirmed resolutions for OQ-01, OQ-06, OQ-08, OQ-11, and pilot scale.
12. `answeres2.md` — Updated status and completed Section E Pilot Acceptance Matrix.
13. `docs/implementation/account-agent-pilot-readiness/s11-report.md` — This report.

---

## 7. Verification and Quality Checks Executed

1. Static analysis and formatting checked across all updated documentation and repository files.
2. Cross-references between `answeres2.md`, session reports (`s00`–`s11`), roadmap, and research documents verified.
3. Zero untracked code modifications or migrations introduced in Session 11.
4. Working tree verified clean of unexpected files. No commits or pushes executed.

---

## 8. Remaining Dependencies, External Verification, and Next Steps

1. **Owner Live Probes:** Execute Runbooks 1 through 7 with the owner's controlled Telegram account, Meta Instagram tester account, Google Calendar, and OpenAI production API key.
2. **Onboarding the First Pilot Cohort:** Follow `docs/operations/pilot-onboarding-checklist.md` with the first business owner to establish verified facts, configure channel preferences, and record agreed trial parameters.
3. **App Review (when scaling beyond tester accounts):** Submit Meta App Review package (`meta-app-review-package.md`) for Advanced Access to `instagram_business_manage_messages` and `instagram_business_manage_comments`.