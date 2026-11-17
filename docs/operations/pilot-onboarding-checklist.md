# Turnkey Pilot Assisted Onboarding Walkthrough & Runbook

- **Target Phase / Task:** Phase 8 Session 16 (`P8-10`, `Gate 3`, `OQ-03`, `OQ-05`, `OQ-08`, `OQ-13`, [ADR-013](../architecture/decisions/ADR-013-authentication-and-tenancy.md), [ADR-024](../architecture/decisions/ADR-024-account-agent-and-delegated-autonomy.md))
- **Status:** Runbook, dry-run verified on 2026-11-16 against a fresh local database (mock Instagram provider, fake LLM). The real Meta consent screen (section 4) cannot be exercised locally; it is checked against Meta's documentation and must be confirmed on the first real pilot.
- **Target Workload:** First 1–5 Assisted Pilot Businesses (e.g. Pilates Studio, Fitness Center, Beauty Salon)
- **Execution Mode:** Assisted (Operator pair-onboarding with business owner in person or via video call)

---

## 1. Pre-Onboarding Eligibility & Prerequisites

Before initiating the onboarding session, the operator and business owner must verify the following prerequisites:

| Requirement | Turkish Description | Verification Method |
|---|---|---|
| **Instagram Account Type** | Instagram Profesyonel (İşletme veya İçerik Üretici) hesabı | In the Instagram app: `Settings and activity -> Account type and tools` must offer *Switch to personal account* (this confirms the account is already Professional). A personal account must first be switched to Professional (Business or Creator). |
| **Facebook Page** | **Gerekmez.** | AgentNest connects with *Instagram API with Instagram Login* (Business Login for Instagram). Meta's documentation states that this setup "does not require a Facebook Page to be linked to the Instagram professional account", so the owner needs neither a linked Page nor Page admin rights. Do not ask for them. |
| **Meta App Tester Role** | Meta Geliştirici panelinde Instagram Test Kullanıcısı (OQ-03) | While the app is in development mode (before App Review), the operator adds the owner's Instagram account in `Meta Developer Portal -> App roles -> Roles -> Instagram Testers`. The owner accepts the invitation in the Instagram app (`Settings -> Apps and websites -> Tester invites`; Meta moves these menu names now and then). Until the invitation is accepted, the consent screen in section 4 fails. |
| **Business Facts Inventory** | Doğrulanmış işletme bilgileri (çalışma saatleri, fiyatlar, adres) | Owner prepares working hours, service pricing, address/directions, a phone number, and how customers book. These are the facts the assistant may quote (section 2.2). |
| **Legal Documentation** | KVKK Aydınlatma Metni ve Veri İşleme Sözleşmesi (DPA) | Operator delivers `docs/legal/kvkk-aydinlatma-metni-template.md` and `docs/legal/dpa-template.md` to owner for review. |
| **Server health (operator, before the visit)** | — | `curl https://<app-host>/readyz` answers `{"status":"ok"}`; on the server `python -m app.cli check-config` and `python -m app.cli migration-status` report no problem. The worker must be running: without it drafts stay at *Hazırlanıyor…* and nothing is sent. |

---

## 2. Workspace Initialization & Fact Seeding (Operator Walkthrough)

There is no `create-workspace` or `seed-facts` command. The workspace is created in the app, with the same wizard an owner would use, and the facts are entered in the app. This keeps one tested path for operator-assisted and self-service setup.

### 2.1 Create the operator account and the workspace

1. **Operator account (once, on the server).** Run it with no `--password` so the password is prompted and stays out of the shell history:
   ```bash
   python -m app.cli create-user --email operator@example.com --display-name "Operator" --locale tr
   ```
   The password needs at least 10 characters. Sign in at `https://<app-host>/login`.
2. **Create the workspace.** On the workspace list tap **Çalışma alanı oluştur** (Create workspace) and complete the three steps: business name (for example `Gölkent Pilates & Wellness`), business type, then market, business language (`Türkçe`/`English`), time zone and currency. A Turkish business gets `Europe/Istanbul` and `TRY` by default. The wizard ends on **İşletme bilgileri** (Business knowledge) of the new workspace. The operator is its first owner.

### 2.2 Enter the verified business facts

