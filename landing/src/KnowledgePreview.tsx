import type { Copy } from './copy'

type Props = { t: Copy['knowledge'] }

export function KnowledgePreview({ t }: Props) {
  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] lg:items-start lg:gap-14">
      <div className="rounded-xl border border-rule bg-surface/60 p-6">
        <p className="font-mono text-xs tracking-wide text-kase uppercase">{t.extractKicker}</p>
        <h3 className="mt-2 font-display text-xl leading-snug font-bold tracking-[-0.01em]">{t.extractTitle}</h3>
        <p className="mt-2.5 text-base leading-relaxed text-muted">{t.extractBody}</p>

        <div className="mt-5 rounded-lg border border-dashed border-muted/50 bg-paper p-4">
          <p className="font-mono text-[0.6875rem] tracking-wide text-muted uppercase">{t.extractSourceLabel}</p>
          <p className="mt-2 font-mono text-xs leading-relaxed text-ink">“{t.extractSourceSample}”</p>
        </div>
      </div>

      <div className="rounded-xl border border-rule bg-paper">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule px-5 py-3.5">
          <span className="font-mono text-xs tracking-wide text-muted uppercase">{t.ledgerTitle}</span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-kase-soft px-2.5 py-0.5 font-mono text-[0.6875rem] font-medium text-kase">
            <span aria-hidden>✓</span>
            {t.verifiedBadge}
          </span>
        </div>

        <ul className="divide-y divide-rule">
          {t.facts.map((fact, i) => (
            <li
              key={fact.label}
              className="grid gap-2 px-5 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:gap-6"
            >
              <div className="flex min-w-0 flex-col">
                <div className="flex items-center gap-2 font-mono text-[0.6875rem] text-muted">
                  <span className="text-kase">{i + 1}</span>
                  <span>{fact.category}</span>
                  <span aria-hidden>·</span>
                  <span>{fact.verifiedAt}</span>
                </div>
                <span className="mt-0.5 font-display text-base font-medium">{fact.label}</span>
              </div>
              <span className="justify-self-start rounded-md bg-kase-soft px-3 py-1 font-display text-base font-bold text-kase sm:justify-self-end">
                {fact.value}
              </span>
            </li>
          ))}
        </ul>

        <div className="border-t border-rule bg-surface/50 px-5 py-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded border border-kase px-2 py-0.5 font-mono text-[0.6875rem] font-medium text-kase uppercase">
              {t.missingRule.badge}
            </span>
            <span className="font-mono text-xs text-ink">{t.missingRule.question}</span>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-muted">{t.missingRule.outcome}</p>
        </div>
      </div>
    </div>
  )
}

