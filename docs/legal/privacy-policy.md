# AgentNest Product Privacy Policy / Gizlilik Politikası

- **Document Version:** 1.0.0 (Provisional Draft for Legal Counsel Review)
- **Effective Date:** November 3, 2026
- **Review Status:** `PENDING_COUNSEL_REVIEW` (Tracking under `OQ-04`, `OQ-12`, `OQ-13`; Gate 3 Pre-condition)
- **Languages:** English (primary legal draft) & Türkçe (özet bilgilendirme)
- **Scope:** AgentNest Platform (Web application, API, background workers, and automated business integrations)

---

## 1. Introduction & Overview

AgentNest ("we", "our", "us", or the "Platform") provides AI-assisted Instagram messaging and content management software for business workspaces (such as wellness studios, clinics, salons, and local service providers).

This Privacy Policy explains how personal data is collected, used, processed, stored, and protected when business owners and their team members ("Users") access the AgentNest platform, and how personal data of third-party customers who interact with businesses via Instagram Direct Messages ("End-Customers") is handled.

> [!IMPORTANT]
> **Data Protection Roles & Responsibilities:**
> - **Platform Users & Accounts:** AgentNest acts as a **Data Controller** (Veri Sorumlusu) for personal data relating to registered platform users (e.g., account credentials, subscription information, and operator audit logs).
> - **End-Customer Instagram Communications:** The tenant business (Workspace Owner) is the **Data Controller** for all customer messages, inquiries, and customer profile identifiers received through Instagram. AgentNest acts strictly as a **Data Processor** (Veri İşleyen) providing automated drafting, scheduling, and message storage services on behalf of the business under the Data Processing Agreement (DPA).
> - **Meta Platforms:** Meta Platforms Ireland Ltd. / Meta Platforms, Inc. acts as an independent data controller regarding Instagram platform services.

---

## 2. Categories of Personal Data Processed

### 2.1 Platform User Data (Data Controller Role)
- **Identity & Contact Details:** Email address, user display name, role within workspace (`owner`, `manager`, `staff`).
- **Security & Authentication:** Cryptographic password hashes (salted and hashed using `argon2id`), active session tokens (stored in encrypted, `HttpOnly`, `SameSite=Lax` cookies), and password reset tokens.
- **Audit Logs:** Immutable audit log records of administrative actions (e.g., login timestamps, workspace configuration changes, role delegations, key rotations, invite emissions, and IP addresses).

### 2.2 Business Tenant & Integration Data (Data Processor Role)
- **Social Account Credentials:** Instagram Business account IDs, usernames, and OAuth access tokens. All access tokens are encrypted at rest using AES-256-GCM authenticated encryption with external key rings and tenant-specific Additional Authenticated Data (`<workspace_id>:<account_id>`). Plaintext tokens are never stored in databases, logs, or worker payloads (`INV-08`).
- **Business Knowledge:** Verified business facts (opening hours, price lists, service descriptions, address/location details).

### 2.3 End-Customer Data (Data Processor Role)
- **Customer Identifiers:** Instagram Scoped IDs (IGSID) and Instagram usernames/handles.
- **Communications Content:** Direct message (DM) inbound text, sent reply text, comment text, and timestamps.
- **AI Processing Snapshots:** Context summaries, classification labels (e.g., pricing inquiry, hours request), and draft responses. Customer text is strictly quarantined in delimited data structures and is never treated as operator commands (`INV-04`, `INV-10`).

---

## 3. Purposes of Processing & Legal Bases

We process personal data only in accordance with applicable data protection laws, including the Turkish Personal Data Protection Law No. 6698 (KVKK) and the General Data Protection Regulation (GDPR):

