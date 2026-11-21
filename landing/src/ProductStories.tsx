import { useState } from 'react'
import type { Copy, Lang } from './copy'
import { Brand } from './BrandIdentity'
import { PhoneFrame } from './PhoneFrame'
import {
  BookIcon,
  CalendarIcon,
  ChatIcon,
  CheckIcon,
  ExampleLabel,
  ImageIcon,
  SectionHeader,
  SettingsIcon,
  UsersIcon,
} from './ui'

type Story = {
  tab: string
  label: string
  question: string
  work: string
  reply: string
  result: string
  note: string
}
type StoryCopy = {
  eyebrow: string
  title: string
  body: string
  example: string
  working: string
  result: string
  stories: Story[]
  capabilities: {
    eyebrow: string
    title: string
    body: string
    languageTitle: string
    languageBody: string
    cards: { title: string; body: string; tag: string }[]
  }
  channel: {
    whatsappTitle: string
    whatsappMessage: string
    whatsappDetail: string
    whatsappNote: string
    appTitle: string
    appItems: string[]
    appNote: string
  }
}

const storiesCopy: Record<Lang, StoryCopy> = {
  tr: {
    eyebrow: 'Bir yanıttan fazlası',
    title: 'Konuşma ilerlesin. İşler tamamlansın.',
    body: 'Soruyu yanıtlamak başlangıç. Pivoris müşterinin ilgisini özel sohbete taşır, randevu talebini işler ve işletmenizdeki değişiklikleri takip eder.',
    example: 'Örnek akış · Canlı işlem yapılmaz',
    working: 'Pivoris ne yapar?',
    result: 'İşletmeniz için sonucu',
    stories: [
      {
        tab: 'Yorumdan DM’e',
        label: 'Instagram yorumu',
        question: '“Aylık üyelik fiyatınız nedir?”',
        work: 'Fiyat sorusunu tanır; doğrulanmış fiyatı uygun özel yanıtla iletir.',
        reply: 'Merhaba! Aylık üyeliğimiz 6.000 ₺.',
        result: 'Yorumdaki ilgi, özel konuşmaya dönüşür.',
        note: 'Uygun yorumlarda, hesap izinleri ve özel yanıt yetkisiyle çalışır. Fiyat herkese açık yorumda paylaşılmaz.',
      },
      {
        tab: 'Mesajdan randevuya',
        label: 'Instagram DM',
        question: '“Yarın 14:00 için randevu alabilir miyim?”',
        work: 'Bağlı takvimde müsaitliği kontrol eder, randevu talebini kararınıza sunar. İşlem doğrulanınca müşteriyi bilgilendirir.',
        reply: 'Randevunuz yarın 14:00–15:00 için oluşturuldu.',
        result: 'Mesaj, takvimde kayıtlı bir randevuya dönüşür.',
        note: 'Mevcut pilotta randevu oluşturma, değiştirme ve iptal işlemleri kararınızla yapılır. Takvim bağlantısı gerekir.',
      },
      {
        tab: 'Tek değişiklik, güncel bilgi',
        label: 'Telegram’dan talimatınız',
        question: '“Aylık üyelik artık 7.000 TL.”',
        work: 'Bilgi güncellendiğinde sonraki yanıtları yeni fiyatla hazırlar; eski bilgiye bağlı bekleyen işleri kontrol eder.',
        reply: 'Fiyat güncellendi. Eski fiyatı kullanan planlı içerik inceleme için bekletildi.',
        result: 'Yanıtlar ve planlı içerikler aynı bilgi kaynağına bağlı kalır.',
        note: 'Bilgi değişikliği doğrulandıktan sonra uygulanır. Etkilenen yanıtlar yeniden hazırlanır, planlı içerikler incelemeye alınır.',
      },
    ],
    capabilities: {
      eyebrow: 'İşletmenizi tanıyan asistan',
      title: 'Hazır yanıtlardan çok daha fazlası.',
      body: 'Müşterinizin dili, konuşmanın geçmişi, gönderdiği fotoğraf… Pivoris bütün bunları işin bağlamında ele alır.',
      languageTitle: 'Müşteriniz hangi dilde yazıyor?',
      languageBody:
        'Türkçe, İngilizce, Almanca, Rusça ve Arapça. İşletmeniz için yanıt dillerini seçin; müşterinizle kendi dilinde iletişim kurun.',
      cards: [
        {
          title: 'Sesi ve görseli bağlama dahil eder',
          body: 'Sesli mesajları yazıya çevirir, fotoğrafları açıklayarak konuşmanın bağlamına ekler. Sesli mesaj yanıtları incelemenizle gönderilir.',
          tag: 'Sesli mesaj + görsel',
        },
        {
          title: 'Müşteriyi ve sizin üslubunuzu hatırlar',
          body: 'İlgili müşteri tercihlerini hatırlar. Samimi ya da resmî dil, yanıt uzunluğu ve emoji kullanımı işletmenize uyarlanır.',
          tag: 'Müşteri hafızası + üslup',
        },
        {
          title: 'Geri dönüş bekleyenleri görün',
          body: 'Fiyat veya randevu sorup henüz randevuya dönüşmeyen müşterileri listeleyin, CSV olarak indirin. İsteğe bağlı takip mesajı taslakları hazırlansın.',
          tag: 'Müşteri listesi + takip',
        },
        {
          title: 'Hızlı öğretin, önce kendiniz deneyin',
          body: 'Web sitenizden ve Instagram profilinizden bilgi önerileri alın. Test sohbetinde, müşteriye mesaj göndermeden asistanınızın yanıtlarını deneyin.',
          tag: 'Bilgi aktarımı + test sohbeti',
        },
      ],
    },
    channel: {
      whatsappTitle: 'Günün özeti',
      whatsappMessage:
        'Bugün 14 mesaj geldi. 11 konuşma otomatik yanıtlandı, 2 konuşma size iletildi; 1 mesaj yanıt bekliyor.',
      whatsappDetail: 'Sıradaki paylaşım: yarın 19:00. İncelemeniz gereken işler uygulamada.',
      whatsappNote:
        'WhatsApp bildirim ve işlem butonları içindir. Serbest metinle talimat vermek için Telegram’ı kullanın.',
      appTitle: 'İşletmeniz tek yerde',
      appItems: [
        'Gelen kutusu ve konuşmalar',
        'İçerik takvimi ve yayınlar',
        'Randevular ve müşteri listesi',
        'Bilgi kartları ve asistan ayarları',
      ],
      appNote: 'Telefon ve bilgisayarınızdan açın. İsterseniz bildirimleri yalnızca uygulamadan alın.',
    },
  },
  en: {
    eyebrow: 'Beyond a reply',
    title: 'Move the conversation forward. Get the work done.',
    body: 'Answering is the start. Pivoris moves customer interest into private chat, handles appointment requests and tracks changes across your business.',
    example: 'Example workflow · No live actions',
    working: 'What does Pivoris do?',
    result: 'What it means for your business',
    stories: [
      {
        tab: 'Comment to DM',
        label: 'Instagram comment',
        question: '“How much is a monthly membership?”',
        work: 'Recognises the pricing question and sends the verified price through an eligible private reply.',
        reply: 'Hi! A monthly membership is ₺6,000.',
        result: 'Interest under a post becomes a private conversation.',
        note: 'Requires an eligible comment, account permissions and private-reply authority. Prices are not shared in public comments.',
      },
      {
        tab: 'Message to appointment',
        label: 'Instagram DM',
        question: '“Can I book tomorrow at 14:00?”',
        work: 'Checks the connected calendar and brings the appointment request to you. Once the operation is confirmed, it informs the customer.',
        reply: 'Your appointment is booked for tomorrow, 14:00–15:00.',
        result: 'A message becomes an appointment recorded in your calendar.',
        note: 'Booking, rescheduling and cancellation require your decision in the current pilot. A calendar connection is required.',
      },
      {
        tab: 'One update, current details',
        label: 'Your Telegram instruction',
        question: '“Monthly membership is now ₺7,000.”',
        work: 'After the fact is updated, future replies use the new price and pending work using the previous version is checked.',
        reply: 'Price updated. Scheduled content using the old price is held for review.',
        result: 'Replies and scheduled content share one source of truth.',
        note: 'Fact changes take effect after confirmation. Affected replies are redrafted and scheduled content is held for review.',
      },
    ],
    capabilities: {
      eyebrow: 'An assistant that knows your business',
      title: 'Much more than canned replies.',
      body: 'Your customer’s language, the conversation history, a photo they sent… Pivoris brings them into context.',
      languageTitle: 'What language does your customer speak?',
      languageBody:
        'Turkish, English, German, Russian and Arabic. Enable the reply languages your business needs and meet customers in their own language.',
      cards: [
        {
          title: 'Brings voice and images into context',
          body: 'Transcribes voice notes and adds image descriptions to the conversation. Voice-based replies are sent after your review.',
          tag: 'Voice notes + images',
        },
        {
          title: 'Remembers customers and your voice',
          body: 'Retains relevant customer preferences. Set a warm or formal tone, reply length and emoji use to suit your business.',
          tag: 'Customer memory + voice',
        },
        {
          title: 'See who still needs a follow-up',
          body: 'List customers whose price or booking enquiry has not become an appointment and export a CSV. Enable optional follow-up drafts.',
          tag: 'Customer list + follow-up',
        },
        {
          title: 'Teach it quickly, try it yourself first',
          body: 'Import suggested facts from your website and Instagram profile. Try your assistant in the test chat without sending real customer messages.',
          tag: 'Import + practice chat',
        },
      ],
    },
    channel: {
      whatsappTitle: 'Daily summary',
      whatsappMessage:
        '14 messages received today. 11 conversations answered automatically, 2 passed to you and 1 message awaiting a reply.',
      whatsappDetail: 'Next post: tomorrow at 19:00. Items needing your attention are in the app.',
      whatsappNote:
        'WhatsApp is for notifications and action buttons. Use Telegram for free-text instructions.',
      appTitle: 'Your business in one place',
      appItems: [
        'Inbox and conversations',
        'Content calendar and publications',
        'Appointments and customer list',
        'Business facts and assistant settings',
      ],
      appNote: 'Open on your phone or computer. Choose app-only notifications if you prefer.',
    },
  },
}

