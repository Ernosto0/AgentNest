import { PRODUCT_NAME } from './brand'

export type Lang = 'tr' | 'en'

export type ChatMessage = {
  from: 'owner' | 'assistant'
  text: string
  time: string
  // A story graphic the owner sends, drawn from these three lines.
  attachment?: { kicker: string; title: string; note: string }
  // Inline buttons under an assistant message. Decisions are buttons, never typed text.
  actions?: string[]
}

// Mirrors the app's status vocabulary (frontend/src/components/StatusBadge.tsx).
export type PostStatus = 'published' | 'scheduled' | 'held' | 'pending'

type Titled = { title: string; body: string }

export type Copy = {
  meta: { title: string; description: string }
  nav: {
    links: { id: string; label: string }[]
    cta: string
    language: string
    toDark: string
    toLight: string
    skip: string
    menu: string
  }
  hero: {
    badge: string
    title: string
    accent: string
    lead: string
    cta: string
    secondary: string
    points: [string, string, string]
  }
  preview: {
    example: string
    screen: string
    greeting: string
    date: string
    waitingTitle: string
    queue: [string, string, string]
    queueCounts: [number, number, number]
    metricsTitle: string
    metrics: [string, string, string]
    metricValues: [number, number, number]
    customer: string
    time: string
    message: string
    reply: [string, string, string]
    facts: [string, string]
    pending: string
    sent: string
    approve: string
    undo: string
  }
  promises: Titled[]
  audience: { label: string; items: string[] }
  problem: {
    eyebrow: string
    title: string
    body: string
    withoutLabel: string
    withLabel: string
    rows: { scenario: string; without: string; withProduct: string }[]
  }
  how: { eyebrow: string; title: string; body: string; steps: Titled[] }
  knowledge: {
    eyebrow: string
    title: string
    body: string
    pasteLabel: string
    pasteSample: string
    pasteNote: string
    ledgerTitle: string
    progress: string // "{n} / {total} doğrulandı"
    verified: string
    unverified: string
    verify: string
    reset: string
    usageNote: string
    facts: { category: string; label: string; value: string }[]
  }
  demo: {
    eyebrow: string
    title: string
    body: string
    points: Titled[]
    tabs: [string, string]
    example: string
    channel: string
    known: {
      customer: string
      time: string
      message: string
      draftLabel: string
      draft: [string, string, string]
      facts: [{ value: string; source: string }, { value: string; source: string }]
      approve: string
      edit: string
      editAlt: string
      editing: string
      saveEdit: string
      pending: string
      sent: string
      replay: string
      hint: string
    }
    unknown: {
      customer: string
      time: string
      message: string
      badge: string
      title: string
      body: string
      questionLabel: string
      question: string
      answer: string
      afterAnswer: string
    }
  }
  owner: {
    eyebrow: string
    title: string
    body: string
    channels: Titled[]
    note: string
    example: string
    bot: string
    botSub: string
    today: string
    placeholder: string
    chat: ChatMessage[]
    commandsTitle: string
    commandsHint: string
    commands: { ask: string; answer: string; action?: string }[]
  }
  content: {
    eyebrow: string
    title: string
    body: string
    note: string
    example: string
    heading: string
    heldReason: string
    posts: { day: string; time: string; kind: string; title: string; status: string; state: PostStatus }[]
  }
  report: {
    title: string
    body: string
    example: string
    heading: string
    asOf: string
    metrics: { label: string; value: string }[]
    footerNote: string
  }
  limits: {
    eyebrow: string
    title: string
    body: string
    escalateBadge: string
    escalate: { title: string; example: string }[]
  }
  trust: {
    eyebrow: string
    title: string
    body: string
    controlTitle: string
    control: Titled[]
    securityTitle: string
    security: Titled[]
  }
  faq: { eyebrow: string; title: string; body: string; items: { q: string; a: string }[] }
  pilot: {
    eyebrow: string
    title: string
    body: string
    expectations: { badge: string; title: string; detail: string }[]
    nextStepsTitle: string
    nextSteps: Titled[]
    whatsappDirectLabel: string
    whatsappPrefill: string
  }
  form: {
    title: string
    subtitle: string
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
    invalidEmail: string
    consentRequired: string
    sent: string
    preview: string
    failed: string
  }
  mobileCta: { label: string; sub: string }
  footer: { tagline: string; trademark: string; top: string }
}

