# Türkiye Pazarı: 30 Günde İlk 10–15 Pilot ve Ödeme Yapan Müşteri Kazanım Planı

**Amaç:** AgentNest için reklam bütçesi harcamadan, sahada birebir temas (Bucak, Burdur, Antalya) ve hedefli Instagram/WhatsApp ulaşımı ile **30 gün içinde 10–15 aktif pilot işletme** kazanmak ve bunların **en az 5'ini ücretli "Kurucu İşletme" (990 ₺/ay) aboneliğine** dönüştürmek.

**İlgili Belgeler:**
- Fiyatlandırma ve Birim Ekonomi: [pricing-and-unit-economics.md](pricing-and-unit-economics.md)
- Pilot Kurulum Rehberi: [pilot-onboarding-checklist.md](../operations/pilot-onboarding-checklist.md)
- Hedef Personalar: [personas-and-use-cases.md](personas-and-use-cases.md)

---

## 1. Temel Strateji: "Yazılım Satma, Kendi İşletmelerini Canlı Göster"

Küçük işletme sahipleri (pilates stüdyoları, güzellik merkezleri, spor salonları, butikler, diyetisyen/klinikler) "yapay zekâ asistanı" veya "otomasyon paneli" satın almak istemezler. Onların iki temel korkusu ve bir büyük acısı vardır:
- **Acı:** Ders/seans arasında veya gece 23:45'te gelen *"Fiyat nedir? Deneme dersi var mı?"* mesajlarına geç dönüp müşteri kaybetmek.
- **Korku 1:** *"Bot müşterime yanlış fiyat söylerse veya saçmalarsa rezil olurum."*
- **Korku 2:** *"Instagram şifremi verirsem hesabım çalınır veya kapanır."*

### Altın Kural: "Önce Kişiselleştirilmiş Demo, Sonra Ziyaret"
Bir işletmeye gitmeden veya mesaj atmadan önce **3 dakikanızı** ayırıp:
1. İşletmenin Instagram profilindeki biyografiyi, öne çıkan hikayelerdeki (Highlights) fiyat/saat bilgilerini veya adresini kopyalayın.
2. Kendi telefonunuzdaki AgentNest demo ortamında ([local-development.md](../operations/local-development.md)) **o işletmenin adıyla bir çalışma alanı (Workspace)** açıp gerçek bilgilerini yapıştırın (`extract_fact_candidates`).
3. İçeride işletmeye özel 2 gerçekçi müşteri DM'i simüle edin.
4. İşletme sahibine **"Size bir yazılım anlatmaya gelmedim, stüdyonuz için hazırladığım asistanı telefonumda 60 saniyede göstermeye geldim"** deyin.

---

## 2. Hedef Müşteri Segmentleri (Öncelik Sırasıyla)

İlk 30 günde her sektöre dağılmak yerine, **DM başına gelir değeri yüksek** ve **soruları standart** olan 3 dikeye odaklanın:

| Öncelik | Segment | Neden En Hızlı Dönüşür? | Tek Müşteri Değeri (İşletme İçin) | En Sık Sorulan 4 Soru |
|---|---|---|---|---|
| **1. Öncelik** | **Reformer Pilates, Yoga & PT Stüdyoları** | Eğitmen ders verirken telefona bakamaz; yanıt gecikince müşteri başka stüdyoya yazar. | 3.500 ₺ – 7.500 ₺ / ay | Aylık paket fiyatı, deneme dersi, saatler, adres/otopark |
| **2. Öncelik** | **Güzellik Salonları, Lazer & Cilt Bakım Merkezleri** | Günde 30–100 arası rutin fiyat/randevu DM'i alırlar, personel yetişemez. | 2.000 ₺ – 10.000 ₺ / paket | İşlem fiyatları, kampanya detayı, randevu müsaitliği, konum |
| **3. Öncelik** | **Butik Spor Salonları, Diyetisyenler & Fizyoterapi** | Kampanya dönemlerinde yoğun mesaj trafiği ve fiyat güncellemesi yaşarlar. | 3.000 ₺ – 8.000 ₺ / paket | Üyelik ücretleri, öğrenci indirimi, çalışma saatleri |