Open **Daha fazla -> İşletme bilgileri** (Business knowledge). Two ways to fill it, and a normal session uses both:

- **Paste to extract.** Tap **Metinden öneri al**, paste the owner's Instagram bio, price list or website text and tap **Önerileri bul**. The assistant proposes facts (worker required); they appear under **Öneriler** (Suggestions) and **nothing is used until a person accepts each one**. Check every value against what the owner says before accepting.
- **Add by hand.** Under **İlginizi bekleyenler** each missing topic has an **Ekle** (Add) button. Use it for anything the extraction missed.

What must exist before the assistant can draft ("Taslaklar için") and before automation can be switched on ("Otomasyon için"), as shown by the setup card on the same page:

| Topic (Turkish label) | Fact key | Value format | Needed for |
|---|---|---|---|
| İşletme adı | `identity.business_name` | text | drafts |
| İletişim yolu | `contact.phone` (or `contact.whatsapp`, `contact.email`) | phone in E.164 (`+905550000000`) or email; one is enough | drafts |
| Adres | `location.address` (or `location.online_only` = yes) | address lines, district, city | drafts |
| Çalışma saatleri | `hours.weekly` | opening ranges per weekday, closed days empty | drafts |
| Rezervasyon talimatı | `booking.instructions` | text, Turkish and English | automation |
| Fiyat politikası | `policy.price_disclosure` | `share` (quote prices) or `do_not_share` | automation |
| Hizmetler | `service.<name>` (at least one) | short description, with a label | automation |

Prices are separate facts per product, for example `pricing.reformer_pack_10` = `4.800 ₺`, unit *package*, label `Reformer 10 seanslık paket`. The assistant may quote a price **only** through such a fact; it never guesses one. Add the prices the owner expects customers to ask about, because the live test in section 5 depends on them.

Optional but useful: `promotion.*` (with an end date), `policy.cancellation`, `brand.voice_guidelines`, `escalation.keywords`.

### 2.3 Safety and autonomy defaults (already in place, verify, do not change on day one)

Checked on a fresh workspace:

