# Pricing Strategy and Unit Economics (Türkiye & Global)

**Purpose:** Define the cost structure (COGS), unit economics, packaging, and pricing tiers for the Pivoris hosted SaaS across both the **Türkiye** (high-touch, TRY) and **Global** (self-service, USD) markets, while respecting the open-source core boundary ([ADR-019](../architecture/decisions/ADR-019-open-source-and-hosted-boundary.md)) and open questions ([OQ-01, OQ-06, OQ-09](../research/open-questions.md)).

> [!IMPORTANT]
> **What is built today (reconciled against code, Feature Phases 1–5 & Pilot Readiness Sessions 01–08, 2026-11-19).** Sell only what an owner can use on day one: one Instagram Professional account per workspace, mobile web app, Telegram owner control (primary), WhatsApp owner control (optional alternative, delivered in Session 02), 5 customer reply languages (`tr`, `en`, `ru`, `de`, `ar` with app UI strictly `tr` and `en`), grounded DM drafts with semi-automation (basic FAQ auto-sends under explicit owner grant; complex questions require human approval), private replies via Comment-to-DM, template images, feed carousels and video Reels, voice note transcripts & image descriptions, lead lists, test chat with Account Agent parity, and daily activity reports. Each workspace has a plan (`starter` 500, `growth` 2,500, or `pro` 7,500 AI replies per month; default `growth` on trial), a monthly reply counter, and warnings at 80% and 100% with a 10% grace buffer (built, P-11; operator manages plans via CLI, see §4 and §8). Automated billing does not exist in the code; all billing is manual (bank transfer / EFT invoice; CLI `plan-extend` is operational quota tracking, not payment enforcement). Pilots are managed by hand (§6, stage 1). The findings per feature are in [§8](#8-what-the-code-supports-today-p-19-check).

---

## 1. Pricing Philosophy & Value Anchor

Small business owners do not buy "tokens", "agent steps", or "API calls". They buy **peace of mind, saved evenings, and captured leads**:
1. **No lost night-time leads:** Answering a *"Merhaba, aylık üyelik ne kadar?"* DM at 23:45 while the studio is closed converts a prospect who would otherwise message a competitor.
2. **Zero hallucination risk:** Unlike generic AI bots, every price, opening hour, and campaign is backed by verified `{{fact:key}}` placeholders and checked by the deterministic claim validator ([INV-02](../invariants.md)).
3. **Zero stale promotions:** Updating a price via natural language automatically places scheduled posts carrying the old price on hold.

### The ROI Anchor
- **In Türkiye:** A single reformer Pilates package, gym membership, or clinic appointment is worth **₺3,000 – ₺7,500**. Hiring a freelance social media manager or agency costs **₺10,000 – ₺25,000/month** (and agencies still ask the owner for price confirmations and don't reply to DMs at midnight). If Pivoris saves **one customer per month** and 15 hours of repetitive typing, a **₺1,490 – ₺2,490/month** subscription delivers a **3x–10x return**.
- **Globally:** Competing tools either require building fragile flowcharts (ManyChat at \$15–\$65/mo), charge steep omnichannel seat prices (Respond.io / Gorgias at \$79–\$159/mo), or use ungrounded AI wrappers (\$49–\$99/mo) that hallucinate discounts. A flat **\$29 – \$59/month** position hits the SMB sweet spot.

---

## 2. Granular Cost Breakdown (COGS & Unit Economics)

Every external cost driver in Pivoris is bounded by deterministic limits in the codebase ([agent-runtime.md](../architecture/agent-runtime.md), [account-agent-contracts.md](../architecture/account-agent-contracts.md), [.env.example](../../.env.example)).

### 2.1 LLM API Costs (OpenAI Responses API)

Per [platform-capabilities.md §4](../research/platform-capabilities.md), the confirmed GPT-6 family pricing is:

| Model Tier | Input (per 1M tokens) | Cached Input (~50% off) | Output (per 1M tokens) | Role in Pivoris |
|---|---|---|---|---|
| **`gpt-6-luna`** (Default) | \$0.10 | \$0.05 | \$0.50 | Default across all tasks (`LLM_MODEL_DEFAULT=gpt-6-luna`, `LLM_REASONING_EFFORT=low`) |
| **`gpt-6.1-sol`** | \$2.00 | \$1.00 | \$10.00 | Optional upgrade for high-nuance `draft_content` or complex multi-turn reasoning |
| **`gpt-6-astra`** | \$10.00 | \$5.00 | \$50.00 | Not needed for runtime SMB tasks |

#### Token Consumption per Operation
Because system prompts are static and ordered first ([agent-runtime.md §10](../architecture/agent-runtime.md)), OpenAI automatically caches prefix tokens across calls.

| Operation | Avg Input Tokens | Avg Output Tokens | Cost on `gpt-6-luna` | Cost on `gpt-6.1-sol` |
|---|---|---|---|---|
| **Legacy `draft_reply`** (1 call + 5% repair/regen rate) | ~1,800 | ~250 | **\$0.00032** | \$0.0064 |
| **Phase 7.5 `account_agent_step`** (avg 2.2 steps per DM/comment turn) | ~5,000 total | ~600 total | **\$0.00080** | \$0.0160 |
| **Owner `interpret_command`** (1 call) | ~1,500 | ~200 | **\$0.00025** | \$0.0050 |
| **Content `draft_content`** (1 call) | ~1,600 | ~450 | **\$0.00039** | \$0.0077 |
| **Onboarding `extract_fact_candidates`** (one-off / rare) | ~2,500 | ~800 | **\$0.00065** | \$0.0130 |

#### Monthly LLM Cost by Customer Activity Profile

| Customer Profile | Monthly Activity Volume | Monthly LLM calls | Monthly Cost (`gpt-6-luna`) | Monthly Cost (Hybrid: `luna` + `sol` for content) |
|---|---|---|---|---|
| **Light SMB** (Burdur Pilates studio, 20 DMs/day) | 600 DMs, 150 comments, 15 posts, 40 owner commands | ~1,700 calls | **\$0.65 / mo** | **\$0.80 / mo** |
| **Typical SMB** (Busy salon/gym, 50 DMs/day) | 1,500 DMs, 600 comments, 25 posts, 90 owner commands | ~4,800 calls | **\$1.85 / mo** | **\$2.10 / mo** |
| **Heavy SMB** (Popular boutique/clinic, 120 DMs/day) | 3,600 DMs, 1,500 comments, 40 posts, 150 owner commands | ~11,500 calls | **\$4.40 / mo** | **\$4.80 / mo** |
| **Hard Ceiling** (`LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY=500`) | Maxed out at 500 calls/day × 30 days | 15,000 calls (cap) | **\$5.80 / mo max** | **\$6.50 / mo max** |

> [!TIP]
> **Cost Control Built Into the Architecture:**
> - **Reply Debounce (`REPLY_DEBOUNCE_SECONDS=8`):** When a customer sends 4 rapid messages in a row (*"Merhaba" / "Fiyat nedir?" / "Hafta sonu açık mısınız?"*), Pivoris coalesces them into **one** LLM draft call.
> - **Hard Daily Cap (`LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY=500`):** Even if an account is targeted by spam or a loop, a workspace can never exceed 500 model calls/day (~15,000/month = **<\$6/month** on `gpt-6-luna`).

---

### 2.2 Infrastructure, Database & Storage Costs

Pivoris is architected as a lean modular monolith ([ADR-001](../architecture/decisions/ADR-001-modular-monolith.md)) using PostgreSQL for both persistence and background jobs ([ADR-004](../architecture/decisions/ADR-004-postgresql-only-datastore.md), [ADR-006](../architecture/decisions/ADR-006-postgres-job-queue.md))—eliminating Redis and Celery overhead.

| Stage | Capacity | Topology ([deployment.md](../architecture/deployment.md)) | Total Monthly Infra | Infra Cost per Workspace |
|---|---|---|---|---|
| **Stage S3: Pilots & Early Traction** | 10 – 50 Workspaces | Single VPS or Railway project (2 vCPU / 4 GB RAM) + Postgres + Cloudflare R2 (media & 35-day encrypted `pg_dump` backups) + Domain | **\$18 – \$30 / mo** | **\$0.50 – \$1.80 / mo** |
| **Stage S4: Growth SaaS** | 50 – 250 Workspaces | 2× App/Worker instances + Managed PostgreSQL (with automated HA) + Cloudflare R2 + Sentry + Uptime monitoring | **\$90 – \$160 / mo** | **\$0.65 – \$1.20 / mo** |
| **Stage S5: Scale** | 250 – 1,000 Workspaces | Scaled API/Worker pool + Dedicated DB + Read Replica + R2 | **\$350 – \$600 / mo** | **\$0.50 – \$0.75 / mo** |

- **Media Storage Cost:** Images are capped at 8 MB (`MEDIA_MAX_IMAGE_BYTES=8388608`), converted to JPEG, and automatically pruned after 90 days (`RETENTION_PUBLISHED_MEDIA_DAYS=90`) or 7 days for orphans (`RETENTION_MEDIA_ORPHAN_DAYS=7`). Video Reels are capped at 300 MB and 2 GiB workspace quota. Using **Cloudflare R2** (\$0.015/GB-month, **\$0 egress** when Meta fetches presigned URLs), 50 posts/month per workspace costs **< \$0.02 / workspace / month**.

---

### 2.3 Channel & Platform Costs (Meta, Telegram, WhatsApp)

| Channel / API | Provider Fee | Notes & Cost Optimization |
|---|---|---|
| **Instagram Graph API** (DMs, Comments, Publishing) | **\$0.00** | Free. Rate-guarded at 50 publishes/day (`PUBLISH_DAILY_LIMIT=50`). |
| **Mobile Web App** | **\$0.00** | Primary interface; zero per-notification cost. Web Push device opt-in supported. |
| **Telegram Bot API** (Phase 9 & Session 01 Owner Channel) | **\$0.00** | 100% free inline approval buttons, media uploads, and alerts. Primary recommended day-one channel. |
| **WhatsApp Business Cloud API** (Optional Owner Channel, delivered in Phase 5 Track A + Session 02) | **\$0.00** inside 24h window<br>**~\$0.005–\$0.04** per utility template outside window | Optional first-class alternative (not compulsory; Telegram and Web remain primary). Replies and utility messages sent **within 24 hours of an owner's message/button tap are free**. Proactive utility templates sent >24h after owner's last interaction incur Meta's per-message fee (~\$0.50–\$2.50/mo per active owner). |

> [!TIP]
> **WhatsApp Margin Protection Rule:**
> WhatsApp is an optional channel choice, not a mandatory requirement. Keep **Web + Telegram** as the primary \$0 messaging COGS foundation, and offer **WhatsApp Owner Control** as an opt-in channel. Daily activity summaries or approval cards naturally refresh the 24-hour WhatsApp service window when tapped, maintaining daytime approval cards at **\$0.00** Meta fee.

---

### 2.4 Total Unit Economics Summary (Per Active Workspace / Month)

| Cost Component | Starter Workspace (Light/Typical, Web/Telegram) | Growth Workspace (Typical/Heavy, WhatsApp + Agent) |
|---|---|---|
| **LLM API (`gpt-6-luna` default)** | \$0.65 – \$1.50 | \$1.85 – \$4.40 |
| **Compute, DB & Encrypted Backups** | \$0.60 – \$1.00 | \$0.75 – \$1.20 |
| **Media & Backup Storage (R2/S3)** | \$0.05 | \$0.10 |
| **Owner Messaging (Telegram vs WhatsApp)** | \$0.00 (Telegram/Web) | \$0.50 – \$2.00 (WhatsApp Cloud API, if opted-in) |
| **Transactional Email (SMTP)** | \$0.05 | \$0.05 |
| **Total Tech COGS / Month** | **\$1.35 – \$2.60 / mo** (~₺48 – ₺95) | **\$3.25 – \$7.75 / mo** (~₺115 – ₺275) |
| **Payment Gateway Fee (~3% – 5%)** | ~\$0.90 – \$1.40 | ~\$1.80 – \$3.00 |
| **Total All-In Marginal Cost** | **~\$2.25 – \$4.00 / mo** | **~\$5.05 – \$10.75 / mo** |

At our recommended pricing below, **Gross Margin is 85%–91% in Türkiye and 86%–92% Globally**.

---

## 3. Türkiye Pricing Plan (TRY · `tr_TR`)

*Note: All TRY prices below are shown excluding 20% KDV (B2B standard in Türkiye; display as `+ KDV` on invoices, or show KDV-included equivalents on local retail checkout).*

### 3.1 Phase 1: Assisted Pilot Programme (First 10–15 Businesses)
Target: Local studios, gyms, salons, cafés, and clinics in Bucak, Burdur, and Antalya ([vision.md §4](vision.md)).

| Stage | Offer | Price | Purpose & Commercial Terms |
|---|---|---|---|
| **1. Pilot Trial (7 Days or 30 Days)** | **Ücretsiz Pilot (7 veya 30 Gün)** | **0 ₺** (No credit card required) | Operator sets up verified facts in 30 mins with the owner, connects Instagram, configures semi-automation delegation and channels, and runs live test DMs. Trial duration is agreed at onboarding (either 7 days or 30 days) and recorded in the Onboarding Record. **No credit card is required, and no automated charge occurs at trial end.** |
| **2. Pilot Founder Lock-In** | **Kurucu İşletme Paketi** | **990 ₺ / ay** (+ KDV)<br>*(Locked for 12 months)* | Rewards the first 10–15 pilot businesses for feedback and case-study permission. Invoiced manually via bank transfer (Havale/EFT) with *E-Arşiv Fatura*. Yields **~82% gross margin**. |

> [!NOTE]
> **Manual Billing & Plan Management:**
> Billing is handled 100% manually. At the conclusion of the agreed free trial (7 or 30 days), the workspace is not automatically charged. The operator issues an EFT/Havale invoice. Workspace quota periods are managed using the CLI command `python -m app.cli plan-extend --workspace <slug> --days <N>`. Running `plan-extend` is an operational quota and period adjustment—it does **not** represent automated payment enforcement or billing renewal.

---

### 3.2 Phase 2: Standard Türkiye Commercial Tiers

| Feature / Limit | **Başlangıç (Starter)** | **İşletme (Growth — Önerilen)** | **Stüdyo & Şube (Pro)** |
|---|---|---|---|
| **Monthly Price (Monthly Billing)** | **1.490 ₺ / ay** | **2.490 ₺ / ay** | **4.490 ₺ / ay** |
| **Annual Price (2 Months Free)** | **1.240 ₺ / ay** *(14.900 ₺/yıl)* | **2.075 ₺ / ay** *(24.900 ₺/yıl)* | **3.740 ₺ / ay** *(44.900 ₺/yıl)* |
| **Connected Instagram Accounts** | 1 Profesyonel Hesap | 1 Profesyonel Hesap | 3 Profesyonel Hesaba Kadar (**Planned**: bugün çalışma alanı başına 1 hesap) |
| **Team Members (`owner`/`manager`/`staff`)** | 2 Kullanıcı (Sahip + 1 Personel) | 5 Kullanıcı | 15 Kullanıcı |
| **Verified Business Knowledge Ledger** | Sınırsız bilgi kartı + Fiyat doğrulayıcı | Sınırsız bilgi kartı + Fiyat doğrulayıcı | Sınırsız + Şubeler arası şablon |
| **AI DM Replies & Drafts** | **500 yanıt / ay** | **2.500 yanıt / ay** | **7.500 yanıt / ay** |
| **Comment Automation ("Fiyat?" → Özel Yanıt)** | Dahil (Yorumdan DM'ye özel yanıt) | Dahil (Yorumdan DM'ye özel yanıt) | Dahil (Yorumdan DM'ye özel yanıt) |
| **Autonomous Account Agent (ADR-024)** | Yarı otonom (Doğrulanmış SSS oto-yanıt + karmaşık sorularda onay) | **Tam Hesap Ajanı** (Müşteri hafızası, takvim rezervasyonları, sesli not transkripti, görsel anlama) | **Tam Hesap Ajanı** + Öncelikli kota |
| **Scheduled Posts, Stories, Carousels & Reels** | 15 paylaşım / ay | 50 paylaşım / ay (Şablon görsel, Carousel & Reel dahil) | 150 paylaşım / ay (Meta 50/gün tavanına kadar) |
| **Auto-Hold on Price Change** | Dahil | Dahil | Dahil |
| **Owner Control Channels** | Mobil Web + **Telegram** (Birincil) | Mobil Web + Telegram + **WhatsApp** (İsteğe bağlı) | Mobil Web + Telegram + **WhatsApp** (İsteğe bağlı) |
| **Reply Languages (Müşteri Yanıt Dilleri)** | 5 Dil (`tr`, `en`, `ru`, `de`, `ar`) | 5 Dil (`tr`, `en`, `ru`, `de`, `ar`) | 5 Dil (`tr`, `en`, `ru`, `de`, `ar`) |
| **Lead List (Potansiyel Müşteri Listesi)** | Dahil (Fiyat ve rezervasyon niyetleri) | Dahil + CSV dışa aktarımı | Dahil + CSV dışa aktarımı |
| **Daily Honest Activity Report** | Günlük özet + 90 gün kayıt | Günlük özet + 1 yıl tam denetim kaydı | Günlük özet + 2 yıl denetim kaydı |
| **Onboarding & Support** | Hızlı metin yapıştırma + E-posta/Destek | **30 dk görüntülü birlikte kurulum** + WhatsApp destek hattı | **Birebir kurulum** + Öncelikli SLA desteği |

### 3.3 Assisted Setup Fee ("Anahtar Teslim Kurulum")
- **One-Time Assisted Setup Fee:** **2.500 ₺** (We extract your price list, verify every fact card together, configure your brand voice, connect Meta permissions, and test 5 live scenarios).
- **Waived (0 ₺)** when the business chooses **İşletme (Growth)** on an annual commitment, or used as a field-sales incentive during in-person visits in Burdur/Antalya (*"Bu hafta birlikte kurarsak 2.500 ₺ kurulum ücreti almıyoruz"*).

---

## 4. Global Pricing Plan (USD · Self-Service SaaS)

For the global English-speaking market ([idea.md §2.2](../idea.md)), onboarding is 100% self-service via paste-to-extract (`extract_fact_candidates`) and interactive sandbox testing.

| Feature / Limit | **Starter** | **Growth (Most Popular)** | **Scale** |
|---|---|---|---|
| **Monthly Price** | **\$29 / mo** | **\$59 / mo** | **\$119 / mo** |
| **Annual Price (~20% off)** | **\$24 / mo** *(\$288/yr)* | **\$49 / mo** *(\$588/yr)* | **\$99 / mo** *(\$1,188/yr)* |
| **Instagram Professional Accounts** | 1 Account | 1 Account | Up to 3 Accounts (**Planned**: 1 per workspace today) |
| **Workspace Seats (`owner`/`manager`/`staff`)** | 2 Seats | 5 Seats | 15 Seats |
| **AI DM Replies & Drafts** | **500 / mo** | **2,500 / mo** | **10,000 / mo** |
| **Comment Moderation & Private Replies** | Comment-to-DM Private Reply Included | Comment-to-DM Private Reply Included | Comment-to-DM Private Reply Included |
| **Account Agent & Semi-Automation** | Semi-autonomous (Verified FAQ auto-reply + human approval) | **Full Account Agent** (Customer memory, bookings, voice/image context) | **Full Account Agent** |
| **Scheduled Feed, Story, Carousel & Reel Posts** | 20 / mo | Unlimited *(up to Meta 50/24h limit)* | Unlimited *(up to Meta 50/24h limit)* |
| **Verified Fact Ledger & Claim Validator** | Included | Included | Included |
| **Auto-Hold Scheduled Posts on Price Change** | Included | Included | Included |
| **Owner Notification & Approval Channels** | Mobile Web + **Telegram** (Primary) | Mobile Web + Telegram + **WhatsApp** (Optional) | Mobile Web + Telegram + **WhatsApp** (Optional) |
| **Reply Languages** | 5 Languages (`en`, `tr`, `ru`, `de`, `ar`) | 5 Languages (`en`, `tr`, `ru`, `de`, `ar`) | 5 Languages (`en`, `tr`, `ru`, `de`, `ar`) |
| **Lead List & Export** | Included | Included + CSV export | Included + CSV export |
| **Audit Log & Message Retention** | 90 days | 365 days | 2 years + JSON/CSV data export (**Planned**: only per-customer/per-conversation export today) |

### Trial & Overage Policy (Global & Türkiye)

> **Built (P-11), except the trial cap and self-service upgrade.** Every workspace has a monthly AI reply quota (the plan's, or an operator override), a counter, warnings at 80% and 100%, a 10% grace buffer and a pause afterwards, all described below and in [§8](#8-what-the-code-supports-today-p-19-check). **Not built:** the 100-reply cap during the 14-day trial (a trial workspace gets its plan's full quota), the one-tap plan upgrade (the operator changes the plan with `python -m app.cli plan-set`), and any billing. The daily model-call cap per workspace (`LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY`) remains a separate safety net.

1. **Free Trial:** Users explore the full simulated workspace immediately with zero credentials (`is_simulated`), paste their bio/price list, and connect their real Instagram account for a 7-day or 30-day trial without credit card.
2. **Soft Overages (No Surprise Bills):** If a workspace reaches 100% of its monthly AI reply quota:
   - We send an owner notification at **80%** and **100%** usage (once per period, to owners and managers, through every channel they use).
   - We provide a **10% grace buffer** so active customer conversations are never abruptly dropped mid-day.
   - After the grace buffer, incoming DMs still appear in the Inbox and trigger human notifications, while AI drafting pauses until the next billing cycle or a plan change (operator changes the plan via CLI; one-tap upgrade is **Planned**). What counts: every customer reply draft the AI prepares (direct message, public comment reply, private reply), once per draft, whether approved, edited, auto-sent or discarded; manual replies, owner commands, content drafts and the test chat do not count. The USD Scale tier (10,000) is set via `plan-set --plan pro --quota 10000`.

---

## 5. Open-Source Core vs. Hosted SaaS Value Boundary

Per [ADR-019](../architecture/decisions/ADR-019-open-source-and-hosted-boundary.md), Pivoris has an open-source core. Why will businesses pay for the Hosted SaaS instead of self-hosting?

| Capability | Self-Hosted Open-Source Core | Pivoris Hosted SaaS |
|---|---|---|
| **Price** | Free (bring your own VPS, S3, OpenAI key) | **₺1,490–₺4,490/mo** or **\$29–\$119/mo** |
| **Meta App Review & Business Verification** | **Self-hoster must apply**, submit screencasts, verify a legal business entity with Meta, and maintain compliance | **Instant 1-click OAuth** via Pivoris's verified Meta App (after Meta App Review is granted; pilots use tester roles until then) |
| **WhatsApp & Telegram Bot Setup** | Self-hoster must register bots, webhooks, and Meta Cloud API numbers | **Pre-configured & managed** |
| **Hosting, TLS, Postgres & S3 Media** | Self-managed Docker Compose, SSH deploys, S3 buckets | **Fully managed**, zero maintenance |
| **Encrypted Off-Site Backups & Restore Drills** | Self-hoster configures `BACKUP_ENCRYPTION_KEY` & S3 | **Automated nightly AES-256-GCM backups** (35-day retention; tooling delivered, scheduling on Railway documented) |
| **Assisted Onboarding & Support** | Community docs only | **30-minute assisted setup** + WhatsApp/Email support |

---

## 6. Billing Infrastructure Roadmap (Resolving OQ-06 in Stages)

Do not build complex billing engineering before paid pilot validation ([mvp-scope.md §4](mvp-scope.md)):

1. **Stage 1 — Assisted Pilots (Workspaces 1–15, Türkiye):**
   - **Billing method:** Manual invoicing (*E-Arşiv Fatura* via GİB portal or Paraşüt) + **EFT/Havale** or a static **iyzico Link / PayTR Link** sent over WhatsApp.
   - **Code changes required:** **Zero.** Manage workspace limits with the operator CLI (`plan-usage`, `plan-set`, `plan-reset`, `plan-extend`).
2. **Stage 2 — Commercial Türkiye Rollout (Workspaces 15–100):**
   - **Billing provider:** **iyzico** (Subscription API with saved cards in TRY) or **PayTR**.
   - **Code changes required:** Add optional `app/hosted/billing` module ([ADR-019](../architecture/decisions/ADR-019-open-source-and-hosted-boundary.md)) storing customer and subscription IDs and driving existing plan fields from webhooks.
3. **Stage 3 — Global Self-Service Launch:**
   - **Billing provider:** **Lemon Squeezy** or **Paddle** (Merchant of Record), or **Stripe Billing**.

---

## 7. Break-Even & Profitability Projections

Assuming **Stage S4 Infrastructure** fixed costs of **~\$120/month** (VPS/Railway + Managed DB + R2 + Domain + Business tools):

| Milestone | Customer Mix | Monthly Recurring Revenue (MRR) | Total Tech + Payment COGS | Net Infrastructure & AI Profit | Gross Margin |
|---|---|---|---|---|---|
| **Break-Even** | **3 Türkiye Starter** customers (3 × ₺1,490) | ~\$130 / mo (₺4,470) | ~\$128 / mo | **+\$2 / mo** (Break-even!) | — |
| **15 Pilot Studios** | 10 Kurucu (₺990) + 5 İşletme (₺2,490) | **~\$650 / mo** (₺22,350) | ~\$175 / mo | **+\$475 / mo** (~₺16,300) | **73%** |
| **50 TR Businesses** | 20 Başlangıç + 25 İşletme + 5 Stüdyo | **~\$3,320 / mo** (₺114,500) | ~\$360 / mo | **+\$2,960 / mo** (~₺102,000) | **89%** |
| **100 TR + 100 Global** | 100 TR (avg ₺2,100) + 100 Global (avg \$48) | **~\$10,900 / mo** (~₺375,000) | ~\$1,150 / mo | **+\$9,750 / mo** (~₺335,000) | **89.4%** |

---

## 8. What the code supports today (P-19 check)

Reconciled against the codebase on 2026-11-19 following Feature Phases 1–5 and Pilot Readiness Sessions 01–08.

| Tier feature | Finding in the code | Status |
|---|---|---|
| WhatsApp owner channel | `backend/app/integrations/channels/whatsapp/` provides a full WhatsApp Cloud API adapter with interactive button approvals, webhook verification, linking flow, quiet hours, and delivery ledger integration (delivered in Feature Phase 5 Track A and Session 02). WhatsApp is an optional channel choice; Telegram and web remain primary. | Delivered (Optional) |
| 5 customer reply languages (`tr`, `en`, `ru`, `de`, `ar`) | Centralized in `app/core/reply_languages.py` (`ReplyLanguage`). Grounding claim validator, calendar responses, approved answers, and Agent DM/comment flows support all 5 languages (delivered in Feature Phase 5 Track D and Session 04). Arabic RTL text respects the 1000-byte limit. App UI remains strictly `tr` and `en`. | Delivered |
| Comment-to-DM on real accounts | Real connections request `instagram_business_manage_comments` in OAuth scopes. Deterministic private-reply rules enforce one-shot replies, price disclosure checks, and auto-escalation (delivered in Feature Phase 3 Track A and Session 08). Public comment moderation remains off for safety. | Delivered |
| Template images | Brand settings (`app/content/brand.py`) and deterministic SVG/Pillow template engine produce styled promotional images with verified facts (delivered in Feature Phase 3 Track B). Price changes automatically hold affected content. | Delivered |
| Lead list | `app/reporting/leads.py` extracts qualifying prospect enquiries for pricing and bookings. Conversion requires an eligible confirmed linked appointment. CSV export includes formula injection sanitization (delivered in Feature Phase 5 Track E and Session 06). | Delivered |
| Carousels and Reels | Media storage, video validation (300 MB cap, 2 GiB workspace quota), feed carousels, and video Reels publishing containers are implemented and verified (delivered in Feature Phase 5 Track B and Session 08). | Delivered |
| Voice notes & image descriptions | Inbound voice notes are transcribed (whisper/fake); image attachments receive contextual descriptions. Durable Agent events wake the Account Agent safely. The transcript approval floor strictly enforces human review (`ask`) for voice replies (delivered in Feature Phase 2, Feature Phase 5 Track B, and Session 05). | Delivered |
| Test chat Account Agent parity | Sandbox (`app/inbox/sandbox.py`) executes production Agent proposal, grounding, and policy evaluation with isolated storage and simulated tool results. Zero external side effects, customer memory writes, or report pollution (delivered in Feature Phase 1 and Session 07). | Delivered |
| Quota warnings (80% and 100%, grace buffer) and monthly AI reply quota | `workspace_plans` and `reply_usage` (migration `0051`), `app/plans/`, and notifications `quota.warning`, `quota.grace`, `quota.paused`. Counted per AI reply draft under a row lock, rolled over monthly, warned once per period; at 110% drafting pauses with `REPLY_QUOTA_PAUSED`. Enforced in code (P-11). | Built (P-11) |
| Manual billing & commercial boundaries | No automated billing exists in the codebase. Pilot billing is handled manually via EFT/Havale invoicing. CLI commands (`plan-usage`, `plan-set`, `plan-reset`, `plan-extend`) manage operational quotas and period records. Running `plan-extend` is an operational period adjustment, not payment enforcement. | Manual in pilot stage 1 |
| Up to three Instagram accounts | `social_accounts` has a unique partial index `uq_social_accounts_active_workspace`: one non-disconnected account per workspace. Multiple concurrent connected accounts require a schema migration. | Planned (1 account per workspace today) |
| Whole-workspace data export | Per-conversation and per-customer JSON export exists (`/workspaces/{ws}/conversations/{id}/export`, `app/operations/data_rights.py`) as a data-rights tool. Whole-workspace and audit-log batch JSON/CSV export is deferred. | Planned (data-rights export exists) |

### Video storage cost (derived, not measured; Session 06)

Using Cloudflare R2 rate of $0.015/GB-month and $0 egress: the 300 MB file cap and 2 GiB/workspace quota imply a worst case of about **$0.03/month/workspace** including thumbnails (roughly 1 MB each). A typical 30–60 s phone Reel of 20–60 MB costs about **$0.0003–$0.0009/month/video** while retained. Orphan videos are removed after 7 days; media referenced only by published items after 90 days. Quota and retention are the cost levers.
