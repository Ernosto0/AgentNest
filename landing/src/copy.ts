import { PRODUCT_NAME } from './brand'

export type Lang = 'tr' | 'en'

type Fact = { value: string; source: string }

export type ChatMessage = {
  from: 'owner' | 'assistant'
  text: string
  time: string
  // A story graphic the owner sends, drawn from these three lines.
  attachment?: { kicker: string; title: string; note: string }
  // The message a button reply answers; WhatsApp shows it quoted above the reply.
  quote?: string
  // Reply buttons under an assistant message.
  actions?: string[]
}

export type PostStatus = 'published' | 'scheduled' | 'held' | 'pending'

export type Copy = {
  meta: { title: string }
  nav: { waitlist: string; language: string; dark: string }
  hero: {
    kicker: string
    pilotBadge: string
    promises: [string, string, string]
    lead: string
    cta: string
    note: string
    preview: {
      dmLabel: string
      dmText: string
      factLabel: string
      factText: string
      stampLabel: string
      stampSub: string
    }
  }
  index: { label: string; links: { id: string; label: string }[] }
  comparison: {
    title: string
    body: string
    withoutLabel: string
    withLabel: string
    rows: { scenario: string; without: string; withProduct: string }[]
  }
  whatsapp: {
    title: string
    body: string
    note: string
    example: string
    online: string
    today: string
    placeholder: string
    clock: string
    chat: ChatMessage[]
    commandsTitle: string
    commandsHint: string
    commands: { ask: string; answer: string; action?: string }[]
  }
  knowledge: {
    title: string
    body: string
    extractKicker: string
    extractTitle: string
    extractBody: string
    extractSourceLabel: string
    extractSourceSample: string
    ledgerTitle: string
    verifiedBadge: string
    facts: { category: string; label: string; value: string; verifiedAt: string }[]
    missingRule: { badge: string; question: string; outcome: string }
  }
  demo: {
    title: string
    body: string
    example: string
    channel: string
    customer: string
    received: string
    message: string
    draftLabel: string
    // The draft is written around two verified facts: before, fact 1, between, fact 2, after.
    draft: [string, string, string]
    facts: [Fact, Fact]
    approve: string
    tapHint: string
    edit: string
    editClosingAlt: string
    editingBadge: string
    saveEdit: string
    stamp: string
    sent: string
    approvedAt: string
    replay: string
  }
  content: {
    title: string
    body: string
    note: string
    example: string
    heading: string
    heldReason: string
    posts: { day: string; time: string; kind: string; title: string; status: string; state: PostStatus }[]
  }
  escalate: { title: string; body: string; badge: string; items: string[]; examples: [string, string, string, string] }
  report: {
    title: string
    body: string
    example: string
    heading: string
    verifiedTag: string
    rows: [string, string][]
    footerNote: string
  }
  control: { title: string; items: { title: string; body: string }[] }
  steps: { title: string; items: { title: string; body: string }[] }
  faq: { title: string; items: { q: string; a: string }[] }
  pilot: {
    title: string
    body: string
    expectationsTitle: string
    expectations: { badge: string; title: string; detail: string }[]
    nextStepsTitle: string
    nextSteps: [string, string]
    whatsappDirectLabel: string
    whatsappPrefill: string
  }
  form: {
    dossierHeader: string
    categoryLabel: string
    categories: string[]
    business: string
    instagram: string
    instagramHint: string
    contact: string
    contactHint: string
    city: string
    consent: string
    submit: string
    sending: string
    required: string
    consentRequired: string
    sent: string
    preview: string
    failed: string
  }
  footer: { trademark: string }
}

