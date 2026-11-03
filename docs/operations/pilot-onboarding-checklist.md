# Turnkey Pilot Assisted Onboarding Walkthrough & Runbook

- **Target Phase / Task:** Phase 8 Session 16 (`P8-10`, `Gate 3`, `OQ-03`, `OQ-05`, `OQ-08`, `OQ-13`, [ADR-013](../architecture/decisions/ADR-013-authentication-and-tenancy.md), [ADR-024](../architecture/decisions/ADR-024-account-agent-and-delegated-autonomy.md))
- **Status:** Complete Production Runbook (Turkish & English Step-by-Step Operator & Owner Guide)
- **Target Workload:** First 1–5 Assisted Pilot Businesses (e.g. Pilates Studio, Fitness Center, Beauty Salon)
- **Execution Mode:** Assisted (Operator pair-onboarding with business owner in person or via video call)

---

## 1. Pre-Onboarding Eligibility & Prerequisites

Before initiating the onboarding session, the operator and business owner must verify the following prerequisites:

| Requirement | Turkish Description | Verification Method |
|---|---|---|
| **Instagram Account Type** | Instagram Profesyonel (İşletme veya İçerik Üretici) hesabı | In Instagram App: `Settings -> Account type and tools` must show *Switch to personal account* (confirming it is already Professional). |
| **Connected Facebook Page** | Instagram hesabına bağlı Facebook Sayfası | In Instagram App: `Settings -> Business -> Connect or create a Facebook Page`. Must be linked to an active Page. |
| **Page Admin Permissions** | İşletme sahibinin Facebook Sayfasında Yönetici (Admin) yetkisi | In Facebook Business Suite: Owner's personal Facebook account must have full control / Admin role on the Page. |
| **Meta App Tester Role** | Meta Geliştirici panelinde Test Kullanıcısı kaydı (OQ-03) | Operator adds owner's Facebook account or Instagram handle to `Meta Developer Portal -> App Roles -> Testers`. Owner accepts invitation at `facebook.com/developer`. |
| **Business Facts Inventory** | Doğrulanmış işletme bilgileri (çalışma saatleri, fiyatlar, adres) | Owner prepares working hours, service pricing, address/directions, and appointment booking rules in advance. |
| **Legal Documentation** | KVKK Aydınlatma Metni ve Veri İşleme Sözleşmesi (DPA) | Operator delivers `docs/legal/kvkk-aydinlatma-metni-template.md` and `docs/legal/dpa-template.md` to owner for review. |

---

## 2. Workspace Initialization & Fact Seeding (Operator Walkthrough)

### 2.1 Provision Workspace & Verified Facts
The operator provisions the tenant workspace via CLI on the production server or API:

```bash
# 1. Create workspace
python -m app.cli create-workspace \
  --name "Gölkent Pilates & Wellness" \
  --slug "golkent-pilates" \
  --language "tr"

# 2. Seed verified business facts
python -m app.cli seed-facts --workspace-slug "golkent-pilates" --facts-file /path/to/golkent-facts.json
```

Sample `golkent-facts.json` verifying factual grounding:
```json
{
  "hours.weekdays": "08:00 - 21:00",
  "hours.saturday": "09:00 - 18:00",
  "hours.sunday": "Kapalı",
  "location.address": "Atatürk Cad. No: 45 Kat: 2, Çankaya, Ankara",
  "location.parking": "Binamızın arkasında 2 saat ücretsiz açık otopark mevcuttur.",
  "pricing.reformer_single": "800 TL",
  "pricing.reformer_pack_10": "4.800 TL (10 seans, 60 gün geçerli)",
  "booking.trial_policy": "İlk deneme seansı ücretsizdir; randevu ile yapılmaktadır."
}
```

### 2.2 Configure Safety & Autonomy Defaults
In strict adherence to **OQ-08** and **OQ-13**:
- **Default Autonomy:** Set to **Human Review Required** (`autonomy: "human_review"`, `auto_send_enabled: false`). All AI replies remain in draft status awaiting human owner approval.
- **Automated Suffix:** Enabled by default (`— Otomatik yanıt`) for any future autonomous messages.
- **Publishing Limit:** Hard cap of 50 operations per 24 hours.

