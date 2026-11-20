# Pre-Launch Feature Recommendations

**Reviewed:** 2026-11-15, at commit `f1cc494` on `main`.
**Companion document:** [pre-launch-problems.md](pre-launch-problems.md) lists what is broken or inconsistent today. This file lists features to add: first the ones competitors have and Pivoris lacks, then the ones that would set it apart.

**Scope note.** Several items below are on the deferred list in [mvp-scope.md](../product/mvp-scope.md) §4. Per the scope guardrails, update that document and the relevant phase plan before building any of them. Effort sizes (S, M, L) are rough estimates from reading the code, not plans.

## 1. The competitive picture

- **Meta Business Agent** became globally available on 2026-06-03 on WhatsApp, Messenger and Instagram. Meta says it answers business questions, recommends catalogue products, books appointments and qualifies leads. It is free to start, with paid tiers announced for later. The source reviewed mentions human takeover rules but no per-reply approval step.
- **ManyChat** is built around comment-to-DM keyword triggers and a flow builder. Reviewers describe its AI as secondary, available from the paid tier.
- **Jotform Instagram Agent** replies to DMs, comments, story replies and story mentions, learns from past DMs and posts, and connects to Google Calendar.
- **Visito** advertises transcription of Instagram voice notes and automatic replies to them.
- **Kommo** is a WhatsApp-first CRM with strong presence in Türkiye, including a beauty-salon offering with appointment handling.
- No competitor found in this search publishes TRY pricing.

**What this means.** "AI answers your Instagram DMs" is now a free, native feature. Pivoris should lead with what Meta and ManyChat do not offer: verified facts, explicit approval, content and reporting in one place, and a Turkish, in-person setup. Section 3 builds on that.

Most of the competitor information comes from vendor pages and third-party reviews, so treat specific claims as vendor-stated. Sources are listed at the end.

## 2. Features competitors have and Pivoris lacks

| ID | Feature | Priority | Effort |
|---|---|---|---|
| F-01 | Installable app and push notifications | Before pilots | M |
| F-02 | "Try your assistant" test chat | Before pilots | S |
| F-03 | Voice message and image understanding | Before pilots | M |
| F-04 | Story replies and story mentions | Soon after | S to M |
| F-05 | Comment-to-DM on real accounts | Soon after (needs Meta access) | M |
| F-06 | WhatsApp owner channel | Decide from pilot interviews | L |
| F-07 | Story and post template images | Soon after | M |
| F-08 | Carousels and Reels | Later | L |
| F-09 | Import facts from a website or the Instagram profile | Before self-service | M |
| F-10 | Customer follow-up and the 7-day human reply | Later | M |
| F-11 | More reply languages | When tourism segment starts | S to M |
| F-12 | Light lead list with export | Later | S |

### F-01. Installable app and push notifications

**What.** Make the web app installable on a phone (manifest, icons, service worker) and send Web Push for approvals, owner questions and failures.

**Why.** Today the only channel outside the app is Telegram. The project's own risk register rates "owners don't open the web app; approvals go stale" (RK-03) as high likelihood and high impact. Telegram use among Turkish small-business owners is unverified (OQ-01).

**Current state.** No manifest and no service worker in `frontend/`. The notification delivery policy and channel abstraction already exist, so Web Push can be one more channel.

**Suggested scope.** Manifest and icons, a minimal service worker for push only (no offline cache at first), a `web_push` channel next to `telegram`, and an opt-in prompt after the first approval. iOS requires the app to be added to the home screen before push works, so the onboarding step must show how.

### F-02. "Try your assistant" test chat

**What.** A screen where the owner types as a customer and sees what the assistant would answer, with the facts it used, before anything is live.

**Why.** Trust is the product. An owner who has watched the assistant answer ten of their own questions correctly will turn it on; one who has not will not. Meta lets businesses test tone against specific queries during setup.

**Current state.** The simulation endpoints (`/simulate/customer-message` and others) exist but are only reachable through the developer panel when demo tools are enabled. A real workspace has no way to test.

**Suggested scope.** Reuse the mock ingestion path in a sandbox conversation flagged `is_simulated`, excluded from reports and never sent. Add it as the last step of onboarding and as a permanent button on the Assistant page.

### F-03. Voice message and image understanding

**What.** Transcribe voice notes and describe images sent in DMs, then handle them like text.

**Why.** Today any attachment becomes `[attachment]` and goes to a human. Voice notes and product photos ("do you have this?", a screenshot of a price) are a large share of small-business DMs. Visito advertises voice transcription as a feature.

**Current state.** Attachments are stored and shown but not analysed ([inbox/drafting.py](../../backend/app/inbox/drafting.py), the `attachment_only` branch). The LLM abstraction has no audio or vision task.

