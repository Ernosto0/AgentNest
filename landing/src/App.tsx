import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import { PRODUCT_NAME } from './brand'
import { copy, type Copy, type Lang, type PostStatus } from './copy'
import { DraftDemo } from './DraftDemo'
import { HeroPreview } from './HeroPreview'
import { KnowledgePreview } from './KnowledgePreview'
import { OwnerChat } from './OwnerChat'
import {
  ArrowRightIcon,
  ArrowUpIcon,
  Badge,
  BookIcon,
  BrandMark,
  CalendarIcon,
  ChartIcon,
  ChatIcon,
  CheckIcon,
  ClockIcon,
  Eyebrow,
  ExampleLabel,
  HandIcon,
  KeyIcon,
  LayersIcon,
  ListIcon,
  MinusCircleIcon,
  MoonIcon,
  PauseIcon,
  PlusIcon,
  SectionHeader,
  SettingsIcon,
  ShieldCheckIcon,
  SmartphoneIcon,
  SunIcon,
  TagIcon,
  TrashIcon,
  UsersIcon,
  buttonLarge,
  buttonPrimary,
  buttonSecondary,
  useReveal,
  type Tone,
} from './ui'
import { WaitlistForm } from './WaitlistForm'

const LANG_KEY = 'landing.lang'
const THEME_KEY = 'landing.theme'
type Theme = 'light' | 'dark'

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(LANG_KEY)
    if (saved === 'tr' || saved === 'en') return saved
  } catch {
    // Storage can be blocked; fall back to the browser language.
  }
  return navigator.language.toLowerCase().startsWith('tr') ? 'tr' : 'en'
}

