import { useEffect, useState, type ReactNode } from 'react'
import { PRODUCT_NAME } from './brand'
import { copy, type Copy, type Lang, type PostStatus } from './copy'
import { KnowledgePreview } from './KnowledgePreview'
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
  const [selectedCmdIdx, setSelectedCmdIdx] = useState<number | null>(null)
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

      <header className="sticky top-0 z-30 border-b border-rule/80 bg-paper/90 backdrop-blur-md">
        <div className={`${container} flex items-center justify-between gap-4 py-4`}>
          <a href="#" className="font-display text-lg font-extrabold tracking-[-0.02em]">
            {PRODUCT_NAME}
          </a>
          <nav className="flex items-center gap-4 sm:gap-6 font-mono text-xs">
            <a
              href="#pilot"
              className="hidden rounded-full border border-kase/40 bg-kase-soft/70 px-3 py-1 font-medium text-kase transition-colors hover:bg-kase hover:text-on-kase sm:inline-flex sm:items-center sm:gap-1"
            >
              <span>{t.nav.waitlist}</span>
              <span aria-hidden>↓</span>
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
        </div>
      </header>

      <main>
        <section className={`${container} pt-10 pb-16 md:pt-20 md:pb-24`}>
          <div className="flex flex-wrap items-center gap-3">
            <p className="font-mono text-xs tracking-wide text-muted">{t.hero.kicker}</p>
            <span aria-hidden className="text-rule">·</span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-kase-soft px-2.5 py-0.5 font-mono text-[0.6875rem] font-medium text-kase">
              <span aria-hidden className="size-1.5 rounded-full bg-kase" />
              {t.hero.pilotBadge}
            </span>
          </div>

          <h1 className="mt-6 font-display text-[clamp(2.5rem,8.4vw,6.75rem)] leading-[0.95] font-extrabold tracking-[-0.045em]">
            {t.hero.promises.map((line) => (
              <span key={line} className="block">
                {line}
              </span>
            ))}
          </h1>

          <div className="mt-10 grid gap-8 md:mt-14 lg:grid-cols-[minmax(0,36rem)_minmax(0,1fr)] lg:items-end lg:justify-between">
            <div>
              <p className="text-xl leading-relaxed md:text-[1.375rem]">{t.hero.lead}</p>
              <div className="mt-8 flex flex-wrap items-center gap-5">
                <a
                  href="#pilot"
                  className="inline-flex h-13 items-center gap-3 rounded-md bg-kase px-7 font-display text-base font-bold text-on-kase shadow-sm transition-transform active:scale-[0.98]"
                >
                  {t.hero.cta}
                  <span aria-hidden>↓</span>
                </a>
                <p className="max-w-[32ch] font-mono text-xs leading-relaxed text-muted">{t.hero.note}</p>
              </div>
            </div>

            <HeroLoopPreview t={t.hero.preview} />
          </div>

          <nav aria-label={t.index.label} className="mt-14 flex flex-wrap items-center gap-2 font-mono text-xs md:mt-20">
            <span className="mr-2 text-muted">{t.index.label}:</span>
            {t.index.links.map((link, i) => (
              <a
                key={link.id}
                href={`#${link.id}`}
                className="rounded-md border border-rule bg-surface/50 px-3 py-1.5 text-ink transition-colors hover:border-kase hover:bg-kase-soft/50 hover:text-kase"
              >
                <span className="mr-1.5 text-kase">0{i + 1}</span>
                {link.label}
              </a>
            ))}
          </nav>
        </section>

        <Section id="karsilastirma" num="01" variant="surface">
          <h2 className={sectionTitle}>{t.comparison.title}</h2>
          <p className={lede}>{t.comparison.body}</p>
          <ComparisonTable t={t.comparison} />
        </Section>

        <Section id="whatsapp" num="02">
          <div className="grid items-center gap-12 md:grid-cols-[25rem_minmax(0,1fr)] md:gap-20">
            <div className="min-w-0 md:order-last">
              <h2 className={sectionTitle}>{t.whatsapp.title}</h2>
              <p className={lede}>{t.whatsapp.body}</p>
              <p className="mt-6 max-w-[34rem] border-l-2 border-kase pl-4 font-mono text-xs leading-relaxed text-muted">
                {t.whatsapp.note}
              </p>
            </div>
            <OwnerChat
              t={t.whatsapp}
              selectedCommand={selectedCmdIdx !== null ? t.whatsapp.commands[selectedCmdIdx] : null}
            />
          </div>
          <Commands
            t={t.whatsapp}
            selectedIdx={selectedCmdIdx}
            onSelect={(idx) => setSelectedCmdIdx(selectedCmdIdx === idx ? null : idx)}
          />
        </Section>

        <Section id="bilgi" num="03" variant="surface">
          <h2 className={sectionTitle}>{t.knowledge.title}</h2>
          <p className={`${lede} mb-12`}>{t.knowledge.body}</p>
          <KnowledgePreview t={t.knowledge} />
        </Section>

        <Section id="dm" num="04">
          <div className="grid items-center gap-12 md:grid-cols-[minmax(0,1fr)_25rem]">
            <div className="min-w-0">
              <h2 className={sectionTitle}>{t.demo.title}</h2>
              <p className={lede}>{t.demo.body}</p>
            </div>
            <PhoneDemo t={t.demo} />
          </div>
        </Section>

        <Section id="icerik" num="05" variant="surface">
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
              <ul className="mt-8 flex flex-col gap-3">
                {t.escalate.items.map((item, i) => (
                  <li key={item} className="rounded-xl border border-rule bg-surface/40 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-display text-lg font-bold">{item}</span>
                      <span className="rounded-full border border-kase/40 bg-kase-soft px-2.5 py-0.5 font-mono text-[0.6875rem] font-medium text-kase">
                        {t.escalate.badge}
                      </span>
                    </div>
                    <p className="mt-1.5 font-serif text-sm italic text-muted">{t.escalate.examples[i]}</p>
                  </li>
                ))}
              </ul>
            </div>

            <div className="min-w-0">
              <h2 className={sectionTitle}>{t.report.title}</h2>
              <p className={lede}>{t.report.body}</p>
              <figure className="mt-8">
                <ExampleLabel>{t.report.example}</ExampleLabel>
                <div className="rounded-xl border border-rule bg-surface p-6 font-mono text-sm shadow-sm">
                  <div className="mb-4 flex items-center justify-between gap-2 border-b border-dashed border-rule pb-3">
                    <p className="text-xs tracking-wide text-muted uppercase">{t.report.heading}</p>
                    <span className="rounded bg-kase-soft px-2 py-0.5 text-[0.6875rem] font-medium text-kase">
                      ✓ {t.report.verifiedTag}
                    </span>
                  </div>
                  <dl className="flex flex-col gap-3">
                    {t.report.rows.map(([label, value]) => (
                      <div key={label} className="flex items-baseline gap-2">
                        <dt className="shrink-0 text-ink">{label}</dt>
                        <span aria-hidden className="min-w-4 flex-1 border-b border-dotted border-muted/50" />
                        <dd className="shrink-0 font-bold tabular-nums text-ink">{value}</dd>
                      </div>
                    ))}
                  </dl>
                  <p className="mt-5 border-t-4 border-double border-rule pt-3 text-xs leading-relaxed text-muted">
                    {t.report.footerNote}
                  </p>
                </div>
              </figure>
            </div>
          </div>
        </Section>

        <Section id="kontrol" num="06" variant="surface">
          <h2 className={sectionTitle}>{t.control.title}</h2>
          <ul className="mt-12 grid gap-6 md:grid-cols-2">
            {t.control.items.map((item, i) => (
              <li key={item.title} className="rounded-xl border border-rule bg-paper p-6">
                <span className="font-mono text-xs text-kase">0{i + 1}</span>
                <h3 className="mt-2 font-display text-xl leading-snug font-bold tracking-[-0.01em]">{item.title}</h3>
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

        <Section id="sss" num="07" variant="surface">
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
          <div className="grid gap-14 lg:grid-cols-[minmax(0,1fr)_minmax(0,28rem)] lg:items-start">
            <div className="min-w-0">
              <h2 className="font-display text-[clamp(2.25rem,5.2vw,4.25rem)] leading-[0.98] font-extrabold tracking-[-0.04em]">
                {t.pilot.title}
              </h2>
              <p className={lede}>{t.pilot.body}</p>

              <div className="mt-12">
                <h3 className="font-mono text-xs tracking-wide text-muted uppercase">{t.pilot.expectationsTitle}</h3>
                <ul className="mt-5 grid gap-6 sm:grid-cols-2">
                  {t.pilot.expectations.map((item) => (
                    <li key={item.title} className="rounded-xl border border-rule bg-surface/50 p-5">
                      <span className="inline-block rounded bg-kase-soft px-2 py-0.5 font-mono text-[0.6875rem] font-medium text-kase">
                        {item.badge}
                      </span>
                      <h4 className="mt-2.5 font-display text-lg leading-snug font-bold tracking-[-0.01em]">{item.title}</h4>
                      <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-muted">{item.detail}</p>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            <WaitlistForm t={t.form} pilot={t.pilot} lang={lang} />
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

function HeroLoopPreview({ t }: { t: Copy['hero']['preview'] }) {
  return (
    <div className="ledger-grid rounded-2xl border border-rule p-4 sm:p-5">
      <div className="relative flex flex-col gap-3 rounded-xl border border-rule bg-paper p-4 shadow-sm font-display">
        <div className="border-b border-dashed border-rule pb-3">
          <p className="font-mono text-[0.6875rem] text-muted uppercase">{t.dmLabel}</p>
          <p className="mt-1 text-sm font-medium text-ink">{t.dmText}</p>
        </div>

        <div className="border-b border-dashed border-rule pb-3">
          <p className="font-mono text-[0.6875rem] text-muted uppercase">{t.factLabel}</p>
          <p className="mt-1 inline-block rounded bg-kase-soft px-2 py-0.5 font-mono text-xs font-medium text-kase">
            ✓ {t.factText}
          </p>
        </div>

        <div className="flex items-center justify-between gap-3 pt-0.5">
          <span className="font-mono text-[0.6875rem] text-muted uppercase">{t.stampLabel}</span>
          <span className="rounded border-2 border-kase px-2.5 py-0.5 font-display text-xs font-extrabold tracking-wider text-kase uppercase">
            {t.stampSub}
          </span>
        </div>
      </div>
    </div>
  )
}

function Section({
  id,
  num,
  variant = 'paper',
  children,
}: {
  id?: string
  num?: string
  variant?: 'paper' | 'surface'
  children: ReactNode
}) {
  const bg = variant === 'surface' ? 'bg-surface/45' : 'bg-paper'
  return (
    <section id={id} className={`scroll-mt-14 border-t border-rule ${bg}`}>
      <div className={`${container} py-20 md:py-28`}>
        {num && (
          <div className="mb-4 flex items-center gap-2 font-mono text-xs text-kase">
            <span>{num}</span>
            <span aria-hidden className="h-px w-6 bg-kase/50" />
          </div>
        )}
        {children}
      </div>
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

function ComparisonTable({ t }: { t: Copy['comparison'] }) {
  return (
    <div className="mt-12 grid gap-6 md:grid-cols-3">
      {t.rows.map((row) => (
        <article key={row.scenario} className="flex flex-col justify-between rounded-xl border border-rule bg-paper p-6 shadow-xs">
          <div>
            <h3 className="font-display text-xl leading-snug font-bold tracking-[-0.01em]">{row.scenario}</h3>
            <div className="mt-5 border-t border-rule pt-4">
              <p className="font-mono text-[0.6875rem] tracking-wide text-muted uppercase">{t.withoutLabel}</p>
              <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-muted">{row.without}</p>
            </div>
          </div>

          <div className="mt-5 rounded-lg border border-kase/20 bg-kase-soft/45 p-4">
            <p className="flex items-center gap-1.5 font-mono text-[0.6875rem] font-medium tracking-wide text-kase uppercase">
              <span aria-hidden className="size-1.5 rounded-full bg-kase" />
              {t.withLabel}
            </p>
            <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-ink">{row.withProduct}</p>
          </div>
        </article>
      ))}
    </div>
  )
}

function Commands({
  t,
  selectedIdx,
  onSelect,
}: {
  t: Copy['whatsapp']
  selectedIdx: number | null
  onSelect: (idx: number) => void
}) {
  return (
    <div className="mt-20 md:mt-28">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-display text-2xl font-bold tracking-[-0.02em]">{t.commandsTitle}</h3>
        <span className="font-mono text-xs text-kase">{t.commandsHint}</span>
      </div>
      <div className="mt-6 grid gap-3 md:grid-cols-2">
        {t.commands.map((command, idx) => {
          const active = selectedIdx === idx
          return (
            <button
              key={command.ask}
              type="button"
              aria-pressed={active}
              onClick={() => onSelect(idx)}
              className={`flex flex-col justify-between gap-3 rounded-xl border p-5 text-left transition-colors ${
                active
                  ? 'border-kase bg-kase-soft/40'
                  : 'border-rule bg-surface/35 hover:border-kase/60 hover:bg-surface/70'
              }`}
            >
              <p className="font-display text-lg font-bold tracking-[-0.01em] text-ink">“{command.ask}”</p>
              <div className="flex flex-col items-start gap-2 text-[0.9375rem] leading-relaxed text-muted">
                <span>{command.answer}</span>
                {command.action && (
                  <span className="rounded-full border border-kase bg-paper px-3 py-0.5 font-display text-xs font-bold text-kase">
                    {command.action}
                  </span>
                )}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

const statusStyle: Record<PostStatus, string> = {
  published: 'border border-ink text-ink bg-paper',
  scheduled: 'border border-rule text-muted bg-paper',
  held: 'bg-kase-soft text-kase font-medium',
  pending: 'border border-dashed border-muted/60 text-muted bg-paper',
}

function ContentPlan({ t }: { t: Copy['content'] }) {
  return (
    <figure className="min-w-0 md:pt-3">
      <ExampleLabel>{t.example}</ExampleLabel>
      <div className="overflow-hidden rounded-xl border border-rule bg-paper shadow-xs">
        <p className="border-b border-rule bg-surface/50 px-5 py-3 font-mono text-xs tracking-wide text-muted uppercase">
          {t.heading}
        </p>
        <ul className="divide-y divide-rule">
          {t.posts.map((post, idx) => (
            <li key={`${post.day}-${post.time}`} className="flex flex-col gap-2.5 px-5 py-4">
              <div className="grid grid-cols-[3rem_2.25rem_minmax(0,1fr)] items-center gap-x-3.5 gap-y-2 sm:grid-cols-[3.25rem_2.5rem_minmax(0,1fr)_auto]">
                <div className="flex flex-col font-mono text-xs tabular-nums">
                  <span className="font-bold text-ink">{post.day}</span>
                  <span className="text-muted">{post.time}</span>
                </div>
                <MiniPostThumb index={idx} kind={post.kind} />
                <div className="flex min-w-0 flex-col">
                  <span className="font-mono text-[0.6875rem] text-muted">{post.kind}</span>
                  <span className="truncate font-display text-base font-medium">{post.title}</span>
                </div>
                <span
                  className={`col-start-3 justify-self-start rounded-full px-2.5 py-0.5 font-mono text-[0.6875rem] sm:col-start-4 sm:justify-self-end ${statusStyle[post.state]}`}
                >
                  {post.state === 'published' && '✓ '}
                  {post.status}
                </span>
              </div>
              {post.state === 'held' && (
                <p className="rounded-md bg-kase-soft/60 px-3 py-1.5 font-mono text-[0.6875rem] leading-snug text-kase">
                  ⚠ {t.heldReason}
                </p>
              )}
            </li>
          ))}
        </ul>
      </div>
    </figure>
  )
}

function MiniPostThumb({ index, kind }: { index: number; kind: string }) {
  const palettes = [
    'bg-[#d7dccd] text-[#1f2a22]',
    'bg-[#e4e5f8] text-[#262a55]',
    'bg-[#f0e6d8] text-[#3d2e1e]',
    'bg-[#dfe7e2] text-[#1f2e28]',
  ]
  const palette = palettes[index % palettes.length]
  return (
    <div
      aria-hidden
      className={`relative flex h-11 w-8 shrink-0 flex-col justify-between overflow-hidden rounded border border-rule/80 p-1 font-display ${palette}`}
    >
      <span className="size-3 self-end rounded-full bg-current/20" />
      <span className="font-mono text-[0.45rem] font-bold tracking-tighter uppercase">{kind.slice(0, 3)}</span>
    </div>
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
