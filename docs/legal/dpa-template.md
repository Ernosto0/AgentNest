# Data Processing Agreement (DPA) Template / Veri İşleme Sözleşmesi

- **Document Reference:** `DPA-TEMPLATE-V1`
- **Parties:** AgentNest Operator (Data Processor / Veri İşleyen) & Tenant Business (Data Controller / Veri Sorumlusu)
- **Legal Alignment:** 6698 sayılı KVKK (Madde 12) ve Regulation (EU) 2016/679 (GDPR Article 28)
- **Review Status:** `PENDING_COUNSEL_REVIEW` (Tracking under `OQ-04`, `OQ-12`, `OQ-13`; Gate 3 Pre-condition)

---

This Data Processing Agreement ("**DPA**") governs the processing of personal data by **AgentNest Operator** ("**Processor**" or "**Veri İşleyen**") on behalf of the customer subscribing to the AgentNest services ("**Controller**" or "**Veri Sorumlusu**").

The Controller and Processor are collectively referred to as the "**Parties**" and individually as a "**Party**".

---

## 1. Scope, Purpose, and Duration of Processing

1.1. **Subject Matter:** This DPA applies to all processing of personal data carried out by Processor in connection with the provision of the AgentNest AI-assisted messaging and social media management platform ("**Services**") pursuant to the Master Services Agreement ("**Principal Agreement**").

1.2. **Nature & Purpose:** The purpose of processing is to enable Controller to receive, view, draft, schedule, automate, and dispatch communications with its customers on connected social platforms (specifically Instagram Direct Messages and comments), and to maintain operational logs, reports, and knowledge bases relating thereto.

1.3. **Duration:** Processing shall continue for the duration of the Principal Agreement until all personal data is deleted or returned in accordance with Section 8 of this DPA.

1.4. **Categories of Data Subjects:**
- Customers and prospective clients of Controller communicating via Instagram ("End-Customers");
- Authorized personnel, employees, and contractors of Controller accessing the Platform ("Users").

1.5. **Categories of Personal Data:**
- End-Customer Instagram Scoped IDs (IGSID), usernames/handles, message content, comment text, and timestamps;
- User names, business email addresses, roles, and administrative action logs;
- Verified business facts and operational rules provided by Controller.

---

## 2. Controller Instructions & Obligations

2.1. **Lawful Basis:** Controller warrants that it has established and maintains a valid legal basis under applicable data protection laws (KVKK Article 5 and GDPR Article 6) for all personal data provided to or collected by Processor through the Services.

2.2. **Transparency:** Controller is solely responsible for providing appropriate privacy notices (Aydınlatma Metni) to its End-Customers, including disclosures regarding automated AI assistance and third-party processing.

2.3. **Documented Instructions:** Processor shall process personal data solely on documented instructions from Controller, including with respect to transfers of personal data to third countries, unless required to do so by applicable law.

---

## 3. Processor Obligations

3.1. **Confidentiality:** Processor shall ensure that all persons authorized to process personal data have committed themselves to confidentiality or are under an appropriate statutory obligation of confidentiality.

3.2. **Technical and Organizational Measures (TOMs):** Processor shall implement and maintain appropriate technical and organizational measures as specified in **Annex 1** to ensure a level of security appropriate to the risk.

3.3. **No Secondary Use or Training:** Processor guarantees that End-Customer communications and Controller confidential data shall **never be used for model training**, profiling, or commercial exploitation for Processor's or any third party's benefit (`INV-09`).

3.4. **Assistance with Data Subject Rights:** Taking into account the nature of processing, Processor shall assist Controller by appropriate technical measures (including export and deletion endpoints) in fulfilling Controller's obligations to respond to data subjects exercising their statutory rights under KVKK and GDPR.

---

## 4. Sub-Processors

4.1. **General Authorization:** Controller grants general written authorization to Processor to engage the sub-processors listed in the [Sub-Processor Register](sub-processor-register.md) (**Annex 2**).

4.2. **Prior Notice of Changes:** Processor shall provide Controller with at least thirty (30) days' advance notice of any intended appointment of new sub-processors or replacement of existing sub-processors. Controller may object in writing on reasonable data protection grounds within fifteen (15) days of receiving such notice.

4.3. **Contractual Pass-Through:** Where Processor engages a sub-processor, Processor shall impose data protection terms substantially no less protective than those in this DPA. Processor remains fully liable to Controller for the performance of the sub-processor's data protection obligations.

---

## 5. Cross-Border Data Transfers

5.1. Where personal data governed by Turkish KVKK is transferred outside of Türkiye, Processor shall ensure compliance with Article 9 of KVKK, utilizing Standard Undertakings (Taahhütname) approved by the Personal Data Protection Board or other recognized legal mechanisms.