---

## 3. Owner Phone Verification & Account Setup (Bilingual Walkthrough)

The operator generates a single-use invite link and delivers it directly to the owner's mobile device via SMS or WhatsApp.

### 🇹🇷 Adım Adım İşletme Sahibi Kurulumu (Türkçe)

1. **Davet Bağlantısını Açma:**
   - Telefonunuza SMS veya WhatsApp ile iletilen tek kullanımlık kurulum bağlantısına dokunun:
     `https://agentnest.io/invites/accept?token=...`
2. **Hesap Oluşturma & Güvenli Şifre Belirleme:**
   - Adınızı, soyadınızı ve en az 10 karakterden oluşan güçlü bir şifre girin.
   - *Hesabımı Oluştur* butonuna dokunun.
3. **Giriş Doğrulaması:**
   - Sistem sizi otomatik olarak güvenli mobil panele yönlendirecektir.
   - Ekranın sağ üst köşesinde işletme adınızın (*Gölkent Pilates & Wellness*) yazdığını doğrulayın.

---

### 🇬🇧 Step-by-Step Owner Setup (English)

1. **Open Invitation Link:**
   - Tap the single-use onboarding invite link sent to your mobile phone via SMS or WhatsApp:
     `https://agentnest.io/invites/accept?token=...`
2. **Create Account & Secure Password:**
   - Enter your full name and a secure password (at least 10 characters).
   - Tap *Create My Account*.
3. **Login Verification:**
   - You will be automatically redirected to the secure mobile dashboard.
   - Verify that your business name (*Gölkent Pilates & Wellness*) appears in the header.

---

## 4. Meta Instagram OAuth Authorization Walkthrough

Now connect the business Instagram account to AgentNest.

### 🇹🇷 Instagram Bağlantısı ve İzin İncelemesi (Türkçe)

1. **Entegrasyonlar Menüsüne Gitme:**
   - Panelde sol/alt menüden **Ayarlar (Settings) -> Entegrasyonlar (Integrations)** bölümüne dokunun.
2. **Instagram ile Bağlan Butonu:**
   - **Instagram Hesabını Bağla (Connect Instagram)** butonuna dokunun. Resmi Facebook / Meta giriş ekranı açılacaktır.
3. **İzinleri Onaylama:**
   - Meta ekranında şu izinler listelenecektir:
     - *Instagram temel profil bilgilerini görüntüleme* (`instagram_basic`)
     - *Instagram mesajlarını yönetme ve yanıtlama* (`instagram_manage_messages`)
     - *Yorumları görüntüleme ve yanıtlama* (`instagram_manage_comments`)
     - *Facebook Sayfası etkileşimlerini yönetme* (`pages_manage_metadata`, `pages_read_engagement`)
   - İlgili Facebook Sayfanızı ve Instagram İşletme hesabınızı seçerek **İzin Ver (Allow)** butonuna dokunun.
4. **Bağlantı Başarısını Doğrulama:**
   - Ekran AgentNest paneline geri dönecektir.
   - Durum rozeti **Bağlandı (Connected)** ve Instagram kullanıcı adınız (örneğin `@golkentpilates`) yeşil ikonla görüntülenecektir.

---

### 🇬🇧 Instagram Connection & Permission Review (English)

1. **Navigate to Integrations:**
   - In the sidebar or mobile menu, navigate to **Settings -> Integrations**.
2. **Connect Instagram Button:**
   - Tap **Connect Instagram Account**. The official Meta authorization screen will appear.
3. **Review & Approve Permissions:**
   - The permissions dialog will display:
     - *View basic Instagram profile information* (`instagram_basic`)
     - *Manage and reply to Instagram direct messages* (`instagram_manage_messages`)
     - *View and moderate post comments* (`instagram_manage_comments`)
     - *Manage Page webhook delivery* (`pages_manage_metadata`, `pages_read_engagement`)
   - Select your Facebook Page and Instagram Business Account, then tap **Allow**.
4. **Confirm Connection Status:**
   - You are redirected back to AgentNest.
   - Confirm that the status badge reads **Connected** with your handle (e.g. `@golkentpilates`).

