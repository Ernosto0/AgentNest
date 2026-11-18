# MVP Scope

**Purpose:** Draw a hard line around what the first build includes, what pilot readiness adds, and what is deferred, and explain why. If a feature is not listed under "Included", it is out of scope for that stage.

## 1. Stages

| Stage | Phases | Outcome | External dependencies |
|---|---|---|---|
| **S1: Local MVP demo** | 1–6 | Complete, honest, simulated end-to-end product on a laptop. Satisfies the original spec §20 "Definition of Done for the First Build". | None (Docker for Postgres only) |
| **S2: Real Instagram** | 7 | One real professional account (founder's own, then 1–3 testers) connected, receiving DMs and publishing images. | Meta app, Standard Access, public HTTPS endpoint, S3-compatible storage |
| **S2.5: Account agent** | 7.5 | Offline agent handles natural multi-turn DMs, comment context, memory, owner questions and delegated supported actions; each real capability has its own research and live acceptance gate. | Offline fake/mock needs no credentials; real comments and private replies depend on verified Meta access |
| **S3: Pilot readiness** | 8 (+9 optional) | Deployed, backed up, secured. Legal basics in place. Optional owner messenger channel. | VPS, domain, legal review, (Telegram/WhatsApp) |
| **S4: Self-service SaaS** | not planned in detail | App Review approved, self-service signup, billing. | Meta Advanced Access, payment provider |

## 2. Included in S1 (local MVP demo)

The test for inclusion: **is it needed to demonstrate the core value loop credibly and safely?**

| Capability | Included scope | Explicitly excluded in S1 |
|---|---|---|
| Accounts & workspaces | Email/password login, workspaces, roles owner/manager/staff, workspace switcher, invite by link, tr/en UI | Email delivery, password reset UI (CLI only), SSO |
| Business knowledge | Typed facts from business templates (with category presets, ADR-023), verification, version history, candidates with discrepancy/contest rules, readiness, paste-text extraction, approved answers, brand voice | structured class timetables, multiple branches |
| Commands | Web command bar. Closed registry: activity questions, pending approvals, content status, failure explanation, fact query, fact update, brand voice update, content draft request, cancel scheduled content. Clarification and confirmation. | Approve/publish/send by command (never), rescheduling by command, multi-step plans |
| Inbox | Mock account, simulated webhooks through the real ingestion path, conversations, debounce, grounded drafts, policy decisions, approvals, manual replies, takeover, messaging window, echo-based supersede (simulated), approved answers | Attachments analysis (images in DMs are shown as "attachment received" → human), story replies to stories we did not publish, story mentions without an owner-set thank-you (both stay with a person), comments, Human Agent tag |
| Content | Image upload with validation, `feed_image` and `story_image`, AI content drafts with overlay text suggestions, claim validation, approve & schedule, mock publish worker with container semantics, retries with deadline, cancel, on-hold on fact change | Video, Reels, image generation, hashtags research, best-time suggestions |
| Approvals | Confirmation and authorisation kinds, binding, expiry, sweep, approvals screen | Multi-level approval chains |
| Reporting | Daily report (computed, templated), activity feed, notification centre, Home dashboard, integration health | Charts, exports, insights from Instagram |
| Simulation | Seed data, dev panel and CLI, failure injection, run-due-jobs, reset, simulation labelling | — |
| AI | `fake` provider (default) and `openai` provider, agent run records, eval datasets and runner | Fine-tuning, other providers, vision |
| Ops | Docker Compose Postgres, CI, structured logs | Deployment, backups (S3 stage) |

### Features judged essential to show the value (the demo must not skip them)
1. A customer price question answered with the **verified** price, after one tap of approval.
2. A price change by natural language that **changes the next answer** and **holds the scheduled post** that contained the old price.
3. A scheduled post that **publishes (simulated) at its time**, survives a worker restart, and does not duplicate on retry.
4. A complaint that is **not** answered automatically.
5. A daily report whose numbers **match the activity log**.
6. Everything visibly labelled **simulated**.

## 3. Added in S2–S3 (pilot readiness)

- Instagram Login OAuth, token encryption and refresh, real webhooks with signature verification, real send and publish (images), S3 media with signed URLs, capability detection, disconnect.
- Deployment to a single VPS (TLS, backups, restore drill), RLS defence in depth, login throttling, security review, retention and deletion jobs, Meta data deletion callback, privacy notice and DPA templates (legal review), SMTP for invites.
- Optional (OQ-01): Telegram owner channel.
- Phase 7.5: one account agent with explicit action-level delegation, durable multi-turn DM/comment handling, bounded customer memory and personality, owner questions, moderation/private replies and existing image-content tools. Its offline work is independently demonstrable; real comment capabilities remain disabled until evidenced.

### Feature Phase 1: before the first pilot (in scope since 2026-11-15)

Planned in [features-phase-1-before-first-pilot/sessions.md](../implementation/features-phase-1-before-first-pilot/sessions.md); source: [pre-launch-feature-recommendations.md](../review/pre-launch-feature-recommendations.md) §4, step 1. These three exist to remove the two biggest pilot risks: owners not trusting the assistant, and owners not seeing approvals (RK-03).

| Capability | Included scope | Explicitly excluded |
|---|---|---|
| **F-02 "Try your assistant" test chat** | The owner (and manager) types as a customer in a sandbox and sees the draft the assistant would produce, its decision (`auto`, `approval_required`, `human_required`, `blocked`), the reason, and the facts used with their verified dates. Works before any Instagram account is connected. Everything is `is_simulated`, is never sent, and never counts in reports, queues, notifications or customer memory. Rate-limited per workspace. Backend in Session 01, screen (last onboarding step and a button on the Assistant page) in Session 02 | Staff access, test chat for comments or content, saving test chats as approved answers, changing draft quality or prompts |
| **F-01 Installable app and Web Push** (moved here from §4 Deferred) | Web manifest and icons, a push-only service worker (no offline cache), a `web_push` owner channel for approvals, owner questions and failures through the existing delivery policy, per-type opt-in, an iOS "Add to Home Screen" guide. Payloads carry no customer message text | Approve or reject buttons inside a notification, offline mode, a native app |
| **D-01 Visible "never invents a price" guarantee** | The verified-fact source beside every placeholder-derived value in drafts and approvals (web and Telegram), and an "unverified values sent: 0" line in the daily report computed from claim-validator results | Any change to the claim validator's rules |

### Feature Phase 2: during pilots (in scope since 2026-11-16)

Planned in [features-phase-2-during-pilots/sessions.md](../implementation/features-phase-2-during-pilots/sessions.md); source: [pre-launch-feature-recommendations.md](../review/pre-launch-feature-recommendations.md) §4, step 2. All eight sessions of the phase are implemented offline (see the [phase summary](../implementation/phase-summaries/features-phase-2-summary.md)); the rows below are the in-scope capabilities and their exclusions.

| Capability | Included scope | Explicitly excluded |
|---|---|---|
| **F-03 Voice and image understanding** (moved here from §2 "Attachments analysis" and "vision") | **Voice notes** (Sessions 01 and 02): an Instagram voice note is downloaded (size, duration and content type capped), transcribed by a transcription provider (`fake` offline, `openai` live; `TRANSCRIPTION_PROVIDER`) and the transcript is stored on the message as a separate, labelled record (`message_transcripts`, `source = "transcript"`, language, model, duration). Session 02 drafts from the transcript like text (labelled as a transcript in the prompt, which says it may contain transcription errors), and the inbox and the approval view show it as "Transcript (automatic)" with its language and a note that the voice note can be listened to in Instagram. **Approval is mandatory for every transcript-based reply**, whatever the delegation says, until transcription quality is measured on real Turkish voice notes (a deterministic policy rule R18, reason `TRANSCRIPT_REQUIRES_APPROVAL`, not a model flag; the account agent has the same guard). A failed download or transcription leaves the message on the existing human path with a reason code. **Images** (Session 03, implemented): a customer's photo or screenshot is downloaded (size and type capped; JPEG, PNG, WebP), described by a tool-less vision task (`describe_image`; `fake` offline, OpenAI live; `IMAGE_DESCRIPTION_ENABLED`) and stored as a separate, labelled record (`message_image_descriptions`, `source = "image_description"`: a short description, the text visible in the picture, a rough kind, an injection flag). The inbox shows it under the message as "What the customer sent (automatic)". **No automatic answer and no pre-filled suggestion**: the conversation stays `human_required` (`ATTACHMENT_ONLY`), the description is never read by a draft, and the text in a picture is untrusted and never a fact. The image is held in memory during the job and never stored; the description follows message-text retention (365 days) and every erasure path. Session 01 holds the audio in memory during the job only and never stores it, so no raw-audio retention rule exists yet (a later session that keeps audio for a player must add one). Transcript text is customer personal data: it follows message-text retention (365 days) and every erasure path | Automatic sending of a transcript-based reply without approval, speaker identification, translation, languages other than Turkish and English, audio or video calls, storing or replaying the raw audio, storing or showing the customer's images, suggested or automatic replies from an image, reading images in the account agent, video attachments, transcription of the business's own (echo) voice messages |
| **D-02 Approval-ladder suggestions** (Feature Phase 2) | A weekly job counts, per reply topic, the owner's unchanged approvals (web or Telegram, bound to the exact text) against edits, rejections and failures. A topic with at least `DELEGATION_SUGGESTION_MIN_UNCHANGED` (20) clean approvals in `DELEGATION_SUGGESTION_WINDOW_DAYS` (28) days and none of the others becomes one suggestion and one `delegation_suggestion` notification per workspace per week, with a card on Today and on the Assistant page. Only opening hours, address and contact, and services are ever suggested, and only while policy and readiness allow `auto`. Confirming goes through the existing delegation preview and apply; "Not now" starts a cool-down | Suggesting price, booking, promotion or FAQ topics; suggesting for simulated or agent-controlled accounts; applying anything from free text; widening the agent's own delegation |
| **F-04 Story replies and mentions** (Feature Phase 2) | A reply to one of the business's own published stories is drafted with that story's title, objective and overlay lines as labelled data (no placeholder values). A plain story mention is answered only by an owner-written thank-you template (an approved answer with intent `story_mention`, one per language), through the normal approval path (`reply.story_mention`). The conversation view labels stories and mentions | Fetching a story caption from the Graph API, stories the business did not publish (drafted as before), a model-written thank-you, automatic mention replies by default |
| **D-03 Missed-customer report in lira** (Feature Phase 2) | A weekly, live-computed report (owner and manager): DMs after the verified opening hours, unanswered conversations, median first-reply time and an estimate in TRY (`after_hours_price_answers x CONVERSION_RATE x median verified TRY price`, with the formula and inputs shown). Without verified hours or a verified price only counts are shown. One counts-only weekly notification | A stored weekly snapshot, normalising price units, any figure from a model, a tuned conversion rate (5% is a placeholder) |
| **D-05 Visible learning loop** (Feature Phase 2) | After an owner answers an assistant question the app and Telegram offer "Save this as a verified fact?" (one tap through the existing candidate accept path; a price, hours, phone, e-mail or URL needs the typed editor) and the Assistant page shows "Learned N things from you this month" | Auto-verifying anything, expiring unsaved candidates, counting hand-typed or staff-proposed facts |
| **D-04 Manage by chat** (Feature Phase 2) | Two more confirmed commands: `content.reschedule` (an existing pending-approval, scheduled or held item moves to a new time; old and new local times are shown) and `agent.pause_until` (pause the account assistant until a local time, with an automatic resume job). Turkish and English interpretation; hash-bound, single-use, expiring confirmation; owner-only for pause. On phones the command box is first on Today | Scheduling new drafts or publishing by free text, legacy-policy pause, changing other automation settings, free-text approval, indefinite pause |

### Feature Phase 3, Track A: comment-to-DM on real accounts (in scope since 2026-11-17)

Planned in [features-phase-3-after-app-review/sessions.md](../implementation/features-phase-3-after-app-review/sessions.md); source: [pre-launch-feature-recommendations.md](../review/pre-launch-feature-recommendations.md) §4, step 3. Moved here from §4 Deferred ("Real-account comment automation before capability acceptance"). Sessions 01 (research and permission request) and 02 (the real path) are implemented and verified offline; every live result is **pending**.

| Capability | Included scope | Explicitly excluded |
|---|---|---|
| **F-05 Comment-to-DM on real accounts** | The OAuth flow requests `instagram_business_manage_comments`; an existing connection shows "reconnect to enable comments"; the permission is recorded as `granted_scopes` and the derived capability `comments_permission`. Session 02: the real Meta comment webhook and private-reply path behind a per-account flag that is off by default, a verified-answer private reply through the existing draft, claim-validator, approval and delegation path, deterministic enforcement of Meta's 7-day and one-message limits with reason codes, a skipped-by-default live probe harness, and a rollout runbook. R75-01 to R75-06 are answered or carried forward in [platform-capabilities.md §1.8](../research/platform-capabilities.md). | Enabling comment actions without the permission, the per-account flag **and** a passing live probe on a dev-mode account (mock results never count as live evidence); comment moderation (hide, delete) on real accounts until its own evidence; any unapproved or invented price in a reply; automatic resend of an unknown outcome; public availability before Meta grants Advanced Access (pilots run on Standard Access with role users) |

**Gate.** A real account may use comment automation only when (1) its `granted_scopes` include `instagram_business_manage_comments`, (2) the account's capability flag is on, (3) the owner's delegation for the action is not `off`, and (4) the live evidence for the matching R75 items is recorded. Until then the Comments tab on real accounts stays labelled "Not yet". Live results are "pending" until recorded.

**Session 02 implementation:** the default-off persisted `social_accounts.comment_automation_enabled` flag (owner-only switch in Connections) exists. Only the actual granted scope plus the flag derive the real `comment_read` and `comment_private_reply` capabilities; public replies and moderation stay disabled on real accounts. Offline ledger, approval and claim-validator tests never satisfy the live gate (**pending**).

### Feature Phase 3, Track B: template images (in scope since 2026-11-17)

| Feature | In scope | Follow-up |
|---|---|---|
| **F-07 Template images** | Deterministic price, hours, services and announcement cards; story/feed sizes; workspace colours/logo; verified fact keys resolved at render time with immutable version evidence; a template picker with live preview in content creation and the Today story prompt; rendered items carry the fact versions used, so a price change holds them; re-render creates a new draft version that needs fresh approval; a confirmed `content.make_price_card` command (TR/EN) | AI image generation; free text with prices, times, phones or URLs on a card; automatic approval or publishing of a rendered image |

### Feature Phase 4: before self-service launch (F-09)

Session 01 (backend and the "Re-import from Instagram" button) and Session 02 (website import and the onboarding step) are implemented offline; live Instagram behaviour is pending V-12, and the website fetcher has been exercised against real sites only by hand.

| Capability | Included scope | Explicitly excluded |
|---|---|---|
| **F-09 Import facts from the Instagram profile and a website** | Session 01: bio and recent captions with dates, warning above 90 days, candidates only, deduplicated, first connection and re-import API. Session 02: SSRF-safe website fetcher (home page plus up to 3 same-site price/contact/about pages, HTML only, 2 MB, host-only audit, 10 imports per workspace per day), candidates with the page address, a website field prefilled from the Instagram profile, and an "Import from Instagram or website" step in workspace creation and on the Knowledge page | Auto-verifying; contact-button fields (no Graph API field); stories, DMs, comments; scraping Instagram web pages; crawling beyond 4 pages; running JavaScript (script-rendered sites yield little text); PDFs and images on a site; gzip-only sites |

### Feature Phase 5, Track A: WhatsApp owner channel (F-06; in scope since 2026-11-18)

Planned in [features-phase-5-on-demand/sessions.md](../implementation/features-phase-5-on-demand/sessions.md). Moved out of §4 Deferred on 2026-11-18 at the owner's request to implement all Feature Phase 5 sessions; **trigger evidence (OQ-01: pilot owners will not use Telegram or push) is not yet recorded**, so the channel stays optional, off by default and never a dependency of the core. Policy reading and decision: [platform-capabilities.md §2.1](../research/platform-capabilities.md) and [ADR-027](../architecture/decisions/ADR-027-whatsapp-owner-channel-scope.md). Every live result is **pending**.

| Capability | Included scope | Explicitly excluded |
|---|---|---|
| **F-06 WhatsApp owner channel** | Session 01: WhatsApp Cloud API client with a mock transport (template, interactive reply buttons, webhook verification), credentials in settings (off without them), a signed webhook, and account linking by the existing one-time code sent to the business number. Session 02: WhatsApp notifications and the daily summary (the Web Push types plus `report.daily_ready`) through the delivery ledger and quiet hours, a session message inside the 24-hour window and an approved template (TR and EN, utility) outside it, per-message cost metadata (category only; no Türkiye price is verified). Session 03: approve and reject reply buttons on approval requests (session messages inside the 24-hour window only; the plain template with no buttons outside it), carrying the Phase 9 single-use hashed expiring action tokens and deciding through the same approval service, with replay, expiry, stale, forwarded, unlinked and revoked-member handling | Free-text commands, any owner text sent to an LLM or the command system, customer message text in a WhatsApp message, free-text approval, a general-purpose assistant on WhatsApp, WhatsApp as a customer channel, live sending before a verified number and approved templates exist |

### Feature Phase 5, Track B: carousels and Reels (F-08, in scope since 2026-11-18)

Moved out of Deferred on 2026-11-18 at the owner's request to implement all Feature Phase 5 sessions; trigger evidence (pilot demand for carousels and Reels) is not yet recorded. Sessions 04–07 (carousel data model, carousel publishing/UI, video upload/validation/storage/thumbnails, and Reels publishing/UI) are implemented and verified offline; live Meta carousel and Reel acceptance remains pending.

| Feature | In scope | Follow-up |
|---|---|---|
| **F-08 Carousels** | Session 04: a `feed_carousel` content type with an ordered list of 2-10 JPEG images (the existing image rules plus one shared aspect ratio), the media order bound into the approval hash, and any item that quotes a fact joining the price-change hold. Session 05 implemented: publishing through the operations ledger (mock and documented Meta flow), multi-upload, ordering and preview UI; live publishing acceptance pending | Mixed images and videos in one carousel, Reels as carousel items, per-item captions (Instagram has none), tagging and location |
| **F-08 Reels** | Sessions 06 & 07 implemented offline: private MP4/MOV ingest + ffprobe/ffmpeg validation + Range streaming + `reel` type (custom JPEG cover or `thumb_offset_ms`, `share_to_feed`, hash-bound approvals) + async `poll_reel_container` ledger publishing and React upload/scrubber/preview UI; live Meta Reel acceptance pending | AI video generation, server-side transcoding, template overlays on video, video/audio auto-fact-checking, Reel insights |

### Feature Phase 5, Track C: follow-up and late replies (F-10, Sessions 08 and 09)

Moved out of Deferred on 2026-11-18 at the owner's request (all Feature Phase 5 sessions were requested); trigger evidence (pilot owners asking for late replies) is not yet recorded. Session 09 (Human Agent tag, 7-day manual replies) moved out of Deferred on the same date and the same basis; the pilot evidence is likewise not yet recorded.

| Capability | Included scope | Explicitly excluded |
|---|---|---|
| **F-10 One follow-up message inside the 24-hour window** | Off by default (workspace setting, owner only). When a customer asked about a price or booking, the assistant's answer (a legacy-controlled, assistant-written reply with intent `pricing` or `booking`) was sent, and the customer then stayed quiet for X hours (setting, 1 to 20, default 6), one follow-up draft is created. The wording is a built-in neutral Turkish/English text or an owner-written text per language; facts only through `{{fact:key}}` placeholders, rendered from usable facts and checked by the claim validator like any reply. The draft always needs the owner's approval (no automatic sending in this session). At most one follow-up per conversation, enforced by a unique row; a new customer message cancels a pending one. The 24-hour window is checked when the draft is made and again at send time (an expired window rejects the send). A weekly report shows follow-ups sent and how many customers wrote back | Automatic (no-approval) follow-ups, more than one per conversation, follow-ups after the window closed (a follow-up never uses the Human Agent tag), follow-ups for threads handled by the Phase 7.5 account agent, follow-ups after a person's own typed reply or a native app reply, a model-written follow-up, marketing broadcasts |
| **F-10b Human Agent tag: a person's reply up to 7 days after the customer's last message** | Behind the capability `human_agent` (a Meta account needs `META_HUMAN_AGENT_ENABLED=true`, set only after Meta grants the Human Agent feature, plus the messaging permission; the simulator supports the tag). A reply a person types in the inbox 24 hours to 7 days after the customer's last message is sent with `messaging_type=MESSAGE_TAG` and `tag=HUMAN_AGENT`, through the same approval and operations ledger as any reply (the tag is part of the approved payload). One deterministic rule decides at creation and again at send time; the draft stores the tag and the database allows it only for a person's own reply. The conversation view shows the window state (open, Human Agent only until a time, closed) in Turkish and English | Any use of the tag by an assistant draft, an approved answer, a follow-up, an agent draft, a job or a system actor (rejected by code, policy and a database constraint); an assistant draft or an edited assistant draft sent as a tagged reply; text started from or equal to an assistant draft; replies after 7 days; other message tags; a UI toggle (the flag is operator-set); proving the feature is granted per account (Meta documents no way, V-HA) |

### Feature Phase 5, Track D: more reply languages

| Capability | Included scope | Explicitly excluded |
|---|---|---|
| **F-11 More reply languages (Feature Phase 5, Track D)** | Script and word-list detection of `ru`, `de`, `ar`; workspace `reply_languages` accepts them; per-language fact formatting, claim-validator formats (Arabic/Persian digits and invisible marks included), escalation keywords and owner-approved answers. Implemented offline in Sessions 10 and 11: 20 eval cases per language (fake provider), owner setting with coverage warning, RTL display (`dir="auto"`) in the inbox and approvals, per-language disclosure text. Live LLM quality in ru/de/ar is **pending** | UI languages, content/post languages, account-agent calendar replies (tr/en only), translation of owner facts, spelled-out numbers |

Moved out of Deferred on 2026-11-18 at the owner's request (the owner asked to implement all Feature Phase 5 sessions); trigger evidence (the tourism segment starting, OQ-11) not yet recorded.

### Feature Phase 5, Track E: light lead list (F-12)

Moved out of "later" on 2026-11-18 at the owner's request (the product owner asked for every Feature Phase 5 session to be implemented); the trigger "owners ask for a call-back list" is treated as confirmed by that request, and trigger evidence from pilot owners is not yet recorded. This is **a filtered view and an export of existing conversations, not a CRM**.

| Capability | Included scope | Explicitly excluded |
|---|---|---|
| **F-12 Light lead list with CSV export** | A list, for a chosen period (workspace-local dates), of real conversations in which the customer asked about a price or a booking and no appointment exists afterwards; the same list as a CSV with four columns only (customer handle, last question, date, conversation link). Owner and manager only (`reports.view`); the export is audited with counts and the period, never customer data; formula injection is escaped; simulated data is never listed | Pipelines, stages, statuses, tags, notes, assignees, custom fields, a "done" marker, scores, reminders and automated follow-up; phone numbers, e-mail addresses or any other customer data in the export; scheduled or e-mailed exports; a link to external CRMs |

## 4. Deferred (with reason and trigger)

| Feature | Reason for deferral | Revisit trigger |
|---|---|---|
| WhatsApp owner channel | Cost, verification, policy uncertainty. **Moved out of Deferred on 2026-11-18** (see Feature Phase 5, Track A above (§3)) | OQ-01 (answered by the owner's request, above (§3)) |
| Story/post **AI image generation** | Not core to the trust loop; model and design effort | OQ-15 after pilots |
| ~~Video/Reels/carousels~~ | Implemented offline in Feature Phase 5 Sessions 04–07 (Track B, F-08); live Meta acceptance pending | Pilot demand |
| ~~Human Agent tag (7-day replies)~~ | Implemented offline in Feature Phase 5 Session 09 (F-10b), off until Meta grants the feature; live check V-HA pending | Meta approval, then pilot demand |
| Billing, plans, usage limits | No paying users yet | Paid commitments (OQ-06) |
| Advanced analytics and Instagram insights | Not the core problem | Pilot demand |
| Multiple Instagram accounts per workspace, agencies | Complexity; not the target segment | Market evidence |
| CRM, lead pipeline, booking integrations | Scope explosion | Strong pilot demand |
| Multi-agent / autonomous campaigns | Contradicts the trust model at this stage | Proven trust + concrete use case |

## 5. Scope guardrails for implementers

- Do not add a table, endpoint, job type or dependency that no phase document lists, without updating the docs first.
- Do not implement a deferred feature "because it is easy". Raise it instead.
- When in doubt between a simpler and a more general implementation, choose the simpler one and note the limitation in the phase summary.
