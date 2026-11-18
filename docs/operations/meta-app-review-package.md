# Meta App Review Package, Permission Rationales & Compliance Guide

- **Target Phase / Task:** Phase 8 Session 16 (`P8-10`, `OQ-03`, `OQ-05`, `Gate 3`, [ADR-013](../architecture/decisions/ADR-013-authentication-and-tenancy.md), [ADR-025](../architecture/decisions/ADR-025-phase-8-hardening-contracts.md))
- **Status:** Complete Offline Preparation (Submission Gated Pending Meta Business Verification & Gate 3 Counsel Sign-Off)
- **Application Name:** `AgentNest` (configurable via `PRODUCT_NAME`)
- **Product Type:** Multi-Tenant AI Operations Assistant for Instagram Businesses (Direct Messages, Comments, Business Knowledge Grounding)
- **Target Audience:** Meta App Review Team, Product Compliance Officers, Operations Administrators

---

## 1. Executive Summary & Review Gate Posture

This package contains the complete technical and operational documentation required for submitting the AgentNest Meta Application for **Advanced Access** on the Meta for Developers platform.

> [!IMPORTANT]
> **Status Separation (Preparation vs. Submission vs. Live Approval):**
> - **Preparation (Session 16):** Fully completed offline. All permission rationales, privacy policy URLs, data deletion callbacks, screencast walkthrough scripts, and reviewer instructions are verified against the codebase.
> - **Submission & Gate 3 Dependency:** Formal submission of this package in the Meta Developer Portal is gated on **OQ-05** (Meta Business Verification of the operating legal entity) and formal legal sign-off on **OQ-04**, **OQ-12**, and **OQ-13**.
> - **Standard Access for Pilot (OQ-03):** Initial assisted pilot businesses (1–5 accounts) are onboarded under Meta Standard Access by adding business owners as designated App Testers / Role members in the Meta App Dashboard, without exposing the broader public until Advanced Access approval is granted.

---

## 2. Public URLs & Legal Endpoints

All endpoints are hosted on the production infrastructure behind Caddy TLS with strict HTTP security headers (HSTS, CSP, X-Frame-Options `DENY`, X-Content-Type-Options `nosniff`).

| Purpose | Public Production URL | Technical Implementation |
|---|---|---|
| **Platform Homepage / App Domain** | `https://agentnest.io` | React + Vite SPA, served via Caddy reverse proxy |
| **Product Privacy Policy** | `https://agentnest.io/privacy` | `frontend/src/features/legal/PrivacyPolicyPage.tsx`, backed by `docs/legal/privacy-policy.md`. Itemizes personal data categories, Turkish KVKK Art. 5/6 and GDPR Art. 6/9 legal bases, sub-processors, and 365-day retention schedules. |
| **Data Deletion Instructions & Lookup** | `https://agentnest.io/data-deletion` | `frontend/src/features/legal/DataDeletionInfoPage.tsx`. Provides user-facing removal guide for Meta App Settings and an unguessable confirmation code lookup form calling `/api/v1/webhooks/meta/data-deletion/{code}`. |
| **Meta Deauthorization Callback** | `https://agentnest.io/api/v1/webhooks/meta/deauthorize` | `app/api/v1/endpoints/webhooks.py`. Verifies `signed_request` HMAC-SHA256 with `META_APP_SECRET`, revokes token credentials, fences active worker jobs, and logs `audit_logs` entry. |
| **Meta Data Deletion Request Callback** | `https://agentnest.io/api/v1/webhooks/meta/data-deletion` | `app/api/v1/endpoints/webhooks.py`. Verifies `signed_request` HMAC-SHA256, schedules asynchronous workspace/account data erasure, and returns a JSON response containing an unguessable tracking code and confirmation URL. |
| **OAuth Redirect / Callback URL** | `https://agentnest.io/oauth/instagram/callback` | State-validated OAuth handshake exchanging short-lived code for 60-day long-lived page/user access tokens, immediately encrypted with AES-256-GCM. |

---

## 3. Permission-by-Permission Rationale & Justification

AgentNest adheres strictly to the principle of least privilege. Only permissions required for customer inquiry triage, fact-grounded response drafting, comment moderation, and webhook event delivery are requested.

