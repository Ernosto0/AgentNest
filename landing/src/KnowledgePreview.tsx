import { useState } from 'react'
import type { Copy } from './copy'
import { AlertIcon, ArrowDownIcon, ArrowRightIcon, Badge, CheckIcon, ExampleLabel, RotateIcon, buttonSecondary } from './ui'

// Paste → picked-out facts → the owner verifies each one. Mirrors the app's knowledge rows:
// "Verify" is the primary action only for unverified facts. Example data only.
const INITIAL = [true, true, false, false]

export function KnowledgePreview({ t, example }: { t: Copy['knowledge']; example: string }) {
  const [verified, setVerified] = useState<boolean[]>(INITIAL)
  const done = verified.filter(Boolean).length
  const progress = t.progress.replace('{n}', String(done)).replace('{total}', String(verified.length))

  return (
    <div className="reveal grid items-start gap-4 lg:grid-cols-[minmax(0,0.85fr)_auto_minmax(0,1.15fr)] lg:gap-6">
      <figure className="rounded-panel border border-dashed border-control/50 bg-surface p-5">
        <figcaption className="flex items-center justify-between gap-2">
          <span className="type-eyebrow text-secondary">{t.pasteLabel}</span>
          <ExampleLabel>{example}</ExampleLabel>
        </figcaption>
        <p className="mt-3 text-[0.9375rem] leading-relaxed">“{t.pasteSample}”</p>
        <p className="mt-4 flex items-center gap-1.5 border-t border-border pt-3 text-xs text-secondary">
          <AlertIcon aria-hidden className="text-attention" />
          {t.pasteNote}
        </p>
      </figure>

      <span aria-hidden className="grid place-items-center text-xl text-control lg:pt-24">
        <ArrowDownIcon className="lg:hidden" />
        <ArrowRightIcon className="hidden lg:block" />
      </span>

      <div className="overflow-hidden rounded-panel border border-border bg-surface">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3.5">
          <span className="font-heading text-sm font-bold">{t.ledgerTitle}</span>
          <span className="flex items-center gap-3">
            <span aria-live="polite" className="text-xs font-medium text-secondary tabular-nums">
              {progress}
            </span>
            <span aria-hidden className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-subtle">
              <span
                className="block h-full rounded-full bg-action transition-[width] duration-500"
                style={{ width: `${(done / verified.length) * 100}%` }}
              />
            </span>
          </span>
        </div>

        <ul className="divide-y divide-border">
          {t.facts.map((fact, i) => (
            <li key={fact.label} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-5 py-3.5">
              <div className="flex min-w-0 flex-col">
                <span className="text-xs text-secondary">
                  {fact.category} · {fact.label}
                </span>
                <span className="mt-0.5 font-heading text-[0.9375rem] font-bold tabular-nums">{fact.value}</span>
              </div>
              {verified[i] ? (
                <Badge tone="success" size="sm" icon={<CheckIcon />} className="pop-in">
                  {t.verified}
                </Badge>
              ) : (
                <span className="flex flex-col items-end gap-1.5 sm:flex-row sm:items-center sm:gap-2">
                  <Badge tone="attention" size="sm">
                    {t.unverified}
                  </Badge>
                  <button
                    type="button"
                    onClick={() => setVerified((v) => v.map((x, j) => (j === i ? true : x)))}
                    aria-label={`${t.verify}: ${fact.label}`}
                    className="inline-flex min-h-9 items-center gap-1.5 rounded-control bg-action px-3 text-xs font-semibold text-on-action hover:bg-action-hover"
                  >
                    <CheckIcon aria-hidden />
                    {t.verify}
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-surface-subtle px-5 py-3">
          <p className="text-xs text-secondary">{t.usageNote}</p>
          {done === verified.length && (
            <button type="button" onClick={() => setVerified(INITIAL)} className={`${buttonSecondary} min-h-9 px-3 text-xs`}>
              <RotateIcon aria-hidden />
              {t.reset}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
