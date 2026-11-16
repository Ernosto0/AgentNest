# Demo script: "it never invents a price" (price-change hold)

**Purpose:** a 10 to 15 minute walk for an owner or a pilot partner. It starts with the strongest proof (change a price once, and everything that quoted the old one stops by itself), then shows where each number in a reply comes from, the daily guarantee line, the practice chat and phone notifications.
**Status:** written from the code paths and the existing E2E specs (`frontend/e2e/scenario-c.spec.ts` "fact change holds the scheduled post", `scenario-b.spec.ts` B5). The steps in Parts 1 to 4 were checked against those specs and the labels in the Turkish catalogs; **this script as a whole was not run end to end on a live stack in the session that wrote it** (see "What was and was not checked" at the end). Phone steps (Part 6) need a real device.
**Language:** the screens are Turkish by default; English labels are given where they differ in meaning. Navigation words used below: **Bugün** = Home, **Gelen kutusu** = Inbox, **İçerik** = Content, **Onaylar** = Approvals, **Daha fazla** = More.

## 0. Set up (once, 5 minutes)

Follow [local-development.md](local-development.md) §2 and §3: Postgres, migrations (`uv run alembic upgrade head`; the head is `0048`), then

```powershell
cd backend
uv run python -m app.cli seed --reset      # demo users, Gölkent Fitness & Pilates, 16 facts, yesterday's history
```

Run the API, the **worker** (drafts, sends and publishing are jobs) and `npm run dev`. Required in `.env`: `LLM_PROVIDER=fake`, `INSTAGRAM_ENABLED_PROVIDERS=mock`, `DEMO_TOOLS_ENABLED=true` (development only). Open <http://localhost:5173> at phone width (DevTools device mode 390 x 844), sign in as `owner@demo.local` with `DEMO_PASSWORD`, and choose **Gölkent Fitness & Pilates**. Do not run the E2E suite at the same time; it resets the same database.

Everything you see from the mock Instagram account carries the **SİMÜLASYON** badge. That is expected.

## 1. Before the change: the post and the reply that quote the price

**1a. A scheduled post that quotes the monthly price** (this is E2E "fact change holds the scheduled post")
1. **İçerik** → **Taslak iste**. In "Ne paylaşmak istiyorsunuz?" type `Aylık üyelik fiyatı hakkında bir gönderi` → **Taslağı hazırla** → **Taslağı aç**.
2. Wait for the caption. It contains **6.000 ₺ / ay**. The price came from the fact, not from the model.
3. Attach `backend/app/demo/media/feed-sample.jpg` (the file input; wait for the preview and "Kaydedildi").
4. **Zamanla**: set **Tarih** and **Saat** (workspace time zone, Europe/Istanbul) about three hours ahead → **Onayla ve zamanla**. The badge reads **Zamanlandı**.

**1b. A reply draft that quotes the same price**
1. **Daha fazla** → **Geliştirici araçları** → the **Fiyat sorusu** button (customer Ayşe; the button has `data-script="price"`).
2. Wait about 8 seconds (`REPLY_DEBOUNCE_SECONDS`), then **Gelen kutusu** → **Ayşe**.
3. The draft card says "Aylık üyelik ücretimiz 6.000 ₺ / ay." and **Onay bekliyor**. Point at the list **Kullanılan bilgiler** under the text: `6.000 ₺ / ay` and **kaynak: Aylık üyelik, doğrulama tarihi …** (the day the seed verified it). Tap the green `6.000 ₺ / ay` in the text for the same source ("Kaynak: Aylık üyelik, doğrulandı …"). The list comes from the server (`facts_used`); the app computes nothing.
4. Do **not** approve it yet.

## 2. Change the price by command

1. **Bugün**. In the command bar type `Aylık üyelik artık 7.000 TL` → **Gönder**.
2. A confirmation card shows **6.000 ₺ / ay → 7.000 ₺ / ay** and a section **Etkilenecek öğeler** (affected items: the scheduled post and the waiting reply draft). Nothing has changed yet: free text never approves anything.
3. **Onayla**. The result says "Aylık üyelik güncellendi: 6.000 ₺ / ay → 7.000 ₺ / ay (sürüm 2)."

## 3. What the system did on its own

**3a. The held post.** **İçerik** → tab **Zamanlanan**: "Zamanlanmış içerik yok". Tab **Sorunlar**: the post, **Beklemede**. Open it: "Kullandığı işletme bilgisi değiştiği için beklemeye alındı." with the button **Olduğu gibi yeniden onayla**. Its publish job was cancelled; it cannot go out with the old price. Re-approving creates a new approval for the new version (the old approval cannot authorise anything).

**3b. The updated draft.** **Gelen kutusu** → **Ayşe**. The old draft was retired (reason `FACT_CHANGED`) and drafted again by the worker (a few seconds): the card now says **7.000 ₺ / ay**, and **Kullanılan bilgiler** shows `7.000 ₺ / ay` with the **new** verification date (today). A reply that was already sent is never touched.

