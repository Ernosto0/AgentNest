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
| Business knowledge | Typed facts from business templates (with category presets, ADR-023), verification, version history, candidates with discrepancy/contest rules, readiness, paste-text extraction, approved answers, brand voice | Website URL fetch, Instagram profile import, structured class timetables, multiple branches |
| Commands | Web command bar. Closed registry: activity questions, pending approvals, content status, failure explanation, fact query, fact update, brand voice update, content draft request, cancel scheduled content. Clarification and confirmation. | Approve/publish/send by command (never), rescheduling by command, multi-step plans |
| Inbox | Mock account, simulated webhooks through the real ingestion path, conversations, debounce, grounded drafts, policy decisions, approvals, manual replies, takeover, messaging window, echo-based supersede (simulated), approved answers | Attachments analysis (images in DMs are shown as "attachment received" → human), story replies to stories we did not publish, story mentions without an owner-set thank-you (both stay with a person), comments, Human Agent tag |
| Content | Image upload with validation, `feed_image` and `story_image`, AI content drafts with overlay text suggestions, claim validation, approve & schedule, mock publish worker with container semantics, retries with deadline, cancel, on-hold on fact change | Video, Reels, carousels, image generation, hashtags research, best-time suggestions |
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

## 4. Deferred (with reason and trigger)

| Feature | Reason for deferral | Revisit trigger |
|---|---|---|
| WhatsApp owner channel | Cost, verification, policy uncertainty | OQ-01 |
| Story/post **AI image generation** | Not core to the trust loop; model and design effort | OQ-15 after pilots |
| Video/Reels/carousels | Transcoding and validation complexity | Pilot demand |
| Website and profile import | SSRF-safe fetching, scraping quality | Self-service onboarding stage |
| Human Agent tag (7-day replies) | Requires separate permission; human-only | Pilot demand for late replies |
| Billing, plans, usage limits | No paying users yet | Paid commitments (OQ-06) |
| Advanced analytics and Instagram insights | Not the core problem | Pilot demand |
| Multiple Instagram accounts per workspace, agencies | Complexity; not the target segment | Market evidence |
| CRM, lead pipeline, booking integrations | Scope explosion | Strong pilot demand |
| Multi-agent / autonomous campaigns | Contradicts the trust model at this stage | Proven trust + concrete use case |
| Additional reply languages (ru, de) | Tourism segment later | OQ-11 |

## 5. Scope guardrails for implementers

- Do not add a table, endpoint, job type or dependency that no phase document lists, without updating the docs first.
- Do not implement a deferred feature "because it is easy". Raise it instead.
- When in doubt between a simpler and a more general implementation, choose the simpler one and note the limitation in the phase summary.