5.2. Where personal data governed by GDPR is transferred outside the European Economic Area (EEA), such transfers shall be based on Standard Contractual Clauses (SCCs) adopted by the European Commission, adequacy decisions, or equivalent approved safeguards.

---

## 6. Personal Data Breach Notification

6.1. **Notice to Controller:** Processor shall notify Controller without undue delay, and in any event within **twenty-four (24) to forty-eight (48) hours**, upon becoming aware of a confirmed personal data breach affecting Controller personal data.

6.2. **Content of Notice:** The notification shall describe:
- The nature of the breach, including categories and approximate number of data subjects and records concerned;
- The name and contact details of Processor's Data Protection Officer or contact person;
- The likely consequences of the personal data breach;
- Measures taken or proposed to be taken to address the breach and mitigate its possible adverse effects.

6.3. **Assistance:** Processor shall provide reasonable cooperation and assistance to Controller in investigating the breach and fulfilling Controller's statutory breach notification duties to authorities (such as the Turkish KVKK Board or European Supervisory Authorities) and affected data subjects.

---

## 7. Audits & Demonstrating Compliance

7.1. Processor shall make available to Controller all information reasonably necessary to demonstrate compliance with the obligations laid down in this DPA.

7.2. Processor shall permit and contribute to audits, including inspections, conducted by Controller or an independent auditor mandated by Controller, subject to reasonable advance notice (not less than 30 business days), non-disclosure agreements, and security protocols designed to prevent cross-tenant access.

---

## 8. Termination, Data Return, and Erasure

8.1. **Workspace Deletion:** Upon termination of the Services or upon Controller's explicit request to delete a workspace:
- The workspace enters a 7-day administrative grace period (`status = deleting`), during which all processing is fenced;
- Following the grace period, all database records, customer communications, vector embeddings, and media files belonging to the workspace are permanently deleted;
- Encrypted backup archives roll off within the automated thirty-five (35) day retention window (`BACKUP_RETENTION_DAYS=35`).

8.2. **Disaster Recovery Safeguard:** In the event of a database restoration from backups taken prior to deletion, Processor's automated restore procedures immediately re-apply `deletion_tombstones` to ensure that previously erased tenant data is not resurrected (`ADR-026`).

8.3. **Audit Row Minimization:** Minimal audit ledger entries certifying the execution of deletion remain immutable at the system level without containing message text or customer PII (`INV-06`, `INV-17`, `ADR-022`).

---

## Annex 1: Technical & Organizational Measures (TOMs)

Processor maintains the following technical and organizational security controls:

1. **Multi-Tenant Separation:**
   - Database-level multi-tenancy enforced by PostgreSQL Row-Level Security (RLS) on all tenant tables, strictly filtering by `app.workspace_id` per transaction (`INV-01`, `ADR-025`).
   - Cross-tenant data isolation verified by automated regression test suites.
2. **Access Control & Authentication:**
   - Password hashing utilizing `argon2id` with high memory-cost parameters.
   - Session tokens stored in encrypted, `HttpOnly`, `SameSite=Lax` cookies with strict sliding-TTL expiration.
   - Role-Based Access Control (RBAC) enforcing discrete privileges (`owner`, `manager`, `staff`).
3. **Data Encryption:**
   - Encryption in transit using TLS 1.3 with automated HSTS preloading.
   - Encryption at rest for OAuth tokens and credentials using AES-256-GCM with tenant-bound Additional Authenticated Data (`<workspace_id>:<account_id>`).
   - Key rotation capability supported by background re-encryption worker jobs (`rotate_token_keys`).
4. **Auditability & Integrity:**
   - Immutable, append-only audit logging (`audit_logs`) with runtime permissions revoking `UPDATE` and `DELETE` operations (`INV-06`, `INV-12`, `ADR-026`).
5. **Infrastructure Security:**
   - Non-root container execution (`UID 10001`) with minimal base images.
   - Continuous dependency vulnerability scanning via `pip-audit` and `npm audit` in CI pipelines.
   - Webhook endpoint protection with mandatory constant-time HMAC-SHA256 signature verification (`X-Hub-Signature-256`).
6. **Data Minimization & Redaction:**
   - Automated daily retention sweeps (`retention_cleanup`) redacting raw payloads after 30 days and message bodies after 365 days.
   - Sentry error monitoring integration configured with strict automated PII, token, and header scrubbing (`scrub_sentry_event`).

---

## Annex 2: List of Approved Sub-Processors

The approved sub-processors are set forth in the [Sub-Processor Register](sub-processor-register.md) and incorporated herein by reference.