**3c. The approval.** **Onaylar** → open **Yanıt gönderme**: the same text, with the same **Kullanılan bilgiler** list beside it. Approve with **Onayla** (or, from the conversation, **Onayla ve gönder**); the badge goes to **Gönderildi** only after the simulated send is confirmed. This is also the "first approval" that offers phone notifications (Part 6).

**3d. Telegram (optional, needs a linked bot, [local-development.md](local-development.md) §3 "Telegram Long Polling").** The approval message lists under the proposed reply: `• 7.000 ₺ / ay — kaynak: Aylık üyelik, doğrulandı 2026-…` (English: `from: Monthly membership, verified …`).

## 4. The guarantee line in the daily report

1. **Daha fazla** → **Günlük rapor** (today). At the top, the card **Uydurma bilgi yok** ("Never an invented number") shows **Gönderilen yanıt** (replies sent) and **Gönderilen doğrulanmamış değer** (unverified values sent): **0**. Both are shown even at zero. Each number comes from the stored claim-validator result of each reply that was actually sent; it is not a constant.
2. The count is above zero only when a sent reply holds a value that is not a verified fact. To show it (optional): in a conversation, write your own reply with a price, for example `Üyelik 5.000 TL` in **Yanıtınız**, and send it. You are warned ("… işletme bilgilerinizdeki doğrulanmış bir değer değil") but not blocked, because a person may write what they like. After the send is confirmed, the report shows the replies sent and, in red, **Doğrulanmamış değer içeren yanıtlar: 1**; the number opens the drill-down (`more/reports/<date>/unverified_values_sent`) with that conversation. A reply counts once, however many values it holds.
3. The same two numbers end the Telegram "Bugünkü özet" reply.

## 5. Practice chat (try it as a customer)

1. **Daha fazla** → **Asistan** → **Asistanınızı deneyin** (also the last, skippable step when creating a workspace; the route is `/w/<id>/more/agent/test`).
2. Tap a starter question such as the one about the monthly price, or type your own as a customer. The reply appears with **SİMÜLASYON**, the decision in plain words and **Kullanılan bilgiler** with the verified date.
3. Ask something it has no fact for. It will not guess a price; it explains that a person would be asked. Nothing here is sent, and none of it counts in reports (the chat is stored apart from conversations). **Baştan başla** clears it. Limits: 20 messages per hour and 60 per day per workspace.
4. Honest limits: the chat uses the legacy drafting path, not the account agent, and it draws on the same daily model budget as real replies.

## 6. Phone notifications (needs a real phone or Chrome with internet access)

1. Generate keys once: `uv run python -m app.cli generate-vapid-keys` and `uv run python -m app.cli generate-key --kind token-encryption` (for `TOKEN_ENCRYPTION_KEYS`, with `TOKEN_ENCRYPTION_ACTIVE_KEY_ID`). Put `WEB_PUSH_VAPID_PUBLIC_KEY`, `WEB_PUSH_VAPID_PRIVATE_KEY`, `WEB_PUSH_SUBJECT=mailto:you@example.com` and `TOKEN_ENCRYPTION_KEYS` in `.env`; restart the API and the worker. Without them the push card stays hidden.
2. The service worker registers in a production build, or with `VITE_ENABLE_SW=true` for `npm run dev`. Android Chrome needs HTTPS (a tunnel, [local-development.md](local-development.md) §10 and §12); an iPhone needs the app added to the Home Screen first (iOS 16.4 or later).
3. Approve something (Part 3c). The prompt **Bir şey kararınızı beklediğinde bildirim alın** appears once; **Bildirimleri aç** and allow the browser permission. (Or: **Daha fazla** → **Bağlantılar** → **Telefon bildirimleri** → **Bu cihazda aç**.)
4. Create another approval (Part 1b again). The phone shows a notification **without any customer text**; tapping it opens **Onaylar**.
5. Exact device steps for Android and iPhone are in [s04-report.md](../implementation/features-phase-1-before-first-pilot/s04-report.md) §7. **Not tested on a real device yet.**

## 7. Reset

**Daha fazla** → **Geliştirici araçları** → **Demo'yu sıfırla**, or `uv run python -m app.cli seed --reset` ([local-development.md](local-development.md) §8).

## What was and was not checked

- **Checked against code and specs:** the command phrase (`Aylık üyelik artık 7.000 TL`), the confirmation and result texts, the hold and its reason, the `price` simulator script and customer, the draft re-draft on a fact change (`inbox/impact.py`, tested by `tests/integration/inbox/test_approved_answers_and_impact.py`), the labels and routes named above (catalogs under `frontend/src/i18n/locales/tr`, `frontend/src/app/router.tsx`), and the new fact-source and report behaviour (`tests/integration/inbox/test_fact_sources.py`, `tests/integration/reporting/test_unverified_values.py`, component tests).
- **Not run live as one sequence:** the hold and the re-draft are covered by separate automated tests; no one ran this exact walk in a browser against a worker in the writing session. Step timings (8 seconds of debounce, the re-draft) depend on the worker running.
- **Needs a real device or account:** Part 6 (push on Android and iOS), Part 3d (a real Telegram bot) and the maskable icon on an Android launcher.
