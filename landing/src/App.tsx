import { useEffect, useState, type ReactNode } from 'react'
import { PRODUCT_NAME } from './brand'
import { copy, type Copy, type Lang, type PostStatus } from './copy'
import { OwnerChat } from './OwnerChat'
import { PhoneDemo } from './PhoneDemo'
import { WaitlistForm } from './WaitlistForm'

const LANG_KEY = 'landing.lang'

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(LANG_KEY)
    if (saved === 'tr' || saved === 'en') return saved
  } catch {
    // Storage can be blocked; fall back to the browser language.
  }
  return navigator.language.toLowerCase().startsWith('tr') ? 'tr' : 'en'
}

const THEME_KEY = 'landing.theme'
type Theme = 'light' | 'dark'

// Light unless the visitor chose dark here (or the host page already set it).
function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    // Storage can be blocked; use the default.
  }
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

const container = 'gutter mx-auto w-full max-w-[76rem]'
const sectionTitle = 'font-display text-[clamp(2rem,4.4vw,3.5rem)] leading-[1.02] font-bold tracking-[-0.03em]'
const lede = 'mt-6 max-w-[34rem] text-lg leading-relaxed text-muted'

export function App() {
  const [lang, setLang] = useState<Lang>(initialLang)
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const t = copy[lang]

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      // Not remembering the choice is fine.
    }
  }, [theme])

  useEffect(() => {
    document.documentElement.lang = lang
    document.title = t.meta.title
    try {
      localStorage.setItem(LANG_KEY, lang)
    } catch {
      // Not remembering the choice is fine.
    }
  }, [lang, t.meta.title])

  return (
    <>
      <InkFilter />

      <header className={`${container} flex items-center justify-between gap-4 py-5`}>
        <span className="font-display text-lg font-extrabold tracking-[-0.02em]">{PRODUCT_NAME}</span>
        <nav className="flex items-center gap-6 font-mono text-xs">
          <a href="#pilot" className="hidden text-muted underline-offset-4 hover:text-ink hover:underline sm:inline">
            {t.nav.waitlist}
          </a>
          <div role="group" aria-label={t.nav.language} className="flex gap-1">
            {(['tr', 'en'] as const).map((code) => (
              <button
                key={code}
                type="button"
                lang={code}
                aria-pressed={lang === code}
                onClick={() => setLang(code)}
                className="rounded px-1.5 py-1 uppercase text-muted aria-pressed:bg-surface aria-pressed:text-ink"
              >
                {code}
              </button>
            ))}
          </div>
          <button
            type="button"
            aria-pressed={theme === 'dark'}
            aria-label={t.nav.dark}
            title={t.nav.dark}
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="grid size-7 place-items-center rounded text-muted aria-pressed:bg-surface aria-pressed:text-ink"
          >
            <svg aria-hidden viewBox="0 0 24 24" width="16" height="16">
              <circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" strokeWidth="1.8" />
              <path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" />
            </svg>
          </button>
        </nav>
      </header>

      <main>
        <section className={`${container} pt-12 pb-16 md:pt-24 md:pb-20`}>
          <p className="font-mono text-xs tracking-wide text-muted">{t.hero.kicker}</p>
          <h1 className="mt-6 font-display text-[clamp(2.5rem,8.4vw,6.75rem)] leading-[0.95] font-extrabold tracking-[-0.045em]">
            {t.hero.promises.map((line) => (
              <span key={line} className="block">
                {line}
              </span>
            ))}
          </h1>
          <div className="mt-10 grid gap-8 md:mt-14 md:grid-cols-[minmax(0,36rem)_auto] md:items-end md:justify-between">
            <p className="text-xl leading-relaxed md:text-[1.375rem]">{t.hero.lead}</p>
            <div className="flex flex-col items-start gap-3">
              <a
                href="#pilot"
                className="inline-flex h-13 items-center gap-3 rounded-md bg-kase px-7 font-display text-base font-bold text-on-kase transition-transform active:scale-[0.98]"
              >
                {t.hero.cta}
                <span aria-hidden>↓</span>
              </a>
              <p className="max-w-[30ch] font-mono text-xs leading-relaxed text-muted">{t.hero.note}</p>
            </div>
          </div>

          <nav aria-label={t.index.label} className="mt-16 flex flex-wrap items-baseline gap-x-6 gap-y-2 font-mono text-xs md:mt-24">
            <span className="text-muted">{t.index.label}</span>
            {t.index.links.map((link) => (
              <a key={link.id} href={`#${link.id}`} className="underline decoration-rule underline-offset-4 hover:decoration-kase">
                {link.label}
              </a>
            ))}
          </nav>
        </section>

        <Section id="whatsapp">
          <div className="grid items-center gap-12 md:grid-cols-[23rem_minmax(0,1fr)] md:gap-20">
            <div className="min-w-0 md:order-last">
              <h2 className={sectionTitle}>{t.whatsapp.title}</h2>
              <p className={lede}>{t.whatsapp.body}</p>
              <p className="mt-6 max-w-[34rem] border-l-2 border-kase pl-4 font-mono text-xs leading-relaxed text-muted">
                {t.whatsapp.note}
              </p>
            </div>
            <OwnerChat t={t.whatsapp} />
          </div>
          <Commands t={t.whatsapp} />
        </Section>

        <Section id="dm">
          <div className="grid items-center gap-12 md:grid-cols-[minmax(0,1fr)_23rem]">
            <div className="min-w-0">
              <h2 className={sectionTitle}>{t.demo.title}</h2>
              <p className={lede}>{t.demo.body}</p>
            </div>
            <PhoneDemo t={t.demo} />
          </div>
        </Section>

        <Section id="icerik">
          <div className="grid gap-12 md:grid-cols-2 md:gap-16">
            <div className="min-w-0">
              <h2 className={sectionTitle}>{t.content.title}</h2>
              <p className={lede}>{t.content.body}</p>
              <p className="mt-4 max-w-[34rem] text-lg leading-relaxed text-muted">{t.content.note}</p>
            </div>
            <ContentPlan t={t.content} />
          </div>
        </Section>

        <Section>
          <div className="grid gap-16 md:grid-cols-2 md:gap-12">
            <div className="min-w-0">
              <h2 className={sectionTitle}>{t.escalate.title}</h2>
              <p className={lede}>{t.escalate.body}</p>
              <ul className="mt-8 divide-y divide-rule border-y border-rule font-display text-xl font-medium">
                {t.escalate.items.map((item) => (
                  <li key={item} className="py-3.5">
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            <div className="min-w-0">
              <h2 className={sectionTitle}>{t.report.title}</h2>
              <p className={lede}>{t.report.body}</p>
              <figure className="mt-8">
                <ExampleLabel>{t.report.example}</ExampleLabel>
                <div className="rounded-lg bg-surface p-5 font-mono text-sm">
                  <p className="mb-4 text-xs tracking-wide text-muted">{t.report.heading}</p>
                  <dl className="flex flex-col gap-2.5">
                    {t.report.rows.map(([label, value]) => (
                      <div key={label} className="flex items-baseline gap-2">
                        <dt className="shrink-0">{label}</dt>
                        <span aria-hidden className="min-w-4 flex-1 border-b border-dotted border-muted/50" />
                        <dd className="shrink-0 tabular-nums">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              </figure>
            </div>
          </div>
        </Section>

        <Section id="kontrol">
          <h2 className={sectionTitle}>{t.control.title}</h2>
          <ul className="mt-12 grid gap-x-12 gap-y-10 md:grid-cols-2">
            {t.control.items.map((item) => (
              <li key={item.title} className="border-t border-rule pt-5">
                <h3 className="font-display text-xl leading-snug font-bold tracking-[-0.01em]">{item.title}</h3>
                <p className="mt-2 max-w-[32rem] text-[1.0625rem] leading-relaxed text-muted">{item.body}</p>
              </li>
            ))}
          </ul>
        </Section>

        <Section>
          <h2 className={sectionTitle}>{t.steps.title}</h2>
          <ol className="mt-12 grid gap-10 md:grid-cols-3 md:gap-8">
            {t.steps.items.map((step, i) => (
              <li key={step.title} className="border-t-2 border-ink pt-4">
                <span className="font-mono text-sm text-kase">{i + 1}</span>
                <h3 className="mt-3 font-display text-xl leading-snug font-bold tracking-[-0.01em]">{step.title}</h3>
                <p className="mt-2 text-[1.0625rem] leading-relaxed text-muted">{step.body}</p>
              </li>
            ))}
          </ol>
        </Section>

        <Section id="sss">
          <div className="grid gap-10 md:grid-cols-[minmax(0,1fr)_minmax(0,40rem)] md:gap-16">
            <h2 className={sectionTitle}>{t.faq.title}</h2>
            <div className="border-t border-rule">
              {t.faq.items.map((item) => (
                <details key={item.q} className="group border-b border-rule">
                  <summary className="flex cursor-pointer list-none items-baseline justify-between gap-6 py-5 font-display text-lg font-bold [&::-webkit-details-marker]:hidden">
                    {item.q}
                    <span aria-hidden className="font-mono text-base font-normal text-kase transition-transform group-open:rotate-45">
                      +
                    </span>
                  </summary>
                  <p className="max-w-[36rem] pb-6 text-[1.0625rem] leading-relaxed text-muted">{item.a}</p>
                </details>
              ))}
            </div>
          </div>
        </Section>

        <Section id="pilot">
          <div className="grid gap-14 md:grid-cols-[minmax(0,1fr)_minmax(0,28rem)]">
            <div className="min-w-0">
              <h2 className="font-display text-[clamp(2.25rem,5.2vw,4.25rem)] leading-[0.98] font-extrabold tracking-[-0.04em]">
                {t.pilot.title}
              </h2>
              <p className={lede}>{t.pilot.body}</p>
            </div>
            <WaitlistForm t={t.form} lang={lang} />
          </div>
        </Section>
      </main>

      <footer className="border-t border-rule">
        <div className={`${container} flex flex-wrap justify-between gap-x-8 gap-y-2 py-8 font-mono text-xs text-muted`}>
          <span>© 2026 {PRODUCT_NAME}</span>
          <span>{t.footer.trademark}</span>
        </div>
      </footer>
    </>
  )
}

function Section({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-4 border-t border-rule">
      <div className={`${container} py-20 md:py-28`}>{children}</div>
    </section>
  )
}

function ExampleLabel({ children }: { children: ReactNode }) {
  return (
    <figcaption className="mb-3 flex items-center gap-2 font-mono text-xs text-muted">
      <span aria-hidden className="size-1.5 rounded-full bg-kase" />
      {children}
    </figcaption>
  )
}

function Commands({ t }: { t: Copy['whatsapp'] }) {
  return (
    <div className="mt-20 md:mt-28">
      <h3 className="font-display text-2xl font-bold tracking-[-0.02em]">{t.commandsTitle}</h3>
      <dl className="mt-6 border-b border-rule">
        {t.commands.map((command) => (
          <div
            key={command.ask}
            className="grid gap-2 border-t border-rule py-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] md:gap-10"
          >
            <dt className="font-display text-xl font-medium tracking-[-0.01em]">“{command.ask}”</dt>
            <dd className="flex flex-col items-start gap-2 text-[1.0625rem] leading-relaxed text-muted">
              {command.answer}
              {command.action && (
                <span className="rounded-full border border-kase px-3 py-0.5 font-display text-sm font-bold text-kase">
                  {command.action}
                </span>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

const statusStyle: Record<PostStatus, string> = {
  published: 'border border-ink text-ink',
  scheduled: 'border border-rule text-muted',
  held: 'bg-kase-soft text-kase',
  pending: 'border border-dashed border-muted/60 text-muted',
}

function ContentPlan({ t }: { t: Copy['content'] }) {
  return (
    <figure className="min-w-0 md:pt-3">
      <ExampleLabel>{t.example}</ExampleLabel>
      <div className="rounded-lg border border-rule">
        <p className="border-b border-rule px-5 py-3 font-mono text-xs tracking-wide text-muted">{t.heading}</p>
        <ul className="divide-y divide-rule">
          {t.posts.map((post) => (
            <li
              key={`${post.day}-${post.time}`}
              className="grid grid-cols-[3.25rem_minmax(0,1fr)] items-center gap-x-4 gap-y-2 px-5 py-4 sm:grid-cols-[3.25rem_minmax(0,1fr)_auto]"
            >
              <div className="flex flex-col font-mono text-xs tabular-nums">
                <span className="text-ink">{post.day}</span>
                <span className="text-muted">{post.time}</span>
              </div>
              <div className="flex min-w-0 flex-col">
                <span className="font-mono text-[0.6875rem] text-muted">{post.kind}</span>
                <span className="font-display text-base font-medium">{post.title}</span>
              </div>
              <span
                className={`col-start-2 justify-self-start rounded-full px-2.5 py-0.5 font-mono text-[0.6875rem] sm:col-start-3 sm:justify-self-end ${statusStyle[post.state]}`}
              >
                {post.state === 'published' && '✓ '}
                {post.status}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </figure>
  )
}

// Roughens the stamp's edges a little, the way rubber-stamp ink sits on paper.
function InkFilter() {
  return (
    <svg aria-hidden width="0" height="0" className="absolute">
      <filter id="ink-edge">
        <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="4" />
        <feDisplacementMap in="SourceGraphic" scale="1.6" />
      </filter>
    </svg>
  )
}