---

## 3. Hafta Hafta 30 Günlük Uygulama Planı

### 1. Hafta (Gün 1–7): "Gizli Müşteri Testi" ve 60 Hedef İşletme Listesi

**Hedef:** 60 işletmelik nitelikli liste çıkarmak, mevcut DM yanıt sürelerini ölçmek ve ilk 15 işletmeyle yüz yüze / WhatsApp temasını başlatmak.

* **Gün 1–2: 60 İşletmelik "Sıcak Liste" Hazırlığı**
  * **Yerel Saha (Bucak & Burdur — 20 İşletme):** Haritalar ve Instagram konum etiketlerinden aktif paylaşım yapan spor/pilates stüdyoları, güzellik salonları, popüler kafeler ve butikler.
  * **Yakın Bölge Saha (Antalya: Konyaaltı, Lara, Muratpaşa — 25 İşletme):** Yüksek DM trafiği olan reformer stüdyoları, estetik/güzellik merkezleri ve turizm bağlantılı hizmet işletmeleri.
  * **Uzaktan / Online (Türkiye Geneli — 15 İşletme):** Instagram'da gönderilerinin altında sürekli *"Fiyat nedir?"*, *"DM bakar mısınız?"* yorumları biriken aktif stüdyolar.
* **Gün 2–3: "Gece 22:30 DM Testi" (En Güçlü Satış Kanıtı)**
  * Listedeki işletmelere akşam 21:30–23:00 arasında normal bir müşteri gibi gerçek bir soru sorun (*"Merhaba, haftada 2 gün reformer pilates fiyatınız nedir ve deneme dersiniz var mı?"*).
  * Kaç saat sonra döndüklerini, eksik bilgi verip vermediklerini tabloya kaydedin. *(Örn: "Sabah 11:20'de döndü — 13 saat gecikme").*
* **Gün 4–5: İlk 10 İşletme İçin Telefonunuzda Kişiselleştirilmiş Demo Hazırlığı**
  * Ziyaret edeceğiniz ilk 10 işletmenin çalışma saatlerini ve adreslerini AgentNest'e yükleyin.
* **Gün 6–7: Bucak & Burdur'da İlk 10 Yüz Yüze Ziyaret**
  * İşletmelerin en sakin olduğu saatlerde (**10:30–12:00** veya **14:00–16:30** arası; asla akşam 18:00 ders yoğunluğunda değil) çat kapı veya kısa telefon aramasıyla ziyaret edin.
  * **1. Hafta Sonu Çıktısı:** 15 görüşme, **3–4 canlı pilot kurulum**.

---

### 2. Hafta (Gün 8–14): İlk Pilot Kurulumları ve Antalya Sahası

**Hedef:** İlk 3–4 pilotu canlıya almak ([pilot-onboarding-checklist.md](../operations/pilot-onboarding-checklist.md)), ilk başarı verilerini toplamak ve Antalya'da 15 işletmeyi ziyaret etmek.

* **Gün 8–9: İlk Pilotların 30 Dakikalık Birlikte Kurulumu**
  * İşletme sahibiyle yan yana oturup gerçek fiyatlarını doğrulayın (`Verified Facts`).
  * Resmi Instagram giriş ekranıyla hesabı bağlayın (Meta Standard Access Tester akışı).
  * Kendi telefonunuzdan işletmeye canlı DM atıp AgentNest'in 5 saniyede hazırladığı doğru fiyatlı taslağı işletme sahibine **tek dokunuşla onaylatın**.
* **Gün 10–12: Antalya Saha Ziyaretleri (15 İşletme) + WhatsApp Video Demo**
  * Antalya'da aynı sokak/mahalle üzerindeki (örn. Lara Şirinyalı veya Konyaaltı Gürsu) 8–10 pilates ve güzellik merkezini aynı gün içinde ziyaret edin.
  * Ziyaret edemediğiniz işletmelere **60 saniyelik kişiselleştirilmiş ekran kaydı (Loom / WhatsApp Video)** gönderin (Şablon aşağıda).