const languages = [
  { code: 'tr', name: 'Türkçe', question: 'Aylık üyelik ne kadar?', reply: 'Aylık üyeliğimiz 6.000 ₺.' },
  {
    code: 'en',
    name: 'English',
    question: 'How much is a monthly membership?',
    reply: 'A monthly membership is ₺6,000.',
  },
  {
    code: 'de',
    name: 'Deutsch',
    question: 'Wie viel kostet die Monatsmitgliedschaft?',
    reply: 'Die Monatsmitgliedschaft kostet 6.000 ₺.',
  },
  {
    code: 'ru',
    name: 'Русский',
    question: 'Сколько стоит месячный абонемент?',
    reply: 'Месячный абонемент стоит 6 000 ₺.',
  },
  { code: 'ar', name: 'العربية', question: 'كم سعر الاشتراك الشهري؟', reply: 'سعر الاشتراك الشهري 6,000 ₺.' },
]

export function JourneySection({ lang }: { lang: Lang }) {
  const t = storiesCopy[lang]
  const [selected, setSelected] = useState(0)
  const story = t.stories[selected]
  return (
    <section id="otomasyon" className="mt-16 bg-band py-20 text-band-text md:py-24">
      <div className="gutter mx-auto max-w-[76rem]">
        <div className="max-w-[48rem]">
          <p className="text-sm font-semibold text-band-accent">{t.eyebrow}</p>
          <h2 className="type-title mt-4 text-white dark:text-primary">{t.title}</h2>
          <p className="mt-5 text-lg leading-relaxed">{t.body}</p>
        </div>
        <div role="group" aria-label={t.title} className="mt-9 flex flex-wrap gap-2">
          {t.stories.map((s, i) => (
            <button
              key={s.tab}
              type="button"
              aria-pressed={selected === i}
              onClick={() => setSelected(i)}
              className="min-h-11 rounded-full border border-band-text/30 px-5 py-2 text-sm font-semibold transition-colors hover:bg-band-text/10 aria-pressed:border-band-accent aria-pressed:bg-band-accent aria-pressed:text-on-band-accent"
            >
              {s.tab}
            </button>
          ))}
        </div>
        <div className="mt-6 rounded-frame border border-band-text/20 bg-canvas p-5 text-primary sm:p-8">
          <div className="mb-7 flex justify-end">
            <ExampleLabel>{t.example}</ExampleLabel>
          </div>
          <div key={selected} className="pop-in grid gap-6 lg:grid-cols-[1fr_1fr_1.1fr] lg:gap-8">
            <div>
              <p className="flex items-center gap-2 text-sm font-semibold text-secondary">
                <ChatIcon />
                {story.label}
              </p>
              <p className="mt-4 rounded-panel border border-border bg-surface p-4 text-lg font-medium leading-relaxed">
                {story.question}
              </p>
            </div>
            <div>
              <p className="flex items-center gap-2 text-sm font-semibold text-action">
                <SettingsIcon />
                {t.working}
              </p>
              <p className="mt-4 text-base leading-relaxed text-secondary">{story.work}</p>
            </div>
            <div className="rounded-panel bg-assistant p-5">
              <p className="text-base leading-relaxed">{story.reply}</p>
              <p className="mt-5 flex items-center gap-2 text-sm font-semibold text-action">
                <CheckIcon />
                {t.result}
              </p>
              <p className="mt-2 font-heading text-lg font-bold">{story.result}</p>
            </div>
          </div>
          <p className="mt-7 border-t border-border pt-5 text-sm leading-relaxed text-secondary">
            {story.note}
          </p>
        </div>
      </div>
    </section>
  )
}

