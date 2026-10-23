import { useState } from 'react'
import type { Copy } from './copy'
import { PhoneFrame } from './PhoneFrame'

type Props = { t: Copy['demo'] }

// An illustration of one approval, not a live product. It is labelled as an example.
export function PhoneDemo({ t }: Props) {
  const [approved, setApproved] = useState(false)
  const [hasInteracted, setHasInteracted] = useState(false)
  const [useAltClosing, setUseAltClosing] = useState(false)
  const [activeFact, setActiveFact] = useState<number | null>(null)
  const [before, between, after] = t.draft
  const closingText = useAltClosing ? t.editClosingAlt : after

  const avatar = (
    <span aria-hidden className="grid size-8 place-items-center rounded-full bg-surface text-xs font-bold text-muted">
      {t.customer.slice(0, 2).toUpperCase()}
    </span>
  )

  return (
    <PhoneFrame label={t.example} title={t.customer} channel={t.channel} avatar={avatar}>
      <div className="flex flex-col gap-4 px-4 pt-5 pb-4">
        <div className="flex max-w-[85%] flex-col gap-1">
          <p className="rounded-2xl rounded-bl-sm bg-surface px-3.5 py-2.5 text-[0.9375rem] leading-snug">{t.message}</p>
          <span className="font-mono text-[0.6875rem] text-muted">{t.received}</span>
        </div>

        <div className="relative rounded-xl border border-rule bg-surface/30 p-3.5">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="font-mono text-[0.6875rem] tracking-wide text-muted uppercase">{t.draftLabel}</p>
            {useAltClosing && !approved && (
              <span className="rounded bg-kase-soft px-1.5 py-0.5 font-mono text-[0.625rem] font-medium text-kase">
                {t.editingBadge}
              </span>
            )}
          </div>
          <p className="text-[0.9375rem] leading-relaxed">
            {before}
            <Fact
              n={1}
              value={t.facts[0].value}
              active={activeFact === 1}
              onSelect={() => setActiveFact(activeFact === 1 ? null : 1)}
              onHover={(v) => setActiveFact(v ? 1 : null)}
            />
            {between}
            <Fact
              n={2}
              value={t.facts[1].value}
              active={activeFact === 2}
              onSelect={() => setActiveFact(activeFact === 2 ? null : 2)}
              onHover={(v) => setActiveFact(v ? 2 : null)}
            />
            <span className={useAltClosing ? 'underline decoration-kase/60 decoration-dashed underline-offset-4' : ''}>
              {closingText}
            </span>
          </p>
          <ol className="mt-3 flex flex-col gap-1 border-t border-dashed border-rule pt-2.5 font-mono text-[0.6875rem] leading-snug text-muted">
            {t.facts.map((fact, i) => {
              const num = i + 1
              const isHighlighted = activeFact === num
              return (
                <li
                  key={fact.source}
                  onMouseEnter={() => setActiveFact(num)}
                  onMouseLeave={() => setActiveFact(null)}
                  onClick={() => setActiveFact(activeFact === num ? null : num)}
                  className={`flex cursor-pointer gap-1.5 rounded px-1.5 py-0.5 transition-colors ${
                    isHighlighted ? 'bg-kase-soft font-medium text-kase' : 'hover:bg-surface'
                  }`}
                >
                  <span className="text-kase">{num}</span>
                  <span className="min-w-0">{fact.source}</span>
                </li>
              )
            })}
          </ol>

          {approved && (
            <div
              aria-hidden
              className="stamp pointer-events-none absolute -top-5 right-3 rounded-md border-[3px] border-kase bg-paper/85 p-[3px] text-kase"
            >
              <div className="rounded-[3px] border border-kase px-3 py-1 text-center">
                <div className="font-display text-lg leading-none font-extrabold tracking-[0.12em] uppercase">{t.stamp}</div>
                <div className="mt-0.5 font-mono text-[0.625rem] tracking-[0.2em]">{t.approvedAt}</div>
              </div>
            </div>
          )}
        </div>

        <div aria-live="polite" className="min-h-11">
          {approved ? (
            <div className="flex items-center justify-between gap-3 py-2.5">
              <span className="font-mono text-xs font-medium text-kase">
                ✓ {t.sent} · {t.approvedAt}
              </span>
              <button
                type="button"
                onClick={() => setApproved(false)}
                className="font-mono text-xs text-muted underline underline-offset-4 hover:text-ink"
              >
                {t.replay}
              </button>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setApproved(true)
                    setHasInteracted(true)
                  }}
                  className="h-11 flex-1 rounded-lg bg-kase text-sm font-bold text-on-kase shadow-sm transition-transform hover:opacity-95 active:scale-[0.98]"
                >
                  {t.approve}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setUseAltClosing((v) => !v)
                    setHasInteracted(true)
                  }}
                  className="h-11 rounded-lg border border-rule bg-paper px-3.5 text-sm font-medium text-ink transition-colors hover:border-kase hover:text-kase"
                >
                  {useAltClosing ? t.saveEdit : t.edit}
                </button>
              </div>
              {!hasInteracted && (
                <p className="font-mono text-[0.6875rem] text-kase">{t.tapHint}</p>
              )}
            </div>
          )}
        </div>
      </div>
    </PhoneFrame>
  )
}

function Fact({
  n,
  value,
  active,
  onSelect,
  onHover,
}: {
  n: number
  value: string
  active: boolean
  onSelect: () => void
  onHover: (hovering: boolean) => void
}) {
  return (
    <mark
      onClick={onSelect}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      className={`cursor-pointer rounded-[3px] px-1 font-medium transition-colors ${
        active ? 'bg-kase text-on-kase' : 'bg-kase-soft text-kase'
      }`}
    >
      {value}
      <sup className="ml-0.5 font-mono text-[0.625rem]">{n}</sup>
    </mark>
  )
}