* **Gün 13–14: İlk Pilotların 1. Hafta Kontrolü**
  * İlk hafta kurulan işletmelere akşam 21:00'de giden **Günlük Özeti** birlikte inceleyin (*"Bakın bu hafta 42 mesaj gelmiş, 11'i gece saatlerinde yanıtlanmış"*).
  * Rutin saat/adres soruları için **Otomatik Yanıt (Auto-send)** özelliğini açmayı teklif edin.
  * **2. Hafta Sonu Çıktısı:** Toplam **7–8 aktif pilot işletme**.

---

### 3. Hafta (Gün 15–21): "Referans Etkisi" ve Vaka Analizi ile Ölçekleme

**Hedef:** İlk pilotların memnuniyetini kullanarak tanıdık işletmelere referansla girmek ve toplam pilot sayısını **12–15'e** tamamlamak.

* **Gün 15–17: İlk Pilotlardan 1'er Referans İsteme ("Esnaf Komşuluğu")**
  * Türkiye'de bir pilates eğitmeni veya güzellik salonu sahibi, başka ilçedeki/şehirdeki en az 3 meslektaşını tanır.
  * Memnun olan pilota şu teklifi yapın: *"Sizin gibi yoğun olan 1 arkadaşınıza bizi önerirseniz ve o da pilota katılırsa, sizin ilk ücretli ayınızı hediye ediyoruz."*