| Category of Data | Processing Purpose | Legal Basis (KVKK) | Legal Basis (GDPR) |
|---|---|---|---|
| User Account & Auth | Creating and managing platform accounts, securing access, authenticating sessions. | KVKK Art. 5/2(c) (Contract performance), Art. 5/2(f) (Legitimate interest). | GDPR Art. 6(1)(b) (Contract), Art. 6(1)(f) (Legitimate interest). |
| Social Account Credentials | Connecting to Meta Instagram Graph API on behalf of the business to send/receive messages. | KVKK Art. 5/2(c) (Contract performance under DPA). | GDPR Art. 6(1)(b) (Contract under DPA). |
| Customer Inbound Messages | Assisting the business in answering customer questions, preparing AI drafts, and executing approved replies. | KVKK Art. 5/2(c) & (f) (Data Processor acting on documented instructions). | GDPR Art. 6(1)(b) & (f) (Processor acting on Controller instructions). |
| Security & Audit Logs | Fraud prevention, security incident triage, system resilience, and compliance auditing (`INV-06`, `INV-12`). | KVKK Art. 5/2(ç) (Legal obligation) & Art. 5/2(f) (Security legitimate interest). | GDPR Art. 6(1)(c) (Legal obligation) & Art. 6(1)(f) (Security legitimate interest). |

---

## 4. Artificial Intelligence & Automated Processing

1. **No Model Training on Customer Data:** Customer message text, customer identifiers, and private business facts processed through the OpenAI API are **never used to train base artificial intelligence models**. Processing utilizes commercial API endpoints governed by Enterprise Zero Data Retention (ZDR) and strict confidentiality terms (`INV-09`).
2. **Deterministic Guardrails & Closed Schemas:** The AI layer produces structured, closed-schema outputs (drafts, detected categories, and usable fact placeholders). The language model cannot execute arbitrary side-effects or dispatch communications without passing through policy validators and owner-configured approval gates.
3. **Automated Reply Disclosure:** By default, responses dispatched autonomously without manual approval append a disclosure suffix (e.g., `" — Otomatik yanıt"` / `" — Automated reply"`) to ensure transparent communication with consumers (`OQ-13`).

---

## 5. Technical & Organizational Security Measures (TOMs)

AgentNest enforces defense-in-depth security measures to protect personal data from unauthorized access, accidental alteration, disclosure, or destruction:

1. **PostgreSQL Row-Level Security (RLS):** All tenant tables are strictly isolated using PostgreSQL Row-Level Security keyed on `app.workspace_id`. Cross-tenant queries are blocked at the database engine level (`INV-01`, `INV-02`, `ADR-025`).
2. **Encryption in Transit & at Rest:**
   - All external communications are protected by TLS 1.3 / HTTPS with HSTS (`max-age=63072000; includeSubDomains; preload`).
   - OAuth tokens and sensitive credentials are encrypted using AES-256-GCM.
   - Database backups are encrypted with AES-256 before being transmitted to off-site object storage.
3. **Immutable Audit Trails:** Audit records (`audit_logs`) are append-only. Runtime application and worker roles possess no `DELETE` or `UPDATE` privileges on audit tables (`INV-06`, `INV-12`, `ADR-022`, `ADR-026`).
4. **Least Privilege Containerization:** All backend and worker services run as unprivileged non-root users (`UID 10001`) inside minimal distroless/Debian containers.
5. **Webhook Cryptographic Verification:** All incoming Meta webhooks are cryptographically authenticated in constant time using `X-Hub-Signature-256` and the HMAC SHA-256 app secret prior to payload parsing (`INV-07`).
6. **Privacy Scrubbing in Monitoring:** Error telemetry (Sentry) and system logs enforce automated sanitization that removes authorization headers, cookies, IP addresses, customer identifiers, and sensitive tokens (`INV-08`, `INV-18`).

---

## 6. Data Retention, Redaction, and Deletion Schedule

We retain personal data only for as long as necessary to fulfill business purposes or comply with statutory requirements. Retention periods are automated via daily background cleanup jobs (`retention_cleanup`):