**Suggested scope.** Start with voice only: fetch the audio, transcribe it, store the transcript on the message labelled as a transcript, and run the normal draft path. Keep approval mandatory for transcript-based replies until quality is measured. Add images second, limited to "describe what the customer sent" for the owner, without automatic answers.

### F-04. Story replies and story mentions

**What.** Treat a reply to the business's story as a normal conversation with the story as context, and acknowledge mentions.

**Why.** Jotform and ManyChat both handle these. Story replies are often the warmest leads because the customer is reacting to a specific offer.

**Current state.** Both are routed to `human_required`.

**Suggested scope.** Story replies first: attach the story's caption or overlay text to the context and draft as usual. For mentions, a single owner-approved thank-you template is enough.

### F-05. Comment-to-DM on real accounts

**What.** When someone comments "price?" on a post, reply privately with the verified answer.

**Why.** This is ManyChat's core feature and the one most small businesses already know by name. The difference Pivoris can offer is that the private reply contains a verified price instead of a fixed link.

**Current state.** Built and tested against the mock provider. On real accounts it cannot work: the OAuth flow does not request a comment permission (see P-05), and research items R75-01 to R75-06 are open.

**Suggested scope.** Finish the research items, add the scope, include it in the App Review submission, then enable per account behind the existing capability flag.

### F-06. WhatsApp owner channel

**What.** Send approvals and the daily summary to the owner on WhatsApp, with buttons.

**Why.** WhatsApp is reported at roughly 88% reach in Türkiye, far above Telegram. The pricing document already lists it in the Growth tier.

**Current state.** Not built. Only Telegram implements the owner channel interface. There is policy risk: WhatsApp's terms restrict general-purpose AI assistants, and whether an AI command interface for owners counts is Meta's call ([platform-capabilities.md](../research/platform-capabilities.md) §2).

**Suggested scope.** Do not start before the pilot interviews answer OQ-01. If owners will not use Telegram or push, build notifications and approval buttons only, and leave free-text commands in the web app to stay clear of the policy question.

### F-07. Story and post template images

**What.** Generate a simple branded image from text: a price card, an opening-hours card, a "this week's classes" card.

**Why.** The Today screen prompts for a story every day, but Instagram stories need the text inside the image, and the owner has to make that image elsewhere. The assistant suggests overlay text and then stops. This is OQ-15.

**Current state.** Upload only. No generation.

**Suggested scope.** Three or four deterministic templates rendered server-side (Pillow), using the workspace's colours and logo, with values filled from verified facts. Because the values come from facts, the existing "hold on price change" logic applies to the image too. No AI image generation.

### F-08. Carousels and Reels

**What.** Schedule multi-image posts and short videos.

**Why.** Every content scheduler supports them, and Instagram's reach favours Reels.