* **Gün 18–19: "Öncesi / Sonrası" Gerçek Vaka Paylaşımı**
  * İlk iki haftada yakalanan gerçek bir senaryoyu (örneğin gece 23:40'ta gelen fiyat sorusunun doğrulanmış kartla yanıtlanması ve müşterinin ertesi gün deneme dersine gelmesi) tek sayfalık görsel/video haline getirin.
* **Gün 20–21: Kalan Kontenjan Kurgusu ile Takip (Follow-up)**
  * İlk 2 haftada *"Düşünelim"* diyen işletmelere mesaj atın: *"15 işletmelik ücretsiz pilot kontenjanımızda son 3 yer kaldı, bu hafta kurulum yaptığımız işletmelere 2.500 ₺ kurulum ücreti almıyoruz."*
  * **3. Hafta Sonu Çıktısı:** Toplam **12–15 aktif pilot işletme**.

---

### 4. Hafta (Gün 22–30): Ücretli Aboneliğe Dönüşüm ("Kurucu İşletme" Kapanışı)

**Hedef:** Aktif kullanan 12–15 pilot işletmeden **en az 5–8 tanesini** ücretli aboneye dönüştürmek.

* **Gün 22–25: "Değer Karnesi" Görüşmesi (Yüz Yüze veya Görüntülü)**
  * Her pilot işletme sahibine son 2–3 haftanın gerçek kayıtlarını ([workflows.md](../architecture/workflows.md)) çıkarıp gösterin:
    * *"Son 21 günde stüdyonuza **184 Instagram DM'i** geldi."*
    * *"Bunların **63 tanesi akşam 20:00'den sonra** geldi ve eskiden sabaha kalıyordu."*
    * *"Hiçbir müşteriye yanlış fiyat verilmedi; toplam **~12 saatlik** yazışma yükünüzü devraldık."*
* **Gün 26–28: "Kurucu İşletme" Fiyat Teklifi ve Tahsilat**
  * Fiyatı doğrudan yeni müşteri kazancıyla kıyaslayın (Kapanış konuşması aşağıda).
  * İlk müşteriler için ödeme sürtünmesini sıfırlayın: **EFT/Havale + E-Arşiv Fatura** veya **iyzico/PayTR Ödeme Linki**.
* **Gün 29–30: Referans Videoları ve 2. Ay Büyüme Planı**
  * Ödeme yapan ilk 5 işletmeden 30 saniyelik samimi bir telefon videosu veya yazılı yorum alın, [landing/](../../landing/) sayfasına ekleyin.

---

## 4. Sahada ve WhatsApp'ta Kullanılacak Hazır Konuşma Metinleri (Scripts)

### A. Yüz Yüze Çat Kapı Ziyaret Metni (Stüdyo / Salon Sahibiyle 60 Saniye)

> **Siz:** "Merhaba [İsim] Hanım/Bey, vaktinizi almayacağım, sadece 60 saniye. Ben [Adınız], burada Burdur/Antalya'daki işletmeler için Instagram DM'lerini yöneten bir sistem geliştirdik. Dün akşam profilinize baktım; çok güzel paylaşımlarınız var ama ders/işlem arasındayken gelen *'Aylık ne kadar? Deneme dersi var mı?'* mesajlarına yetişmek çok zor oluyor.
>
> Size bir şey satmaya gelmedim. Gelmeden önce sizin Instagram profilinizdeki saat ve bilgileri sisteme yükledim. Bakın telefonumda sizin stüdyonuzun bir kopyası var. Şimdi müşteriniz gece 23:45'te *'Aylık üyelik ne kadar, hamile pilatesi var mı?'* diye yazsa ne oluyor, 15 saniyede göstereyim mi?"
>
> *(Telefonu uzatıp canlı olarak doğrulanmış fiyat kartını, uydurmama kuralını ve tek tuşla onayı gösterirsiniz).*
>
> **Kapanış:** "Şu an bölgemizdeki seçilmiş **10 işletmeyle 30 günlük tamamen ücretsiz bir pilot** yapıyoruz. Kart bilgisi veya taahhüt yok, Instagram şifrenizi de bize vermiyorsunuz. Yarın 25 dakikanız varsa çayınızı içerken gerçek hesabınıza kuralım, 1 ay kendi müşterilerinizle deneyin. Memnun kalmazsanız tek tuşla kaldırırız. Yarın saat 11:00 mi uygun olur, 14:00 mü?"

---

### B. Instagram DM / WhatsApp İlk Ulaşım Mesajı ("60 Saniyelik Video" Tekniği)

Soğuk metin mesajları okunmaz; ancak işletmenin kendi Instagram profilinin göründüğü 45 saniyelik bir video %70+ yanıt alır:

> **Mesaj:**
> "Merhaba [İşletme Adı] ekibi 👋
> Dün akşam saat 22:30'da sayfanıza fiyat soran bir müşterinin gözünden baktım. Seans yoğunluğunuzda her gün aynı fiyat, saat ve konum sorularını tek tek yazmanın ne kadar yorucu olduğunu biliyorum.
>
> Sizin profilinizdeki bilgilerle **[İşletme Adı]'na özel** asla fiyat uydurmayan, fiyat değişince eski story'leri otomatik durduran bir Instagram asistanı hazırladım. Nasıl çalıştığını **45 saniyelik şu videoda** kendi sayfanız üzerinden gösterdim: [Video/Loom Linki]
>
> Şu an sadece 10 stüdyo ile **30 gün ücretsiz pilot** yapıyoruz ve kurulumu 30 dakikada birlikte tamamlıyoruz. İncelemek isterseniz bu hafta hangi gün 15 dakikanız olur?"

---

### C. En Sık Gelen 4 İtiraza Net Yanıtlar

1. **"Ya müşterime yanlış bir şey yazarsa, olmayan indirim sözü verirse?"**
   * **Yanıt:** *"En büyük farkımız tam olarak bu. Sıradan yapay zekalar tahmin yürütür; bizim sistemimiz ise sadece sizin onayladığınız bilgi kartlarını kullanır. Kayıtlı olmayan bir soru gelirse (örneğin 'Bel fıtığım var hangi hoca uygun?') asla cevap uydurmaz, mesajı doğrudan size devreder. Üstelik ilk 2 hafta siz onaylamadan hiçbir mesajı tek başına göndermez."*
2. **"Instagram şifremi vermem gerekiyor mu? Hesabım zarar görür mü?"**
   * **Yanıt:** *"Kesinlikle hayır. Şifrenizi bize hiç söylemiyorsunuz; kendi telefonunuzdan Instagram'ın resmi giriş ekranıyla bağlanıyorsunuz. İstediğiniz saniye tek dokunuşla bağlantıyı kesebilirsiniz."*
3. **"Bizim işimiz butik, müşteriler samimi ilgi bekliyor, robot gibi dursun istemem."**
   * **Yanıt:** *"Çok haklısınız. Zaten şikayet, pazarlık veya özel sağlık sorularına sistem dokunmaz, size haber verir. Sistem sadece günde 20 kere tekrar ettiğiniz 'Saat kaçta açıksınız, adres nerede, aylık paket ne kadar?' sorularını sizin konuşma dilinizle ve 'Ayşe Hanım' diye hitap ederek hazırlar; siz de tek dokunuşla onaylarsınız."*
4. **"Şu an bütçemiz yok / Pahalı gelir."**
   * **Yanıt:** *"İlk 30 gün tamamen ücretsiz ve hiçbir kart bilgisi ya da sözleşme istemiyoruz. 30 günün sonunda ise normalde 1.490 ₺ olan paketimiz, ilk 10 pilot işletmemize özel 1 yıl boyunca **ayda sadece 990 ₺** (ve 2.500 ₺ kurulum ücreti de tamamen ücretsiz). Yani ayda **gece gelen tek bir müşteriyi** bile kaçırmamanızı sağlasa, kendi parasını 5 katıyla çıkarıyor."*

---

### D. 4. Hafta Ücretli Aboneliğe Dönüşüm (Kapanış) Konuşması

> **Siz:** "[İsim] Hanım, 3 haftalık pilot sürecimiz harika geçti. Kayıtlara baktım; bu ay **142 müşteri mesajı** gelmiş, bunların **48'i mesai saatleri dışında** gelmiş ve anında yanıtlanmış.
>
> Önümüzdeki haftadan itibaren normalde aylık **1.490 ₺ + 2.500 ₺ kurulum** olan sistemimizi, ilk pilot işletmelerimizden biri olduğunuz için kurulum ücreti almadan, 12 ay sabit fiyat garantisiyle **aylık 990 ₺ (+ KDV)** olarak devam ettirebiliyoruz.
>
> Sizin tek bir aylık üyeliğiniz **6.000 ₺**; yani asistanımız ayda gece yazan **tek bir kişiyi bile** kaçırmamanızı sağlasa, 6 aylık abonelik ücretini tek günde çıkarıyor. Faturalandırmayı aylık mı tanımlayalım, yoksa 2 ay hediyeli yıllık (9.900 ₺) olarak mı sabitleyelim?"

---

## 5. 30 Günlük Dönüşüm Hunisi (Hedeflenen Sayılar ve KPI'lar)

| Aşama | Hedef Sayı | Dönüşüm Oranı | Nasıl Takip Edilir? |
|---|---|---|---|
| **1. Listelenen Hedef İşletme** | **60 İşletme** | %100 | Bucak/Burdur (20), Antalya (25), Online (15) |
| **2. Birebir Ziyaret / Özel Video Gönderimi** | **45 İşletme** | %75 | Yüz yüze ziyaret + WhatsApp 45 sn demo videosu |
| **3. Canlı Demo Gösterimi (60 sn)** | **25 İşletme** | %55 | Telefon üzerinde işletmenin kendi bilgileriyle canlı simülasyon |
| **4. 30 Günlük Ücretsiz Pilota Başlayan** | **12 – 15 İşletme** | %50 | 30 dk birlikte kurulum + gerçek Instagram bağlantısı ([pilot-onboarding-checklist.md](../operations/pilot-onboarding-checklist.md)) |
| **5. Ücretli "Kurucu İşletme"ye Dönüşen** | **5 – 8 İşletme** | %45 – %55 | 990 ₺/ay (Kurucu) veya 1.490 ₺ – 2.490 ₺/ay (Standart) |

> [!TIP]
> **Finansal Sonuç:** İlk 30 günün sonunda sadece **5 pilot işletmenin** 990 ₺ – 1.490 ₺ bandında ücretli aboneliğe geçmesi bile AgentNest'in tüm sunucu, veritabanı, yedekleme ve OpenAI (`gpt-6-luna`) maliyetlerini **fazlasıyla karşılayıp kâra geçirir** ([pricing-and-unit-economics.md §7](pricing-and-unit-economics.md)).