// index.html already applied the saved choice (or the OS preference) before first paint.
function initialTheme(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

const container = 'gutter mx-auto w-full max-w-[76rem]'

export function App() {
  const [lang, setLang] = useState<Lang>(initialLang)
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const t = copy[lang]
  const revealRoot = useReveal([lang])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#0d1410' : '#f7f8f3')
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      // Not remembering the choice is fine.
    }
  }, [theme])

  useEffect(() => {
    document.documentElement.lang = lang
    document.title = t.meta.title
    document.querySelector('meta[name="description"]')?.setAttribute('content', t.meta.description)
    try {
      localStorage.setItem(LANG_KEY, lang)
    } catch {
      // Not remembering the choice is fine.
    }
  }, [lang, t.meta.title, t.meta.description])

  const heroRef = useRef<HTMLElement>(null)
  const pilotRef = useRef<HTMLElement>(null)
  const heroVisible = useInView(heroRef)
  const pilotVisible = useInView(pilotRef)
  const active = useActiveSection(t.nav.links.map((l) => l.id).concat('pilot'))

  return (
    <div ref={revealRoot}>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-control focus:bg-surface focus:px-4 focus:py-3 focus:shadow-frame"
      >
        {t.nav.skip}
      </a>

      <SiteHeader
        t={t}
        lang={lang}
        setLang={setLang}
        theme={theme}
        setTheme={setTheme}
        active={active}
      />

      <main id="main" tabIndex={-1} className="outline-none">
        <Hero t={t} heroRef={heroRef} />
        <Promises t={t} />
        <Problem t={t.problem} />
        <HowItWorks t={t} />
        <Section id="demo" tone="surface">
          <div className="grid grid-cols-1 items-center gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] lg:gap-20">
            <div>
              <SectionHeader eyebrow={t.demo.eyebrow} title={t.demo.title} body={t.demo.body} />
              <ul className="reveal mt-10 flex flex-col gap-5">
                {t.demo.points.map((point, i) => (
                  <li key={point.title} className="flex gap-4">
                    <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-panel bg-assistant text-lg text-action">
                      {[<TagIcon key="t" />, <CheckIcon key="c" />, <HandIcon key="h" />][i]}
                    </span>
                    <div>
                      <h3 className="font-heading text-base font-bold">{point.title}</h3>
                      <p className="mt-0.5 text-[0.9375rem] leading-relaxed text-secondary">{point.body}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
            <div className="reveal">
              <DraftDemo t={t.demo} />
            </div>
          </div>
        </Section>
        <OwnerSection t={t.owner} />
        <ContentAndReport t={t} />
        <Limits t={t.limits} />
        <Trust t={t.trust} />
        <Faq t={t.faq} />
        <Pilot t={t} lang={lang} pilotRef={pilotRef} />
      </main>

      <SiteFooter t={t} />
      <MobileCta t={t} hidden={heroVisible || pilotVisible} />
    </div>
  )
}

/* ------------------------------------------------------------------ header */

function SiteHeader({
  t,
  lang,
  setLang,
  theme,
  setTheme,
  active,
}: {
  t: Copy
  lang: Lang
  setLang: (l: Lang) => void
  theme: Theme
  setTheme: (t: Theme) => void
  active: string | null
}) {
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <header
      className={`sticky top-0 z-40 border-b transition-colors ${
        scrolled || open ? 'border-border bg-canvas/90 backdrop-blur-md' : 'border-transparent bg-canvas'
      }`}
    >
      <div className={`${container} flex h-16 items-center gap-4`}>
        <a href="#" className="flex items-center gap-2.5 rounded-control" aria-label={PRODUCT_NAME}>
          <BrandMark name={PRODUCT_NAME} />
          <span className="font-heading text-lg font-bold tracking-tight">{PRODUCT_NAME}</span>
        </a>

        <nav aria-label={t.nav.menu} className="ml-6 hidden items-center gap-1 lg:flex">
          {t.nav.links.map((link) => (
            <a
              key={link.id}
              href={`#${link.id}`}
              aria-current={active === link.id ? 'true' : undefined}
              className="rounded-control px-3 py-2 text-sm font-medium text-secondary transition-colors hover:text-primary aria-[current]:bg-surface-subtle aria-[current]:text-primary"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-1.5">
          <LangSwitch t={t} lang={lang} setLang={setLang} />
          <button
            type="button"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            aria-label={theme === 'dark' ? t.nav.toLight : t.nav.toDark}
            title={theme === 'dark' ? t.nav.toLight : t.nav.toDark}
            className="grid size-10 place-items-center rounded-control text-lg text-secondary transition-colors hover:bg-surface-subtle hover:text-primary"
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>
          <span className="ml-1.5 hidden sm:block">
            <a href="#pilot" className={`${buttonPrimary} whitespace-nowrap`}>
              {t.nav.cta}
            </a>
          </span>
          <button
            type="button"
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={t.nav.menu}
            onClick={() => setOpen((v) => !v)}
            className="grid size-10 place-items-center rounded-control text-lg text-primary hover:bg-surface-subtle lg:hidden"
          >
            <span aria-hidden className="relative block h-3 w-4">
              <span className={`absolute left-0 h-0.5 w-4 rounded bg-current transition-transform ${open ? 'top-[5px] rotate-45' : 'top-0'}`} />
              <span className={`absolute top-[5px] left-0 h-0.5 w-4 rounded bg-current transition-opacity ${open ? 'opacity-0' : ''}`} />
              <span className={`absolute left-0 h-0.5 w-4 rounded bg-current transition-transform ${open ? 'top-[5px] -rotate-45' : 'top-[10px]'}`} />
            </span>
          </button>
        </div>
      </div>

      {open && (
        <nav id="mobile-nav" aria-label={t.nav.menu} className="border-t border-border bg-canvas lg:hidden">
          <div className={`${container} flex flex-col py-3`}>
            {t.nav.links.map((link) => (
              <a
                key={link.id}
                href={`#${link.id}`}
                onClick={() => setOpen(false)}
                className="flex min-h-12 items-center justify-between border-b border-border text-base font-medium last:border-b-0"
              >
                {link.label}
                <ArrowRightIcon aria-hidden className="text-control" />
              </a>
            ))}
            <a href="#pilot" onClick={() => setOpen(false)} className={`${buttonPrimary} mt-3 w-full`}>
              {t.nav.cta}
            </a>
          </div>
        </nav>
      )}
    </header>
  )
}

function LangSwitch({ t, lang, setLang }: { t: Copy; lang: Lang; setLang: (l: Lang) => void }) {
  return (
    <div role="group" aria-label={t.nav.language} className="flex rounded-control border border-border bg-surface p-0.5">
      {(['tr', 'en'] as const).map((code) => (
        <button
          key={code}
          type="button"
          lang={code}
          aria-pressed={lang === code}
          onClick={() => setLang(code)}
          className="min-h-8 min-w-9 rounded-[0.375rem] px-2 text-xs font-semibold text-secondary uppercase transition-colors aria-pressed:bg-band aria-pressed:text-band-text"
        >
          {code}
        </button>
      ))}
    </div>
  )
}

/* -------------------------------------------------------------------- hero */

function Hero({ t, heroRef }: { t: Copy; heroRef: RefObject<HTMLElement | null> }) {
  return (
    <section ref={heroRef} className="relative overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute -top-48 right-[-12rem] size-[44rem] rounded-full bg-fact/50 blur-3xl dark:bg-fact/40" />
        <div className="dot-field absolute inset-x-0 top-0 h-[36rem] [mask-image:linear-gradient(to_bottom,black,transparent)]" />
      </div>

      <div className={`${container} relative grid items-center gap-14 pt-10 pb-24 md:pt-16 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-14 lg:pb-28`}>
        <div className="max-w-[40rem]">
          <p className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-[0.8125rem] font-medium">
            <span aria-hidden className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-50 motion-reduce:hidden" />
              <span className="relative inline-flex size-2 rounded-full bg-success" />
            </span>
            {t.hero.badge}
          </p>

          <h1 className="type-display mt-6">
            {t.hero.title}{' '}
            <span className="block text-action">{t.hero.accent}</span>
          </h1>

          <p className="mt-6 text-lg leading-relaxed text-secondary md:text-xl md:leading-relaxed">{t.hero.lead}</p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
            <a href="#pilot" className={`${buttonPrimary} ${buttonLarge}`}>
              {t.hero.cta}
              <ArrowRightIcon aria-hidden />
            </a>
            <a href="#nasil" className={`${buttonSecondary} ${buttonLarge}`}>
              {t.hero.secondary}
            </a>
          </div>

          <ul className="mt-7 flex flex-wrap gap-x-5 gap-y-2 text-sm text-secondary">
            {t.hero.points.map((point) => (
              <li key={point} className="flex items-center gap-1.5">
                <CheckIcon aria-hidden className="text-success" />
                {point}
              </li>
            ))}
          </ul>
        </div>

        <HeroPreview t={t.preview} />
      </div>
    </section>
  )
}

function Promises({ t }: { t: Copy }) {
  const icons = [<ClockIcon key="t" />, <ChatIcon key="s" />, <CalendarIcon key="c" />]
  return (
    <section aria-label={t.promises.map((p) => p.title).join(' ')} className="relative">
      <div className={container}>
        <ul className="reveal grid overflow-hidden rounded-frame border border-border bg-surface md:grid-cols-3">
          {t.promises.map((promise, i) => (
            <li key={promise.title} className="flex gap-4 border-border p-6 not-last:border-b md:not-last:border-r md:not-last:border-b-0 lg:p-7">
              <span aria-hidden className="grid size-11 shrink-0 place-items-center rounded-panel bg-assistant text-xl text-action">
                {icons[i]}
              </span>
              <div>
                <h2 className="font-heading text-lg font-bold tracking-tight">{promise.title}</h2>
                <p className="mt-1 text-[0.9375rem] leading-relaxed text-secondary">{promise.body}</p>
              </div>
            </li>
          ))}
        </ul>

        <div className="reveal mt-8 flex flex-wrap items-center justify-center gap-2">
          <span className="mr-1 text-sm text-secondary">{t.audience.label}:</span>
          {t.audience.items.map((item) => (
            <span key={item} className="rounded-full border border-border bg-surface px-3 py-1 text-sm font-medium">
              {item}
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ---------------------------------------------------------------- sections */

function Section({
  id,
  tone = 'canvas',
  children,
  className = '',
}: {
  id?: string
  tone?: 'canvas' | 'surface'
  children: ReactNode
  className?: string
}) {
  const bg = tone === 'surface' ? 'border-y border-border bg-surface' : ''
  return (
    <section id={id} className={`py-20 md:py-28 ${bg} ${className}`}>
      <div className={container}>{children}</div>
    </section>
  )
}

function Problem({ t }: { t: Copy['problem'] }) {
  return (
    <Section id="neden" className="mt-8">
      <SectionHeader eyebrow={t.eyebrow} title={t.title} body={t.body} />
      <div className="mt-12 grid gap-5 md:grid-cols-3">
        {t.rows.map((row) => (
          <article key={row.scenario} className="reveal flex flex-col rounded-frame border border-border bg-surface p-2">
            <h3 className="px-4 pt-4 pb-3 font-heading text-lg leading-snug font-bold tracking-tight">{row.scenario}</h3>
            <div className="px-4 pb-4">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-secondary">
                <MinusCircleIcon aria-hidden /> {t.withoutLabel}
              </p>
              <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-secondary">{row.without}</p>
            </div>
            <div className="mt-auto rounded-panel bg-assistant p-4">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-action">
                <CheckIcon aria-hidden /> {t.withLabel}
              </p>
              <p className="mt-1.5 text-[0.9375rem] leading-relaxed">{row.withProduct}</p>
            </div>
          </article>
        ))}
      </div>
    </Section>
  )
}

function HowItWorks({ t }: { t: Copy }) {
  const icons = [<BookIcon key="b" />, <ChatIcon key="c" />, <CheckIcon key="k" />, <ChartIcon key="r" />]
  return (
    <Section id="nasil" tone="surface">
      <SectionHeader eyebrow={t.how.eyebrow} title={t.how.title} body={t.how.body} />

      <ol className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {t.how.steps.map((step, i) => (
          <li key={step.title} className="reveal relative rounded-frame border border-border bg-canvas p-5" style={{ transitionDelay: `${i * 70}ms` }}>
            <div className="flex items-center justify-between">
              <span aria-hidden className="grid size-10 place-items-center rounded-panel bg-band text-lg text-band-accent">
                {icons[i]}
              </span>
              <span className="font-heading text-3xl font-extrabold text-border tabular-nums">{String(i + 1).padStart(2, '0')}</span>
            </div>
            <h3 className="mt-5 font-heading text-lg leading-snug font-bold tracking-tight">{step.title}</h3>
            <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-secondary">{step.body}</p>
          </li>
        ))}
      </ol>

      <div className="mt-20 grid gap-8 md:mt-24">
        <div className="reveal grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-end lg:gap-16">
          <div>
            <Eyebrow>{t.knowledge.eyebrow}</Eyebrow>
            <h3 className="mt-3 font-heading text-[clamp(1.5rem,1.2rem+1.2vw,2.125rem)] leading-tight font-extrabold tracking-[-0.025em]">
              {t.knowledge.title}
            </h3>
          </div>
          <p className="text-[1.0625rem] leading-relaxed text-secondary">{t.knowledge.body}</p>
        </div>
        <KnowledgePreview t={t.knowledge} example={t.demo.example} />
      </div>
    </Section>
  )
}

function OwnerSection({ t }: { t: Copy['owner'] }) {
  const [selected, setSelected] = useState<number | null>(null)
  const channelIcons = [<SmartphoneIcon key="s" />, <ChatIcon key="c" />]
  return (
    <Section id="yonetim">
      <div className="grid gap-12 lg:grid-cols-[minmax(0,25rem)_minmax(0,1fr)] lg:gap-20">
        <div className="reveal order-last lg:sticky lg:top-20 lg:order-first lg:self-start">
          <OwnerChat t={t} selected={selected === null ? null : t.commands[selected]} />
        </div>
        <div className="min-w-0">
          <SectionHeader eyebrow={t.eyebrow} title={t.title} body={t.body} />

          <div className="reveal mt-10">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <h3 className="font-heading text-lg font-bold tracking-tight">{t.commandsTitle}</h3>
              <p className="text-sm text-secondary">{t.commandsHint}</p>
            </div>
            <div className="mt-4 grid gap-2.5 sm:grid-cols-2">
              {t.commands.map((command, idx) => (
                <button
                  key={command.ask}
                  type="button"
                  aria-pressed={selected === idx}
                  onClick={() => setSelected(selected === idx ? null : idx)}
                  className="group flex min-h-13 items-center gap-3 rounded-panel border border-border bg-surface px-4 py-3 text-left text-[0.9375rem] transition-colors hover:border-control aria-pressed:border-action aria-pressed:bg-assistant"
                >
                  <span
                    aria-hidden
                    className="grid size-6 shrink-0 place-items-center rounded-full border border-border text-sm text-secondary transition-colors group-aria-pressed:border-action group-aria-pressed:bg-action group-aria-pressed:text-on-action"
                  >
                    {selected === idx ? <CheckIcon /> : <PlusIcon />}
                  </span>
                  <span className="font-medium">“{command.ask}”</span>
                </button>
              ))}
            </div>
          </div>

          <ul className="reveal mt-10 grid gap-x-6 gap-y-5 border-t border-border pt-8 sm:grid-cols-2">
            {t.channels.map((channel, i) => (
              <li key={channel.title} className="flex gap-3.5">
                <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-panel bg-assistant text-lg text-action">
                  {channelIcons[i]}
                </span>
                <div>
                  <h3 className="font-heading text-base font-bold">{channel.title}</h3>
                  <p className="mt-0.5 text-sm leading-relaxed text-secondary">{channel.body}</p>
                </div>
              </li>
            ))}
          </ul>
          <p className="reveal mt-6 flex gap-3 rounded-panel bg-assistant p-4 text-sm leading-relaxed">
            <ShieldCheckIcon aria-hidden className="mt-0.5 shrink-0 text-lg text-action" />
            {t.note}
          </p>
        </div>
      </div>
    </Section>
  )
}

const postTone: Record<PostStatus, { tone: Tone; icon: ReactNode }> = {
  published: { tone: 'success', icon: <CheckIcon /> },
  scheduled: { tone: 'info', icon: <CalendarIcon /> },
  held: { tone: 'attention', icon: <PauseIcon /> },
  pending: { tone: 'attention', icon: <ClockIcon /> },
}

function ContentAndReport({ t }: { t: Copy }) {
  return (
    <Section id="paylasim" tone="surface">
      <div className="grid gap-16 lg:grid-cols-2 lg:gap-16">
        <div className="min-w-0">
          <SectionHeader eyebrow={t.content.eyebrow} title={t.content.title} body={t.content.body} />
          <figure className="reveal mt-10">
            <div className="overflow-hidden rounded-frame border border-border bg-canvas">
              <figcaption className="flex items-center justify-between gap-2 border-b border-border bg-surface px-5 py-3">
                <span className="font-heading text-sm font-bold">{t.content.heading}</span>
                <ExampleLabel>{t.content.example}</ExampleLabel>
              </figcaption>
              <ul className="divide-y divide-border">
                {t.content.posts.map((post, idx) => (
                  <li key={`${post.day}-${post.time}`} className="flex flex-col gap-2.5 px-5 py-3.5">
                    <div className="flex items-center gap-3.5">
                      <div className="flex w-10 shrink-0 flex-col text-xs tabular-nums">
                        <span className="font-bold">{post.day}</span>
                        <span className="text-secondary">{post.time}</span>
                      </div>
                      <PostThumb index={idx} />
                      <div className="flex min-w-0 flex-1 flex-col">
                        <span className="text-xs text-secondary">{post.kind}</span>
                        <span className="truncate text-sm font-semibold">{post.title}</span>
                      </div>
                      <Badge tone={postTone[post.state].tone} size="sm" icon={postTone[post.state].icon} className="hidden sm:inline-flex">
                        {post.status}
                      </Badge>
                    </div>
                    <Badge tone={postTone[post.state].tone} size="sm" icon={postTone[post.state].icon} className="self-start sm:hidden">
                      {post.status}
                    </Badge>
                    {post.state === 'held' && (
                      <p className="flex items-start gap-2 rounded-control bg-attention-subtle px-3 py-2 text-xs leading-snug text-attention">
                        <PauseIcon aria-hidden className="mt-px shrink-0" />
                        {t.content.heldReason}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-secondary">{t.content.note}</p>
          </figure>
        </div>

        <div className="min-w-0 lg:pt-[7.5rem]">
          <div className="reveal">
            <h3 className="font-heading text-[clamp(1.5rem,1.2rem+1.2vw,2.125rem)] leading-tight font-extrabold tracking-[-0.025em]">
              {t.report.title}
            </h3>
            <p className="mt-4 max-w-[34rem] text-[1.0625rem] leading-relaxed text-secondary">{t.report.body}</p>
          </div>
          <figure className="reveal mt-8 rounded-frame border border-border bg-canvas p-5">
            <figcaption className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-heading text-sm font-bold">{t.report.heading}</p>
                <p className="text-xs text-secondary">{t.report.asOf}</p>
              </div>
              <ExampleLabel>{t.report.example}</ExampleLabel>
            </figcaption>
            <dl className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
              {t.report.metrics.map(({ label, value }) => (
                <div key={label} className="rounded-panel border border-border bg-surface px-3.5 py-3">
                  <dt className="text-xs text-secondary">{label}</dt>
                  <dd
                    className={`mt-1 font-heading font-bold tabular-nums ${
                      /^\d+$/.test(value) ? 'text-[1.75rem] leading-9 text-action' : 'text-base leading-9'
                    }`}
                  >
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="mt-4 flex items-start gap-2 text-xs leading-relaxed text-secondary">
              <CheckIcon aria-hidden className="mt-0.5 shrink-0 text-success" />
              {t.report.footerNote}
            </p>
          </figure>
        </div>
      </div>
    </Section>
  )
}

function PostThumb({ index }: { index: number }) {
  const palettes = ['bg-[#d7dccd]', 'bg-[#e9dfcf]', 'bg-[#dfe7e2]', 'bg-[#e5e9d6]']
  return (
    <span aria-hidden className={`relative h-11 w-8 shrink-0 overflow-hidden rounded-md ring-1 ring-black/5 ${palettes[index % palettes.length]}`}>
      <span className="absolute -top-2 -right-2 size-5 rounded-full bg-[#253b31]/80" />
      <span className="absolute right-1.5 bottom-1.5 left-1.5 h-1 rounded-full bg-[#253b31]/40" />
    </span>
  )
}

function Limits({ t }: { t: Copy['limits'] }) {
  return (
    <Section id="sinirlar">
      <SectionHeader eyebrow={t.eyebrow} title={t.title} body={t.body} />
      <ul className="mt-12 grid gap-4 sm:grid-cols-2">
        {t.escalate.map((item) => (
          <li key={item.title} className="reveal rounded-frame border border-border bg-surface p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-heading text-lg font-bold tracking-tight">{item.title}</h3>
              <Badge tone="attention" size="sm" icon={<HandIcon />}>
                {t.escalateBadge}
              </Badge>
            </div>
            <p className="mt-2.5 rounded-panel bg-surface-subtle px-3.5 py-2.5 text-sm leading-relaxed text-secondary italic">{item.example}</p>
          </li>
        ))}
      </ul>
    </Section>
  )
}

function Trust({ t }: { t: Copy['trust'] }) {
  const controlIcons = [<SettingsIcon key="a" />, <HandIcon key="b" />, <UsersIcon key="c" />, <ListIcon key="d" />]
  const securityIcons = [<KeyIcon key="a" />, <ShieldCheckIcon key="b" />, <LayersIcon key="c" />, <TrashIcon key="d" />]
  const group = (title: string, items: Copy['trust']['control'], icons: ReactNode[]) => (
    <div className="reveal">
      <h3 className="type-eyebrow text-band-accent">{title}</h3>
      <ul className="mt-5 grid gap-x-8 gap-y-6 sm:grid-cols-2">
        {items.map((item, i) => (
          <li key={item.title} className="flex gap-3.5">
            <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-panel bg-white/8 text-lg text-band-accent ring-1 ring-white/10">
              {icons[i]}
            </span>
            <div>
              <p className="font-heading font-bold text-white dark:text-primary">{item.title}</p>
              <p className="mt-1 text-[0.9375rem] leading-relaxed text-band-text/80">{item.body}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
  return (
    <section id="guven" className="bg-band py-20 text-band-text md:py-28">
      <div className={container}>
        <header className="reveal max-w-[44rem]">
          <p className="type-eyebrow text-band-accent">{t.eyebrow}</p>
          <h2 className="type-title mt-3 text-white dark:text-primary">{t.title}</h2>
          <p className="mt-5 max-w-[38rem] text-lg leading-relaxed text-band-text/85">{t.body}</p>
        </header>
        <div className="mt-14 grid gap-14 lg:grid-cols-2 lg:gap-16">
          {group(t.controlTitle, t.control, controlIcons)}
          {group(t.securityTitle, t.security, securityIcons)}
        </div>
      </div>
    </section>
  )
}

function Faq({ t }: { t: Copy['faq'] }) {
  return (
    <Section id="sss">
      <div className="grid gap-10 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] lg:gap-16">
        <div className="lg:sticky lg:top-28 lg:self-start">
          <SectionHeader eyebrow={t.eyebrow} title={t.title} body={t.body} />
        </div>
        <div className="reveal overflow-hidden rounded-frame border border-border bg-surface">
          {t.items.map((item) => (
            <details key={item.q} className="group border-b border-border last:border-b-0">
              <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-6 px-5 py-4 font-heading text-base font-bold transition-colors hover:bg-surface-subtle sm:px-6 [&::-webkit-details-marker]:hidden">
                {item.q}
                <span
                  aria-hidden
                  className="grid size-7 shrink-0 place-items-center rounded-full border border-border text-secondary transition-transform group-open:rotate-45 group-open:border-action group-open:bg-action group-open:text-on-action"
                >
                  <PlusIcon />
                </span>
              </summary>
              <p className="max-w-[40rem] px-5 pb-5 text-[0.9375rem] leading-relaxed text-secondary sm:px-6">{item.a}</p>
            </details>
          ))}
        </div>
      </div>
    </Section>
  )
}

function Pilot({ t, lang, pilotRef }: { t: Copy; lang: Lang; pilotRef: RefObject<HTMLElement | null> }) {
  return (
    <section id="pilot" ref={pilotRef} className="relative overflow-hidden border-t border-border bg-assistant py-20 md:py-28">
      <div aria-hidden className="dot-field pointer-events-none absolute inset-0 [mask-image:linear-gradient(to_bottom,black,transparent_70%)]" />
      <div className={`${container} relative grid gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,31rem)] lg:gap-16`}>
        <div className="min-w-0">
          <SectionHeader eyebrow={t.pilot.eyebrow} title={t.pilot.title} body={t.pilot.body} />

          <ul className="mt-10 grid gap-3 sm:grid-cols-2">
            {t.pilot.expectations.map((item) => (
              <li key={item.title} className="reveal rounded-panel border border-border bg-surface p-5">
                <Badge tone="brand" size="sm">
                  {item.badge}
                </Badge>
                <h3 className="mt-3 font-heading text-base font-bold">{item.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-secondary">{item.detail}</p>
              </li>
            ))}
          </ul>

          <div className="reveal mt-10">
            <h3 className="type-eyebrow text-secondary">{t.pilot.nextStepsTitle}</h3>
            <ol className="mt-4 grid gap-4 sm:grid-cols-3">
              {t.pilot.nextSteps.map((step, i) => (
                <li key={step.title} className="flex gap-3 sm:flex-col sm:gap-2">
                  <span className="grid size-8 shrink-0 place-items-center rounded-full bg-band font-heading text-sm font-bold text-band-accent">
                    {i + 1}
                  </span>
                  <div>
                    <p className="font-semibold">{step.title}</p>
                    <p className="text-sm text-secondary">{step.body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>

        <div className="lg:sticky lg:top-24 lg:self-start">
          <WaitlistForm t={t.form} pilot={t.pilot} lang={lang} />
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ footer */

function SiteFooter({ t }: { t: Copy }) {
  return (
    <footer className="border-t border-border bg-canvas pb-24 md:pb-0">
      <div className={`${container} grid gap-8 py-12 md:grid-cols-[minmax(0,1fr)_auto] md:items-start`}>
        <div className="max-w-md">
          <div className="flex items-center gap-2.5">
            <BrandMark name={PRODUCT_NAME} size="sm" />
            <span className="font-heading font-bold">{PRODUCT_NAME}</span>
          </div>
          <p className="mt-3 text-sm text-secondary">{t.footer.tagline}</p>
        </div>
        <nav aria-label={t.nav.menu} className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
          {t.nav.links.map((link) => (
            <a key={link.id} href={`#${link.id}`} className="text-secondary hover:text-primary">
              {link.label}
            </a>
          ))}
          <a href="#pilot" className="font-semibold text-action hover:underline">
            {t.nav.cta}
          </a>
        </nav>
      </div>
      <div className={`${container} flex flex-col gap-3 border-t border-border py-6 text-xs text-secondary md:flex-row md:items-center md:justify-between`}>
        <p className="max-w-3xl leading-relaxed">{t.footer.trademark}</p>
        <div className="flex shrink-0 items-center gap-4">
          <span>© 2026 {PRODUCT_NAME}</span>
          <a href="#" className="inline-flex items-center gap-1 hover:text-primary">
            <ArrowUpIcon aria-hidden /> {t.footer.top}
          </a>
        </div>
      </div>
    </footer>
  )
}

/** Phones only: a quiet call to action once the hero is gone, hidden again at the form. */
function MobileCta({ t, hidden }: { t: Copy; hidden: boolean }) {
  return (
    <div
      aria-hidden={hidden}
      className={`fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface/95 px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-md transition-transform duration-300 md:hidden ${
        hidden ? 'pointer-events-none translate-y-full' : ''
      }`}
    >
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1 leading-tight">
          <p className="truncate text-sm font-semibold">{PRODUCT_NAME}</p>
          <p className="truncate text-xs text-secondary">{t.mobileCta.sub}</p>
        </div>
        <a href="#pilot" tabIndex={hidden ? -1 : undefined} className={`${buttonPrimary} shrink-0`}>
          {t.mobileCta.label}
        </a>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------- hooks */

function useInView(ref: RefObject<HTMLElement | null>) {
  const [inView, setInView] = useState(true)
  useEffect(() => {
    const el = ref.current
    if (!el || !('IntersectionObserver' in window)) return
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold: 0 })
    observer.observe(el)
    return () => observer.disconnect()
  }, [ref])
  return inView
}

/** The section in the upper part of the viewport, for the header's current-section marker. */
function useActiveSection(ids: string[]) {
  const [active, setActive] = useState<string | null>(null)
  const key = ids.join(',')
  useEffect(() => {
    if (!('IntersectionObserver' in window)) return
    const visible = new Map<string, boolean>()
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) visible.set(entry.target.id, entry.isIntersecting)
        setActive(key.split(',').find((id) => visible.get(id)) ?? null)
      },
      { rootMargin: '-35% 0px -60% 0px' },
    )
    for (const id of key.split(',')) {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    }
    return () => observer.disconnect()
  }, [key])
  return active
}