**Current state.** Only `feed_image` and `story_image` ([content/models.py:29](../../backend/app/content/models.py#L29)).

**Suggested scope.** Carousels first; they reuse image validation and need only container changes. Reels need video validation, larger storage and longer container processing, so leave them until pilots ask.

### F-09. Import facts from a website or the Instagram profile

**What.** Give a website address or connect the profile, and get fact candidates to review.

**Why.** Onboarding currently depends on the owner pasting text. Jotform learns from past DMs and posts; Meta learns from catalogues. For self-service signup this is the difference between a five-minute and a thirty-minute setup.

**Current state.** Paste-to-extract only. The candidate review flow already exists and can receive the output.

**Suggested scope.** Profile import first (bio, contact buttons, recent captions through the existing API grant), since it needs no outbound fetching. Website fetch needs SSRF protection and is second. All imported values stay unverified candidates.

### F-10. Customer follow-up and the 7-day human reply

**What.** Two related things. A single polite follow-up inside the 24-hour window when a customer asked about a price and went quiet. And the Human Agent tag, which lets a person reply up to seven days later.

**Why.** ManyChat sells follow-up sequences. Without the tag, a DM the owner misses for a day can no longer be answered through the API at all.

**Current state.** No proactive follow-up to customers was found in the backend. The Human Agent tag is not implemented and needs its own Meta permission.

**Suggested scope.** One follow-up at most, owner-approved by default, never after the window closes. Add the Human Agent tag for manual replies only.

### F-11. More reply languages

**What.** Reply in Russian, German and Arabic in addition to Turkish and English.

**Why.** The planned Antalya segment serves tourists. Today any other language is escalated with `LANGUAGE_UNSUPPORTED`.

**Current state.** `reply_languages` is per workspace but only `tr` and `en` are accepted.

**Suggested scope.** The model can already write these languages. The work is in the deterministic parts: language detection, the claim validator's number and date formats, and eval sets per language.

### F-12. Light lead list with export

**What.** A list of customers who asked about a price or booking and did not convert, with a CSV export.

**Why.** Kommo is strong in Türkiye because owners want to see who to call back. A full CRM is a declared non-goal, and should stay one.

**Suggested scope.** One filtered view over existing conversations and customer memory, plus export. No pipelines, stages or custom fields.

## 3. Features that would set Pivoris apart

These build on things the product already does that the competitors reviewed do not.

| ID | Feature | Effort |
|---|---|---|
| D-01 | Make the "never invents a price" guarantee visible | S |
| D-02 | Approval ladder with automatic suggestions | M |
| D-03 | Missed-customer report in lira | S to M |
| D-04 | Lead with "manage by chat, no flow builder" | S |
| D-05 | Show the assistant learning from owner answers | S |
| D-06 | Local package: Turkish, KVKK, TRY invoice, in-person setup | S |

### D-01. Make the "never invents a price" guarantee visible

**What exists.** Prices, hours and contacts come only from verified facts through placeholders, and a claim validator checks every draft. A price change automatically holds scheduled posts that carry the old price. None of the competitors reviewed describes anything like this.

**What to add.** Show the source beside every number in a draft ("from: Monthly membership, verified 3 Nov"). Add a line to the daily report: "Replies sent: 42. Unverified values: 0." Put the price-change hold in the first minute of every sales demo.

### D-02. Approval ladder with automatic suggestions

**What exists.** Everything starts as approval-required, and the owner can turn on automatic sending per low-risk intent.

**What to add.** Have the product propose the next step: "You approved this kind of answer 20 times without editing it. Send these automatically from now on?" No such suggestion mechanism exists in the code today. This turns approval from a chore into a path, and it is the opposite of the "switch it on and hope" model.

**Suggested scope.** A weekly job that counts unchanged approvals per intent and creates one notification with a confirm button. The existing delegation preview and apply endpoints do the rest.

### D-03. Missed-customer report in lira

**What to add.** A weekly summary: DMs that arrived outside opening hours, median time to first reply before and after, conversations left unanswered, and an estimate in TRY using the business's own verified prices.

**Why.** The pricing document's whole argument is "one saved customer a month pays for the subscription". This report is the proof, generated from data the system already holds, and it is what the owner shows a business partner.

### D-04. Lead with "manage by chat, no flow builder"

**What exists.** The owner types "monthly membership is now 7,000 TL" and the fact is updated, versioned and applied to the next reply. ManyChat requires building flows.

**What to add.** Mostly positioning. Move the command box to the top of the Today screen on phones (see P-13), and make sure every common task has a command. Rescheduling and "pause the assistant until tomorrow" are obvious candidates.

### D-05. Show the assistant learning from owner answers

**What exists.** When the assistant lacks a fact, it asks the owner (`owner.ask`) and can use the answer.

**What to add.** Close the loop visibly: after the owner answers, offer "Save this as a verified fact?" in one tap, and show a running count on the Assistant page ("Learned 14 things from you this month"). Owners should see the knowledge base grow from daily use instead of from data entry.

### D-06. Local package: Turkish, KVKK, TRY invoice, in-person setup

**What exists.** Turkish-first interface and replies, KVKK document templates, a planned in-person onboarding.

**What to add.** State it on the landing page as a package, with a TRY price once pricing is settled. No competitor found publishes TRY pricing or offers local setup.

## 4. Suggested order

1. **Before the first pilot:** F-02 (test chat), F-01 (push), D-01 (visible guarantee). All three reduce the two biggest pilot risks: owners not trusting the assistant and owners not seeing approvals.
2. **During pilots:** F-03 (voice), D-03 (missed-customer report), D-02 (approval ladder), F-04 (story replies).
3. **After App Review:** F-05 (comment-to-DM), F-07 (template images).
4. **Before self-service launch:** F-09 (import), plus signup and billing from the problems document (P-10, P-11).
5. **On demand:** F-06 (WhatsApp, pending OQ-01), F-08, F-10, F-11, F-12.

## Sources

- [Meta Business Agent global launch (ppc.land)](https://ppc.land/meta-business-agent-brings-ai-customer-service-to-whatsapp-globally/)
- [Meta's customer service agent pilot for small businesses (CX Today)](https://cxtoday.com/meta-introduces-a-customer-service-ai-agent-for-facebook-instagram-targets-smbs-with-free-trial)
- [Jotform Instagram Agent features](https://www.jotform.com/tr/ai/instagram-agent/features/)
- [Visito Instagram AI](https://www.visitoai.com/ai-agents/instagram-ai)
- [ManyChat review (Featurebase)](https://www.featurebase.app/blog/manychat-review)
- [Kommo for beauty salons](https://www.kommo.com/tr/sektorler/guzellik/)
- [Customer communication in Türkiye: WhatsApp and CRM (ShiftDelete)](https://shiftdelete.net/turkiyede-musteri-iletisimi-whatsapp-ile-crm-arasinda-satis-yonetiminin-yeni-dengesi?amp=1)