export function CapabilitiesSection({ lang }: { lang: Lang }) {
  const t = storiesCopy[lang].capabilities
  const [selected, setSelected] = useState(0)
  const language = languages[selected]
  const icons = [
    <ImageIcon key="image" />,
    <UsersIcon key="users" />,
    <ChatIcon key="chat" />,
    <BookIcon key="book" />,
  ]
  return (
    <section id="yetenekler" className="border-y border-border bg-surface py-20 md:py-28">
      <div className="gutter mx-auto max-w-[76rem]">
        <SectionHeader eyebrow={t.eyebrow} title={t.title} body={t.body} />
        <div className="mt-12 grid gap-4 lg:grid-cols-3">
          <article className="rounded-frame border border-border bg-assistant p-6 sm:p-8 lg:row-span-2">
            <h3 className="font-heading text-2xl font-bold tracking-tight">{t.languageTitle}</h3>
            <p className="mt-4 text-base leading-relaxed text-secondary">{t.languageBody}</p>
            <div role="group" aria-label={t.languageTitle} className="mt-6 flex flex-wrap gap-2">
              {languages.map((l, i) => (
                <button
                  key={l.code}
                  type="button"
                  lang={l.code}
                  aria-pressed={i === selected}
                  onClick={() => setSelected(i)}
                  className="min-h-11 rounded-full border border-border bg-surface px-3 text-sm font-semibold aria-pressed:border-action aria-pressed:bg-action aria-pressed:text-on-action"
                >
                  {l.name}
                </button>
              ))}
            </div>
            <div
              key={language.code}
              lang={language.code}
              dir={language.code === 'ar' ? 'rtl' : 'ltr'}
              className="pop-in mt-8 space-y-3 text-base leading-relaxed"
            >
              <p className="mr-5 rounded-2xl rounded-bl-sm border border-border bg-surface p-3">
                {language.question}
              </p>
              <p className="ml-5 rounded-2xl rounded-br-sm bg-action p-3 text-on-action">{language.reply}</p>
            </div>
            <div className="mt-5">
              <ExampleLabel>{storiesCopy[lang].example}</ExampleLabel>
            </div>
          </article>
          {t.cards.map((card, i) => (
            <article key={card.title} className="rounded-frame border border-border bg-canvas p-6">
              <span
                aria-hidden
                className="grid size-10 place-items-center rounded-panel bg-assistant text-xl text-action"
              >
                {icons[i]}
              </span>
              <h3 className="mt-5 font-heading text-xl font-bold tracking-tight">{card.title}</h3>
              <p className="mt-3 text-base leading-relaxed text-secondary">{card.body}</p>
              <p className="mt-5 text-sm font-semibold text-action">{card.tag}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

export function ChannelPreview({
  lang,
  channel,
  owner,
}: {
  lang: Lang
  channel: number
  owner: Copy['owner']
}) {
  const t = storiesCopy[lang].channel
  return (
    <PhoneFrame label={owner.example} clock="21:00">
      <div className="flex min-h-[32rem] flex-col bg-canvas">
        <div className="flex items-center gap-3 border-b border-border bg-surface p-4">
          <Brand variant="monogram" size="sm" />
          <div>
            <p className="font-semibold">Pivoris</p>
            <p className="text-sm text-secondary">{owner.channels[channel].title}</p>
          </div>
        </div>
        {channel === 1 ? (
          <div className="dot-field flex flex-1 flex-col justify-center gap-4 p-4">
            <div className="rounded-2xl rounded-bl-sm border border-border bg-surface p-4">
              <p className="flex items-center gap-2 font-heading font-bold">
                <CalendarIcon className="text-action" />
                {t.whatsappTitle}
              </p>
              <p className="mt-3 text-base leading-relaxed">{t.whatsappMessage}</p>
              <p className="mt-3 text-sm leading-relaxed text-secondary">{t.whatsappDetail}</p>
              <p className="mt-3 text-right text-xs text-secondary">21:00</p>
            </div>
            <p className="rounded-panel bg-assistant p-3 text-sm leading-relaxed text-secondary">
              {t.whatsappNote}
            </p>
          </div>
        ) : (
          <div className="flex flex-1 flex-col p-5">
            <p className="mt-4 font-heading text-2xl font-bold">{t.appTitle}</p>
            <ul className="mt-6 space-y-3">
              {t.appItems.map((item) => (
                <li
                  key={item}
                  className="flex items-center gap-3 rounded-panel border border-border bg-surface p-4 text-base"
                >
                  <CheckIcon className="shrink-0 text-success" />
                  {item}
                </li>
              ))}
            </ul>
            <p className="mt-6 text-sm leading-relaxed text-secondary">{t.appNote}</p>
          </div>
        )}
      </div>
    </PhoneFrame>
  )
}