export const copy: Record<Lang, Copy> = {
  tr: {
    meta: {
      title: `${PRODUCT_NAME} · Küçük işletmeler için Instagram asistanı`,
      description:
        'Instagram’da zaman kazanın, müşteri mesajlarını gözden kaçırmayın. AgentNest işletmenizin bilgileriyle yanıt hazırlar, paylaşımlarınızı planlar. Kontrol sizde kalır.',
    },
    nav: {
      links: [
        { id: 'nasil', label: 'Nasıl çalışır' },
        { id: 'demo', label: 'Örnekler' },
        { id: 'guven', label: 'Güvenlik' },
        { id: 'sss', label: 'Sorular' },
      ],
      cta: 'Pilota başvurun',
      language: 'Dil',
      toDark: 'Koyu temaya geç',
      toLight: 'Açık temaya geç',
      skip: 'İçeriğe geç',
      menu: 'Menü',
    },
    hero: {
      badge: 'Ücretsiz pilot programı · Başvurular açık',
      title: 'Instagram işletmenizi büyütsün,',
      accent: 'vaktinizi tüketmesin.',
      lead:
        `${PRODUCT_NAME} müşteri mesajlarına işletmenizin bilgileriyle yanıt hazırlar, paylaşımlarınızı planlar ve önemli konuları size getirir. Kontrol her zaman sizde kalır.`,
      cta: 'Ücretsiz pilota başvurun',
      secondary: 'Nasıl çalıştığını görün',
      points: ['30 gün ücretsiz', 'Kart bilgisi yok', 'Kurulum 30 dakika'],
    },
    preview: {
      example: 'Örnek ekran',
      screen: 'Bugün',
      greeting: 'Günaydın, Ayşe',
      date: 'Salı, 10 Kasım',
      waitingTitle: 'Sizi bekleyenler',
      queue: ['Onay bekleyen yanıt', 'Size iletilen konuşma', 'Beklemedeki paylaşım'],
      queueCounts: [2, 1, 1],
      metricsTitle: 'Bugün',
      metrics: ['Gelen mesaj', 'Gönderilen yanıt', 'Yayınlanan paylaşım'],
      metricValues: [14, 11, 1],
      customer: 'ayse.yilmaz',
      time: '23:47',
      message: 'Merhaba, aylık üyelik ne kadar? Deneme dersi var mı?',
      reply: ['Merhaba Ayşe Hanım, aylık üyeliğimiz ', ', ilk deneme dersiniz ', '. Size uygun bir gün ayarlayalım mı?'],
      facts: ['6.000 ₺', 'ücretsiz'],
      pending: 'Onay bekliyor',
      sent: 'Gönderildi',
      approve: 'Onayla ve gönder',
      undo: 'Tekrar göster',
    },
    promises: [
      {
        title: 'Tekrar eden sorularda zaman kazanın.',
        body: 'Fiyat, saat ve adres sorularının yanıtları, doğruladığınız bilgilerle hazır olsun. Her seferinde baştan yazmayın.',
      },
      {
        title: 'Müşteri mesajlarını gözden kaçırmayın.',
        body: 'Yanıt bekleyen mesajları ve size iletilen önemli konuşmaları bir arada görün. Hazır yanıtları tek dokunuşla onaylayın.',
      },
      {
        title: 'Paylaşımlarınız son dakikaya kalmasın.',
        body: 'İçeriklerinizi önceden planlayın, onayınızla yayınlansın. Nelerin yayınlandığını, nelerin beklediğini görün.',
      },
    ],
    audience: {
      label: 'Kimler için',
      items: ['Pilates ve spor stüdyoları', 'Güzellik salonları', 'Kafeler', 'Butikler', 'Klinikler', 'Hizmet işletmeleri'],
    },
    problem: {
      eyebrow: 'İşletmenize daha çok zaman',
      title: 'İşinizin arasında bir de DM yetiştirmeyin.',
      body:
        'Müşterilerinizle ilgilenirken mesajlar birikir, aynı sorular tekrar gelir, paylaşımlar ertelenir. AgentNest yanıtları ve planları hazırlar; siz önemli konulara odaklanırsınız.',
      withoutLabel: 'Bugün',
      withLabel: `${PRODUCT_NAME} ile`,
      rows: [
        {
          scenario: 'Gece 23:45’te gelen “Aylık ne kadar?” sorusu',
          without: 'Yorgunlukla geç görülür ya da sabaha kalır. Müşteri beklerken başka bir stüdyoya yazar.',
          withProduct:
            'Doğrulanmış fiyatla taslak hemen hazırlanır. Tek dokunuşla siz gönderirsiniz ya da açtıysanız otomatik yanıtlanır.',
        },
        {
          scenario: '“Ya müşterime yanlış fiyat söylerse?” endişesi',
          without: 'Sıradan yapay zekâ araçları bilmediği detayı tahmin eder, olmayan indirimi vaat eder, pazarlığa girer.',
          withProduct: 'Yalnızca doğruladığınız bilgileri kullanır. Kayıtlı olmayan bir soru gelirse tahmin etmez, size iletir.',
        },
        {
          scenario: 'Fiyat değişince unutulan planlı paylaşımlar',
          without: 'Fiyat güncellenir ama Cuma için planlanan story eski fiyatla yayınlanır.',
          withProduct: 'Yeni fiyatı girdiğiniz an, eski fiyatı içeren planlı paylaşımlar kendiliğinden beklemeye alınır.',
        },
      ],
    },
    how: {
      eyebrow: 'Nasıl çalışır',
      title: 'Dört adımda, her adımı sizin bildiğiniz bir sistem.',
      body: 'Kurulumdan sonra işiniz yalnızca onaylamak. Asistan bilmediği yerde durur ve size sorar.',
      steps: [
        {
          title: 'Bilgilerinizi verirsiniz',
          body: 'Fiyat listenizi ya da biyografinizi yapıştırırsınız. Bilgileri ayıklar, siz tek tek doğrularsınız.',
        },
        {
          title: 'Mesaj gelince taslak hazırlanır',
          body: 'Instagram DM’i gelir gelmez, doğrulanmış bilgilerle bir yanıt taslağı yazılır.',
        },
        {
          title: 'Siz onaylarsınız',
          body: 'Tek dokunuşla gönderir, düzenler ya da konuşmayı devralırsınız. Rutin soruları otomatiğe bırakabilirsiniz.',
        },
        {
          title: 'Akşam özetini alırsınız',
          body: 'Kaç mesaj geldi, ne gönderildi, ne bekliyor. Sayılar gerçek kayıtlardan gelir.',
        },
      ],
    },
    knowledge: {
      eyebrow: 'Bilgi kaynağı',
      title: 'İşletmenizi sizin verdiğiniz bilgilerden tanır.',
      body:
        'Tablo ya da teknik panel doldurmazsınız. Müşterilere gönderdiğiniz hazır fiyat mesajını yapıştırın; içindeki fiyat, saat ve kampanyalar bilgi kartlarına dönüşür. Taslaklarda yalnızca sizin doğruladıklarınız kullanılır.',
      pasteLabel: 'Yapıştırdığınız metin',
      pasteSample:
        'Reformer Pilates Stüdyosu · Hafta içi 08:00–21:00 · Aylık üyelik (haftada 2 ders) 6.000 TL. İlk deneme dersimiz ücretsizdir. Adres: Bahçelievler Mah. No: 12',
      pasteNote: 'Ayıklama bir bilgiyi kendiliğinden doğrulamaz.',
      ledgerTitle: 'Bilgi kartlarınız',
      progress: '{n} / {total} doğrulandı',
      verified: 'Doğrulandı',
      unverified: 'Doğrulanmadı',
      verify: 'Doğrula',
      reset: 'Baştan göster',
      usageNote: 'Doğrulanmamış bilgi hiçbir taslakta kullanılmaz.',
      facts: [
        { category: 'Fiyat', label: 'Aylık üyelik (haftada 2)', value: '6.000 ₺' },
        { category: 'Kampanya', label: 'İlk deneme dersi', value: 'Ücretsiz' },
        { category: 'Saatler', label: 'Hafta içi çalışma saatleri', value: '08:00 – 21:00' },
        { category: 'Adres', label: 'Stüdyo konumu', value: 'Bahçelievler Mah. No: 12' },
      ],
    },
    demo: {
      eyebrow: 'Müşteri mesajları',
      title: 'Her fiyatın bir kaynağı var.',
      body:
        'Taslaktaki her fiyat ve kampanya, sizin doğruladığınız bir bilgiden gelir ve kaynağı altında yazar. Bilgi kayıtlı değilse taslak yazılmaz; soru size gelir.',
      points: [
        { title: 'Kaynağı belli taslak', body: 'Vurgulu her bilginin hangi karttan geldiği altında yazar.' },
        { title: 'Tek dokunuşla onay', body: 'Gönderir, düzenler ya da konuşmayı devralırsınız.' },
        { title: 'Bilmediğinde durur', body: 'Kayıtlı olmayan soruya taslak yazmaz, size sorar.' },
      ],
      tabs: ['Bilgi kayıtlı', 'Bilgi kayıtlı değil'],
      example: 'Örnek ekran',
      channel: 'Instagram DM',
      known: {
        customer: 'ayse.yilmaz',
        time: '23:47',
        message: 'Merhaba, aylık üyelik ne kadar? Deneme dersi var mı?',
        draftLabel: 'Yanıt taslağı',
        draft: ['Merhaba Ayşe Hanım, aylık üyeliğimiz ', '. İlk deneme dersiniz ', '. Size uygun bir gün ayarlayalım mı?'],
        facts: [
          { value: '6.000 ₺', source: 'Aylık üyelik · Fiyat · 12 Ekim’de doğrulandı' },
          { value: 'ücretsiz', source: 'İlk deneme dersi · Kampanya · 3 Ekim’de doğrulandı' },
        ],
        approve: 'Onayla ve gönder',
        edit: 'Düzenle',
        editAlt: '. Bu hafta uygun olduğunuz bir günü birlikte seçelim mi?',
        editing: 'Düzenlendi',
        saveEdit: 'Diğer ifade',
        pending: 'Onay bekliyor',
        sent: 'Gönderildi · 23:48',
        replay: 'Tekrar göster',
        hint: 'Vurgulu bilgilere dokunup kaynağını görün.',
      },
      unknown: {
        customer: 'elif.k',
        time: '21:12',
        message: 'Hamile pilatesi dersiniz var mı?',
        badge: 'Size iletildi',
        title: 'Taslak yazılmadı',
        body: 'Bu konuda doğrulanmış bir bilgi yok. Asistan tahmin etmek yerine durdu ve size sordu.',
        questionLabel: 'Asistanın size sorusu',
        question: '“Hamile pilatesi dersi” hakkında kayıtlı bilgi yok. Müşteriye ne söyleyelim?',
        answer: 'Yanıtı siz yazarsınız',
        afterAnswer: 'Cevabınızı bilgi olarak eklerseniz, bir dahaki benzer soruda onu kullanır.',
      },
    },
    owner: {
      eyebrow: 'Telefonunuzdan yönetin',
      title: 'Yazın, sorun, dokunarak onaylayın.',
      body:
        'Fiyat değişikliğini yazın, bir fotoğraf gönderin, günün özetini sorun. Önemli her işlem size butonlu bir onay olarak gelir.',
      channels: [
        {
          title: 'Telefonunuzdaki web uygulaması',
          body: 'Kurulum gerektirmez. Bugün ekranı, gelen kutusu ve onaylar tek yerde.',
        },
        {
          title: 'Telegram',
          body: 'Bildirimler ve onaylar sohbet olarak gelir. Hesabınızı tek kullanımlık bir kodla bağlarsınız.',
        },
      ],
      note: '“Tamam” yazmak hiçbir şeyi onaylamaz. Her onay tek bir işleme bağlı bir butondur, bir kez kullanılır ve süresi dolar.',
      example: 'Örnek sohbet',
      bot: PRODUCT_NAME,
      botSub: 'bot',
      today: 'Bugün',
      placeholder: 'Mesaj yazın',
      chat: [
        { from: 'owner', text: 'Aylık üyelik artık 7.000 TL', time: '09:12' },
        {
          from: 'assistant',
          text: 'Aylık üyelik fiyatını 6.000 ₺ yerine 7.000 ₺ yapayım mı?',
          time: '09:12',
          actions: ['Evet, güncelle', 'Vazgeç'],
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
          text: 'Story taslağı hazır: yarın 19:00. Onaylarsanız planlarım.',
          time: '09:14',
          actions: ['Onayla', 'Reddet'],
        },
      ],
      commandsTitle: 'Başka neler yazabilirsiniz',
      commandsHint: 'Sohbette görmek için birine dokunun',
      commands: [
        { ask: 'Bugün kaç DM geldi?', answer: '14 mesaj geldi. 11’i yanıtlandı, 2’si size iletildi, 1’i yanıt bekliyor.' },
        { ask: 'Onay bekleyen ne var?', answer: '2 yanıt ve 1 paylaşım onayınızı bekliyor.', action: 'Onaylara git' },
        {
          ask: 'Deneme dersi için bir story hazırla.',
          answer: 'Taslak hazır. İçindeki fiyat ve tarih doğrulanmış bilgilerden geliyor.',
          action: 'Taslağı gör',
        },
        {
          ask: 'Yanıtlar biraz daha samimi olsun.',
          answer: 'Yanıt tonunu daha samimi yapayım mı? Sonraki taslaklarda geçerli olur.',
          action: 'Evet, güncelle',
        },
        {
          ask: 'Dünkü paylaşım neden yayınlanmadı?',
          answer: 'Instagram görseli kabul etmedi: oranı desteklenmiyordu. Yeni bir görsel gönderirseniz yeniden hazırlarım.',
        },
        { ask: 'Yarınki paylaşımı iptal et.', answer: 'Yarın 19:00 story’sini iptal edeyim mi?', action: 'İptal et' },
      ],
    },
    content: {
      eyebrow: 'Paylaşımlar',
      title: 'Paylaşımlarınız planlı ve kontrollü.',
      body:
        'Ne paylaşmak istediğinizi yazın. Taslak doğrulanmış bilgilerle hazırlanır, siz onaylarsınız, saati gelince paylaşılır.',
      note: 'Planlandı, yayınlandı demek değildir. Paylaşım gerçekten yayınlanınca haber verir, yayınlanamazsa nedenini söyler.',
      example: 'Örnek',
      heading: 'Bu hafta',
      heldReason: 'Fiyat 6.000 ₺ → 7.000 ₺ olarak değiştiği için kendiliğinden beklemeye alındı.',
      posts: [
        { day: 'Pzt', time: '19:00', kind: 'Story', title: 'Deneme dersi', status: 'Yayınlandı', state: 'published' },
        { day: 'Çar', time: '12:30', kind: 'Gönderi', title: 'Sabah reformer grubu', status: 'Planlandı', state: 'scheduled' },
        { day: 'Cum', time: '19:00', kind: 'Story', title: 'Üyelik kampanyası', status: 'Beklemede', state: 'held' },
        { day: 'Paz', time: '10:00', kind: 'Gönderi', title: 'Hafta sonu saatleri', status: 'Onay bekliyor', state: 'pending' },
      ],
    },
    report: {
      title: 'Akşam, günün dürüst bir özeti.',
      body: 'Sayılar gerçek kayıtlardan gelir. Başarısız olan her şey nedeniyle birlikte yazılır.',
      example: 'Örnek',
      heading: 'Günün özeti',
      asOf: '21:00 itibarıyla',
      metrics: [
        { label: 'Gelen mesaj', value: '14' },
        { label: 'Gönderilen yanıt', value: '11' },
        { label: 'Size iletilen', value: '2' },
        { label: 'Yanıt bekleyen', value: '1' },
        { label: 'Yayınlanan paylaşım', value: '0' },
        { label: 'Sıradaki paylaşım', value: 'Yarın 19:00' },
      ],
      footerNote: 'Planlanan paylaşım, Instagram yayınlandığını doğrulayana kadar “yayınlanan” sayılmaz.',
    },
    limits: {
      eyebrow: 'Son söz sizde',
      title: 'Bazı mesajlar her zaman size gelir.',
      body: 'Bunlara otomatik yanıt verilmez. Mesaj size bildirilir, yanıtı siz yazarsınız.',
      escalateBadge: 'Size iletilir',
      escalate: [
        { title: 'Şikâyetler', example: '“Bugünkü ders çok kalabalıktı, memnun kalmadım.”' },
        { title: 'İade talepleri', example: '“Bu ay gelemedim, kalan derslerimin iadesini alabilir miyim?”' },
        { title: 'İndirim ve pazarlık', example: '“İki arkadaş yazılırsak indirim yapar mısınız?”' },
        { title: 'Emin olamadığı her şey', example: '“Bel fıtığım var, hangi eğitmenle çalışmam uygun olur?”' },
      ],
    },
    trust: {
      eyebrow: 'Kontrol ve güvenlik',
      title: 'Kontrol sizde. Verileriniz de.',
      body: 'Neyin otomatik olacağına siz karar verirsiniz. Her işlemin kim tarafından, ne zaman yapıldığı kayıtlıdır.',
      controlTitle: 'Kontrol',
      control: [
        {
          title: 'Neyin otomatik olacağını siz seçersiniz',
          body: 'Örneğin saat ve adres soruları otomatik yanıtlanır, fiyat soruları onayınıza gelir.',
        },
        {
          title: 'Konuşmayı devralabilirsiniz',
          body: 'Müşteriyle kendiniz konuşurken otomasyon o konuşmada durur; bıraktığınızda devam eder.',
        },
        {
          title: 'Ekibinize uygun roller',
          body: 'Personel taslak hazırlar. Fiyat değişikliği ve yayın sizin onayınızla olur.',
        },
        {
          title: 'Her işlemin kaydı',
          body: 'Ne gönderildi, kim onayladı, ne zaman oldu. Hepsi tek bir listede.',
        },
      ],
      securityTitle: 'Güvenlik',
      security: [
        {
          title: 'Instagram şifreniz bize gelmez',
          body: 'Hesap, Instagram’ın resmi giriş ekranıyla bağlanır. Bağlantıyı istediğiniz an kaldırırsınız.',
        },
        {
          title: 'Onaylar tek kullanımlık',
          body: 'Her onay bir işleme ve onun son haline bağlıdır. Metin değişirse onay geçersiz olur.',
        },
        {
          title: 'İşletmeniz kendi alanında',
          body: 'Her işletmenin verisi ayrı tutulur; başka bir işletme sizinkini göremez.',
        },
        {
          title: 'Silme hakkı sizde',
          body: 'Bağlantıyı kaldırdığınızda ilgili veriler silinir. Silme talebinizi her zaman iletebilirsiniz.',
        },
      ],
    },
    faq: {
      eyebrow: 'Sorular',
      title: 'Sık sorulanlar',
      body: 'Cevabını bulamadığınız bir şey varsa pilot formuna yazın, sizi arayalım.',
      items: [
        {
          q: 'Instagram şifremi vermem gerekiyor mu?',
          a: 'Hayır. Hesabınızı Instagram’ın resmi giriş ekranıyla bağlarsınız, şifreniz bize hiç gelmez. Bağlantıyı istediğiniz an kaldırabilirsiniz, ilgili veriler de silinir.',
        },
        {
          q: 'Müşterime yanlış bir şey yazarsa?',
          a: 'Fiyat, saat, adres ve kampanya bilgilerini yalnızca sizin doğruladıklarınızdan alır ve her yanıt gönderilmeden önce bu açıdan kontrol edilir. Emin olamadığı mesajları size bırakır.',
        },
        {
          q: 'Gece gelen mesajlar ne olur?',
          a: 'Rutin sorular için otomatik yanıtı açtıysanız hemen yanıtlanır. Açmadıysanız taslak hazır bekler, siz uygun olduğunuzda onaylarsınız. Instagram’ın 24 saatlik yanıt kuralına uyar.',
        },
        {
          q: 'WhatsApp’tan yönetebilir miyim?',
          a: 'Şimdilik hayır. Telefonunuzdaki web uygulamasını ya da Telegram’ı kullanırsınız; ikisinde de aynı onaylar ve bildirimler var. WhatsApp’ı pilot işletmelerin geri bildirimine göre değerlendiriyoruz.',
        },
        {
          q: 'Gönderi yorumlarına da yanıt veriyor mu?',
          a: 'Henüz değil. Yorum yanıtları, Meta’nın gerekli izinleri gerçek hesaplarda doğrulandıktan sonra açılacak. O zamana kadar yorumlar sizde kalır.',
        },
        {
          q: 'Kurulumu kendim yapabilir miyim?',
          a: 'Evet. İşletme türünüzü seçer, biyografinizi ya da fiyat listenizi yapıştırırsınız; bilgileri o ayıklar, siz tek tek doğrularsınız. Pilot süresince isterseniz birlikte de kuruyoruz.',
        },
        {
          q: 'Ekibim de kullanabilir mi?',
          a: 'Evet. Ekip üyelerini davet edersiniz. Personel yanıt ve paylaşım taslağı hazırlar; fiyat değişikliği ve yayın işletme sahibi ya da yöneticinin onayıyla olur.',
        },
        {
          q: 'Pilot bitince ne olacak?',
          a: 'Pilot 30 gün ücretsizdir ve kart bilgisi istemiyoruz. Devam etmek isterseniz pilot işletmelere 12 ay sabit kurucu fiyatı sunuyoruz. Kendiliğinden ücretlendirme yoktur; devam etmezseniz bağlantıyı kaldırırsınız, verileriniz silinir.',
        },
      ],
    },
    pilot: {
      eyebrow: 'Pilot programı',
      title: 'İşletmenize daha çok zaman ayırın.',
      body:
        'Mesajları ve paylaşımları daha az uğraşla yönetmeyi 30 gün ücretsiz deneyin. Instagram’ı aktif kullanan 10–15 yerel işletmeyle başlıyoruz. Başvurunuzdan sonra sizi arayıp ihtiyaçlarınızı konuşuruz.',
      expectations: [
        {
          badge: '30 dakika',
          title: 'Kurulumu birlikte yapıyoruz',
          detail: 'Yerinde ya da görüntülü; fiyat ve saatlerinizi birlikte girip 5 gerçek müşteri sorusuyla deneriz.',
        },
        {
          badge: '30 gün ücretsiz',
          title: 'Ücret ve kart bilgisi yok',
          detail: 'Kendi müşterilerinizle, gerçek iş akışınızda deneyin. Memnun kalmazsanız bağlantıyı kaldırın.',
        },
        {
          badge: 'Birebir destek',
          title: 'Kurucu ekiple doğrudan çalışırsınız',
          detail: 'Çağrı merkezi değil; işletmenizi tanıyan, doğrudan ulaşabileceğiniz küçük bir ekip.',
        },
        {
          badge: 'Resmi bağlantı',
          title: 'Şifreniz sizde kalır',
          detail: 'Instagram’ın resmi giriş ekranı. Bağlantıyı kestiğiniz an erişim durur.',
        },
      ],
      nextStepsTitle: 'Başvurudan sonra',
      nextSteps: [
        { title: '24 saat içinde', body: 'Sizi kısaca arar ya da mesaj atarız.' },
        { title: 'Uygun bir günde', body: 'Kurulumu 30 dakikada birlikte tamamlarız.' },
        { title: 'Sonrasında', body: 'Taslaklar ve onaylar telefonunuza gelir.' },
      ],
      whatsappDirectLabel: 'Form doldurmak istemiyor musunuz? Bize WhatsApp’tan yazın',
      whatsappPrefill: `Merhaba, ${PRODUCT_NAME} pilot programı hakkında bilgi almak istiyorum.`,
    },
    form: {
      title: 'Pilot başvurusu',
      subtitle: 'Yaklaşık 1 dakika sürer.',
      categoryLabel: 'İşletme türü',
      categories: [
        'Güzellik / Bakım',
        'Kafe / Restoran',
        'Mağaza / Butik',
        'Spor / Pilates',
        'Klinik / Sağlık',
        'Hizmet işletmesi',
        'Diğer',
      ],
      business: 'İşletme adı',
      instagram: 'Instagram hesabı',
      instagramHint: '@kullaniciadi',
      contact: 'E-posta',
      contactHint: 'Size buradan ulaşacağız',
      city: 'Şehir',
      consent:
        'Bilgilerimin yalnızca pilot programı hakkında benimle iletişime geçmek için kullanılmasını kabul ediyorum. Bilgilerim başkasıyla paylaşılmaz ve istediğimde silinir.',
      submit: 'Başvuruyu gönder',
      sending: 'Gönderiliyor…',
      required: 'Bu alan gerekli.',
      invalidEmail: 'Geçerli bir e-posta adresi girin.',
      consentRequired: 'Devam etmek için onay kutusunu işaretleyin.',
      sent: 'Teşekkürler, başvurunuz alındı. 24 saat içinde size ulaşacağız.',
      preview: 'Önizleme: bu form henüz bir yere bağlı değil. Bilgileriniz gönderilmedi.',
      failed: 'Gönderilemedi. Bağlantınızı kontrol edip tekrar deneyin.',
    },
    mobileCta: { label: 'Ücretsiz pilota başvurun', sub: '30 gün · kart yok' },
    footer: {
      tagline: 'Instagram’a daha az vakit, işletmenize daha çok zaman. Kontrol her zaman sizde.',
      trademark:
        'Instagram ve WhatsApp, Meta Platforms, Inc.’in ticari markalarıdır; Telegram, sahibinin ticari markasıdır. Bu ürün bu şirketlerle bağlantılı değildir.',
      top: 'Başa dön',
    },
  },
  en: {
    meta: {
      title: `${PRODUCT_NAME} · An Instagram assistant for small businesses`,
      description:
        'Save time on Instagram and keep track of customer messages. AgentNest drafts replies using your business details and plans your posts. You stay in control.',
    },
    nav: {
      links: [
        { id: 'nasil', label: 'How it works' },
        { id: 'demo', label: 'Examples' },
        { id: 'guven', label: 'Security' },
        { id: 'sss', label: 'Questions' },
      ],
      cta: 'Apply for the pilot',
      language: 'Language',
      toDark: 'Switch to dark theme',
      toLight: 'Switch to light theme',
      skip: 'Skip to content',
      menu: 'Menu',
    },
    hero: {
      badge: 'Free pilot programme · Applications open',
      title: 'Let Instagram grow your business,',
      accent: 'not take up your day.',
      lead:
        `${PRODUCT_NAME} drafts replies to customer messages using your business details, plans your posts and brings important conversations to you. You always stay in control.`,
      cta: 'Apply for the free pilot',
      secondary: 'See how it works',
      points: ['Free for 30 days', 'No card needed', '30-minute setup'],
    },
    preview: {
      example: 'Example screen',
      screen: 'Today',
      greeting: 'Good morning, Anna',
      date: 'Tuesday, 10 November',
      waitingTitle: 'Waiting for you',
      queue: ['Replies awaiting approval', 'Conversations passed to you', 'Posts on hold'],
      queueCounts: [2, 1, 1],
      metricsTitle: 'Today',
      metrics: ['Messages received', 'Replies sent', 'Posts published'],
      metricValues: [14, 11, 1],
      customer: 'anna.berg',
      time: '23:47',
      message: 'Hi! How much is a monthly membership? Do you have a trial class?',
      reply: ['Hi Anna, a monthly membership is ', ' and your first trial class is ', '. Shall we find a day that suits you?'],
      facts: ['₺6,000', 'free'],
      pending: 'Awaiting approval',
      sent: 'Sent',
      approve: 'Approve and send',
      undo: 'Show again',
    },
    promises: [
      {
        title: 'Save time on recurring questions.',
        body: 'Replies about prices, hours and your address are ready using details you verified. No need to write them from scratch each time.',
      },
      {
        title: 'Keep customer messages in view.',
        body: 'See messages awaiting a reply and important conversations passed to you in one place. Approve prepared replies with one tap.',
      },
      {
        title: 'Keep posts off your last-minute list.',
        body: 'Plan content ahead and publish with your approval. See what has been published and what is still waiting.',
      },
    ],
    audience: {
      label: 'Made for',
      items: ['Pilates and fitness studios', 'Beauty salons', 'Cafés', 'Boutiques', 'Clinics', 'Service businesses'],
    },
    problem: {
      eyebrow: 'More time for your business',
      title: 'One less task between customers.',
      body:
        'While you look after customers, messages pile up, the same questions return and posts get postponed. AgentNest prepares replies and plans so you can focus on what needs you.',
      withoutLabel: 'Today',
      withLabel: `With ${PRODUCT_NAME}`,
      rows: [
        {
          scenario: 'A “How much per month?” DM at 23:45',
          without: 'Seen late after a long day or left until morning. While waiting, the customer messages another studio.',
          withProduct:
            'A draft is ready right away with your verified price. You send it with one tap, or it goes out automatically if you chose that.',
        },
        {
          scenario: 'The worry: “What if it quotes the wrong price?”',
          without: 'Generic AI bots guess missing details, invent discounts and get pulled into haggling.',
          withProduct: 'It uses only details you verified. If a question is not on record, it does not guess; it passes it to you.',
        },
        {
          scenario: 'Scheduled posts forgotten when a price changes',
          without: 'You update the price, but Friday’s scheduled story still goes out with the old one.',
          withProduct: 'The moment you enter the new price, scheduled posts that show the old one are put on hold automatically.',
        },
      ],
    },
    how: {
      eyebrow: 'How it works',
      title: 'Four steps, each one a system you understand.',
      body: 'After setup, your job is to approve. Where the assistant does not know something, it stops and asks you.',
      steps: [
        {
          title: 'You give it your details',
          body: 'Paste your price list or bio. It picks out the facts and you verify them one by one.',
        },
        {
          title: 'A DM arrives, a draft is ready',
          body: 'As soon as an Instagram DM comes in, a reply is drafted from verified details.',
        },
        {
          title: 'You approve',
          body: 'Send with one tap, edit, or take over the conversation. Routine questions can run automatically.',
        },
        {
          title: 'You get the evening summary',
          body: 'How many messages came in, what was sent, what is waiting. Numbers come from real records.',
        },
      ],
    },
    knowledge: {
      eyebrow: 'Source of truth',
      title: 'It knows your business from what you tell it.',
      body:
        'No spreadsheets or technical dashboards. Paste the price message you already send customers; the prices, hours and offers in it become fact cards. Drafts use only the ones you verified.',
      pasteLabel: 'The text you paste',
      pasteSample:
        'Reformer Pilates Studio · Weekdays 08:00–21:00 · Monthly membership (2x/week) ₺6,000. Your first trial class is free. Address: Bahçelievler Mah. No: 12',
      pasteNote: 'Picking out a fact never verifies it.',
      ledgerTitle: 'Your fact cards',
      progress: '{n} of {total} verified',
      verified: 'Verified',
      unverified: 'Not verified',
      verify: 'Verify',
      reset: 'Show again',
      usageNote: 'An unverified fact is never used in a draft.',
      facts: [
        { category: 'Price', label: 'Monthly membership (2x/week)', value: '₺6,000' },
        { category: 'Offer', label: 'First trial class', value: 'Free' },
        { category: 'Hours', label: 'Weekday opening hours', value: '08:00 – 21:00' },
        { category: 'Address', label: 'Studio location', value: 'Bahçelievler Mah. No: 12' },
      ],
    },
    demo: {
      eyebrow: 'Customer messages',
      title: 'Every price has a source.',
      body:
        'Every price and offer in a draft comes from a fact you verified, and its source is listed underneath. If a fact is not on record, no draft is written; the question comes to you.',
      points: [
        { title: 'A draft with sources', body: 'Every highlighted fact shows which card it came from.' },
        { title: 'One-tap approval', body: 'Send it, edit it or take over the conversation.' },
        { title: 'It stops when it does not know', body: 'No draft for a question that is not on record; it asks you.' },
      ],
      tabs: ['Fact on record', 'Fact not on record'],
      example: 'Example screen',
      channel: 'Instagram DM',
      known: {
        customer: 'anna.berg',
        time: '23:47',
        message: 'Hi! How much is a monthly membership? Do you have a trial class?',
        draftLabel: 'Draft reply',
        draft: ['Hi Anna, a monthly membership is ', ' and your first trial class is ', '. Shall we find a day that suits you?'],
        facts: [
          { value: '₺6,000', source: 'Monthly membership · Price · verified 12 Oct' },
          { value: 'free', source: 'First trial class · Offer · verified 3 Oct' },
        ],
        approve: 'Approve and send',
        edit: 'Edit',
        editAlt: '. Would you like to pick a day this week together?',
        editing: 'Edited',
        saveEdit: 'Other phrasing',
        pending: 'Awaiting approval',
        sent: 'Sent · 23:48',
        replay: 'Show again',
        hint: 'Tap a highlighted fact to see its source.',
      },
      unknown: {
        customer: 'emma.k',
        time: '21:12',
        message: 'Do you offer prenatal Pilates?',
        badge: 'Passed to you',
        title: 'No draft written',
        body: 'There is no verified fact about this. Instead of guessing, the assistant stopped and asked you.',
        questionLabel: 'The assistant asks you',
        question: 'Nothing is on record about “prenatal Pilates”. What should we tell the customer?',
        answer: 'You write the reply',
        afterAnswer: 'If you save your answer as a fact, it is used the next time someone asks.',
      },
    },
    owner: {
      eyebrow: 'Run it from your phone',
      title: 'Write, ask, approve with a tap.',
      body:
        'Text a price change, send a photo, ask for today’s summary. Anything important comes back to you as a confirmation with buttons.',
      channels: [
        {
          title: 'The web app on your phone',
          body: 'Nothing to install. Today, the inbox and approvals in one place.',
        },
        {
          title: 'Telegram',
          body: 'Notifications and approvals arrive as a chat. You link your account with a one-time code.',
        },
      ],
      note: 'Typing “ok” never approves anything. Every approval is a button tied to one action; it works once and expires.',
      example: 'Example chat',
      bot: PRODUCT_NAME,
      botSub: 'bot',
      today: 'Today',
      placeholder: 'Message',
      chat: [
        { from: 'owner', text: 'Monthly membership is 7,000 now', time: '09:12' },
        {
          from: 'assistant',
          text: 'Change the monthly membership from ₺6,000 to ₺7,000?',
          time: '09:12',
          actions: ['Yes, update', 'Cancel'],
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
          text: 'Story draft ready for tomorrow at 19:00. Approve and I will schedule it.',
          time: '09:14',
          actions: ['Approve', 'Reject'],
        },
      ],
      commandsTitle: 'Other things you can write',
      commandsHint: 'Tap one to see it in the chat',
      commands: [
        { ask: 'How many DMs today?', answer: '14 messages. 11 answered, 2 passed to you, 1 waiting for a reply.' },
        { ask: 'What is waiting for me?', answer: '2 replies and 1 post are waiting for your approval.', action: 'Open approvals' },
        {
          ask: 'Make a story for the trial class.',
          answer: 'The draft is ready. Its price and date come from verified facts.',
          action: 'See draft',
        },
        {
          ask: 'Make the replies a bit friendlier.',
          answer: 'Make the reply tone friendlier? It applies to new drafts.',
          action: 'Yes, update',
        },
        {
          ask: 'Why didn’t yesterday’s post go out?',
          answer: 'Instagram rejected the image because its ratio was not supported. Send a new image and I will prepare it again.',
        },
        { ask: 'Cancel tomorrow’s post.', answer: 'Cancel tomorrow’s 19:00 story?', action: 'Cancel post' },
      ],
    },
    content: {
      eyebrow: 'Posts',
      title: 'Your posts, planned and checked.',
      body: 'Say what you want to post. The draft uses verified details, you approve it, and it goes out at the set time.',
      note: 'Scheduled does not mean published. You hear when a post actually goes out, and if it fails, you hear why.',
      example: 'Example',
      heading: 'This week',
      heldReason: 'Put on hold automatically because the price changed from ₺6,000 to ₺7,000.',
      posts: [
        { day: 'Mon', time: '19:00', kind: 'Story', title: 'Trial class', status: 'Published', state: 'published' },
        { day: 'Wed', time: '12:30', kind: 'Post', title: 'Morning reformer group', status: 'Scheduled', state: 'scheduled' },
        { day: 'Fri', time: '19:00', kind: 'Story', title: 'Membership offer', status: 'On hold', state: 'held' },
        { day: 'Sun', time: '10:00', kind: 'Post', title: 'Weekend hours', status: 'Awaiting approval', state: 'pending' },
      ],
    },
    report: {
      title: 'Each evening, an honest account of the day.',
      body: 'Every number comes from real records. Anything that failed is listed with the reason.',
      example: 'Example',
      heading: 'Daily summary',
      asOf: 'As of 21:00',
      metrics: [
        { label: 'Messages received', value: '14' },
        { label: 'Replies sent', value: '11' },
        { label: 'Passed to you', value: '2' },
        { label: 'Awaiting reply', value: '1' },
        { label: 'Posts published', value: '0' },
        { label: 'Next post', value: 'Tomorrow 19:00' },
      ],
      footerNote: 'A scheduled post is not counted as published until Instagram confirms it went live.',
    },
    limits: {
      eyebrow: 'You have the final say',
      title: 'Some messages always come to you.',
      body: 'These never get an automatic reply. You are notified and you write the answer.',
      escalateBadge: 'Passed to you',
      escalate: [
        { title: 'Complaints', example: '“Today’s class was too crowded, I wasn’t happy with it.”' },
        { title: 'Refund requests', example: '“I couldn’t come this month, can I get a refund for my remaining sessions?”' },
        { title: 'Discounts and haggling', example: '“If two of us sign up together, can we get a discount?”' },
        { title: 'Anything it isn’t sure about', example: '“I have a herniated disc, which instructor would suit me?”' },
      ],
    },
    trust: {
      eyebrow: 'Control and security',
      title: 'You stay in control. So does your data.',
      body: 'You decide what runs automatically. Every action is recorded with who did it and when.',
      controlTitle: 'Control',
      control: [
        {
          title: 'You choose what runs automatically',
          body: 'For example, hours and address questions are answered automatically, price questions come to you.',
        },
        {
          title: 'Take over any conversation',
          body: 'While you talk to a customer yourself, automation pauses for that conversation; hand it back and it continues.',
        },
        {
          title: 'Roles that fit your team',
          body: 'Staff draft replies and posts. Price changes and publishing need your approval.',
        },
        {
          title: 'Every action recorded',
          body: 'What was sent, who approved it and when. All of it in one list.',
        },
      ],
      securityTitle: 'Security',
      security: [
        {
          title: 'Your Instagram password never reaches us',
          body: 'Your account connects through Instagram’s official login. Disconnect whenever you like.',
        },
        {
          title: 'Single-use approvals',
          body: 'Each approval is tied to one action and its exact final version. If the text changes, the approval no longer counts.',
        },
        {
          title: 'Your business, its own space',
          body: 'Each business’s data is kept separate; no other business can see yours.',
        },
        {
          title: 'You can have it deleted',
          body: 'When you disconnect, the related data is deleted. You can ask for deletion at any time.',
        },
      ],
    },
    faq: {
      eyebrow: 'Questions',
      title: 'Frequently asked',
      body: 'Something not covered here? Write it in the pilot form and we will call you.',
      items: [
        {
          q: 'Do I have to give you my Instagram password?',
          a: 'No. You connect your account through Instagram’s official login, and your password never reaches us. You can disconnect at any time, and the related data is deleted.',
        },
        {
          q: 'What if it tells a customer something wrong?',
          a: 'Prices, hours, addresses and offers come only from details you verified, and every reply is checked for them before it is sent. Messages it is unsure about are left to you.',
        },
        {
          q: 'What happens to messages at night?',
          a: 'If you switched on automatic replies for routine questions, they are answered right away. If not, the draft waits for you to approve when it suits you. It follows Instagram’s 24-hour reply rule.',
        },
        {
          q: 'Can I run it from WhatsApp?',
          a: 'Not yet. You use the web app on your phone or Telegram; both have the same approvals and notifications. We are considering WhatsApp based on pilot feedback.',
        },
        {
          q: 'Does it reply to post comments too?',
          a: 'Not yet. Comment replies will be switched on once the required Meta permissions are verified on real accounts. Until then, comments stay with you.',
        },
        {
          q: 'Can I set it up myself?',
          a: 'Yes. Choose your business type, paste your bio or price list, and it picks out the details for you to verify one by one. During the pilot we can also set it up with you.',
        },
        {
          q: 'Can my team use it?',
          a: 'Yes. You invite team members. Staff draft replies and posts; price changes and publishing need the owner’s or a manager’s approval.',
        },
        {
          q: 'What happens after the pilot?',
          a: 'The pilot is free for 30 days and needs no card. If you want to continue, pilot businesses get a founder price fixed for 12 months. Nothing is charged automatically; if you stop, you disconnect and your data is deleted.',
        },
      ],
    },
    pilot: {
      eyebrow: 'Pilot programme',
      title: 'Make more time for your business.',
      body:
        'Try managing messages and posts with less effort, free for 30 days. We are starting with 10–15 local businesses that use Instagram actively. After you apply, we call you to discuss your needs.',
      expectations: [
        {
          badge: '30 minutes',
          title: 'We set it up together',
          detail: 'In person or on a video call, we enter your prices and hours and try 5 real customer questions.',
        },
        {
          badge: 'Free for 30 days',
          title: 'No fee, no card',
          detail: 'Try it with your own customers in your real workflow. Not for you? Disconnect.',
        },
        {
          badge: 'Direct support',
          title: 'You work with the founding team',
          detail: 'No ticket queue; a small team that knows your business and that you can reach directly.',
        },
        {
          badge: 'Official login',
          title: 'Your password stays yours',
          detail: 'Instagram’s official login screen. Disconnect and access stops immediately.',
        },
      ],
      nextStepsTitle: 'After you apply',
      nextSteps: [
        { title: 'Within 24 hours', body: 'We call or message you briefly.' },
        { title: 'On a day that suits you', body: 'We finish the 30-minute setup together.' },
        { title: 'From then on', body: 'Drafts and approvals come to your phone.' },
      ],
      whatsappDirectLabel: 'Prefer not to fill in a form? Message us on WhatsApp',
      whatsappPrefill: `Hi, I would like to learn more about the ${PRODUCT_NAME} pilot programme.`,
    },
    form: {
      title: 'Pilot application',
      subtitle: 'Takes about a minute.',
      categoryLabel: 'Business type',
      categories: ['Beauty / Salon', 'Café / Restaurant', 'Shop / Retail', 'Fitness / Pilates', 'Clinic / Health', 'Services', 'Other'],
      business: 'Business name',
      instagram: 'Instagram account',
      instagramHint: '@username',
      contact: 'Email',
      contactHint: 'This is how we will reach you',
      city: 'City',
      consent:
        'I agree that my details are used only to contact me about the pilot programme. They are not shared with anyone and are deleted when I ask.',
      submit: 'Send application',
      sending: 'Sending…',
      required: 'This field is required.',
      invalidEmail: 'Enter a valid email address.',
      consentRequired: 'Tick the consent box to continue.',
      sent: 'Thank you, we received your application. We will be in touch within 24 hours.',
      preview: 'Preview: this form is not connected yet. Nothing was sent.',
      failed: 'Could not send. Check your connection and try again.',
    },
    mobileCta: { label: 'Apply for the free pilot', sub: '30 days · no card' },
    footer: {
      tagline: 'Less time on Instagram. More time for your business. Always in your control.',
      trademark:
        'Instagram and WhatsApp are trademarks of Meta Platforms, Inc.; Telegram is a trademark of its owner. This product is not affiliated with these companies.',
      top: 'Back to top',
    },
  },
}