export const copy: Record<Lang, Copy> = {
  tr: {
    meta: { title: `${PRODUCT_NAME} · Küçük işletmeler için Instagram asistanı` },
    nav: { waitlist: 'Pilot listesi', language: 'Dil', dark: 'Koyu tema' },
    hero: {
      kicker: 'Küçük işletmeler için Instagram asistanı',
      pilotBadge: 'Erken Erişim · Pilot Programı',
      promises: ['Fiyat uydurmaz.', 'Onaysız göndermez.', 'Olmayanı oldu demez.'],
      lead:
        "Müşteri DM'lerine sizin doğruladığınız bilgilerle yanıt hazırlar, paylaşımlarınızı planlar ve gün sonunda ne olduğunu anlatır. Siz hepsini WhatsApp'tan yönetir, önemli olanı tek dokunuşla onaylarsınız.",
      cta: 'Pilot listesine katılın',
      note: 'Kurulumu sizinle birlikte, 30 dakikada yapıyoruz.',
      preview: {
        dmLabel: '1 · Gelen Instagram DM (23:47)',
        dmText: '“Merhaba, aylık üyelik ne kadar? Deneme dersi var mı?”',
        factLabel: '2 · Doğrulanan Bilgi Kaynağı',
        factText: '6.000 ₺ (Aylık üyelik) · Ücretsiz (Deneme dersi)',
        stampLabel: '3 · WhatsApp’tan Tek Dokunuş',
        stampSub: 'ONAYLANDI · 23:48',
      },
    },
    index: {
      label: 'Bu sayfada',
      links: [
        { id: 'karsilastirma', label: 'Neden farklı' },
        { id: 'whatsapp', label: 'WhatsApp’tan yönetim' },
        { id: 'bilgi', label: 'Bilgi kaynağı' },
        { id: 'dm', label: 'Müşteri mesajları' },
        { id: 'icerik', label: 'Paylaşımlar' },
        { id: 'kontrol', label: 'Kontrol sizde' },
        { id: 'sss', label: 'Sorular' },
      ],
    },
    comparison: {
      title: 'Ders arasında DM yetiştirmeye çalışmayın.',
      body:
        'Her gün aynı fiyat, saat ve adres sorularını yanıtlamak zaman alır; sıradan bir bot kurmak ise müşteriye yanlış bilgi verme riski taşır. İkisinin arasında güvenilir bir yol var.',
      withoutLabel: 'Bugünkü durum',
      withLabel: `${PRODUCT_NAME} ile`,
      rows: [
        {
          scenario: 'Gece 23:45’te gelen “Aylık ne kadar?” sorusu',
          without:
            'Ders yorgunluğuyla geç görülür ya da sabaha kalır. Müşteri yanıt beklerken başka bir stüdyoya yazar.',
          withProduct:
            'Doğrulanmış fiyat ve deneme dersi bilgisiyle taslak anında hazırlanır; seçiminize göre tek dokunuşla ya da otomatik yanıtlanır.',
        },
        {
          scenario: '“Ya müşterime yanlış fiyat söylerse?” endişesi',
          without:
            'Sıradan yapay zekâ araçları bilmediği detayı tahmin eder, olmayan indirimi vaat eder veya pazarlığa girer.',
          withProduct:
            'Yalnızca sizin onayladığınız bilgi kartlarını kullanır. Kayıtlı olmayan bir soru gelirse tahmin yürütmez, mesajı size devreder.',
        },
        {
          scenario: 'Fiyat değiştiğinde unutulan eski paylaşımlar',
          without:
            'Üyelik fiyatı güncellenir ama önceden planlanan Cuma story’si eski fiyatla yayınlanır; müşteriye mahcup olunur.',
          withProduct:
            'WhatsApp’tan yeni fiyatı yazdığınız an, eski fiyatı içeren tüm planlı paylaşımlar kendiliğinden beklemeye alınır.',
        },
      ],
    },
    whatsapp: {
      title: 'WhatsApp’tan yönetin.',
      body:
        'Yeni bir uygulama öğrenmenize gerek yok. Fiyat değişikliğini yazın, bir fotoğraf gönderin, günün özetini sorun. Önemli her işlem için size butonlu bir onay gelir.',
      note:
        '“Tamam” yazmak hiçbir şeyi onaylamaz. Her onay tek bir işleme bağlıdır ve bir süre sonra geçersiz olur. İsterseniz Telegram’dan ya da telefonunuzdaki web uygulamasından da yönetebilirsiniz.',
      example: 'Örnek ekran',
      online: 'çevrimiçi',
      today: 'Bugün',
      placeholder: 'Mesaj',
      clock: '09:14',
      chat: [
        { from: 'owner', text: 'Aylık üyelik artık 7.000 TL', time: '09:12' },
        {
          from: 'assistant',
          text: 'Aylık üyelik fiyatını 6.000 ₺ yerine 7.000 ₺ yapayım mı?',
          time: '09:12',
          actions: ['Evet, güncelle', 'Vazgeç'],
        },
        {
          from: 'owner',
          quote: 'Aylık üyelik fiyatını 6.000 ₺ yerine 7.000 ₺ yapayım mı?',
          text: 'Evet, güncelle',
          time: '09:13',
        },
        {
          from: 'assistant',
          text: 'Güncellendi. Eski fiyatı içeren Cuma 19:00 story’sini beklemeye aldım.',
          time: '09:13',
        },
        {
          from: 'owner',
          attachment: { kicker: 'Reformer Pilates', title: 'Deneme dersi', note: 'ücretsiz' },
          text: 'Bunu yarın 19:00’da story olarak paylaş',
          time: '09:14',
        },
        {
          from: 'assistant',
          text: 'Story yarın 19:00 için hazır. Onaylıyor musunuz?',
          time: '09:14',
          actions: ['Onayla', 'Saati değiştir'],
        },
      ],
      commandsTitle: 'Başka neler yazabilirsiniz',
      commandsHint: 'WhatsApp ekranında görmek için bir komuta dokunun',
      commands: [
        { ask: 'Bugün kaç DM geldi?', answer: '14 mesaj geldi. 11’i yanıtlandı, 2’si size iletildi, 1’i yanıt bekliyor.' },
        {
          ask: 'Deneme dersi için bir story hazırla.',
          answer: 'Taslak hazır. İçindeki fiyat ve tarih doğrulandı, onayınızı bekliyor.',
          action: 'Taslağı gör',
        },
        { ask: 'Yanıtlar biraz daha samimi olsun.', answer: 'Yanıt tonu güncellendi. Bundan sonraki taslaklarda geçerli.' },
        { ask: 'Onay bekleyen ne var?', answer: '2 yanıt ve 1 paylaşım onayınızı bekliyor.' },
        {
          ask: 'Dünkü paylaşım neden yayınlanmadı?',
          answer: 'Instagram görseli kabul etmedi, çünkü oranı 9:16 değildi. Yeni bir görsel gönderirseniz yeniden planlarım.',
        },
        { ask: 'Yarınki paylaşımı iptal et.', answer: 'Yarın 19:00 story’sini iptal edeyim mi?', action: 'İptal et' },
      ],
    },
    knowledge: {
      title: 'İşletmenizi nereden tanıyor?',
      body:
        'Karmaşık tablolar veya teknik paneller doldurmazsınız. Mevcut fiyat listenizi ya da Instagram biyografinizi yapıştırırsınız; bilgileri tek tek ayıklar, siz yalnızca doğrularsınız.',
      extractKicker: 'Adım 1 · Hızlı aktarım',
      extractTitle: 'Mevcut metninizi olduğu gibi yapıştırın.',
      extractBody:
        'WhatsApp’ta müşterilere gönderdiğiniz hazır fiyat mesajını veya profil yazınızı verin; içindeki fiyat, saat ve kampanyaları otomatik olarak bilgi kartlarına dönüştürsün.',
      extractSourceLabel: 'Yapıştırılan metin örneği',
      extractSourceSample:
        'Reformer Pilates Stüdyosu · Hafta içi 08:00-21:00 · Aylık üyelik (haftada 2 ders) 6.000 TL. İlk deneme dersimiz ücretsizdir. Adres: Bahçelievler Mah. No: 12',
      ledgerTitle: 'Adım 2 · Doğrulanmış İşletme Kartınız',
      verifiedBadge: 'Doğrulandı',
      facts: [
        {
          category: 'Fiyatlar',
          label: 'Aylık üyelik (Haftada 2)',
          value: '6.000 ₺',
          verifiedAt: '12 Ekim’de doğrulandı',
        },
        {
          category: 'Kampanyalar',
          label: 'İlk deneme dersi',
          value: 'Ücretsiz',
          verifiedAt: '3 Ekim’de doğrulandı',
        },
        {
          category: 'Saatler',
          label: 'Hafta içi çalışma saatleri',
          value: '08:00 – 21:00',
          verifiedAt: '1 Ekim’de doğrulandı',
        },
        {
          category: 'Adres',
          label: 'Stüdyo konumu',
          value: 'Bahçelievler Mah. No: 12',
          verifiedAt: '1 Ekim’de doğrulandı',
        },
      ],
      missingRule: {
        badge: 'Kayıtlı bilgi yoksa',
        question: 'Örnek müşteri sorusu: “Hamile pilatesi dersiniz var mı?”',
        outcome: 'Kartlarda bu bilgi yoksa asla uydurmaz. Yanıt taslağı üretmez, soruyu doğrudan size iletir.',
      },
    },
    demo: {
      title: 'Her fiyatın bir kaynağı var.',
      body:
        'Taslaktaki her fiyat, saat ve kampanya, sizin girip doğruladığınız bir bilgiden gelir ve kaynağı altında yazar. Bir bilgi eksikse tahmin etmez, size sorar.',
      example: 'Örnek ekran',
      channel: 'Instagram',
      customer: 'ayse.yilmaz',
      received: '23:47',
      message: 'Merhaba, aylık üyelik ne kadar? Deneme dersi var mı?',
      draftLabel: 'Taslak yanıt',
      draft: ['Merhaba Ayşe Hanım, aylık üyeliğimiz ', '. İlk deneme dersiniz ', '. Size uygun bir gün ayarlayalım mı?'],
      facts: [
        { value: '6.000 ₺', source: 'Aylık üyelik · Fiyatlar · 12 Ekim’de doğrulandı' },
        { value: 'ücretsiz', source: 'Deneme dersi · Kampanyalar · 3 Ekim’de doğrulandı' },
      ],
      approve: 'Onayla ve gönder',
      tapHint: '← Dokunup deneyin',
      edit: 'Düzenle',
      editClosingAlt: '. Uygun olduğunuz bir günü birlikte seçelim mi?',
      editingBadge: 'Taslak düzenleniyor',
      saveEdit: 'Metni değiştir',
      stamp: 'Onaylandı',
      sent: 'Gönderildi',
      approvedAt: '23:48',
      replay: 'Tekrar göster',
    },
    content: {
      title: 'Paylaşımlarınız da planlı.',
      body:
        'Ne paylaşmak istediğinizi yazın. Taslak doğrulanmış bilgilerle hazırlanır, siz onaylarsınız, saati gelince paylaşılır. Bir fiyat değişirse, eski fiyatı içeren paylaşım kendiliğinden beklemeye alınır.',
      note: 'Planlandı, yayınlandı demek değildir. Paylaşım gerçekten yayınlanınca haber verir, yayınlanamazsa nedenini söyler.',
      example: 'Örnek',
      heading: 'Bu hafta',
      heldReason: 'Fiyat 6.000 ₺ → 7.000 ₺ olarak güncellendiği için otomatik beklemeye alındı.',
      posts: [
        { day: 'Pzt', time: '19:00', kind: 'Story', title: 'Deneme dersi', status: 'Yayınlandı', state: 'published' },
        { day: 'Çar', time: '12:30', kind: 'Gönderi', title: 'Sabah reformer grubu', status: 'Planlandı', state: 'scheduled' },
        { day: 'Cum', time: '19:00', kind: 'Story', title: 'Üyelik kampanyası', status: 'Beklemede · eski fiyat', state: 'held' },
        { day: 'Paz', time: '10:00', kind: 'Gönderi', title: 'Hafta sonu saatleri', status: 'Onay bekliyor', state: 'pending' },
      ],
    },
    escalate: {
      title: 'Bazı mesajlar her zaman size gelir.',
      body: 'Bunlara otomatik yanıt verilmez. Mesaj size bildirilir, yanıtı siz yazarsınız.',
      badge: 'Size iletilir',
      items: ['Şikâyetler', 'İade talepleri', 'İndirim ve pazarlık', 'Emin olamadığı her şey'],
      examples: [
        '“Bugünkü ders çok kalabalıktı, memnun kalmadım.”',
        '“Bu ay gelemedim, kalan derslerimin iadesini alabilir miyim?”',
        '“İki arkadaş yazılırsak aylık ücrete indirim yapar mısınız?”',
        '“Bel fıtığım var, hangi eğitmenle çalışmam uygun olur?”',
      ],
    },
    report: {
      title: 'Akşam, günün dürüst bir özeti.',
      body: 'Sayılar gerçek kayıtlardan gelir. Planlanan bir paylaşım yayınlanmış gibi gösterilmez, başarısız olan her şey nedeniyle birlikte yazılır.',
      example: 'Örnek',
      heading: 'Günün özeti · 21:00',
      verifiedTag: 'Gerçek kayıt',
      rows: [
        ['Gelen mesaj', '14'],
        ['Onaylanan yanıt', '11'],
        ['Size iletilen', '2'],
        ['Yanıt bekleyen', '1'],
        ['Planlanan paylaşım', 'Yarın 19:00'],
        ['Yayınlanan paylaşım', '0'],
      ],
      footerNote: 'Planlanan paylaşımlar gerçekten yayınlanana kadar “0” olarak görünür.',
    },
    control: {
      title: 'Kontrol sizde.',
      items: [
        {
          title: 'Neyin otomatik olacağını siz seçersiniz.',
          body: 'Örneğin saat ve adres soruları otomatik yanıtlanır, fiyat soruları onayınıza gelir. İstediğiniz zaman değiştirirsiniz.',
        },
        {
          title: 'Bir konuşmayı devralabilirsiniz.',
          body: 'Bir müşteriyle kendiniz konuşmak istediğinizde o konuşmada otomasyon durur. Bıraktığınızda kaldığı yerden devam eder.',
        },
        {
          title: 'Ekibinize uygun roller.',
          body: 'Personel yanıt ve paylaşım taslağı hazırlar. Fiyat değişikliği ve yayın sizin onayınızla olur.',
        },
        {
          title: 'Her işlemin kaydı tutulur.',
          body: 'Ne gönderildi, kim onayladı, ne zaman oldu. Hepsini tek bir listede görürsünüz.',
        },
      ],
    },
    steps: {
      title: 'Nasıl başlarsınız',
      items: [
        {
          title: 'Bilgilerinizi birlikte giriyoruz.',
          body: 'Fiyatlar, saatler, adres ve kampanyalar. Kurulumu işletmenize gelip sizinle yapıyoruz. Her bilgiyi siz doğrularsınız.',
        },
        {
          title: 'Instagram hesabınızı bağlıyoruz.',
          body: 'Instagram’ın resmi giriş ekranıyla bağlanır. Sonra birkaç örnek müşteri sorusuyla yanıtları birlikte deneriz.',
        },
        {
          title: 'Gerisini WhatsApp’tan yönetirsiniz.',
          body: 'Taslaklar ve onaylar telefonunuza gelir. Hazır olduğunuzda sık sorulan sorular için otomatik yanıtı açarsınız.',
        },
      ],
    },
    faq: {
      title: 'Sık sorulanlar',
      items: [
        {
          q: 'Instagram şifremi vermem gerekiyor mu?',
          a: 'Hayır. Hesabınızı Instagram’ın resmi giriş ekranıyla bağlarsınız, şifreniz bize hiç gelmez. Bağlantıyı istediğiniz an kaldırabilirsiniz, ilgili veriler de silinir.',
        },
        {
          q: 'Müşterime yanlış bir şey yazarsa?',
          a: 'Fiyat, saat, adres ve kampanya gibi bilgileri yalnızca sizin doğruladıklarınızdan alır. Her yanıt gönderilmeden önce bu açıdan kontrol edilir. Emin olamadığı mesajları size bırakır.',
        },
        {
          q: 'Gece gelen mesajlar ne olur?',
          a: 'Rutin sorular için otomatik yanıtı açtıysanız hemen yanıtlanır. Açmadıysanız taslak hazır bekler, siz uygun olduğunuzda onaylarsınız. Instagram’ın 24 saatlik yanıt kuralına uyar.',
        },
        {
          q: 'WhatsApp kullanmak zorunda mıyım?',
          a: 'Hayır. Telegram’ı ya da telefonunuzdaki web uygulamasını da kullanabilirsiniz. Hepsinde aynı onaylar ve bildirimler var.',
        },
        {
          q: 'Kurulumu kendim yapabilir miyim?',
          a: 'Evet. Instagram biyografinizi ya da fiyat listenizi yapıştırın, bilgileri o çıkarır, siz tek tek doğrularsınız. İsterseniz işletmenize gelip birlikte de kuruyoruz.',
        },
        {
          q: 'Hangi işletmeler için uygun?',
          a: 'Instagram üzerinden müşterileriyle iletişim kuran tüm yerel işletmeler için: kafeler, butikler, güzellik salonları, spor stüdyoları, klinikler ve hizmet işletmeleri.',
        },
      ],
    },
    pilot: {
      title: 'Pilot listesine katılın',
      body:
        'Instagram kullanan seçilmiş yerel işletmelerle pilot uygulamaya başlıyoruz. Listeye katılırsanız sizi arayıp işletmenizi ve Instagram’ı nasıl kullandığınızı konuşuruz. Uygun olursa kurulumu sizinle birlikte yaparız.',
      expectationsTitle: 'Pilot programı hakkında bilmeniz gerekenler',
      expectations: [
        {
          badge: '30 dakika · Birlikte kurulum',
          title: 'Kurulumu sizinle birlikte yapıyoruz.',
          detail:
            'İster yerinde ister görüntülü görüşmeyle; fiyat ve saatlerinizi birlikte giriyor, 5 gerçek müşteri sorusuyla canlı test yapıyoruz.',
        },
        {
          badge: 'Ücretsiz pilot · Taahhüt yok',
          title: 'İlk deneme sürecinde ücret veya kart bilgisi istemiyoruz.',
          detail:
            'Sistemi kendi müşterilerinizle, gerçek iş akışınızda deneyin. Memnun kalmazsanız tek dokunuşla Instagram bağlantısını kaldırabilirsiniz.',
        },
        {
          badge: '10–15 işletme · Birebir destek',
          title: 'Her işletmeyle doğrudan kurucu ekip ilgileniyor.',
          detail:
            'Kalabalık bir çağrı merkezi değil; işletmenizin çalışma düzenini bilen, ihtiyaç duyduğunuzda doğrudan ulaşabileceğiniz küçük bir ekiple çalışırsınız.',
        },
        {
          badge: 'Resmi bağlantı · Şifre paylaşılmaz',
          title: 'Instagram şifreniz her zaman sizde kalır.',
          detail:
            'Hesabınız Instagram’ın resmi giriş ekranıyla bağlanır. Bağlantıyı kestiğiniz anda erişim durur ve verileriniz silinir.',
        },
      ],
      nextStepsTitle: 'Formu gönderdikten sonra ne olur?',
      nextSteps: [
        '24 saat içinde sizi kısaca arar veya WhatsApp’tan yazarız.',
        'Uygun bir gün seçip 30 dakikada kurulumu birlikte tamamlarız.',
      ],
      whatsappDirectLabel: 'Form doldurmak istemiyor musunuz? Bize doğrudan WhatsApp’tan yazın →',
      whatsappPrefill: `Merhaba, ${PRODUCT_NAME} pilot programı hakkında bilgi almak istiyorum.`,
    },
    form: {
      dossierHeader: 'Pilot Başvuru Kartı',
      categoryLabel: 'İşletme türü',
      categories: [
        'Güzellik / Bakım',
        'Kafe / Restoran',
        'Mağaza / Butik',
        'Spor / Pilates',
        'Klinik / Sağlık',
        'Hizmet İşletmesi',
        'Diğer',
      ],
      business: 'İşletme adı',
      instagram: 'Instagram hesabı',
      instagramHint: '@kullaniciadi',
      contact: 'Telefon veya e-posta',
      contactHint: 'Size buradan ulaşacağız',
      city: 'Şehir',
      consent:
        'Bilgilerimin yalnızca pilot programı hakkında benimle iletişime geçmek için kullanılmasını kabul ediyorum. Bilgilerim başkasıyla paylaşılmaz ve istediğimde silinir.',
      submit: 'Listeye katıl',
      sending: 'Gönderiliyor…',
      required: 'Bu alan gerekli.',
      consentRequired: 'Devam etmek için onay kutusunu işaretleyin.',
      sent: 'Teşekkürler, listeye eklendiniz. Sizinle iletişime geçeceğiz.',
      preview: 'Önizleme: bu form henüz bir yere bağlı değil. Bilgileriniz gönderilmedi.',
      failed: 'Gönderilemedi. Bağlantınızı kontrol edip tekrar deneyin.',
    },
    footer: {
      trademark: 'Instagram ve WhatsApp, Meta Platforms, Inc.’in ticari markalarıdır. Bu ürün Meta ile bağlantılı değildir.',
    },
  },
  en: {
    meta: { title: `${PRODUCT_NAME} · An Instagram assistant for small businesses` },
    nav: { waitlist: 'Pilot waitlist', language: 'Language', dark: 'Dark mode' },
    hero: {
      kicker: 'An Instagram assistant for small businesses',
      pilotBadge: 'Early Access · Pilot Programme',
      promises: ['Never invents a price.', 'Never sends without you.', 'Never claims what didn’t happen.'],
      lead:
        'It drafts replies to your Instagram DMs using only details you have verified, plans your posts, and tells you what happened each day. You run it all from WhatsApp and approve what matters with one tap.',
      cta: 'Join the pilot waitlist',
      note: 'We set it up together with you in 30 minutes.',
      preview: {
        dmLabel: '1 · Incoming Instagram DM (23:47)',
        dmText: '“Hi! How much is a monthly membership? Do you have a trial class?”',
        factLabel: '2 · Verified Fact Source',
        factText: '₺6,000 (Monthly membership) · Free (Trial class)',
        stampLabel: '3 · One-Tap WhatsApp Sign-off',
        stampSub: 'APPROVED · 23:48',
      },
    },
    index: {
      label: 'On this page',
      links: [
        { id: 'karsilastirma', label: 'Why it is different' },
        { id: 'whatsapp', label: 'Run it from WhatsApp' },
        { id: 'bilgi', label: 'How it knows' },
        { id: 'dm', label: 'Customer messages' },
        { id: 'icerik', label: 'Posts' },
        { id: 'kontrol', label: 'You stay in control' },
        { id: 'sss', label: 'Questions' },
      ],
    },
    comparison: {
      title: 'Stop trying to catch up on DMs between classes.',
      body:
        'Answering the same price, hours and address questions every day drains your time—while a generic chatbot risks telling a customer the wrong price. There is a reliable middle ground.',
      withoutLabel: 'Without it',
      withLabel: `With ${PRODUCT_NAME}`,
      rows: [
        {
          scenario: 'A “How much is monthly membership?” DM at 23:45',
          without:
            'Seen late after a long day or left until morning. While waiting, the customer messages another studio.',
          withProduct:
            'A draft is prepared right away using your verified price and trial-class rule—sent with one tap, or automatically if you chose.',
        },
        {
          scenario: 'The fear of “What if it quotes the wrong price?”',
          without:
            'Generic AI bots guess missing details, invent discounts, or get pulled into haggling.',
          withProduct:
            'Uses only the fact cards you have verified. If a customer asks something not on record, it never guesses—it passes the message to you.',
        },
        {
          scenario: 'Scheduled posts left behind when prices change',
          without:
            'You update your membership fee, but Friday’s scheduled story still goes out with the old price.',
          withProduct:
            'The moment you text the new price on WhatsApp, any scheduled post carrying the old price is put on hold automatically.',
        },
      ],
    },
    whatsapp: {
      title: 'Run it from WhatsApp.',
      body:
        'There is no new app to learn. Text a price change, send a photo, ask for today’s summary. Anything important comes back to you as a confirmation with buttons.',
      note:
        'Typing “ok” never approves anything. Each approval belongs to one action and expires after a while. You can also use Telegram or the web app on your phone.',
      example: 'Example screen',
      online: 'online',
      today: 'Today',
      placeholder: 'Message',
      clock: '09:14',
      chat: [
        { from: 'owner', text: 'Monthly membership is 7,000 now', time: '09:12' },
        {
          from: 'assistant',
          text: 'Change the monthly membership from ₺6,000 to ₺7,000?',
          time: '09:12',
          actions: ['Yes, update', 'Cancel'],
        },
        {
          from: 'owner',
          quote: 'Change the monthly membership from ₺6,000 to ₺7,000?',
          text: 'Yes, update',
          time: '09:13',
        },
        {
          from: 'assistant',
          text: 'Updated. I put Friday’s 19:00 story on hold because it still shows the old price.',
          time: '09:13',
        },
        {
          from: 'owner',
          attachment: { kicker: 'Reformer Pilates', title: 'Trial class', note: 'free' },
          text: 'Post this as a story tomorrow at 19:00',
          time: '09:14',
        },
        {
          from: 'assistant',
          text: 'The story is ready for tomorrow at 19:00. Approve it?',
          time: '09:14',
          actions: ['Approve', 'Change time'],
        },
      ],
      commandsTitle: 'Other things you can write',
      commandsHint: 'Tap a command to preview it on the WhatsApp screen',
      commands: [
        { ask: 'How many DMs today?', answer: '14 messages. 11 answered, 2 passed to you, 1 waiting for a reply.' },
        {
          ask: 'Make a story for the trial class.',
          answer: 'The draft is ready. Its price and date are verified, and it is waiting for your approval.',
          action: 'See draft',
        },
        { ask: 'Make the replies a bit friendlier.', answer: 'Reply tone updated. It applies to new drafts from now on.' },
        { ask: 'What is waiting for me?', answer: '2 replies and 1 post are waiting for your approval.' },
        {
          ask: 'Why didn’t yesterday’s post go out?',
          answer: 'Instagram rejected the image because it was not 9:16. Send a new image and I will schedule it again.',
        },
        { ask: 'Cancel tomorrow’s post.', answer: 'Cancel tomorrow’s 19:00 story?', action: 'Cancel post' },
      ],
    },
    knowledge: {
      title: 'How does it know your business?',
      body:
        'You do not fill out complex spreadsheets or dashboards. Paste your existing price list or Instagram bio; it picks out the facts one by one, and you simply verify them.',
      extractKicker: 'Step 1 · Quick import',
      extractTitle: 'Paste the text you already have.',
      extractBody:
        'Share the price message you usually send on WhatsApp or your profile bio; it turns your prices, hours and offers into structured fact cards.',
      extractSourceLabel: 'Example pasted text',
      extractSourceSample:
        'Reformer Pilates Studio · Weekdays 08:00-21:00 · Monthly membership (2x/week) ₺6,000. First trial class is free. Address: Bahçelievler Mah. No: 12',
      ledgerTitle: 'Step 2 · Your Verified Business Card',
      verifiedBadge: 'Verified',
      facts: [
        {
          category: 'Prices',
          label: 'Monthly membership (2x/week)',
          value: '₺6,000',
          verifiedAt: 'Verified 12 Oct',
        },
        {
          category: 'Campaigns',
          label: 'First trial class',
          value: 'Free',
          verifiedAt: 'Verified 3 Oct',
        },
        {
          category: 'Hours',
          label: 'Weekday opening hours',
          value: '08:00 – 21:00',
          verifiedAt: 'Verified 1 Oct',
        },
        {
          category: 'Address',
          label: 'Studio location',
          value: 'Bahçelievler Mah. No: 12',
          verifiedAt: 'Verified 1 Oct',
        },
      ],
      missingRule: {
        badge: 'When a fact is not on record',
        question: 'Example customer question: “Do you offer prenatal Pilates?”',
        outcome: 'If it is not on your verified cards, it never invents an answer. No draft is sent—the question is passed straight to you.',
      },
    },
    demo: {
      title: 'Every price has a source.',
      body:
        'Every price, opening hour and campaign in a draft comes from a fact you entered and verified, and the source is listed underneath. If a fact is missing, it asks you instead of guessing.',
      example: 'Example screen',
      channel: 'Instagram',
      customer: 'anna.berg',
      received: '23:47',
      message: 'Hi! How much is a monthly membership? Do you have a trial class?',
      draftLabel: 'Draft reply',
      draft: ['Hi Anna, a monthly membership is ', ' and your first trial class is ', '. Shall we find a day that suits you?'],
      facts: [
        { value: '₺6,000', source: 'Monthly membership · Prices · verified 12 Oct' },
        { value: 'free', source: 'Trial class · Campaigns · verified 3 Oct' },
      ],
      approve: 'Approve and send',
      tapHint: '← Tap to try it',
      edit: 'Edit',
      editClosingAlt: '. Would you like to pick a day this week?',
      editingBadge: 'Editing draft',
      saveEdit: 'Switch phrasing',
      stamp: 'Approved',
      sent: 'Sent',
      approvedAt: '23:48',
      replay: 'Show again',
    },
    content: {
      title: 'Your posts, planned and checked.',
      body:
        'Say what you want to post. The draft uses verified details, you approve it, and it goes out at the set time. If a price changes, any post that still shows the old price is put on hold automatically.',
      note: 'Scheduled does not mean published. You hear when a post actually goes out, and if it fails, you hear why.',
      example: 'Example',
      heading: 'This week',
      heldReason: 'Put on hold automatically because the price changed from ₺6,000 to ₺7,000.',
      posts: [
        { day: 'Mon', time: '19:00', kind: 'Story', title: 'Trial class', status: 'Published', state: 'published' },
        { day: 'Wed', time: '12:30', kind: 'Post', title: 'Morning reformer group', status: 'Scheduled', state: 'scheduled' },
        { day: 'Fri', time: '19:00', kind: 'Story', title: 'Membership offer', status: 'On hold · old price', state: 'held' },
        { day: 'Sun', time: '10:00', kind: 'Post', title: 'Weekend hours', status: 'Awaiting approval', state: 'pending' },
      ],
    },
    escalate: {
      title: 'Some messages always come to you.',
      body: 'These never get an automatic reply. You are notified and you write the answer.',
      badge: 'Passed to you',
      items: ['Complaints', 'Refund requests', 'Discounts and haggling', 'Anything it isn’t sure about'],
      examples: [
        '“Today’s class was too crowded, I wasn’t happy with it.”',
        '“I couldn’t attend this month, can I get a refund for my remaining sessions?”',
        '“If two of us sign up together, can you give us a discount on the monthly fee?”',
        '“I have a herniated disc—which instructor would be best for me?”',
      ],
    },
    report: {
      title: 'Each evening, a plain account of the day.',
      body: 'Every number comes from real records. A scheduled post is never shown as published, and anything that failed is listed with the reason.',
      example: 'Example',
      heading: 'Daily summary · 21:00',
      verifiedTag: 'Real record',
      rows: [
        ['Messages received', '14'],
        ['Replies approved', '11'],
        ['Passed to you', '2'],
        ['Awaiting reply', '1'],
        ['Post scheduled', 'Tomorrow 19:00'],
        ['Posts published', '0'],
      ],
      footerNote: 'Scheduled posts remain “0” published until Instagram confirms they went live.',
    },
    control: {
      title: 'You stay in control.',
      items: [
        {
          title: 'You choose what runs automatically.',
          body: 'For example, questions about hours and address are answered automatically, while price questions come to you. Change it any time.',
        },
        {
          title: 'Take over any conversation.',
          body: 'When you want to talk to a customer yourself, automation stops for that conversation. Hand it back and it picks up where it left off.',
        },
        {
          title: 'Roles that fit your team.',
          body: 'Staff can draft replies and posts. Price changes and publishing need your approval.',
        },
        {
          title: 'Every action is recorded.',
          body: 'What was sent, who approved it, and when. All of it in one list.',
        },
      ],
    },
    steps: {
      title: 'How you get started',
      items: [
        {
          title: 'We enter your details together.',
          body: 'Prices, hours, address and campaigns. We come to your business and set it up with you. You verify every detail.',
        },
        {
          title: 'We connect your Instagram account.',
          body: 'It connects through Instagram’s official login. Then we try a few typical customer questions together.',
        },
        {
          title: 'You run the rest from WhatsApp.',
          body: 'Drafts and approvals come to your phone. When you are ready, turn on automatic replies for common questions.',
        },
      ],
    },
    faq: {
      title: 'Questions',
      items: [
        {
          q: 'Do I have to give you my Instagram password?',
          a: 'No. You connect your account through Instagram’s official login, and your password never reaches us. You can disconnect at any time, and the related data is deleted.',
        },
        {
          q: 'What if it tells a customer something wrong?',
          a: 'Prices, hours, addresses and campaigns come only from details you verified, and every reply is checked for them before it is sent. Messages it is unsure about are left to you.',
        },
        {
          q: 'What happens to messages at night?',
          a: 'If you turned on automatic replies for routine questions, they are answered right away. If not, the draft waits for you to approve when it suits you. It follows Instagram’s 24-hour reply rule.',
        },
        {
          q: 'Do I have to use WhatsApp?',
          a: 'No. You can use Telegram or the web app on your phone. All of them have the same approvals and notifications.',
        },
        {
          q: 'Can I set it up myself?',
          a: 'Yes. Paste your Instagram bio or price list, it picks out the details, and you verify each one. If you prefer, we come to your business and set it up together.',
        },
        {
          q: 'Which businesses is it for?',
          a: 'For any small business that communicates with customers on Instagram: cafés, boutiques, salons, fitness studios, clinics and service businesses.',
        },
      ],
    },
    pilot: {
      title: 'Join the pilot waitlist',
      body:
        'We are starting with a small cohort of local businesses using Instagram. If you join, we will call you to talk about your business and how you use Instagram. If it is a good fit, we set it up together with you.',
      expectationsTitle: 'What to expect in the pilot programme',
      expectations: [
        {
          badge: '30 minutes · Guided setup',
          title: 'We set it up together with you.',
          detail:
            'In person or over a quick video call, we enter your prices and hours together and test 5 real customer questions live.',
        },
        {
          badge: 'Free pilot · No commitment',
          title: 'No fee or card required for the initial pilot.',
          detail:
            'Try it with your own customers in your real daily workflow. If it is not for you, disconnect your Instagram account with one tap.',
        },
        {
          badge: '10–15 businesses · Direct support',
          title: 'You work directly with the founding team.',
          detail:
            'No ticket queues—we work closely with a small cohort of local businesses so you can reach us directly whenever you need help.',
        },
        {
          badge: 'Official login · Password stays yours',
          title: 'We never ask for your Instagram password.',
          detail:
            'Your account connects through Instagram’s official login screen. Disconnect at any time and access stops immediately.',
        },
      ],
      nextStepsTitle: 'What happens after you submit?',
      nextSteps: [
        'We call or message you on WhatsApp within 24 hours.',
        'We pick a convenient day and complete the 30-minute setup together.',
      ],
      whatsappDirectLabel: 'Prefer not to fill out a form? Message us directly on WhatsApp →',
      whatsappPrefill: `Hi, I would like to learn more about the ${PRODUCT_NAME} pilot programme.`,
    },
    form: {
      dossierHeader: 'Pilot Application Card',
      categoryLabel: 'Business type',
      categories: [
        'Beauty / Salon',
        'Café / Restaurant',
        'Shop / Retail',
        'Fitness / Yoga',
        'Clinic / Health',
        'Services',
        'Other',
      ],
      business: 'Business name',
      instagram: 'Instagram account',
      instagramHint: '@username',
      contact: 'Phone or email',
      contactHint: 'This is how we will reach you',
      city: 'City',
      consent:
        'I agree that my details are used only to contact me about the pilot programme. They are not shared with anyone and are deleted when I ask.',
      submit: 'Join the waitlist',
      sending: 'Sending…',
      required: 'This field is required.',
      consentRequired: 'Tick the consent box to continue.',
      sent: 'Thank you, you are on the list. We will be in touch.',
      preview: 'Preview: this form is not connected yet. Nothing was sent.',
      failed: 'Could not send. Check your connection and try again.',
    },
    footer: {
      trademark: 'Instagram and WhatsApp are trademarks of Meta Platforms, Inc. This product is not affiliated with Meta.',
    },
  },
}
