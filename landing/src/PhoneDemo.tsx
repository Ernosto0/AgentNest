import { useState } from 'react'
import type { Copy } from './copy'
import { PhoneFrame } from './PhoneFrame'

type Props = { t: Copy['demo'] }

// An illustration of one approval, not a live product. It is labelled as an example.
export function PhoneDemo({ t }: Props) {
  const [approved, setApproved] = useState(false)
  const [before, between, after] = t.draft

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

        <div className="relative rounded-xl border border-rule p-3.5">
          <p className="mb-2 font-mono text-[0.6875rem] tracking-wide text-muted uppercase">{t.draftLabel}</p>
          <p className="text-[0.9375rem] leading-relaxed">
            {before}
            <Fact n={1} value={t.facts[0].value} />
            {between}
            <Fact n={2} value={t.facts[1].value} />
            {after}
          </p>
          <ol className="mt-3 flex flex-col gap-0.5 border-t border-dashed border-rule pt-2.5 font-mono text-[0.6875rem] leading-snug text-muted">
            {t.facts.map((fact, i) => (
              <li key={fact.source} className="flex gap-1.5">
                <span className="text-kase">{i + 1}</span>
                <span className="min-w-0">{fact.source}</span>
              </li>
            ))}
          </ol>

          {approved && (
            <div
              aria-hidden
              className="stamp pointer-events-none absolute -top-5 right-3 rounded-md border-[3px] border-kase bg-paper/70 p-[3px] text-kase"
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
              <span className="font-mono text-xs text-kase">
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
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setApproved(true)}
                className="h-11 flex-1 rounded-lg bg-kase text-sm font-bold text-on-kase transition-transform active:scale-[0.98]"
              >
                {t.approve}
              </button>
              <button
                type="button"
                disabled
                className="h-11 cursor-default rounded-lg border border-rule px-4 text-sm font-medium text-muted"
              >
                {t.edit}
              </button>
            </div>
          )}
        </div>
      </div>
    </PhoneFrame>
  )
}

function Fact({ n, value }: { n: number; value: string }) {
  return (
    <mark className="rounded-[3px] bg-kase-soft px-1 font-medium text-kase">
      {value}
      <sup className="ml-0.5 font-mono text-[0.625rem]">{n}</sup>
    </mark>
  )
}
