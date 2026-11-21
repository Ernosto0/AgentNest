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
type Packaged = Titled & { badge?: string }

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
    source: string
    sent: string
    showSource: string
    hideSource: string
  }
  promises: Titled[]
  audience: { label: string; items: string[] }
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
      facts: { value: string; source: string }[]
      sent: string
      hint: string
    }
    unknown: {
      customer: string
      time: string
      message: string
      badge: string
      body: string
      questionLabel: string
      question: string
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
  trust: {
    eyebrow: string
    title: string
    body: string
    controlTitle: string
    control: Titled[]
    securityTitle: string
    security: Titled[]
  }
  // The local package (D-06). Five items, in this order: language, KVKK documents, invoice,
  // setup, verified-price guarantee. The price is not copy: it comes from config.ts.
  localPackage: {
    eyebrow: string
    title: string
    body: string
    items: [Packaged, Packaged, Packaged, Packaged, Packaged]
    legalLabel: string
    legal: { label: string; path: string }[]
    priceLabel: string
    cta: string
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
        'Pivoris rutin Instagram mesajlarını otomatik yanıtlar, yorumları özel sohbete taşır ve içeriklerinizi planlar. Telegram’dan yönetin, WhatsApp’tan gelişmeleri takip edin.',
    },
    nav: {
      links: [
        {
          id: 'otomasyon',
          label: 'Otomasyon',
        },
        {
          id: 'yonetim',
          label: 'Sohbetten yönetim',
        },
        {
          id: 'yetenekler',
          label: 'Yetenekler',
        },
        {
          id: 'paket',
          label: 'Paket',
        },
        {
          id: 'sss',
          label: 'Sorular',
        },
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
      title: 'Siz işletmenize odaklanın.',
      accent: 'Rutin işleri Pivoris halletsin.',
      lead: 'Müşteri sorularını güncel bilgilerinizle otomatik yanıtlasın, yorumları özel sohbette karşılasın, içeriklerinizi hazırlayıp planlasın. Telegram’dan talimat verin; önemli gelişmeler seçtiğiniz kanala gelsin.',
      cta: 'Ücretsiz pilota başvurun',
      secondary: 'Otomasyonu keşfedin',
      points: ['30 gün ücretsiz', 'Kart bilgisi yok', 'Kurulum 30 dakika'],
    },
    preview: {
      example: 'Örnek ekran',
      screen: 'Rutin iletişim',
      greeting: 'Günaydın, Ayşe',
      date: 'Salı, 10 Kasım',
      waitingTitle: 'Asistanınızın bugünü',
      queue: ['Otomatik yanıtlanan konuşma', 'Size iletilen konuşma', 'Sıradaki paylaşım'],
      queueCounts: [11, 2, 1],
      metricsTitle: 'Bugün',
      metrics: ['Gelen mesaj', 'Otomatik yanıt', 'Size iletilen'],
      metricValues: [14, 11, 2],
      customer: 'ayse.yilmaz',
      time: '23:47',
      message: 'Merhaba, aylık üyelik ne kadar?',
      reply: ['Merhaba! Aylık üyeliğimiz ', '. ', ''],
      facts: ['6.000 ₺', ''],
      source: 'Aylık üyelik · Doğrulanmış fiyat',
      sent: 'Otomatik yanıtlandı',
      showSource: 'Yanıtın kaynağını görün',
      hideSource: 'Kaynağı gizle',
    },
    promises: [
      {
        title: 'Rutin sorular kendiliğinden yanıtlansın.',
        body: 'Fiyat, saat, adres ve hizmet sorularını güncel işletme bilgilerinizle karşılasın. Her mesaj için telefonunuza uzanmayın.',
      },
      {
        title: 'İşletmenizi sohbetten yönetin.',
        body: 'Telegram’dan fotoğraf gönderin, içerik hazırlatın, günün özetini sorun. Bildirimler için WhatsApp’ı da seçebilirsiniz.',
      },
      {
        title: 'İlgi, konuşmada kaybolmasın.',
        body: 'Yorumdan özel mesaja, müsaitlikten randevuya uzanan akışları ve geri dönüş bekleyen müşterileri bir arada takip edin.',
      },
    ],
    audience: {
      label: 'Kimler için',
      items: [
        'Pilates ve spor stüdyoları',
        'Güzellik salonları',
        'Kafeler',
        'Butikler',
        'Klinikler',
        'Hizmet işletmeleri',
      ],
    },
    how: {
      eyebrow: 'Nasıl çalışır',
      title: 'İşletmenizi öğretin. Rutin işleri devredin.',
      body: 'Bir kez kurun; asistanınız müşteri sorularını karşılasın. Siz sohbetten yönetin ve günün sonunda neler olduğunu görün.',
      steps: [
        {
          title: 'İşletmenizi tanıtın',
          body: 'Web sitenizden, Instagram profilinizden veya fiyat listenizden başlayın. Kullanılacak bilgileri doğrulayın.',
        },
        {
          title: 'Otomasyonu seçin',
          body: 'Rutin DM ve yorum yanıtlarını otomatiğe alın. Üslubu ve asistanınızın yapabileceği işleri belirleyin.',
        },
        {
          title: 'Asistanınız çalışsın',
          body: 'Soruları güncel bilgilerinizle yanıtlasın, konuşmanın bağlamını korusun, eksik bilgiyi gerektiğinde size sorsun.',
        },
        {
          title: 'Sohbetten takip edin',
          body: 'Telegram’dan görev verin. Günlük özetler ve önemli gelişmeler uygulama, Telegram veya WhatsApp’ınıza gelsin.',
        },
      ],
    },
    knowledge: {
      eyebrow: 'Bilgi kaynağı',
      title: 'Bir kez öğretin, her yanıtta güncel kalsın.',
      body: 'Web sitenizden ve Instagram profilinizden bilgi önerileri alın veya hazır fiyat mesajınızı yapıştırın. Doğruladığınız fiyatlar, saatler ve hizmetler hem müşteri yanıtlarına hem içeriklere kaynak olsun.',
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
      usageNote:
        'Güncellenen bilgi gelecekteki yanıtlara yansır; eski kaynağa bağlı içerikler incelemeye alınır.',
      facts: [
        { category: 'Fiyat', label: 'Aylık üyelik (haftada 2)', value: '6.000 ₺' },
        { category: 'Kampanya', label: 'İlk deneme dersi', value: 'Ücretsiz' },
        { category: 'Saatler', label: 'Hafta içi çalışma saatleri', value: '08:00 – 21:00' },
        { category: 'Adres', label: 'Stüdyo konumu', value: 'Bahçelievler Mah. No: 12' },
      ],
    },
    demo: {
      eyebrow: 'Otomatik müşteri iletişimi',
      title: 'Soru geldi. Yanıt gitti. Siz işinize devam ettiniz.',
      body: 'Rutin sorularda yanıt hazırlamakla kalmaz, etkinleştirdiğiniz otomasyonla doğrudan gönderir. Fiyat ve saat gibi bilgiler doğruladığınız kayıtlardan gelir.',
      points: [
        {
          title: 'Rutin sorularda otomatik gönderim',
          body: 'Selamlama, çalışma saatleri, adres, hizmet ve uygun standart fiyat soruları kendi akışında yanıtlanır.',
        },
        {
          title: 'İşletmenizin bilgisiyle konuşur',
          body: 'Yanıttaki fiyatın kaynağı bellidir. Bir değişiklik yaptığınızda sonraki yanıtlar güncel bilgiyi kullanır.',
        },
        {
          title: 'Gerektiğinde sizi sohbete dahil eder',
          body: 'Eksik bilgi veya özel bir talep varsa size sorar. Her rutin mesajı sizin yazmanız gerekmez.',
        },
      ],
      tabs: ['Otomatik yanıt', 'Size ihtiyaç var'],
      example: 'Örnek ekran',
      channel: 'Instagram DM',
      known: {
        customer: 'ayse.yilmaz',
        time: '23:47',
        message: 'Merhaba, aylık üyelik ne kadar?',
        draftLabel: 'Pivoris yanıtladı',
        draft: ['Merhaba! Aylık üyeliğimiz ', '. ', ''],
        facts: [
          {
            value: '6.000 ₺',
            source: 'Aylık üyelik · Fiyat · 12 Ekim’de doğrulandı',
          },
        ],
        sent: 'Otomatik gönderildi · 23:47',
        hint: 'Kaynağı görmek için fiyata dokunun.',
      },
      unknown: {
        customer: 'elif.k',
        time: '21:12',
        message: 'Hamile pilatesi dersiniz var mı?',
        badge: 'Size iletildi',
        body: 'Bu konuda doğrulanmış bir bilgi yok. Asistan tahmin etmek yerine durdu ve size sordu.',
        questionLabel: 'Asistanın size sorusu',
        question: '“Hamile pilatesi dersi” hakkında kayıtlı bilgi yok. Müşteriye ne söyleyelim?',
        afterAnswer: 'Cevabınızı bilgi olarak eklerseniz, bir dahaki benzer soruda onu kullanır.',
      },
    },
    owner: {
      eyebrow: 'Sohbetten yönetim',
      title: 'İşletmenize bir mesaj kadar yakın.',
      body: 'Telegram’dan talimat verin, fotoğraf gönderin, asistandan bilgi alın. Günün özetini ve önemli gelişmeleri uygulama, Telegram veya WhatsApp üzerinden takip edin.',
      channels: [
        {
          title: 'Telegram',
          body: 'Komutlar, fotoğraftan içerik hazırlama, asistana görev verme, sorulara yanıt ve günlük özetler.',
        },
        {
          title: 'WhatsApp',
          body: 'Günlük özetler, önemli bildirimler ve desteklenen mesajlaşma süresi içinde onay/ret butonları. Serbest metinle komut verme Telegram’da.',
        },
        {
          title: 'Web uygulaması',
          body: 'Gelen kutusu, içerik takvimi, müşteri listeleri ve asistan ayarları. Telefonunuzdan veya bilgisayarınızdan.',
        },
      ],
      note: 'Rutin müşteri iletişimi otomatik ilerler. Randevu değişiklikleri, yayınlama ve özel talepler gibi karar gerektiren işler size gelir. Kullanılabilir kanallar ve işlemler hesap bağlantınıza bağlıdır.',
      example: 'Örnek sohbet',
      bot: PRODUCT_NAME,
      botSub: 'Telegram · İşletme asistanınız',
      today: 'Bugün',
      placeholder: 'Mesaj yazın',
      chat: [
        {
          from: 'owner',
          time: '09:12',
          attachment: {
            kicker: 'Reformer Pilates',
            title: 'Deneme dersi',
            note: 'ücretsiz',
          },
          text: 'Bu fotoğrafla deneme dersi için bir story hazırla.',
        },
        {
          from: 'assistant',
          time: '09:12',
          text: 'Fotoğrafı aldım. Deneme dersi bilginizle bir Story taslağı hazırlıyorum.',
        },
        {
          from: 'owner',
          time: '09:14',
          text: 'Bugün kaç DM geldi?',
        },
        {
          from: 'assistant',
          time: '09:14',
          text: '14 mesaj geldi. 11 konuşma otomatik yanıtlandı; 2 konuşma size iletildi, 1 mesaj yanıt bekliyor.',
        },
      ],
      commandsTitle: 'Telegram’dan neler isteyebilirsiniz?',
      commandsHint: 'Sohbette görmek için birine dokunun',
      commands: [
        {
          ask: 'Bugün kaç DM geldi?',
          answer:
            '14 mesaj geldi. 11 konuşma otomatik yanıtlandı, 2 konuşma size iletildi; 1 mesaj yanıt bekliyor.',
        },
        {
          ask: 'Deneme dersi için bir story hazırla.',
          answer:
            'İşletme bilgilerinizden bir Story taslağı hazırlıyorum. İçerik ekranında inceleyebilirsiniz.',
        },
        {
          ask: 'Yanıtlar biraz daha samimi olsun.',
          answer: 'Yanıt tonunu daha samimi yapayım mı? Sonraki taslaklarda geçerli olur.',
          action: 'Evet, güncelle',
        },
        {
          ask: 'Yarınki paylaşımı cuma 19:00’a al.',
          answer: 'İlgili paylaşımın yeni zamanı Cuma 19:00 olacak. Değişikliği uygulayayım mı?',
          action: 'Saati değiştir',
        },
        {
          ask: 'Aylık üyelik artık 7.000 TL.',
          answer:
            'Aylık üyeliği 7.000 ₺ olarak güncelleyeyim mi? Eski fiyatı kullanan içerikleri de kontrol edeceğim.',
          action: 'Güncelle',
        },
        {
          ask: 'Son 7 günde Instagram’da durum nasıl?',
          answer: 'Son 7 günün erişim, görüntülenme ve etkileşim verilerini bağlı hesabınızdan getiriyorum.',
        },
      ],
    },
    content: {
      eyebrow: 'Paylaşımlar',
      title: 'Fikirden yayın takvimine, aynı yerde.',
      body: 'Gönderi, Story, carousel ve Reels içeriklerinizi hazırlayın ve planlayın. Doğrulanmış fiyatlarınızdan markanıza uygun fiyat kartları oluşturun; zamanı gelen onaylı içerikler yayınlansın.',
      note: 'Planlandı, yayınlandı demek değildir. Paylaşım gerçekten yayınlanınca haber verir, yayınlanamazsa nedenini söyler.',
      example: 'Örnek',
      heading: 'Bu hafta',
      heldReason: 'Fiyat 6.000 ₺ → 7.000 ₺ olarak değiştiği için kendiliğinden beklemeye alındı.',
      posts: [
        {
          day: 'Pzt',
          time: '19:00',
          kind: 'Story · Fiyat kartı',
          title: 'Deneme dersi',
          status: 'Yayınlandı',
          state: 'published',
        },
        {
          day: 'Çar',
          time: '12:30',
          kind: 'Reels',
          title: 'Stüdyoda bir gün',
          status: 'Planlandı',
          state: 'scheduled',
        },
        {
          day: 'Cum',
          time: '19:00',
          kind: 'Carousel',
          title: 'Üyelik seçenekleri',
          status: 'Beklemede',
          state: 'held',
        },
        {
          day: 'Paz',
          time: '10:00',
          kind: 'Gönderi',
          title: 'Hafta sonu saatleri',
          status: 'Taslak hazır',
          state: 'pending',
        },
      ],
    },
    report: {
      title: 'Ne yaptığını sormanız yeterli.',
      body: 'Kaç mesaj geldi, hangi konuşmalar yanıtlandı, kim size ihtiyaç duyuyor? Gerçek kayıtlardan günün özetini alın; erişim, görüntülenme ve etkileşim verilerini de takip edin.',
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
    trust: {
      eyebrow: 'Kontrol ve güvenlik',
      title: 'Kontrol sizde. Verileriniz de.',
      body: 'Neyin otomatik olacağına siz karar verirsiniz. Her işlemin kim tarafından, ne zaman yapıldığı kayıtlıdır.',
      controlTitle: 'Kontrol',
      control: [
        {
          title: 'Otomasyonun kapsamını seçin',
          body: 'Rutin DM ve uygun yorum yanıtlarını otomatik çalıştırın. İşlem bazında otomatik, bana sor veya kapalı seçeneklerini belirleyin.',
        },
        {
          title: 'İstediğiniz an devralın',
          body: 'Müşteriyle kendiniz konuşurken asistan o konuşmada bekler. Diğer konuşmalar kendi akışında ilerler.',
        },
        {
          title: 'Ekibinizle birlikte çalışın',
          body: 'İşletme sahibi, yönetici ve personel rolleriyle görevleri paylaşın; birden fazla işletmeyi kendi çalışma alanında yönetin.',
        },
        {
          title: 'Ne olduğunu görün',
          body: 'Otomatik gönderilenler, sizin kararınızla yapılanlar ve bekleyen işler etkinlik geçmişinde bir arada.',
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
    localPackage: {
      eyebrow: 'Yerel paket',
      title: 'Yazılımın yanında, işletmenizin ihtiyaç duyduğu her şey.',
      body: 'Türkçe çalışır, kurulumu birlikte yaparız, hukuki belgeleri hazırlarız. Aşağıdakilerin hepsi bugün için geçerlidir; henüz hazır olmayanı yanında açıkça belirttik.',
      items: [
        {
          title: 'Beş dilde müşteri iletişimi',
          body: 'Müşterilerinizi Türkçe, İngilizce, Almanca, Rusça ve Arapça karşılayın. İşletmenizin yanıt dillerini seçin; uygulamayı Türkçe veya İngilizce kullanın.',
        },
        {
          title: 'KVKK belgeleri hazırlandı',
          badge: 'Taslak · hukuki inceleme bekliyor',
          body: 'Gizlilik politikası, kullanım koşulları ve veri silme sayfası uygulamada yer alır. Müşterilerinize göstereceğiniz KVKK aydınlatma metni şablonunu ve veri işleme sözleşmesi taslağını kurulumda size veririz. Belgeler henüz avukat incelemesinden geçmedi; kendi unvanınızla yayınlamadan önce kendi avukatınıza da onaylatmanızı öneririz.',
        },
        {
          title: 'Türk lirasıyla fatura',
          badge: 'Planlanan',
          body: 'Pilot ücretsizdir ve kendiliğinden ücretlendirme yoktur. Ücretli döneme geçerseniz faturalandırma Türk lirası (₺) ile yapılacak; ödeme ve fatura düzeni (e-arşiv fatura, havale/EFT ya da ödeme bağlantısı) başlamadan önce sizinle netleştirilir.',
        },
        {
          title: 'Yerinde ya da görüntülü kurulum',
          body: 'İlk kurulumu birlikte yaparız: yerinde (şimdilik Burdur ve Antalya çevresinde) ya da görüntülü görüşmeyle, yaklaşık 30 dakikada. Fiyat ve saatlerinizi birlikte girer, gerçek müşteri sorularıyla deneriz.',
        },
        {
          title: 'Fiyatı uydurmaz',
          body: 'Yanıttaki fiyat, saat, tarih ve telefon gibi değerler yalnızca sizin doğruladığınız bilgi kartlarından gelir. Kartlarda olmayan bir değer içeren taslak müşteriye gönderilmez, konuşma size kalır. Uygulamada her değerin hangi karttan ve hangi tarihte doğrulandığı görünür; günlük özet “gönderilen doğrulanmamış değer” sayısını da gösterir. Bilgi kartlarının doğru ve güncel olması sizin sorumluluğunuzdadır.',
        },
      ],
      legalLabel: 'Uygulamadaki belgeler',
      legal: [
        { label: 'Gizlilik politikası', path: '/privacy' },
        { label: 'Kullanım koşulları', path: '/terms' },
        { label: 'Veri silme', path: '/data-deletion' },
      ],
      priceLabel: 'Paket fiyatı',
      cta: 'Pilota başvurun',
    },
    faq: {
      eyebrow: 'Sorular',
      title: 'Sık sorulanlar',
      body: 'Cevabını bulamadığınız bir şey varsa pilot formuna yazın, sizi arayalım.',
      items: [
        {
          q: 'Her mesajı tek tek onaylamam gerekiyor mu?',
          a: 'Hayır. Otomasyonu etkinleştirdiğinizde selamlama, çalışma saati, adres, hizmet ve uygun standart fiyat soruları otomatik yanıtlanabilir. Özel teklifler, randevu değişiklikleri, sesli mesaj yanıtları ve hassas konular ayrıca değerlendirilir. Asistanın kapsamını siz belirlersiniz.',
        },
        {
          q: 'Telegram ile WhatsApp arasında ne fark var?',
          a: 'Telegram’dan komut verebilir, fotoğraf gönderebilir, içerik hazırlatabilir, asistanın sorularını yanıtlayabilir ve rapor sorabilirsiniz. WhatsApp günlük özetler ve bildirimler içindir; desteklenen mesajlaşma süresi içinde onay/ret butonları da sunar. WhatsApp’ta serbest metinle asistana komut verilmez.',
        },
        {
          q: 'Gönderi yorumlarıyla da ilgileniyor mu?',
          a: 'Evet. Hesabın gerekli izinleri ve otomasyon ayarları uygunsa rutin yorumlara yanıt verebilir ve uygun yorumlara özel mesaj gönderebilir. Fiyat bilgileri herkese açık yorumda paylaşılmaz; uygun durumda özel yanıta taşınır. Kullanım, Instagram’ın mesajlaşma ve izin sınırları içindedir.',
        },
        {
          q: 'Hangi dillerde müşterilere yanıt veriyor?',
          a: 'Türkçe, İngilizce, Almanca, Rusça ve Arapça müşteri yanıtlarını destekler. İşletmeniz için kullanacağınız dilleri seçersiniz. Uygulamanın arayüzü Türkçe ve İngilizcedir. Dilin belirsiz olduğu mesajlar size yönlendirilir.',
        },
        {
          q: 'Instagram şifremi vermem gerekiyor mu?',
          a: 'Hayır. Hesabınızı Instagram’ın resmi giriş ekranıyla bağlarsınız. Şifreniz Pivoris’e gelmez; bağlantıyı uygulamadan kaldırabilirsiniz.',
        },
        {
          q: 'Randevu ve takip mesajları nasıl çalışıyor?',
          a: 'Bağlı takvim üzerinden müsaitlik kontrol edilebilir; randevu oluşturma, değiştirme ve iptal talepleri hazırlanır. Mevcut pilotta takvim değişiklikleri sizin kararınızla yapılır. İsteğe bağlı takip mesajı, uygun konuşmalarda bir kez taslak olarak hazırlanır ve mesajlaşma süresi içinde onayınızla gönderilir.',
        },
        {
          q: 'Asistanı müşteriye açmadan deneyebilir miyim?',
          a: 'Evet. Test sohbetinde işletmenizin bilgileri ve mevcut asistan ayarlarıyla örnek müşteri soruları deneyebilirsiniz. Gerçek müşteriye mesaj gönderilmez, randevu oluşturulmaz veya içerik yayınlanmaz.',
        },
        {
          q: 'Kurulumu kendim yapabilir miyim?',
          a: 'Evet. İşletme türünüzü seçip web sitenizden, Instagram profilinizden veya yapıştırdığınız metinden bilgi önerileri alabilirsiniz. Bilgileri doğrulayıp otomasyonu seçersiniz. Pilot süresince kurulumu birlikte de yapıyoruz.',
        },
        {
          q: 'Pilot bitince ne olacak?',
          a: 'Pilot 30 gün ücretsizdir; kart bilgisi istemiyoruz ve kendiliğinden ücretlendirme yoktur. Devam etmek isterseniz paket koşullarını birlikte netleştiririz. Pilot işletmelere 12 ay sabit kurucu fiyatı sunuyoruz.',
        },
      ],
    },
    pilot: {
      eyebrow: 'Pilot programı',
      title: 'İşletmenize daha çok zaman ayırın.',
      body: 'Rutin soruların otomatik yanıtlandığı, içerik ve müşteri takibinin tek yerde toplandığı bir iş gününü 30 gün ücretsiz deneyin. Instagram’ı aktif kullanan 10–15 yerel işletmeyle başlıyoruz.',
      expectations: [
        {
          badge: '30 dakika',
          title: 'Kurulumu birlikte yapıyoruz',
          detail:
            'Yerinde ya da görüntülü; fiyat ve saatlerinizi birlikte girip 5 gerçek müşteri sorusuyla deneriz.',
        },
        {
          badge: '30 gün ücretsiz',
          title: 'Ücret ve kart bilgisi yok',
          detail:
            'Kendi müşterilerinizle, gerçek iş akışınızda deneyin. Memnun kalmazsanız bağlantıyı kaldırın.',
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
        { title: 'Sonrasında', body: 'Asistanınız rutin soruları karşılar, günün özeti telefonunuza gelir.' },
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
      tagline: 'İşletmenizi bilen, rutin işleri halleden asistanınız.',
      trademark:
        'Instagram ve WhatsApp, Meta Platforms, Inc.’in ticari markalarıdır; Telegram, sahibinin ticari markasıdır. Bu ürün bu şirketlerle bağlantılı değildir.',
      top: 'Başa dön',
    },
  },
  en: {
    meta: {
      title: `${PRODUCT_NAME} · An Instagram assistant for small businesses`,
      description:
        'Pivoris automatically answers routine Instagram questions, moves comments into private conversations and plans content. Manage tasks on Telegram and follow updates on WhatsApp.',
    },
    nav: {
      links: [
        {
          id: 'otomasyon',
          label: 'Automation',
        },
        {
          id: 'yonetim',
          label: 'Chat control',
        },
        {
          id: 'yetenekler',
          label: 'Capabilities',
        },
        {
          id: 'paket',
          label: 'Package',
        },
        {
          id: 'sss',
          label: 'Questions',
        },
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
      title: 'Focus on your business.',
      accent: 'Let Pivoris handle the routine.',
      lead: 'Automatically answer customer questions with your latest business details, respond to comments in private and prepare and schedule content. Give instructions on Telegram; get important updates on the channel you choose.',
      cta: 'Apply for the free pilot',
      secondary: 'Explore the automation',
      points: ['Free for 30 days', 'No card needed', '30-minute setup'],
    },
    preview: {
      example: 'Example screen',
      screen: 'Routine conversations',
      greeting: 'Good morning, Anna',
      date: 'Tuesday, 10 November',
      waitingTitle: 'Your assistant’s day',
      queue: ['Conversations answered automatically', 'Conversations passed to you', 'Upcoming post'],
      queueCounts: [11, 2, 1],
      metricsTitle: 'Today',
      metrics: ['Messages received', 'Automatic replies', 'Passed to you'],
      metricValues: [14, 11, 2],
      customer: 'anna.berg',
      time: '23:47',
      message: 'Hi, how much is a monthly membership?',
      reply: ['Hi! A monthly membership is ', '. ', ''],
      facts: ['₺6,000', ''],
      source: 'Monthly membership · Verified price',
      sent: 'Answered automatically',
      showSource: 'See the reply’s source',
      hideSource: 'Hide source',
    },
    promises: [
      {
        title: 'Let recurring questions answer themselves.',
        body: 'Prices, hours, your address and services, answered with current business details. No need to reach for your phone every time.',
      },
      {
        title: 'Run your business through chat.',
        body: 'Send a photo on Telegram, ask for content or check today’s summary. Choose WhatsApp for notifications too.',
      },
      {
        title: 'Keep customer interest moving.',
        body: 'Follow the journey from comment to private chat and availability to appointment. See the customers who still need a follow-up.',
      },
    ],
    audience: {
      label: 'Made for',
      items: [
        'Pilates and fitness studios',
        'Beauty salons',
        'Cafés',
        'Boutiques',
        'Clinics',
        'Service businesses',
      ],
    },
    how: {
      eyebrow: 'How it works',
      title: 'Teach it your business. Delegate the routine.',
      body: 'Set up once and let your assistant handle customer questions. Manage it through chat and see what happened at the end of the day.',
      steps: [
        {
          title: 'Introduce your business',
          body: 'Start with your website, Instagram profile or price list. Verify the details your assistant will use.',
        },
        {
          title: 'Choose your automation',
          body: 'Enable automatic routine DM and comment replies. Set the voice and the tasks your assistant can handle.',
        },
        {
          title: 'Let your assistant work',
          body: 'It answers with current details, keeps conversation context and asks you when information is missing.',
        },
        {
          title: 'Stay in touch through chat',
          body: 'Give tasks on Telegram. Get daily summaries and important updates in the app, Telegram or WhatsApp.',
        },
      ],
    },
    knowledge: {
      eyebrow: 'Source of truth',
      title: 'Teach it once. Keep every reply current.',
      body: 'Import suggested details from your website and Instagram profile, or paste a price message you already use. Verified prices, hours and services become the shared source for replies and content.',
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
      usageNote:
        'Updated facts carry into future replies; content that depends on the old version is flagged for review.',
      facts: [
        { category: 'Price', label: 'Monthly membership (2x/week)', value: '₺6,000' },
        { category: 'Offer', label: 'First trial class', value: 'Free' },
        { category: 'Hours', label: 'Weekday opening hours', value: '08:00 – 21:00' },
        { category: 'Address', label: 'Studio location', value: 'Bahçelievler Mah. No: 12' },
      ],
    },
    demo: {
      eyebrow: 'Automatic customer conversations',
      title: 'Question received. Reply sent. Your day continues.',
      body: 'For routine questions, it goes beyond drafting and sends the reply with the automation you enable. Prices and hours come from your verified records.',
      points: [
        {
          title: 'Automatic replies to routine questions',
          body: 'Greetings, hours, your location, services and eligible standard pricing enquiries are answered automatically.',
        },
        {
          title: 'Your business details in every answer',
          body: 'A price has a traceable source. Update a fact and future replies use the latest version.',
        },
        {
          title: 'Brings you in when needed',
          body: 'Missing information or a special request? It asks you. You do not have to write every routine reply.',
        },
      ],
      tabs: ['Automatic reply', 'Needs your input'],
      example: 'Example screen',
      channel: 'Instagram DM',
      known: {
        customer: 'anna.berg',
        time: '23:47',
        message: 'Hi, how much is a monthly membership?',
        draftLabel: 'Pivoris replied',
        draft: ['Hi! A monthly membership is ', '. ', ''],
        facts: [
          {
            value: '₺6,000',
            source: 'Monthly membership · Price · verified 12 Oct',
          },
        ],
        sent: 'Sent automatically · 23:47',
        hint: 'Tap the price to see its source.',
      },
      unknown: {
        customer: 'emma.k',
        time: '21:12',
        message: 'Do you offer prenatal Pilates?',
        badge: 'Passed to you',
        body: 'There is no verified fact about this. Instead of guessing, the assistant stopped and asked you.',
        questionLabel: 'The assistant asks you',
        question: 'Nothing is on record about “prenatal Pilates”. What should we tell the customer?',
        afterAnswer: 'If you save your answer as a fact, it is used the next time someone asks.',
      },
    },
    owner: {
      eyebrow: 'Manage through chat',
      title: 'Your business, a message away.',
      body: 'Give instructions on Telegram, send a photo or ask your assistant a question. Follow daily summaries and important updates in the app, Telegram or WhatsApp.',
      channels: [
        {
          title: 'Telegram',
          body: 'Commands, photo-to-content, assistant tasks, answers to owner questions and daily summaries.',
        },
        {
          title: 'WhatsApp',
          body: 'Daily summaries, important notifications and approve/reject buttons within the supported messaging window. Free-text commands are available on Telegram.',
        },
        {
          title: 'Web app',
          body: 'Your inbox, content calendar, customer lists and assistant settings. On your phone or computer.',
        },
      ],
      note: 'Routine customer conversations run automatically. Decisions such as calendar changes, publication and special requests come to you. Available channels and actions depend on your connected account.',
      example: 'Example chat',
      bot: PRODUCT_NAME,
      botSub: 'Telegram · Your business assistant',
      today: 'Today',
      placeholder: 'Message',
      chat: [
        {
          from: 'owner',
          time: '09:12',
          attachment: {
            kicker: 'Reformer Pilates',
            title: 'Trial class',
            note: 'free',
          },
          text: 'Prepare a trial-class story with this photo.',
        },
        {
          from: 'assistant',
          time: '09:12',
          text: 'Photo received. I’m preparing a Story draft using your trial-class details.',
        },
        {
          from: 'owner',
          time: '09:14',
          text: 'How many DMs came in today?',
        },
        {
          from: 'assistant',
          time: '09:14',
          text: '14 messages received. 11 conversations answered automatically, 2 passed to you and 1 message awaiting a reply.',
        },
      ],
      commandsTitle: 'What can you ask on Telegram?',
      commandsHint: 'Tap one to see it in the chat',
      commands: [
        {
          ask: 'How many DMs came in today?',
          answer:
            '14 messages received. 11 conversations answered automatically, 2 passed to you and 1 message waiting for a reply.',
        },
        {
          ask: 'Prepare a story for our trial class.',
          answer: 'I’m preparing a Story draft using your business details. You can review it in Content.',
        },
        {
          ask: 'Make the replies a little warmer.',
          answer: 'Shall I make the voice warmer for future drafts?',
          action: 'Update voice',
        },
        {
          ask: 'Move tomorrow’s post to Friday at 19:00.',
          answer: 'The post will move to Friday at 19:00. Apply the change?',
          action: 'Change time',
        },
        {
          ask: 'Monthly membership is now ₺7,000.',
          answer: 'Update the monthly membership to ₺7,000? I’ll also check content using the old price.',
          action: 'Update price',
        },
        {
          ask: 'How did Instagram do over the last 7 days?',
          answer:
            'I’m retrieving reach, views and interactions for the last 7 days from your connected account.',
        },
      ],
    },
    content: {
      eyebrow: 'Posts',
      title: 'From idea to publishing calendar.',
      body: 'Prepare and schedule feed posts, Stories, carousels and Reels. Create branded price cards from verified facts. Approved content publishes when its scheduled time arrives.',
      note: 'Scheduled does not mean published. You hear when a post actually goes out, and if it fails, you hear why.',
      example: 'Example',
      heading: 'This week',
      heldReason: 'Put on hold automatically because the price changed from ₺6,000 to ₺7,000.',
      posts: [
        {
          day: 'Mon',
          time: '19:00',
          kind: 'Story · Price card',
          title: 'Trial class',
          status: 'Published',
          state: 'published',
        },
        {
          day: 'Wed',
          time: '12:30',
          kind: 'Reels',
          title: 'A day at the studio',
          status: 'Scheduled',
          state: 'scheduled',
        },
        {
          day: 'Fri',
          time: '19:00',
          kind: 'Carousel',
          title: 'Membership options',
          status: 'On hold',
          state: 'held',
        },
        {
          day: 'Sun',
          time: '10:00',
          kind: 'Feed post',
          title: 'Weekend hours',
          status: 'Draft ready',
          state: 'pending',
        },
      ],
    },
    report: {
      title: 'Just ask what happened.',
      body: 'How many messages arrived, which conversations got answers and who needs you? Get a summary from recorded activity, and follow reach, views and interactions too.',
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
    trust: {
      eyebrow: 'Control and security',
      title: 'You stay in control. So does your data.',
      body: 'You decide what runs automatically. Every action is recorded with who did it and when.',
      controlTitle: 'Control',
      control: [
        {
          title: 'Choose what runs automatically',
          body: 'Enable automatic routine DM and eligible comment replies. Set individual actions to automatic, ask me or off.',
        },
        {
          title: 'Step in at any time',
          body: 'Your assistant waits while you speak to a customer yourself. Other conversations continue independently.',
        },
        {
          title: 'Work with your team',
          body: 'Share work through owner, manager and staff roles. Keep each business in its own workspace.',
        },
        {
          title: 'See what happened',
          body: 'Automatic sends, actions you decided and work still waiting appear together in the activity history.',
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
    localPackage: {
      eyebrow: 'Local package',
      title: 'Beyond the software, what a local business needs.',
      body: 'It works in Turkish, we set it up with you, and the legal documents are prepared. Everything below is true today; what is not ready yet is marked next to it.',
      items: [
        {
          title: 'Customer conversations in five languages',
          body: 'Welcome customers in Turkish, English, German, Russian and Arabic. Choose your reply languages and use the app in Turkish or English.',
        },
        {
          title: 'KVKK documents prepared',
          badge: 'Draft · awaiting legal review',
          body: 'The privacy policy, the terms and a data-deletion page are in the app. We hand you the KVKK information-notice template for your customers and a draft data processing agreement during setup. They have not been through a lawyer’s review yet; before you publish them under your company name, we recommend your own lawyer approves them.',
        },
        {
          title: 'Invoiced in Turkish lira',
          badge: 'Planned',
          body: 'The pilot is free and nothing is charged automatically. If you move to a paid plan, billing will be in Turkish lira (₺); the payment and invoice arrangement (e-archive invoice, bank transfer or a payment link) is agreed with you before it starts.',
        },
        {
          title: 'Set up in person or by video',
          body: 'We do the first setup together: in person (for now around Burdur and Antalya) or on a video call, in about 30 minutes. We enter your prices and hours together and try it with real customer questions.',
        },
        {
          title: 'No made-up prices',
          body: 'Prices, hours, dates and phone numbers in a reply come only from the business facts you have verified. A draft that contains a value that is not in your facts is not sent; the conversation is left to you. The app shows which fact each value came from and when it was verified, and the daily summary shows how many unverified values were sent. Keeping your facts correct and up to date is your responsibility.',
        },
      ],
      legalLabel: 'Documents in the app',
      legal: [
        { label: 'Privacy policy', path: '/privacy' },
        { label: 'Terms of use', path: '/terms' },
        { label: 'Data deletion', path: '/data-deletion' },
      ],
      priceLabel: 'Package price',
      cta: 'Apply for the pilot',
    },
    faq: {
      eyebrow: 'Questions',
      title: 'Frequently asked',
      body: 'Something not covered here? Write it in the pilot form and we will call you.',
      items: [
        {
          q: 'Do I need to approve every message?',
          a: 'No. With automation enabled, greetings, opening hours, location, services and eligible standard pricing questions can be answered automatically. Custom offers, calendar changes, voice-note replies and sensitive topics need separate attention. You choose your assistant’s scope.',
        },
        {
          q: 'How are Telegram and WhatsApp different?',
          a: 'Telegram supports commands, photo uploads, content requests, answers to assistant questions and report queries. WhatsApp provides daily summaries and notifications, plus approve/reject buttons within the supported messaging window. WhatsApp does not accept free-text assistant commands.',
        },
        {
          q: 'Does it handle post comments too?',
          a: 'Yes. With the required account permissions and automation settings, it can answer routine comments and send eligible private replies to commenters. Prices are not disclosed in public comments; eligible enquiries move to private replies. Instagram permissions and messaging limits still apply.',
        },
        {
          q: 'Which languages can customers use?',
          a: 'Customer replies support Turkish, English, German, Russian and Arabic. Choose which languages to enable for your business. The app interface is Turkish and English. Messages with uncertain language are passed to you.',
        },
        {
          q: 'Do I need to share my Instagram password?',
          a: 'No. Connect through Instagram’s official sign-in screen. Your password never reaches Pivoris, and you can disconnect in the app.',
        },
        {
          q: 'How do bookings and follow-ups work?',
          a: 'A connected calendar can be checked for availability and booking, rescheduling and cancellation requests can be prepared. Calendar changes require your decision in the current pilot. Optional follow-ups create one draft for eligible conversations, sent with your approval within the messaging window.',
        },
        {
          q: 'Can I try the assistant before using it with customers?',
          a: 'Yes. Use the test chat to try example questions with your business details and current assistant settings. It sends no real customer messages, creates no appointments and publishes no content.',
        },
        {
          q: 'Can I set it up myself?',
          a: 'Yes. Choose your business type and import suggested details from your website, Instagram profile or pasted text. Verify the details and choose your automation. Assisted setup is also available during the pilot.',
        },
        {
          q: 'What happens after the pilot?',
          a: 'The pilot is free for 30 days, with no card required or automatic charges. If you want to continue, we agree the package terms together. Pilot businesses get a founder price fixed for 12 months.',
        },
      ],
    },
    pilot: {
      eyebrow: 'Pilot programme',
      title: 'Make more time for your business.',
      body: 'Try a working day with automatic routine replies, content and customer follow-up in one place, free for 30 days. We are starting with 10–15 local businesses active on Instagram.',
      expectations: [
        {
          badge: '30 minutes',
          title: 'We set it up together',
          detail:
            'In person or on a video call, we enter your prices and hours and try 5 real customer questions.',
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
        { title: 'From then on', body: 'Your assistant handles routine questions and sends your daily summary.' },
      ],
      whatsappDirectLabel: 'Prefer not to fill in a form? Message us on WhatsApp',
      whatsappPrefill: `Hi, I would like to learn more about the ${PRODUCT_NAME} pilot programme.`,
    },
    form: {
      title: 'Pilot application',
      subtitle: 'Takes about a minute.',
      categoryLabel: 'Business type',
      categories: [
        'Beauty / Salon',
        'Café / Restaurant',
        'Shop / Retail',
        'Fitness / Pilates',
        'Clinic / Health',
        'Services',
        'Other',
      ],
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
      tagline: 'An assistant that knows your business and handles the routine.',
      trademark:
        'Instagram and WhatsApp are trademarks of Meta Platforms, Inc.; Telegram is a trademark of its owner. This product is not affiliated with these companies.',
      top: 'Back to top',
    },
  },
}
