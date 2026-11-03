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

| Meta Permission / Feature | Access Level | Why AgentNest Requires This Permission | User Experience & Technical Flow | Data Storage & Security Controls |
|---|---|---|---|---|
| **`instagram_basic`** | Advanced Access | **Required to discover and identify the connected Instagram Professional Account.** AgentNest needs the Instagram user ID, username, profile picture URL, and account type to bind the account to the tenant's workspace. | During Meta OAuth, AgentNest queries `GET /me/accounts` and `GET /{page_id}?fields=instagram_business_account{id,username,name}`. The business handle and avatar are displayed in the dashboard so staff know which account is active. | Stored in PostgreSQL `social_accounts` table. Access tokens are encrypted at rest with `AES-256-GCM` (`INV-10`). No personal follower lists are ingested. |
| **`instagram_manage_messages`** | Advanced Access | **Core Feature: Ingesting inbound Direct Messages and dispatching approved or supervised factual replies.** Allows businesses to respond to customer inquiries (business hours, class schedules, pricing, location) via AI assistance with human-in-the-loop oversight. | Real-time webhook events (`messages`, `messaging_postbacks`) notify the API. Incoming messages appear in the Unified Inbox. AgentNest drafts a response grounded in verified business facts. Staff can edit and click "Send", or enable automated sending with a mandatory disclosure suffix (`— Otomatik yanıt`). Outbound messages are sent via `POST /{page_id}/messages`. | Messages are stored with PostgreSQL Row-Level Security (`app.workspace_id`). Message text is retained for 365 days (or custom workspace setting) and scrubbed upon customer erasure or deletion tombstone re-application. |
| **`instagram_manage_comments`** | Advanced Access | **Core Feature: Reading and responding to comments on Instagram posts, reels, and media.** Allows businesses to address customer comments (e.g. "Fiyat nedir?", "Neredesiniz?") publicly or initiate private reply DMs for sensitive details. | Webhook `feed` / comment events notify AgentNest. Comments appear in the Comments & Moderation dashboard. Staff or the delegated account agent can submit a public reply via `POST /{comment_id}/replies` or initiate a private reply via `POST /{page_id}/messages` with `recipient.comment_id`. | Comments and moderation state are isolated per workspace. Zero training on customer comments (OpenAI Zero Data Retention agreement). |
| **`pages_manage_metadata`** | Advanced Access | **Required for Webhook Ingestion Delivery.** Subscribes the business's connected Facebook Page to Instagram webhook topic fields (`messages`, `message_reactions`, `feed`). Without this permission, Meta does not deliver real-time webhook events to AgentNest's server. | Immediately following OAuth token exchange, AgentNest executes `POST /{page_id}/subscribed_apps?subscribed_fields=messages,messaging_postbacks,message_reactions,feed`. This is an automated background configuration step. | No Page metadata is stored or modified beyond subscribing to the required webhook fields. |
| **`pages_read_engagement`** | Advanced Access | **Required to identify connected Facebook Pages and retrieve Page Access Tokens.** Instagram Professional accounts are linked to Facebook Pages. AgentNest needs Page-level read engagement to query the associated Instagram Business Account ID. | When the user authorizes Meta Login, AgentNest calls `GET /me/accounts` to enumerate the Pages managed by the user, identifying the one connected to the target Instagram Professional account. | Stored as encrypted Page access tokens with AES-256-GCM. Unused Pages are discarded and never stored. |
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

### Screencast 3: Public Comment Moderation & Private Reply Transition
- **Permission Demonstrated:** `instagram_manage_comments`
- **Duration:** ~60 seconds
- **Video Script Steps:**
  1. On Instagram, test customer comments on an AgentNest post: *"Detaylı seans programı ve fiyat bilgisi alabilir miyim?"* ("Can I get detailed session schedule and pricing?")
  2. In AgentNest's Comments & Moderation dashboard, the new comment appears in real time under the "Needs Review" queue.
  3. The operator views the comment and clicks "Send Private Reply".
  4. AgentNest presents a draft private reply addressing the question and inviting the customer to book a trial session.
  5. Operator approves the reply. AgentNest sends the private message via Meta Graph API using `recipient: {"comment_id": "<comment_id>"}`.
  6. Simultaneously, the operator clicks "Reply Publicly": *"Merhaba, detaylı fiyat ve program bilgilerimizi mesaj kutunuza (DM) ilettik! Sevgiler."*
  7. Instagram immediately reflects the public reply under the post and delivers the direct message to the customer's DM inbox.

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
- [ ] **Feature Flags:** Verify `META_STORIES_ENABLED=false` and unsupported capabilities remain disabled in the production configuration.
