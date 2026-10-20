# User Journeys, Screens, Edge Cases and Failure States

**Purpose:** How real people move through the product on a phone, what they see in each state, and what happens when things go wrong. Backend contracts for the same flows are in [workflows.md](../architecture/workflows.md). This document is the UX source of truth.

UI copy examples are in Turkish (the primary market) with English in brackets. Final copy lives in the i18n catalogs.

## 1. Navigation and screen inventory

**Mobile (< 768 px):** bottom tab bar with five tabs plus a persistent command bar on Home.

| Tab | Screens |
|---|---|
| **Ana sayfa (Home)** | Status strip (account connection, **SİMÜLASYON** badge if applicable, AI mode), attention cards (approvals waiting, conversations needing a human, failures, on-hold content), upcoming posts (next 3), today's numbers (from the report service), **command bar** |
| **Gelen kutusu (Inbox)** | Conversation list with filters: *Yanıt bekliyor* (needs reply), *Onay bekliyor* (needs approval), *Size devredildi* (needs human), *Tümü* (all). Conversation detail. |
| **İçerik (Content)** | Tabs (G15): Drafts (`draft`, `pending_approval`), Scheduled (`scheduled`, `publishing`, `retry_scheduled`), Published, Problems (`on_hold`, `failed`, `rejected`). `cancelled` items are in no tab. Content editor. "Ask for a draft" sheet. |
| **Onaylar (Approvals)** | Pending approvals list (badge count). Approval detail sheet. Recent decisions. |
| **Daha fazla (More)** | Business knowledge, Suggestions (fact candidates), Approved answers, Reports, Activity, Notifications, Settings (business, members, automation, connections, language), Dev panel (demo only) |

**Desktop (≥ 768 px):** left sidebar with the same items. The command bar sits in the header.

**Global elements:** workspace switcher (top), notification bell with count, simulation banner when the current workspace uses a mock account ("Bu çalışma alanı simülasyondur, gerçek Instagram'a hiçbir şey gönderilmez" / "This workspace is simulated; nothing is sent to real Instagram").

### Status vocabulary (shared across screens; [INV-18](../invariants.md))
| Internal state | Badge (tr / en) | Colour + icon (never colour alone) |
|---|---|---|
| Draft | Taslak / Draft | grey, pencil |
| Pending approval | Onay bekliyor / Awaiting approval | amber, clock |
| Needs human | Size devredildi / Needs you | orange, hand |
| Scheduled | Zamanlandı / Scheduled | blue, calendar |
| On hold | Beklemede / On hold | orange, pause |
| Sending / Publishing | Gönderiliyor / Yayınlanıyor | blue, spinner |
| Checking | Kontrol ediliyor / Checking | blue, magnifier |
| Sent / Published | Gönderildi / Yayınlandı | green, check |
| Failed | Başarısız / Failed | red, alert |
| Expired | Süresi doldu / Expired | grey, hourglass |
| Simulated (modifier) | SİMÜLASYON / SIMULATED | purple outline badge appended to any of the above |

## 2. Journeys

### J1: Assisted onboarding (founder + owner, at the business) [UC-01…04, UC-20]
**Goal:** In one 30–45 minute visit, reach readiness `ready_for_drafts` or `ready`, and show the first drafted answer.

1. The founder logs in, creates the workspace "Lale Pilates" (fictional), category *Pilates stüdyosu*, market Türkiye, timezone Europe/Istanbul, currency TRY. The founder invites the owner, who sets her password on her own phone via the one-time link (displayed as a QR code in S1). Ownership: the founder transfers the `owner` role to the business owner and keeps `manager` (or leaves) as she prefers. Audited.
2. **Knowledge wizard:** the category template shows groups (İletişim, Konum, Çalışma saatleri, Hizmetler, Fiyatlar, Kampanyalar, Rezervasyon, Politikalar, Marka dili). Each item shows `missing`, `suggested`, or `verified`.
3. *Yapıştır ve çıkar (Paste & extract):* the founder pastes the Instagram bio and a price list photo's text typed by the owner. Suggestions appear as candidates with the excerpt they came from. The owner taps **Doğru (Correct)** or edits each one. Nothing becomes verified without her tap.
4. Opening hours editor: weekday chips with time ranges, plus holiday exceptions.
5. **Price disclosure policy:** "Fiyatları DM'den paylaşalım mı?" (Share prices via DM?). Yes, or "No, invite them to call/visit" (`policy.price_disclosure`).
6. **Readiness checklist** turns green item by item. Automation stays on "Her yanıt için onay iste" (Ask approval for every reply) by default.
7. **Test a question:** "Bir müşteri gibi soru sor" (Ask like a customer) sends a simulated message through the pipeline (in S1 always; in S2+ only on demo workspaces). The owner sees the draft card with the facts used.
8. Connect Instagram: in S1 a mock account is connected and the screen states it is simulated. In S2+ the Instagram Login flow runs on the owner's phone.