> [!WARNING]
> **Comment permission (Feature Phase 3, Session 01, 2026-11-17).** The Instagram Login flow in `backend/app/integrations/instagram/oauth.py` now requests five scopes: `instagram_business_basic`, `instagram_business_manage_messages`, `instagram_business_content_publish`, `instagram_business_manage_insights` and **`instagram_business_manage_comments`**. Granting it records the permission (`granted_scopes`, capability `comments_permission`) and nothing else: the comment read/private-reply capabilities require the default-off owner flag; public effects remain off, and live evidence must close the carried-forward items of R75-01..R75-06 ([platform-capabilities.md §1.8](../research/platform-capabilities.md)). Existing connections keep working and show "reconnect to enable comments". **Do not record Screencast 3 or submit the comment permission until Session 02's path works on a dev-mode test account**; the screencast must show a real effect, not the mock.
>
> **Permission names.** The rows below for `instagram_basic`, `instagram_manage_messages`, `pages_manage_metadata` and `pages_read_engagement` were written with the Facebook Login names. The code uses Instagram API with Instagram Login, whose scopes are the `instagram_business_*` names and which requests no `pages_*` permission. The comment row has been rewritten for the real scope; the remaining rows and Screencasts 1 and 2 still need the same reconciliation before submission (not part of Session 01).
>
> **Access level.** Per [Meta's App Review page](https://developers.facebook.com/documentation/instagram-platform/app-review.md) (read 2026-11-17), `instagram_business_manage_comments` needs Advanced Access, and therefore App Review, only when the app serves businesses you do not own or manage. Pilot businesses added as app role users run on Standard Access without review. The same page lists a screencast per permission (English UI, captions), step-by-step test instructions and a successful API call as requirements.

| Meta Permission / Feature | Access Level | Why AgentNest Requires This Permission | User Experience & Technical Flow | Data Storage & Security Controls |
|---|---|---|---|---|
| **`instagram_basic`** | Advanced Access | **Required to discover and identify the connected Instagram Professional Account.** AgentNest needs the Instagram user ID, username, profile picture URL, and account type to bind the account to the tenant's workspace. | During Meta OAuth, AgentNest queries `GET /me/accounts` and `GET /{page_id}?fields=instagram_business_account{id,username,name}`. The business handle and avatar are displayed in the dashboard so staff know which account is active. | Stored in PostgreSQL `social_accounts` table. Access tokens are encrypted at rest with `AES-256-GCM` (`INV-10`). No personal follower lists are ingested. |
| **`instagram_manage_messages`** | Advanced Access | **Core Feature: Ingesting inbound Direct Messages and dispatching approved or supervised factual replies.** Allows businesses to respond to customer inquiries (business hours, class schedules, pricing, location) via AI assistance with human-in-the-loop oversight. | Real-time webhook events (`messages`, `messaging_postbacks`) notify the API. Incoming messages appear in the Unified Inbox. AgentNest drafts a response grounded in verified business facts. Staff can edit and click "Send", or enable automated sending with a mandatory disclosure suffix (`— Otomatik yanıt`). Outbound messages are sent via `POST /{page_id}/messages`. | Messages are stored with PostgreSQL Row-Level Security (`app.workspace_id`). Message text is retained for 365 days (or custom workspace setting) and scrubbed upon customer erasure or deletion tombstone re-application. |
| **`instagram_business_manage_comments`** | Advanced Access (needed for businesses we do not own or manage; Standard Access for pilot role users) | **Reading and answering comments on the connected business's own posts, reels and stories, and sending one private reply (DM) to a commenter.** Customers ask "Fiyat nedir?" or "Neredesiniz?" in comments; the owner wants the verified answer sent privately instead of posted publicly. Used for: (1) receiving the `comments` webhook for the account's own media, (2) reading a comment, (3) a public reply `POST /{comment-id}/replies`, (4) hide/unhide `POST /{comment-id}?hide=`, (5) a private reply `POST /{ig-user-id}/messages` with `recipient.comment_id` within 7 days of the comment. | **Use-case description (paste into the submission).** "AgentNest helps small Instagram businesses answer customers. The business owner connects their own professional account with Instagram Login. When a customer comments on one of the business's posts, AgentNest shows the comment in the owner's inbox and drafts an answer from facts the owner verified (opening hours, prices, address). Nothing is sent without the owner's approval unless the owner has switched on automatic replies for this action. The owner can reply publicly or send one private reply to the commenter, hide an abusive comment, or ignore it. We use the permission only on comments on the connected account's own media, store comment text only inside the owner's workspace, and never use it for advertising, profiling or training." Technical flow: the `comments` webhook field is subscribed for the account (`POST /{ig-user-id}/subscribed_apps`), the comment appears in **Inbox -> Comments**, a grounded draft is approved by the owner, and the action runs through our operations ledger (write-ahead record, one attempt, reconcile before any retry; an unknown outcome is never resent). The private reply is limited by the app to one per comment, inside Meta's 7-day window (a live broadcast: during the broadcast), after which a customer reply opens the usual 24-hour DM window. | Comment text, author ID and username are stored per workspace under row-level security and deleted with the workspace, by the retention schedule or on a data-deletion request. No follower lists. Comment handling follows the privacy rules in [security-and-privacy.md](../architecture/security-and-privacy.md) (no usernames or IDs are placed in model prompts). Granted scopes are stored per account; the token is encrypted at rest. |
| **`pages_manage_metadata`** | Advanced Access | **Required for Webhook Ingestion Delivery.** Subscribes the business's connected Facebook Page to Instagram webhook topic fields (`messages`, `message_reactions`, `feed`). Without this permission, Meta does not deliver real-time webhook events to AgentNest's server. | Immediately following OAuth token exchange, AgentNest executes `POST /{page_id}/subscribed_apps?subscribed_fields=messages,messaging_postbacks,message_reactions,feed`. This is an automated background configuration step. | No Page metadata is stored or modified beyond subscribing to the required webhook fields. |
| **`pages_read_engagement`** | Advanced Access | **Required to identify connected Facebook Pages and retrieve Page Access Tokens.** Instagram Professional accounts are linked to Facebook Pages. AgentNest needs Page-level read engagement to query the associated Instagram Business Account ID. | When the user authorizes Meta Login, AgentNest calls `GET /me/accounts` to enumerate the Pages managed by the user, identifying the one connected to the target Instagram Professional account. | Stored as encrypted Page access tokens with AES-256-GCM. Unused Pages are discarded and never stored. |
| **`instagram_business_manage_insights`** | Advanced Access | **Performance & Insights.** Enables collection of account and content performance metrics for the Today dashboard. | Queried via `GET /{ig-user-id}/insights` and `GET /{media-id}/insights`. Cached account metrics are displayed for 7/28-day windows with explicit history-coverage checks. Live Meta permission and data validation remain a separate release gate. | Aggregated metrics only; individual follower identities are never queried or stored. Snapshots are workspace-scoped and deleted with the workspace. |
| **Human Agent** *(feature, Feature Phase 5 Session 09; request only when a pilot owner needs late replies)* | Advanced Access feature; needs App Review, Business Verification and possibly additional contracts ([Human Agent reference](https://developers.facebook.com/documentation/development/features-reference/human-agent.md), read 2026-11-18) | **Let a person on the business team answer a customer's support question after the 24-hour window, up to 7 days after the customer's last message.** Used when the business was closed (weekend, holiday) or the question took longer than a day. Never used for assistant replies. | In the inbox a conversation past 24 hours shows "Human Agent window: only your own typed reply, until <time>". A team member types the reply (not an assistant draft, not an edited assistant draft, not a follow-up), approves it, and it is sent with `messaging_type=MESSAGE_TAG` and `tag=HUMAN_AGENT`. The tag is rejected for every automated source by a deterministic rule (and a database constraint). It is on only when `META_HUMAN_AGENT_ENABLED=true` and the account can message. | The same stored message, approval and audit records as any reply; no new data is collected. |
| **`instagram_content_publish`** *(Staged / Deferred)* | Staged (Phase 9) | **Scheduled Publishing of Feed Posts and Stories.** Allows business owners to schedule approved announcements and educational posts. | Deferred until post-pilot phase. Feature-flagged off (`META_STORIES_ENABLED=false`) in initial App Review submission to maintain minimal scope. | Assets stored in encrypted S3/R2 storage with pre-signed URLs. |

---

## 4. Test User Credentials & Testing Environment

To enable Meta's App Review team to execute an end-to-end evaluation, AgentNest provides dedicated sandbox test users, pre-configured Instagram Professional accounts, and active test environments.

### 4.1 Testing Credentials & URLs

- **Test Application URL:** `https://staging.agentnest.io` (or review instance provided in submission notes)
- **Test Operator Login:**
  - **Email:** `meta-reviewer@agentnest.io`
  - **Password:** Provided in the confidential "Review Notes" field of the submission form.
  - **Workspace Role:** `Owner` of pre-seeded workspace `"Review Studio Istanbul"`
- **Connected Meta Review Test User:**
  - **Facebook User Name:** `AgentNest Reviewer`
  - **Connected Facebook Page:** `AgentNest Review Studio` (`ID: 109823485723491`)
  - **Instagram Professional Account:** `@agentnest_review_studio` (`IG ID: 17841400234891234`)
  - **Account Type:** Instagram Business Account (linked to the test Facebook Page)

### 4.2 Pre-Configured Verified Knowledge (Facts)

The test workspace is seeded with verified business facts to demonstrate grounded AI replies:
- `hours.weekdays`: "08:00 - 21:00"
- `hours.saturday`: "09:00 - 18:00"
- `location.address`: "Bağdat Caddesi No: 142, Kadıköy, İstanbul"
- `pricing.single_session`: "750 TRY"
- `pricing.monthly_pack`: "4,500 TRY (10 seans)"

### 4.3 Reviewer Test Steps for the Comment Permission (live recording pending)

1. Complete the [real-account rollout prerequisites](account-agent-rollout.md#real-account-comment-to-dm-rollout-feature-phase-3): app Live/access, reconnect with granted comment scope, manual comments subscription and readback. Authentic delivery and subscription acceptance remain pending.
2. Sign in as the test owner, open Settings → Connections, verify **Comment permission**, then enable **Comment-to-DM (private replies)**. This account flag defaults off. Activate the account agent and keep *Reply privately to comments* at **Ask**.
3. Confirm a usable verified membership price fact. From a disposable customer add a new top-level comment on a recent owned post: “How much is a monthly membership?” / “Aylık üyelik ne kadar?”
4. In Inbox → Comments inspect the drafted private reply grounded through the verified price placeholder. Approve its exact version. Wait for the operation to show sent, then independently inspect the customer's Instagram Inbox/Requests.
5. Verify a second private reply is refused. Current conservative rule is one per customer/account ever, one per comment, inside seven days minus ten minutes. Reply-to-reply comments are refused pending evidence. An unverified price must never render.
6. Turn the flag off; a pending private reply must stop with `CAPABILITY_MISSING`. No public reply, hide/unhide or delete is available on a real account. Unknown sends remain visibly unresolved and are never resent automatically.

**Recording and all live outcomes: pending.** Offline MockTransport tests are not a screencast or App Review acceptance. Record sanitized ledger outcomes and the R75 evidence before submitting; no token or personal text in reports.

---

## 5. Screencast Scenarios & Authentic Workflow Demonstration Scripts

Meta requires video screencasts demonstrating each requested permission in an authentic, live user workflow. Below are the exact scripts used to record the screencast submissions.

### Screencast 1: Meta Login, Account Discovery & Webhook Setup
- **Permissions Demonstrated:** `instagram_basic`, `pages_read_engagement`, `pages_manage_metadata`
- **Duration:** ~60 seconds
- **Video Script Steps:**
  1. Reviewer signs in to `https://staging.agentnest.io` as `meta-reviewer@agentnest.io`.
  2. Dashboard displays an empty or reconnectable Instagram status card with a prominent "Connect Instagram Account" button.
  3. Clicking "Connect" launches the official Meta OAuth dialog (`https://www.facebook.com/v25.0/dialog/oauth`).
  4. The screen highlights the requested permissions: Instagram profile info (`instagram_basic`), Page engagement (`pages_read_engagement`), and Page metadata (`pages_manage_metadata`).
  5. User accepts the permissions and selects the `AgentNest Review Studio` Page and `@agentnest_review_studio` account.
  6. The popup closes. AgentNest calls `POST /api/v1/workspaces/{id}/integrations/meta/connect`, subscribes the Page to webhooks via `pages_manage_metadata`, encrypts the long-lived access token, and updates the UI status to **Connected** with username `@agentnest_review_studio`.

### Screencast 2: Direct Message Inquiry, AI Drafting & Approval Workflow
- **Permission Demonstrated:** `instagram_manage_messages`
- **Duration:** ~75 seconds
- **Video Script Steps:**
  1. The screencast splits screen: Left side shows an authentic Instagram mobile app or web interface logged in as a test customer (`@fitness_fan_test`); Right side shows the AgentNest Unified Inbox.
  2. From the customer account, send a DM: *"Merhaba, çalışma saatleriniz ve reformer pilates paket fiyatlarınız nedir?"* ("Hello, what are your hours and reformer pilates package prices?")
  3. On the right side, AgentNest receives the webhook payload in real time. The conversation thread instantly updates with a status badge *Hazırlanıyor…* (Generating draft).
  4. The LLM extracts the intent, queries the verified business facts (`hours.weekdays`, `pricing.monthly_pack`), and generates a draft reply.
  5. The draft is presented to the business operator in the Unified Inbox:
     > *"Merhaba! Hafta içi 08:00 - 21:00 saatleri arasında hizmet vermekteyiz. Reformer pilates 10 seanslık aylık paketimiz 4.500 TL'dir. — Otomatik yanıt"*
  6. The operator clicks "Approve & Send" (or makes a minor edit).
  7. AgentNest dispatches the message via Meta Graph API `/messages`.
  8. The left screen shows the customer account receiving the DM instantly, complete with the automated disclosure suffix.

### Screencast 3: Comments, Approved Reply and Private Reply (`instagram_business_manage_comments`)
- **Permission Demonstrated:** `instagram_business_manage_comments` (with `instagram_business_basic`, and `instagram_business_manage_messages` for the follow-up DM)
- **Duration:** ~90 seconds. UI in English, with captions.
- **Status:** **pending.** Record it only on a real dev-mode test account after Session 02 has enabled the comment path (per-account flag on, `comments` webhook subscribed). Do not record it against the mock provider: Meta requires the real end-to-end experience.
- **Video Script Steps:**
  1. Show the connection: sign in at the review instance as the test owner, open **Settings -> Connections**. If the account was connected before the permission existed, show the note "Reconnect to enable comments" and click **Reconnect with Instagram**. Show the Instagram consent screen listing "Manage comments" and accept. The card now lists "Comment permission".
  2. On a phone (screen-recorded Instagram app), a test customer account comments on a post of the test business: *"How much is a monthly membership?"*
  3. In AgentNest **Inbox -> Comments** the comment appears (webhook delivery, not polling). Show the verified fact `pricing.monthly_pack` the draft will use.
  4. AgentNest shows the drafted private reply built from the fact placeholder (the price is inserted from the verified fact, not typed by the model). The owner reads it and clicks **Approve**.
  5. Show the operation status moving to *sent*, then the DM arriving in the customer's Instagram inbox (Requests folder if the customer does not follow the account), with the link to the post.
  6. Show that a second private reply is refused under the conservative per-customer/per-comment limits. Public replies and moderation are disabled on real accounts.
  7. Show **Settings -> Connections** that the owner can turn comment-to-DM off or disconnect at any time.

### Screencast 4: Data Deletion Callback, Deauthorization & Compliance Status
- **Requirements Demonstrated:** Meta Platform Terms §4.a (Data Protection), Deauthorization & Data Deletion Callbacks
- **Duration:** ~50 seconds
- **Video Script Steps:**
  1. User navigates to Facebook/Instagram Settings -> Apps and Websites -> AgentNest, and clicks "Remove" / "Disconnect".
  2. Meta issues a `POST` request with a `signed_request` payload to `https://agentnest.io/api/v1/webhooks/meta/deauthorize`.
  3. AgentNest validates the HMAC-SHA256 signature, revokes the token, pauses active account agents, fences in-progress outbound operations, and updates the workspace status to `needs_reauth`.
  4. In the Meta Settings, user clicks "Send Request" under Data Deletion. Meta dispatches `POST` to `https://agentnest.io/api/v1/webhooks/meta/data-deletion`.
  5. AgentNest verifies the signature, initiates data erasure orchestration, generates an unguessable confirmation code (e.g. `del_f49b1a0e8c724128`), and returns the confirmation URL:
     `https://agentnest.io/api/v1/webhooks/meta/data-deletion/del_f49b1a0e8c724128`.
  6. User visits `https://agentnest.io/data-deletion`, enters the confirmation code, and sees a clean status confirmation: **Status: Deleted / Cleared**.

### Screencast 5: Human Agent Reply After 24 Hours (Human Agent feature)
- **Feature Demonstrated:** Human Agent (with `instagram_business_manage_messages`)
- **Duration:** ~60 seconds. UI in English, with captions.
- **Status:** **pending.** Record it only on a real dev-mode test account once Meta has granted the feature to the app (`META_HUMAN_AGENT_ENABLED=true`). The mock provider supports the tag for offline tests, but Meta requires the real experience.
- **Video Script Steps:**
  1. A test customer sends a question on Instagram. Do not reply for more than 24 hours (for the recording, use a conversation whose last customer message is older than a day).
  2. In AgentNest **Inbox** open the conversation: the header says "Human Agent window: only your own typed reply, until <date and time>" and the assistant's drafts and follow-ups are not offered for sending.
  3. The team member types a reply in their own words and sends it. Show that pasting the assistant's draft text is refused ("A reply after 24 hours can only be a message you typed yourself").
  4. Show the approval and the sent state; show the reply arriving in the customer's Instagram inbox.
  5. Show a conversation older than 7 days: the header says the reply window is closed and the reply box refuses to send.

---

## 6. Business Verification Prerequisites (`OQ-05`)

Meta App Review requires **Business Verification** in the Meta Business Manager before Advanced Access can be approved for business messaging permissions.

### 6.1 Legal Entity Identification Requirements
The operating legal entity (Founder's company) must be verified in Meta Business Suite:
- **Entity Type:** Limited Liability Company (*Limited Şirket* / *Anonim Şirket*) or Registered Sole Proprietorship (*Şahıs Şirketi*) in the Republic of Türkiye.
- **Required Documents:**
  1. **Tax Registration Certificate (*Vergi Levhası*):** Shows official registered business name, tax identification number (VKN), and registered address.
  2. **Trade Registry Gazette (*Ticaret Sicil Gazetesi*) or Chamber Registration (*Oda Kayıt Faaliyet Belgesi*):** Proves legal existence and authorized signatories.
  3. **Official Address Proof:** Fixed-line telephone bill, municipal certificate, or official bank statement matching the exact legal name and physical address.
- **Domain Verification:**
  - Root domain `agentnest.io` verified in Meta Business Manager via DNS TXT record:
    `facebook-domain-verification=<hash_key>`
  - SSL/TLS certificate issued and active.

### 6.2 Pre-Verification Pilot Architecture (Standard Access)
Per **OQ-03** and **ADR-013**:
- Before Meta Business Verification and App Review approval are completed, pilot businesses are served using **Standard Access**.
- Each pilot business Instagram account and Facebook Page Admin is invited as a **Tester** in the Meta App Dashboard under `Roles -> Roles -> Add Testers`.
- Standard Access provides full Graph API capabilities for users with defined roles in the app, allowing up to 5 pilot businesses to operate with zero permission limitations while formal verification is underway.

---

## 7. App Review Submission Checklist

Before clicking "Submit for Review" in the Meta Developer Portal, verify:

- [ ] **Privacy Policy:** `https://agentnest.io/privacy` is publicly accessible (HTTP 200), responsive on mobile, and contains valid contact details.
- [ ] **Data Deletion URL:** `https://agentnest.io/data-deletion` is publicly accessible and functional.
- [ ] **Data Deletion Callback:** `https://agentnest.io/api/v1/webhooks/meta/data-deletion` responds with JSON status URL to signed Meta requests.
- [ ] **Deauthorization Callback:** `https://agentnest.io/api/v1/webhooks/meta/deauthorize` responds HTTP 200 to signed Meta requests.
- [ ] **Business Verification:** Meta Business Manager shows "Verified" status with green badge.
- [ ] **Screencasts:** High-resolution MP4/WebM files recorded for all 4 scenarios with English annotations or subtitles.
- [ ] **Test User Credentials:** Valid username, password, and two-factor bypass instructions provided in reviewer notes.
- [ ] **Comment permission:** `instagram_business_manage_comments` is in `SCOPES` (done, Feature Phase 3 Session 01); Session 02's real comment path works on a dev-mode test account; Screencast 3 is recorded on that account (not the mock); section 4.3 steps were run end to end; the carried-forward R75 items that affect what the reviewer sees are recorded in [platform-capabilities.md §1.8](../research/platform-capabilities.md).
- [ ] **Human Agent (only if requested):** Business Verification is complete; Screencast 5 is recorded on a real dev-mode account; `META_HUMAN_AGENT_ENABLED` stays `false` until Meta grants the feature; V-HA in `platform-capabilities.md` is answered (request shape under Instagram Login, error when not granted, 7-day boundary).
- [ ] **Feature Flags:** Verify `META_STORIES_ENABLED=false` and unsupported capabilities remain disabled in the production configuration.

