# AgentNest Sub-Processor Register / Alt Veri İşleyen Kaydı

- **Document Reference:** `LEGAL-SUBPROCESSOR-REG-V1`
- **Effective Date:** November 3, 2026
- **Review Status:** `PENDING_COUNSEL_REVIEW` (Tracking under `OQ-04`, `OQ-12`; Gate 3 Pre-condition)
- **Applicability:** All AgentNest hosted production workspaces and tenants

---

## 1. Overview & Policy

Under the [AgentNest Data Processing Agreement](dpa-template.md) (DPA), AgentNest ("Processor") engages selected third-party service providers ("Sub-Processors") to support the delivery of infrastructure, artificial intelligence processing, email communication, and error monitoring services.

Before engaging any Sub-Processor, AgentNest conducts due diligence to verify that the entity maintains robust technical and organizational security measures, adheres to industry standards (e.g., ISO 27001, SOC 2 Type II), and provides appropriate contractual commitments regarding data protection and confidentiality.

---

## 2. Register of Active & Authorized Sub-Processors

| Sub-Processor Name | Corporate Location | Nature & Purpose of Processing | Personal Data Categories Processed | Cross-Border Transfer Safeguard | Certifications / Security |
|---|---|---|---|---|---|
| **Hetzner Online GmbH** *(Default EU Cloud Hosting)* | Gunzenhausen / Falkenstein, Germany (EU) | Primary VPS compute infrastructure, Docker container execution, PostgreSQL database hosting, and local Redis caching. | All platform data: user accounts, tenant workspaces, encrypted tokens, message logs, and audit trails. | Intra-EU processing; GDPR Art. 28 DPA. *(If OQ-04 resolves to Türkiye hosting, Equinix/Turkcell TR data center replaces this entry).* | ISO/IEC 27001 certified data centers. |
| **OpenAI, LLC / OpenAI Ireland Ltd.** | San Francisco, California, USA / Dublin, Ireland | Automated artificial intelligence processing: intent classification, reply drafting, fact extraction, and safety filtering. | End-Customer message snippets, detected intent keywords, business verified facts. *(No user passwords, tokens, or customer handles are sent; INV-08, INV-18).* | EU-US Data Privacy Framework; Standard Contractual Clauses (SCCs); KVKK Taahhütname; Commercial Enterprise Zero Data Retention (ZDR) policy. | SOC 2 Type II; ISO 27001; strict prohibition on training models with API customer data (`INV-09`). |
| **Cloudflare, Inc. (Cloudflare R2)** | San Francisco, California, USA / Global Anycast | S3-compatible off-site object storage for encrypted database backups and customer media assets (images). | Encrypted database backup dumps (`.dump` encrypted with AES-256 before transmission) and published media items. | Standard Contractual Clauses (SCCs); EU-US Data Privacy Framework; client-side encryption enforced prior to transit. | SOC 2 Type II; ISO 27001; PCI DSS. |
| **Resend, Inc.** *(or Postmark / SendGrid)* | San Francisco, California, USA | Transactional email delivery: member invitations, password reset links, and operator critical alerts. | Recipient email address, user display name, time-limited cryptographic reset/invite tokens. *(No customer messages or Instagram tokens).* | Standard Contractual Clauses (SCCs); EU-US Data Privacy Framework; GDPR DPA. | SOC 2 Type II; TLS 1.3 enforced. |
| **Functional Software, Inc. (Sentry)** *(Optional Monitoring)* | San Francisco, California, USA | Application error tracking, diagnostic stack traces, and unhandled exception triage. | Application exception stack traces and error codes. **PII and tokens are strictly scrubbed prior to transmission** (`scrub_sentry_event` strips Authorization, Cookie, email, IP, and tokens; INV-08, INV-18). | Standard Contractual Clauses (SCCs); GDPR DPA; client-side redaction hook. | SOC 2 Type II; HIPAA; ISO 27001. |

---

## 3. Independent Platform Partners (Non-Sub-Processors)

The following entities operate as **independent data controllers** rather than sub-processors of AgentNest:

| Entity Name | Corporate Location | Role & Relationship | Data Flow |
|---|---|---|---|
| **Meta Platforms Ireland Ltd. / Meta Platforms, Inc.** | Dublin, Ireland / Menlo Park, California, USA | Social Media Platform Provider (Instagram Graph API, Webhooks). Direct relationship with End-Customers and Business Social Accounts. | Inbound webhooks (`X-Hub-Signature-256` verified) and outbound message API calls. Meta operates under its own Privacy Policy and Platform Terms. |

---

## 4. Sub-Processor Change Notification Process

In accordance with Section 4 of the DPA:
1. **Advance Notice:** AgentNest shall provide business workspace owners with at least **thirty (30) days' advance notice** prior to adding or replacing any sub-processor.
2. **Notification Channels:** Notifications are delivered via platform in-app alerts and email to registered Workspace Owners.
3. **Right to Object:** Controllers may object in writing on reasonable data protection grounds within fifteen (15) days of receiving the notification. If an objection cannot be resolved amicably, Controller retains the right to terminate the Services without penalty.

---

## 5. Hosting Region & KVKK Cross-Border Transfer Status (`OQ-04`)

> [!NOTE]
> **Open Question OQ-04 Tracking:**
> The AgentNest software architecture is designed to be completely **region-agnostic**:
> - It runs on standard Docker Compose with PostgreSQL, Redis, and S3-compatible storage.
> - In self-hosted or dedicated Turkish deployments, the entire infrastructure stack (compute, database, storage) can be hosted inside Turkish borders (e.g., Turkcell, Vodafone, or Equinix Istanbul data centers) to satisfy local data residency preferences.
> - Where foreign cloud providers (such as OpenAI for LLM inference) are utilized, transfers are safeguarded by Standard Contractual Clauses and KVKK Standard Undertakings (Taahhütname) submitted to the Turkish Personal Data Protection Board.

