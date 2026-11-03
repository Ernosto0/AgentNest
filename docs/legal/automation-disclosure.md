# AI Automation Disclosure Policy & Recommended Wording

- **Document Reference:** `LEGAL-AUTOMATION-DISCLOSURE-V1`
- **Applicable Open Question:** `OQ-13` ("Is an automation disclosure legally required in Türkiye for automated DMs, and what wording?")
- **Effective Date:** November 3, 2026
- **Review Status:** `PENDING_COUNSEL_REVIEW` (Tracking under `OQ-13`; Gate 3 Pre-condition)

---

## 1. Legal Analysis & Context

### 1.1 Turkish Legal Landscape
Under Turkish legislation:
1. **Law on the Protection of Consumers (Law No. 6502):** Prohibits deceptive or misleading commercial practices. Misleading consumers regarding the identity, qualifications, or nature of the counterparty (e.g., misrepresenting an automated chatbot as a human specialist or medical practitioner) creates regulatory risk and potential administrative fines.
2. **Regulation on Commercial Communication and Commercial Electronic Messages:** Requires clear identification of the sender and transparent information regarding the nature of the message.
3. **KVKK (Law No. 6698) Fair Processing Principles:** Personal data must be processed fairly, transparently, and in good faith (Art. 4). Data subjects should not be misled about whether they are conversing with an autonomous system.

### 1.2 Emerging Global Standards (EU AI Act Article 50)
The EU Artificial Intelligence Act (Regulation 2024/1689, Article 50) establishes transparency obligations:
> *"Providers shall ensure that AI systems intended to interact directly with natural persons are designed and developed in such a way that the natural persons concerned are informed that they are interacting with an AI system, unless this is obvious from the points of view of a reasonable and reasonably well-informed, observant and circumspect natural person."*

While AgentNest primarily serves Turkish SMBs in the pilot phase, adopting clear automation transparency aligns with both Turkish consumer protection norms and international best practices.

---

## 2. Platform Architecture & Technical Implementation

AgentNest implements a granular, tiered disclosure model based on the level of autonomy involved in each message:

```
[Inbound Customer DM]
         │
         ▼
[Policy Evaluation & LLM Generation]
         │
    ┌────┴───────────────────────────┐
    ▼                                ▼
[Autonomous Auto-Send]       [Human Review Required]
(e.g., hours, address, FAQs) (e.g., pricing, custom questions)
    │                                │
    ▼                                ▼
Appends Disclosure Suffix     Approved / Edited by Owner/Staff
" — Otomatik yanıt"                  │
                                     ▼
                              Sent Without Suffix
                              (Human-reviewed / authored)
```

### 2.1 Suffix Automation Rules
1. **Fully Autonomous Replies (`auto_sent = true`):**
   - When the agent responds directly without operator intervention (e.g., verified store location, opening hours, standard policy answers), the platform **appends a disclosure suffix by default**.
   - Default Turkish suffix: `" — Otomatik yanıt"`
   - Default English suffix: `" — Automated reply"`
2. **Human-Approved Replies (`auto_sent = false`):**
   - When an AI-generated draft is reviewed, approved, or edited by a workspace owner or manager, no automated suffix is appended by default because human oversight and verification were actively exercised.
3. **Manual Human Replies:**
   - Messages authored directly by human staff in the Inbox never receive an automated suffix.
4. **Configurability:**
   - Workspace owners can customize or disable the suffix in Workspace Automation Settings (`more/automation`), provided their counsel approves alternative disclosures (such as bio disclosures).

---

## 3. Recommended Wording for Businesses

To maintain high customer trust and ensure legal compliance, businesses are provided with recommended disclosure wording across their customer touchpoints:

### 3.1 In-Message Suffix Options (Configurable per Workspace)
- **Standard (Default):**
  - TR: `\n\n— Otomatik yanıt`
  - EN: `\n\n— Automated reply`
- **Friendly / Studio Style:**
  - TR: `\n\n(Bu mesaj asistanımız tarafından otomatik iletilmiştir.)`
  - EN: `\n\n(This message was sent automatically by our virtual assistant.)`
- **Assisted with Human Escalation Notice:**
  - TR: `\n\n— Otomatik yanıt (Yetkili ekibimiz en kısa sürede inceleyecektir)`
  - EN: `\n\n— Automated reply (Our team will review your message shortly)`

### 3.2 Instagram Bio / Profile Disclosures (Recommended Practice)
Businesses are encouraged to include an explicit notice in their Instagram profile biography or link-in-bio:
- **Short Bio Template:**
  > *"📍 Nişantaşı, İstanbul | 🕒 09:00 - 20:00 | 🤖 DM'leriniz yapay zekâ asistanımız ve ekibimiz tarafından yanıtlanmaktadır."*
- **Comprehensive Aydınlatma Link:**
  > *"DM Aydınlatma Metni ve Gizlilik: [linkin.bio/isletme-kvkk]"*

### 3.3 Escalation to Human Staff
Whenever a customer asks to speak with a human or expresses dissatisfaction:
- The system automatically transitions the thread to `human_required` (`HUMAN_TAKEOVER`).
- Automated replies are immediately suspended.
- In-app notification alerts the workspace staff.

---

## 4. Open Question `OQ-13` Resolution Tracking

- **Status:** **Provisional default confirmed and implemented**.
- **Default Position:** Disclosure suffix is enabled by default for all auto-sent replies (`— Otomatik yanıt` / `— Automated reply`).
- **Counsel Sign-Off:** Pending formal counsel endorsement prior to Gate 3 pilot launch.