| Data Asset | Implemented Retention & Redaction Period | Post-Expiry Action | Regulatory / Operational Note |
|---|---|---|---|
| **Raw Webhook Payloads** (`inbound_events.payload`) | 30 days | Payload nulled at 30 days; metadata row deleted at 90 days. | Minimizes raw transmission exposure; point gap markers preserved. |
| **Agent Run Inputs** (`agent_runs.input_snapshot`) | 30 days | Input snapshot payload nulled. | Keeps run execution status and token cost metrics. |
| **Customer Message Text** (`messages.text`, `reply_drafts.text`) | 365 days (provisional) | Message text nulled; metadata (timestamp, intent flags, direction) retained. | Preserves historical business reports without retaining customer text (`INV-17`). |
| **Owner Tasks & Clarifications** | 180 days (provisional) | `request_text` redacted, clarification unlinked. | Retains status ledger and task completion records. |
| **Owner Questions & Answers** | 180 days (provisional) | Question/Answer text nulled; source message hash cleared. | Protects proprietary communications. |
| **Agent Steps & Actions** | 30 days (provisional) | Payload checkpoints and policy grant snapshots scrubbed. | Removes customer prompt data. |
| **Encrypted Database Backups** | 35 days | Automatically expired and pruned from off-site storage. | Aligned with RPO/RTO and 35-day key custody policy (`ADR-026`). |
| **Immutable Audit Logs** | 2 years (provisional) | No runtime purge. Purge requires out-of-band migrator procedure. | Preserves evidence for dispute resolution and compliance audits (`ADR-026`). |

> [!NOTE]
> Retention periods marked *provisional* are established under `OQ-12` and are subject to final legal counsel endorsement before Gate 3 completion.

---

## 7. Data Deletion & Customer Rights (GDPR & KVKK)

### 7.1 Customer Erasure & Disconnection
- **Account Disconnection:** When a business disconnects an Instagram account, access tokens are wiped immediately. Workspace owners may elect to purge all associated conversation history. Incomplete or uncertain operations retain minimal reconciliation evidence until verified (`INV-17`, `ADR-022`).
- **Workspace Deletion:** Initiating workspace deletion places the tenant in a 7-day grace period (`status = deleting`). Following the grace period, all tenant database records and associated media files are permanently deleted via cascading foreign keys. Backups roll off naturally after 35 days, with deletion tombstones re-applied upon any disaster recovery (`ADR-026`).
- **Meta Data Deletion Callback:** In compliance with Meta Platform Terms, AgentNest provides an automated endpoint (`/api/v1/webhooks/meta/data-deletion`) supporting verified `signed_request` calls. Upon receipt, customer data is purged, and a permanent confirmation code with a tracking URL is returned to the user.

### 7.2 Data Subject Rights
Under KVKK Article 11 and GDPR Articles 15–22, data subjects possess the right to:
- Learn whether their personal data is being processed;
- Request access to and copies of their personal data;
- Request correction of inaccurate or incomplete personal data;
- Request deletion or destruction of their personal data;
- Object to automated decision-making producing legal effects;
- Lodge a complaint with the Turkish Personal Data Protection Authority (KVKK Kurumu) or competent European Data Protection Authority.

To exercise these rights, platform users or end-customers may contact our privacy team at `privacy@agentnest.io`.

---

## 8. Third-Party Sub-Processors & Cross-Border Transfers

To provide the platform services, AgentNest engages vetted third-party service providers (sub-processors) for infrastructure, object storage, transactional email, error monitoring, and artificial intelligence processing.

A complete and continuously maintained list of sub-processors, their corporate locations, and applicable cross-border transfer safeguards is available in the [Sub-Processor Register](sub-processor-register.md).

---

## 9. Contact & Inquiries

For questions, comments, or data subject requests regarding this Privacy Policy:
- **Email:** `privacy@agentnest.io`
- **Data Protection Officer / Responsible Operator:** `dpo@agentnest.io`
- **Postal Address:** AgentNest Operations Team, [Registered Entity Address Pending OQ-05], Istanbul, Türkiye