**Edge cases:** the owner does not know an exact price ("depends") → enter a text fact with conditions, or set price disclosure to "do not share". Two branches → out of scope; use one workspace per branch. The owner refuses to verify a value → it stays a candidate and is never used.
**Failure states:** extraction fails (LLM error) → "Metni şu an işleyemedik, elle girebilirsiniz" (We couldn't process the text right now, you can enter it manually); the pasted text is kept. Invite link expired → regenerate.

### J2: Daily inbox triage on the phone [UC-05, 07, 08, 09]
1. A notification badge shows "3 onay bekliyor". The owner opens Approvals or Inbox → *Onay bekliyor*.
2. **Draft card** (in the conversation view):
   - Customer messages (grouped burst), time, and a **window timer** ("Yanıt için 21 sa kaldı" / "21 h left to reply").
   - Proposed reply text, with rendered fact values highlighted. Tapping a value shows "Kaynak: Aylık üyelik fiyatı, doğrulandı 12 Ekim".
   - **Why this needs approval:** reason chips (e.g., "Fiyat içeriyor", "Otomatik gönderim kapalı").
   - Actions: **Onayla ve gönder** (Approve & send), **Düzenle** (Edit), **Reddet** (Reject), overflow: *Konuşmayı devral* (Take over), *Onaylı yanıt olarak kaydet* (Save as approved answer).
3. After approval, the status changes *Gönderiliyor → Gönderildi*. With the mock the badge also reads SİMÜLASYON.
4. **Escalated conversation** (complaint): no sendable draft. The card says "Bu mesaj şikayet içeriyor, yanıtı siz yazmalısınız" (This message contains a complaint; please write the reply yourself). An optional suggestion can be inserted into the editor; sending it counts as the owner's own reply.
5. The owner replies directly in the Instagram app instead → the draft becomes *Geçersiz (yanıtlandı)* (Superseded, replied in Instagram) once the echo arrives.

**Edge cases:**
- The customer writes again while a draft awaits approval → the draft is superseded, a new draft covers all unanswered messages, and the old approval is cancelled. The card says "Yeni mesaj geldi, taslak güncellendi".
- The approval is tapped twice (double tap, two devices) → the second tap shows "Bu onay zaten verildi" with no second send.
- The window closes before approval → the draft is *Süresi doldu* with the explanation "Instagram 24 saat sonra yanıt göndermeye izin vermiyor. Instagram uygulamasından yanıtlayabilirsiniz." (Instagram doesn't allow replies after 24 h via apps; you can reply in the Instagram app.)
- The edited text contains a price that differs from the fact → inline validation: "Bu tutar doğrulanmış fiyatlarla eşleşmiyor" with options to correct it or to update the fact (opens the fact update confirmation).
- A customer message in Russian → needs human with reason "Desteklenmeyen dil".
- The customer sends only a photo → "Görsel alındı, yanıtı siz vermelisiniz" (Image received; you should reply).

**Failure states:** send failed (permission revoked) → red badge with "Instagram bağlantısı yenilenmeli" and a reconnect action. Outcome unknown → "Gönderilip gönderilmediği kontrol ediliyor…" for up to 10 minutes, then "Gönderim doğrulanamadı. Lütfen Instagram'da kontrol edin." (Could not confirm sending; please check Instagram.) It is never shown as sent.

### J3: Price change by natural language [UC-10, UC-11]
1. The owner types in the command bar: "Aylık üyelik artık 7.000 TL".
2. Status "Anlıyorum…" (interpreting; ~1 s with fake, a few seconds with a real LLM).
3. **Confirmation card:** "Aylık üyelik fiyatı: 6.000 ₺ → **7.000 ₺**. Bu değişiklik gelecekteki yanıtlarda kullanılacak." Below: **Etkilenenler (Affected):** "1 zamanlanmış gönderi beklemeye alınacak, 1 onaylı yanıt incelenmeli, 1 bekleyen taslak yeniden oluşturulacak." Buttons: **Onayla** (Confirm), **Vazgeç** (Cancel).
4. After confirming: "Güncellendi". The affected items appear as attention cards with direct links. The scheduled post shows *Beklemede: fiyat değişti* (On hold: price changed) with actions "Düzenle" or "Olduğu gibi onayla" (approve as is) or "İptal et".
5. Next customer price question → the draft uses 7.000 ₺.

**Edge cases:** an ambiguous fact ("fiyat artık 7000", but the workspace has monthly, 3-month and student prices) → clarification chips listing the three price facts. "7.000" in an `en` workspace → the confirmation shows the formatted value explicitly. The same value as current → "Zaten 7.000 ₺" with no change. A staff member issues the command → the result is a **candidate** awaiting owner verification, and the fact becomes contested ([business-knowledge.md §5](../architecture/business-knowledge.md)). The confirmation is not answered within 30 minutes → expired, nothing changed.
**Failure:** interpretation fails → "Anlayamadım. Şöyle deneyebilirsiniz: …" with examples; nothing changes.

### J4: Create and schedule a Story [UC-13, UC-14, UC-16]
1. The command "Deneme dersi için bir story hazırla" (or Content → "Taslak iste").
2. Status *Hazırlanıyor…* → content draft with: format Story, **overlay text suggestions** ("İlk deneme dersi ücretsiz!" only if a verified promotion fact exists; otherwise neutral copy), visual concept notes, facts used, and an empty media slot: "Story için 9:16 bir görsel ekleyin. Instagram'da story metni görselin üzerinde olmalıdır." (Add a 9:16 image; story text must be on the image.)
3. The owner uploads a photo (camera roll). Validation runs: PNG converted, aspect ratio warning if not 9:16.
4. **Approve & schedule:** date and time picker in the workspace timezone ("Bugün 19:00, İstanbul saati"). Summary of exactly what will be published. **Onayla ve zamanla**.
5. The card shows *Zamanlandı · Bugün 19:00*. At 19:00 → *Yayınlanıyor* → *Yayınlandı* with a link to the post (in mock: a simulated permalink, badge SİMÜLASYON).

**Edge cases:** the time is in the past → validation error. The schedule is more than 60 days ahead → validation error (configurable). No image → cannot submit a story. Staff submits → pending approval for owner/manager. The account is disconnected before the scheduled time → *Beklemede: hesap bağlantısı yok* (On hold: account not connected). Edited after approval → back to draft, and approval is required again.
**Failure states:** publish failed (transient) → *Tekrar denenecek 19:05* (will retry 19:05). Still failing after the deadline (default 6 h) → *Başarısız* with the reason and "Düzenle ve yeniden gönder". Invalid media → failure with "Görsel Instagram tarafından kabul edilmedi" and a fix suggestion.

### J5: "What happened today?" [UC-12, UC-17, UC-18]
- The command "Bugün kaç DM geldi?" → answer card: "Bugün 14 mesaj, 9 konuşma. 6 yanıt gönderildi (2 otomatik, 4 onaylı), 2 konuşma sizi bekliyor." with links. Simulated data is labelled.
- **Daily report** (also generated at 20:00 workspace time, notification "Günlük rapor hazır"): sections Messages, Approvals, Content, Knowledge changes, Problems. Every number links to the filtered list behind it.
- **Activity:** chronological feed in plain language ("Sistem, Ayşe'ye fiyat yanıtı taslağı hazırladı", "Selin taslağı onayladı", "Yanıt gönderildi (simülasyon)").

### J6: Something went wrong [UC-15, UC-22]
- **Reauth needed:** red banner on Home "Instagram bağlantınız yenilenmeli. Yenilenene kadar yanıt gönderilemez ve gönderiler yayınlanamaz." Button: *Bağlantıyı yenile*. Scheduled posts due during the outage go *Beklemede*.
- **Provider outage / rate limited:** amber banner "Instagram'a şu an ulaşılamıyor, otomatik olarak tekrar denenecek." Status per item. No user action needed unless deadlines pass.
- **"Dünkü gönderi neden başarısız oldu?"** → command answer from the operation's error code: what happened, when, and what to do.

### J7: Staff member [P3]
- Sees the inbox and can write manual replies and request drafts. Approving AI drafts requires the `reply.approve` permission (owner/manager by default).
- Proposing a price change → becomes a candidate. The owner sees "Elif fiyat değişikliği önerdi" in Suggestions.
- Cannot change automation settings, connections or members.

### J8: Developer / demo walkthrough [UC-19]
Scripted in [local-development.md §6](../operations/local-development.md): seed → log in as demo owner → simulate messages from the Dev panel → approve → change price → create and schedule a story 2 minutes ahead (or use "run due jobs now") → inject failure → view the report → reset.

### J9: Global self-service (later, S4)
Sign up → workspace basics → paste or import → verify → connect Instagram → test question. Same screens without the founder; the readiness checklist does the guiding.

## 3. Cross-cutting UX rules

1. **Explicit actions only for consequential steps.** Approve, publish, send and confirm are distinct buttons with a verb. No swipe-to-approve. No approval from notifications without opening the detail (web). Messenger buttons in Phase 9 carry the full summary in the message.
2. **Show sources.** Wherever a fact value appears in a draft, it can be traced to its fact and version.
3. **Never block on AI.** Every AI-dependent screen has a manual path (write the reply yourself, enter facts manually, write the caption yourself).
4. **Time is always in the workspace timezone** and labelled when ambiguous ("İstanbul saati").
5. **Errors say what happened and what to do**, in the user's language, from error codes ([observability.md §4](../architecture/observability.md)).
6. **Empty states teach:** "Henüz mesaj yok. Demo'da 'Müşteri mesajı simüle et' ile deneyebilirsiniz."
7. **Loading and async states are explicit:** *Anlıyorum…*, *Hazırlanıyor…*, *Kontrol ediliyor…*, each with a timeout message if it runs too long (> 30 s: "Beklenenden uzun sürüyor").