- **Every reply waits for the owner.** Each topic starts on **Önce bana sor** (ask me first); no topic sends on its own. Auto-send is blocked until the facts above exist, an Instagram account is connected, and the owner has pressed **Bu ayarları inceledim** (I have reviewed these settings) on **Daha fazla -> Otomasyon ve Instagram**. Leave all topics on *Önce bana sor* for the first days (OQ-08).
- **Automation disclosure (OQ-13).** The disclosure is on by default and is appended **only to replies the assistant sends on its own**: `Bu yanıt otomatik olarak hazırlanmıştır.` (English: `This reply was prepared automatically.`). A reply the owner approves or writes is sent without it. The text can be changed under workspace settings. There is no `— Otomatik yanıt` suffix.
- **Publishing limit.** At most 50 posts per 24 hours per account (`PUBLISH_DAILY_LIMIT`, Meta's own ceiling).
- **Cost guard.** At most 500 model calls per workspace per day (`LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY`).
- **Monthly AI reply allowance.** Every workspace starts on the `growth` plan, status `trial` (2,500 AI reply drafts per month, 10% grace, warnings at 80% and 100% to the owner and managers, then AI drafting pauses while messages still arrive). The operator changes it: `python -m app.cli plan-usage --workspace <slug>` shows the numbers, `plan-set --workspace <slug> --plan starter|growth|pro [--quota N | --clear-override] [--status trial|active|past_due|cancelled]` changes the plan, `plan-reset` starts a fresh period now, `plan-extend --days N` moves the period end. The owner sees it in Settings (Plan and AI replies) and on Today from 80%.

---

## 3. Owner Phone Verification & Account Setup (Bilingual Walkthrough)

The operator creates a single-use invite and delivers it to the owner's phone via SMS or WhatsApp.

**Operator:** `Daha fazla -> Üyeler -> Üye davet et`, choose the role **owner** (Sahip) for the business owner, tap **Davet oluştur**, and send the **Davet bağlantısı** (invite link) or show its QR code. The link has the form `https://<app-host>/invite/<token>`, is valid for 7 days, works once, and is shown only at creation (create a new one if it is lost). The operator stays an owner of the workspace; tell the owner, who can remove or change roles under **Üyeler**. The last owner cannot be removed.

### 🇹🇷 Adım Adım İşletme Sahibi Kurulumu (Türkçe)

1. **Davet Bağlantısını Açma:**
   - Telefonunuza SMS veya WhatsApp ile iletilen tek kullanımlık bağlantıya dokunun:
     `https://<uygulama-adresi>/invite/<kod>`
2. **Hesap Oluşturma:**
   - **Adınız**, **E-posta** ve en az 10 karakterden oluşan bir **Parola** girin.
   - **Hesap oluştur ve katıl** butonuna dokunun. (Zaten hesabınız varsa *Giriş yap* deyin; sonra davete geri dönersiniz.)
3. **Giriş Doğrulaması:**
   - Sistem sizi otomatik olarak çalışma alanına yönlendirir.
   - Üst çubukta işletme adınızın (*Gölkent Pilates & Wellness*) yazdığını ve ana ekranda *Merhaba, <adınız>* selamını gördüğünüzü doğrulayın.

---

### 🇬🇧 Step-by-Step Owner Setup (English)

1. **Open Invitation Link:**
   - Tap the single-use link sent to your phone via SMS or WhatsApp:
     `https://<app-host>/invite/<token>`
2. **Create Account:**
   - Enter your **name**, **email** and a **password** of at least 10 characters.
   - Tap **Create account and join**. (If you already have an account, tap *Sign in*; you return to the invite afterwards.)
3. **Login Verification:**
   - You are redirected into the workspace automatically.
   - Verify that your business name (*Gölkent Pilates & Wellness*) appears in the header and the home screen greets you by name.

---

## 4. Meta Instagram OAuth Authorization Walkthrough

Now connect the business Instagram account to AgentNest. The owner signs in with their **Instagram** credentials; no Facebook account or Page is involved.

### 🇹🇷 Instagram Bağlantısı ve İzin İncelemesi (Türkçe)

1. **Bağlantılar Ekranına Gitme:**
   - **Daha fazla -> Instagram bağlantısı** (ya da **Ayarlar -> Bağlantılar**) bölümüne dokunun.
2. **Instagram ile Bağlan Butonu:**
   - **Instagram ile bağlan** butonuna dokunun. Resmi Instagram giriş ve izin ekranı açılacaktır. (Buton yalnızca sunucuda gerçek Meta sağlayıcısı açıksa görünür; yerel denemelerde **Demo hesabı bağla (simülasyon)** görünür.)
3. **İzinleri Onaylama:**
   - Ekranda AgentNest'in şu erişimleri istediği listelenir (Instagram kendi cümlelerini kullanır; teknik adları parantezde):
     - Profil bilgilerinizi görme (`instagram_business_basic`)
     - Mesajlarınızı yönetme ve yanıtlama (`instagram_business_manage_messages`)
     - Gönderi ve hikâye paylaşma (`instagram_business_content_publish`)
     - Hesap istatistiklerini görme (`instagram_business_manage_insights`)
     - Yorumları yönetme (`instagram_business_manage_comments`)
   - **İzin Ver (Allow)** butonuna dokunun. Yorum izni, yorum otomasyonunu tek başına etkinleştirmez (aşağıdaki not).
4. **Bağlantı Başarısını Doğrulama:**
   - Ekran AgentNest'e geri döner; durum **bağlı** ve Instagram kullanıcı adınız görünür.
   - **Yapabildikleri** satırında verilen izinlere göre *Mesajlaşma*, *Gönderi yayınlama* ve *Yorum izni* görünür. *Yorum izni* yorum otomasyonunun açık olduğu anlamına gelmez.

> **Not (yorumlar):** Uygulama artık `instagram_business_manage_comments` iznini ister; yalnızca Meta'nın gerçekten verdiği izin `comments_permission` olarak kaydedilir. Önceden bağlanan gerçek hesaplarda izin yoksa **Ayarlar -> Bağlantılar** ekranı bağlantıyı yenileme notu ve sahibine **Instagram ile bağlantıyı yenile** butonunu gösterir. Mevcut mesajlaşma ve paylaşım etkilenmez. İzin verilse de R75 kanıtları ve Session 02 hesap bazlı etkinleştirme kapısı tamamlanana kadar yorum eylemleri kapalıdır; **Gelen kutusu -> Yorumlar** *Henüz yok* olarak kalır. Meta App Review onayı / geliştirme hesabı izni ve canlı kanıtlar ayrıca doğrulanmalıdır; pilot sahibine yorum yanıtı vaat etmeyin.

---

### 🇬🇧 Instagram Connection & Permission Review (English)

1. **Navigate to the connection screen:**
   - **More -> Instagram connection** (or **Settings -> Connections**).
2. **Connect button:**
   - Tap **Connect with Instagram**. The official Instagram sign-in and permission screen opens. (The button appears only when the real Meta provider is enabled on the server; local trials show **Connect demo account (simulation)**.)
3. **Review & approve permissions:**
   - The screen lists the access AgentNest asks for (Instagram words it its own way; technical names in brackets):
     - View your profile information (`instagram_business_basic`)
     - Manage and reply to your messages (`instagram_business_manage_messages`)
     - Publish posts and stories (`instagram_business_content_publish`)
     - View account insights (`instagram_business_manage_insights`)
     - Manage comments (`instagram_business_manage_comments`)
   - Tap **Allow**. Comment permission alone does not enable comment automation (see below).
4. **Confirm connection status:**
   - You are redirected back to AgentNest; the status reads **connected** with your handle.
   - The **Capabilities** line lists *Messaging*, *Publishing* and *Comment permission* according to the actual grants. *Comment permission* does not mean comment automation is enabled.

> **Note (comments):** the app now requests `instagram_business_manage_comments`; only Meta's actual grant is recorded as `comments_permission`. Existing real accounts without the grant show a reconnect note in **Settings -> Connections**, with **Reconnect with Instagram** for the owner. Messaging and publishing keep working. Comment actions stay disabled even with consent until R75 evidence and Session 02 per-account activation are complete; **Inbox -> Comments** keeps its *Not yet* label. Meta App Review approval / development-account permission and live evidence must be verified separately; do not promise comment replies to a pilot owner. See the [App Review package](meta-app-review-package.md).

---

## 5. Supervised Live Test & First Message Walkthrough

To ensure total trust and verify fact-grounded accuracy, conduct a live test with the owner. Prepare it from the facts entered in section 2: ask a question that one of **your own verified facts answers** (the assistant hands everything else to a person, see step 2).

| Step | Action | Turkish Walkthrough | English Walkthrough | Expected Outcome |
|---|---|---|---|---|
| **1. Send Inbound DM** | Owner or operator sends DM from a personal Instagram account | Kişisel Instagram hesabınızdan işletmenizin hesabına, girdiğiniz bir bilgiyle yanıtlanabilecek bir DM gönderin: *"Merhaba, reformer 10 seanslık paket fiyatınız nedir?"* | Send a DM from a separate account to the business that one of your facts answers: *"Hello, what is your 10-session reformer pack price?"* | The message appears in **Gelen kutusu -> Mesajlar** within seconds (webhook), marked *Size gerek var* until the draft is ready. |
| **2. Review AI Draft** | Inspect draft in AgentNest Inbox | **Gelen kutusu**'nu açıp konuşmaya dokunun. Hazırlanırken *Hazırlanıyor…* görünür; sonra *Asistanın taslağı* ve *Onay bekliyor* çıkar. | Open the conversation in **Inbox**. *Preparing…* shows while the draft is made, then *Assistant's draft* with *Waiting for approval*. | Draft quotes the fact exactly, e.g. *"Merhaba! Reformer 10 seanslık paket ücretimiz 4.800 ₺."* The price is shown as a chip tied to its fact. If no fact covers the question, the assistant answers *Asistan emin olamadı* / *Size devredildi* (handed to you) instead of guessing: that is correct behaviour, not a fault. |
| **3. Grounding Verification** | Compare draft with facts | Taslaktaki fiyat ve bilginin girdiğiniz bilgilerle birebir aynı olduğunu doğrulayın. Uydurma bilgi olmamalıdır. | Verify that the price matches the entered facts exactly. No invented or unverified facts. | Facts strictly validated. |
| **4. Human Approval** | Owner approves draft | Yanıtı inceleyin, dilerseniz **Düzenle** ile değiştirin ve **Onayla ve gönder** butonuna dokunun. | Review the text, optionally **Edit**, and tap **Approve and send**. | AgentNest sends the message through the Instagram API; the draft shows *Gönderildi* (Sent) with *"<name> onayladı (date time)"*. |
| **5. Delivery Confirmation** | Check sender phone | Kişisel Instagram DM kutunuzu kontrol edin; yanıtın ulaştığını doğrulayın. | Check the test Instagram account's DM inbox to verify delivery. | The customer account receives the message. The disclosure sentence is **not** added to an owner-approved reply (section 2.3). |

---

## 6. Emergency Rollback & Contingency Runbooks

The business owner must know how to pause, override, or immediately disconnect AgentNest at any time.

### Contingency Runbook A: Immediate Emergency Disconnect (Tek Tıkla Bağlantı Kesme)
- **When to use:** In case of any unexpected behavior, account security concern, or desire to immediately stop all AgentNest access.
- **Action (In-App):**
  1. Go to **More -> Instagram connection** (**Daha fazla -> Instagram bağlantısı**).
  2. Tap **Bağlantıyı kes** (Disconnect). A dialog asks to confirm and offers to delete the conversation and message history as well (**Konuşma ve mesaj geçmişini de sil**, off by default).
  3. Tap **Evet, bağlantıyı kes**. Replies and posts can no longer be sent; AgentNest drops its stored token.
- **Action (From Instagram):**
  1. Open Instagram -> Settings -> Apps and websites.
  2. Select `AgentNest` and tap **Remove**.
  3. Meta calls the deauthorization webhook and AgentNest fences all background operations for that account.

### Contingency Runbook B: Pause Automatic Replies (Yapay Zekayı Duraklatma)
- **When to use:** If the owner wants to handle DMs manually for a holiday or high-traffic event.
- **Action:**
  1. Go to **More -> Automation and Instagram** (**Daha fazla -> Otomasyon ve Instagram**).
  2. Set every topic to **Her zaman bana bırak** (always leave it to me) and tap **Kaydet**. Nothing is sent without the owner; existing conversations can still be answered from the Inbox (**Kendi yanıtını yaz**).
  3. If the account assistant was switched on (**Daha fazla -> Asistan**, *Hesap asistanını etkinleştir*), the same page offers **Asistanı duraklat** (Pause assistant), which stops new assistant work until resumed.
- On the default setting (*Önce bana sor*) nothing is ever sent without the owner's tap, so pausing is only needed once the owner has turned on **Otomatik gönder** for a topic.

### Contingency Runbook C: Emergency Operator Escalation (Operatör Destek Hattı)
- **Emergency Contact:** `ops@agentnest.io` / WhatsApp Destek Hattı: `+90 (5XX) XXX XX XX` (placeholders until the domain and numbers are decided, P-07).
- **SLA:** 15-minute response time for active pilot businesses during pilot hours (08:00 - 22:00 TRT).
- **Incident Playbook:** Check **Daha fazla -> Sistem durumu** (connection, delivery and background jobs) first. On the server, `python -m app.cli check-config` and `migration-status` confirm configuration; `python -m app.cli post-restore-reconcile` is only for after a database restore (it re-applies erasure tombstones and fences stale operations), not for routine incidents.

### Feature Phase 3 comment-to-DM / yorumdan DM

- [ ] Owner reconnects to grant comment permission, completes manual subscription/readback and live gate, then enables **Comment-to-DM (private replies)** in Connections; activates the agent with **Ask** delegation and a verified fact. Follow [the rollout](account-agent-rollout.md#real-account-comment-to-dm-rollout-feature-phase-3). Live evidence pending; public moderation stays off.
- [ ] Hesap sahibi yorum izni için bağlantıyı yeniler; manuel aboneliği ve canlı kanıtları tamamladıktan sonra Bağlantılar'da **Yorumdan DM’ye (özel yanıtlar)** ayarını açar. Asistanı doğrulanmış bilgiyle ve **Sor** yetkisiyle etkinleştirir. Canlı sonuçlar bekleniyor; herkese açık yanıt ve moderasyon kapalıdır.
