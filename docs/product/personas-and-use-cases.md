# Personas and Use Cases

**Purpose:** Who uses or is affected by the product, what they do, and which use cases matter most. Detailed step-by-step flows are in [user-journeys.md](user-journeys.md).

These personas are **hypotheses** to validate in pilot interviews (original spec §3). Gyms and Pilates studios are the first segment, beauty salons a possible second, and Antalya tourism businesses later.

## 1. Personas

### P1: Selin, Pilates studio owner (primary)
- Runs a 2-instructor reformer Pilates studio in Burdur. About 300 followers, 10–30 DMs per day, more after posting a campaign.
- Answers DMs on her phone between sessions, often at night. Repeats price, schedule and trial-session answers. Sometimes forgets to answer.
- Not technical. Uses Instagram, WhatsApp and a banking app daily. Has never configured software beyond installing apps.
- Wants: fewer repetitive replies, no wrong prices, a simple way to post weekly class announcements.
- Fears: "the bot says something wrong to my customers", a price she did not approve, losing control of her account.
- **Implications:** Turkish UI, approval-by-default, readable approval cards, no jargon, setup done *with* her (assisted onboarding).

### P2: Murat, gym owner/manager (primary)
- Owns a mid-size gym in Bucak with a front-desk staff member. Membership prices change once or twice a year. Frequent campaigns (student discount, summer package).
- Wants: correct campaign answers, a daily summary ("how many people asked about prices?"), staff able to help without seeing everything.
- **Implications:** promotion facts with validity windows, `staff` role, daily report, fact change → affected content flagged.

### P3: Elif, front-desk staff (secondary)
- Helps reply to DMs and prepares posts, but must not change prices or publish without the owner.
- **Implications:** `staff` role. Staff can draft, write manual replies, propose fact changes (as candidates) and submit content for approval.

### P4: The founder as onboarding assistant (internal)
- Visits businesses, connects their Instagram account, enters and verifies facts together with the owner, configures automation, tests questions, and explains approvals.
- Belongs to several workspaces **as an invited member** (no hidden superuser).
- **Implications:** fast fact entry (category templates, paste-and-extract), readiness checklist, a "test a customer question" tool, workspace switcher, audit attribution to the founder's own user.

### P5: The customer (affected, not a user)
- Writes to the business on Instagram in Turkish (or English as a tourist). Expects quick, correct, polite answers. May complain, ask for discounts or refunds, or send irrelevant or malicious text.
- **Implications:** never receives fabricated information; complaints reach a human; replies only within the 24-hour window; automation disclosure where required (OQ-13); personal data minimised.

### P6: Self-hosting developer (secondary, open source)
- Clones the repository, runs the demo locally, and maybe connects their own Meta app.
- **Implications:** demo without credentials, clear setup docs, mock and real adapters, honest docs about Meta App Review.

### P7: Global self-service owner (later)
- English-speaking small business owner who signs up alone.
- **Implications:** self-service onboarding with extraction, documentation, billing (deferred).

## 2. Use cases (prioritised)

Priority: **M** = MVP local demo (Phases 1–6), **P** = pilot readiness (Phases 7–9), **L** = later.

| ID | Use case | Actor | Priority |
|---|---|---|---|
| UC-01 | Create a workspace and configure business basics (name, category, language, timezone, currency) | Owner, founder | M |
| UC-02 | Enter, verify and edit business facts from a category template | Owner, founder | M |
| UC-03 | Paste existing text (bio, price list) and get fact candidates to accept or reject | Owner, founder | M |
| UC-04 | See readiness checklist and what is missing | Owner | M |
| UC-05 | Receive a customer DM, get a grounded draft, approve/edit/reject it | Owner, manager | M |
| UC-06 | Let routine replies be sent automatically for chosen intents | Owner | M (off by default) |
| UC-07 | Get escalations for complaints, refunds, discounts, ambiguous or unsupported messages, and reply manually | Owner, staff | M |
| UC-08 | Take over a conversation (stop automation) and release it | Owner, staff | M |
| UC-09 | Save a reply as a reusable approved answer | Owner, manager | M |
| UC-10 | Change a fact by natural language ("aylık üyelik artık 7.000 TL") with confirmation | Owner, manager | M |
| UC-11 | Be told which drafts, approved answers and scheduled posts are affected by a fact change | Owner | M |
| UC-12 | Ask questions about activity ("bugün kaç DM geldi?") | Owner, manager | M |
| UC-13 | Ask for a content draft ("deneme dersi için bir story hazırla") | Owner, manager, staff | M |
| UC-14 | Upload an image, attach it to content, approve and schedule it | Owner, manager | M |
| UC-15 | See publication results and failures with clear next steps | Owner | M |
| UC-16 | Cancel a scheduled post (by button or by command) | Owner, manager | M |
| UC-17 | Read the daily report derived from records | Owner, manager | M |
| UC-18 | View activity log ("what did the system do?") | Owner, manager | M |
| UC-19 | Simulate customers, failures and time in the demo; reset the demo | Developer, founder | M |
| UC-20 | Invite a member (staff, the founder) and remove them | Owner | M |
| UC-21 | Connect a real Instagram professional account via Instagram Login | Owner, founder | P |
| UC-22 | Reconnect after token expiry or revocation | Owner | P |
| UC-23 | Disconnect the account and delete associated data | Owner | P |
| UC-24 | Receive notifications and approve from a messenger (Telegram/WhatsApp) | Owner | P (OQ-01) |
| UC-25 | Send media to the messenger with "schedule this story for 19:00" | Owner | P/L |
| UC-26 | Reply to "fiyat?" comments via private reply | Owner | L (Advanced Access) |
| UC-27 | Self-service signup and billing | Global owner | L |

## 3. Key behavioural assumptions to validate in interviews

| Assumption | Why it matters | How to validate |
|---|---|---|
| Owners will open a web app (installed to the home screen) at least daily | Approvals depend on it | Ask about current app habits; observe in pilots |
| Owners prefer approving drafts to writing replies | Core value | Pilot: draft acceptance rate |
| Owners accept that price questions get exact prices via DM (some prefer "call us") | Pricing intent policy | Ask; fact `policy.price_disclosure` |
| Owners use Telegram (or not) | Channel #2 choice (OQ-01) | Ask directly |
| Comment-to-DM ("fiyat?") is a major lead source | Post-MVP priority (OQ-07) | Ask; look at their posts |
| Owners have their prices written somewhere (bio, highlight, website) | Extraction usefulness | Ask; inspect profile |
| Owners will tolerate a short "automated reply" disclosure | Compliance (OQ-13) | Ask |