---

## 5. Supervised Live Test & First Message Walkthrough

To ensure total trust and verify fact-grounded accuracy, conduct a live test with the owner:

| Step | Action | Turkish Walkthrough | English Walkthrough | Expected Outcome |
|---|---|---|---|---|
| **1. Send Inbound DM** | Owner or operator sends DM from a personal Instagram account | Kişisel Instagram hesabınızdan işletmenizin Instagram hesabına DM gönderin: *"Merhaba, reformer seans paket fiyatlarınızı öğrenebilir miyim?"* | Send a DM from a separate account to the business: *"Hello, what are your reformer package prices?"* | Message arrives instantly in AgentNest Unified Inbox via webhook. |
| **2. Review AI Draft** | Inspect draft in AgentNest Inbox | AgentNest panelinde Mesaj Kutusu (Inbox) ekranını açın. Gelen mesajın altında *Hazırlanıyor…* rozeti belirecek ve birkaç saniye içinde taslak yanıt oluşturulacaktır. | Open AgentNest Unified Inbox. Under the incoming message, the AI drafts a factual response. | Draft displays: *"Merhaba! Reformer pilates 10 seanslık paketimiz 4.800 TL'dir (60 gün geçerlidir). — Otomatik yanıt"* |
| **3. Grounding Verification** | Compare draft with facts | Taslaktaki fiyat ve bilginin yüklenen işletme bilgileriyle (4.800 TL) birebir örtüştüğünü doğrulayın. Asla uydurma veya halüsinasyon bilgi olmamalıdır. | Verify that the price matches the seeded business facts exactly (4,800 TL). No hallucinated or unverified facts. | Facts strictly validated. |
| **4. Human Approval** | Owner approves draft | Yanıtı inceleyin, dilerseniz metni düzenleyin ve **Onayla ve Gönder (Approve & Send)** butonuna dokunun. | Review the text, optionally edit, and tap **Approve & Send**. | AgentNest dispatches message via Meta Graph API; status updates to *Sent*. |
| **5. Delivery Confirmation** | Check sender phone | Kişisel Instagram DM kutunuzu kontrol edin. Yanıtın ulaştığını doğrulayın. | Check the test Instagram account's DM inbox to verify delivery. | Customer account receives the message with the disclosure suffix. |

---

## 6. Emergency Rollback & Contingency Runbooks

The business owner must know how to pause, override, or immediately disconnect AgentNest at any time.

### Contingency Runbook A: Immediate Emergency Disconnect (Tek Tıkla Bağlantı Kesme)
- **When to use:** In case of any unexpected behavior, account security concern, or desire to immediately stop all AgentNest access.
- **Action (In-App):**
  1. Go to **Settings -> Integrations**.
  2. Click **Instagram Bağlantısını Kes (Disconnect Instagram)**.
  3. Confirm the modal. AgentNest immediately revokes tokens, pauses background workers, and deletes local cached session credentials.
- **Action (From Instagram/Facebook App):**
  1. Open Instagram -> Settings -> Security / Permissions -> Apps and Websites.
  2. Select `AgentNest` and tap **Remove**.
  3. Meta immediately triggers the deauthorization webhook; AgentNest fences all background operations within 2 seconds.

### Contingency Runbook B: Pause Autonomous Processing (Yapay Zekayı Duraklatma)
- **When to use:** If the owner wants to handle DMs manually for a holiday or high-traffic event.
- **Action:**
  1. Navigate to **Agent & Autonomy Settings**.
  2. Toggle **Yapay Zeka Asistanı (AI Assistant)** to `Paused / Kapalı`.
  3. AgentNest ceases drafting and auto-actions; existing conversations can still be answered manually from the Inbox.

### Contingency Runbook C: Emergency Operator Escalation (Operatör Destek Hattı)
- **Emergency Contact:** `ops@agentnest.io` / WhatsApp Destek Hattı: `+90 (5XX) XXX XX XX`
- **SLA:** 15-minute response time for active pilot businesses during pilot hours (08:00 - 22:00 TRT).
- **Incident Playbook:** Operator can run `python -m app.cli post-restore-reconcile` or freeze workspace tenant jobs remotely.
