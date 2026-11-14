import { useState } from 'react'
import type { Copy } from './copy'
import { PhoneFrame } from './PhoneFrame'
import { Badge, CheckIcon, ClockIcon, HandIcon, PencilIcon, QuestionIcon, RotateIcon, buttonPrimary, buttonSecondary } from './ui'

type Scenario = 0 | 1

// One customer DM seen in the app's inbox, in two cases: the fact is on record (a sourced draft) or
// it is not (no draft; the question goes to the owner). Example data only.
export function DraftDemo({ t }: { t: Copy['demo'] }) {
  const [scenario, onScenario] = useState<Scenario>(0)
  const conversation = scenario === 0 ? t.known : t.unknown
  return (
    <div className="flex flex-col items-center gap-5">
      <ScenarioTabs t={t} scenario={scenario} onScenario={onScenario} />
      <PhoneFrame label={t.example} clock={conversation.time}>
        <div className="flex items-center gap-3 border-b border-border px-4 py-3">
          <span aria-hidden className="grid size-9 place-items-center rounded-full bg-surface-subtle text-xs font-bold text-secondary">
            {conversation.customer.slice(0, 2).toUpperCase()}
          </span>
          <div className="flex min-w-0 flex-col leading-tight">
            <span className="truncate text-sm font-semibold">{conversation.customer}</span>
            <span className="text-xs text-secondary">{t.channel}</span>
          </div>
        </div>
        <div key={scenario} className="pop-in flex flex-1 flex-col gap-3 bg-canvas px-3.5 pt-4 pb-4">
          <div className="flex max-w-[85%] flex-col gap-1">
            <p className="rounded-2xl rounded-bl-sm border border-border bg-surface px-3.5 py-2.5 text-[0.9375rem] leading-snug">
              {conversation.message}
            </p>
            <span className="pl-1 text-[0.6875rem] text-secondary tabular-nums">{conversation.time}</span>
          </div>
          {scenario === 0 ? <KnownDraft t={t.known} /> : <UnknownFact t={t.unknown} />}
        </div>
      </PhoneFrame>
    </div>
  )
}

function ScenarioTabs({ t, scenario, onScenario }: { t: Copy['demo']; scenario: Scenario; onScenario: (s: Scenario) => void }) {
  return (
    <div role="tablist" aria-label={t.title} className="inline-flex rounded-full border border-border bg-surface p-1">
      {t.tabs.map((label, i) => (
        <button
          key={label}
          role="tab"
          type="button"
          aria-selected={scenario === i}
          onClick={() => onScenario(i as Scenario)}
          className="min-h-9 rounded-full px-4 text-sm font-medium text-secondary transition-colors hover:text-primary aria-selected:bg-band aria-selected:text-band-text"
        >
          {label}
        </button>
      ))}
    </div>
  )
}

function KnownDraft({ t }: { t: Copy['demo']['known'] }) {
  const [approved, setApproved] = useState(false)
  const [edited, setEdited] = useState(false)
  const [active, setActive] = useState<number | null>(null)
  const [before, between, after] = t.draft
  const closing = edited ? t.editAlt : after

  const fact = (n: number) => (
    <button
      type="button"
      aria-pressed={active === n}
      aria-label={`${t.facts[n - 1].value}: ${t.facts[n - 1].source}`}
      onClick={() => setActive(active === n ? null : n)}
      onMouseEnter={() => setActive(n)}
      onMouseLeave={() => setActive(null)}
      className={`rounded px-1 font-semibold transition-colors ${active === n ? 'bg-action text-on-action' : 'bg-fact text-on-fact'}`}
    >
      {t.facts[n - 1].value}
      <sup className="ml-0.5 text-[0.625rem]">{n}</sup>
    </button>
  )

  const text = (
    <>
      {before}
      {fact(1)}
      {between}
      {fact(2)}
      <span className={edited ? 'underline decoration-action/50 decoration-dashed underline-offset-4' : ''}>{closing}</span>
    </>
  )

  if (approved) {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex max-w-[88%] flex-col items-end gap-1 self-end">
          <p className="pop-in rounded-2xl rounded-br-sm bg-action px-3.5 py-2.5 text-[0.9375rem] leading-snug text-on-action">
            {before}
            {t.facts[0].value}
            {between}
            {t.facts[1].value}
            {closing}
          </p>
          <span aria-live="polite" className="flex items-center gap-1 pr-1 text-[0.6875rem] font-medium text-success">
            <CheckIcon aria-hidden /> {t.sent}
          </span>
        </div>
        <button type="button" onClick={() => setApproved(false)} className={`${buttonSecondary} mt-auto min-h-10 self-center text-sm`}>
          <RotateIcon aria-hidden />
          {t.replay}
        </button>
      </div>
    )
  }

  return (
    <div className="mt-auto flex flex-col rounded-panel border border-border bg-surface p-3.5">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-secondary">{t.draftLabel}</span>
        {edited ? (
          <Badge tone="info" size="sm" icon={<PencilIcon />}>
            {t.editing}
          </Badge>
        ) : (
          <Badge tone="attention" size="sm" icon={<ClockIcon />}>
            {t.pending}
          </Badge>
        )}
      </div>
      <p className="text-[0.9375rem] leading-relaxed">{text}</p>
      <ol className="mt-3 flex flex-col gap-0.5 border-t border-dashed border-border pt-2.5 text-[0.6875rem] leading-snug text-secondary">
        {t.facts.map((f, i) => (
          <li
            key={f.source}
            className={`flex gap-1.5 rounded px-1.5 py-1 transition-colors ${active === i + 1 ? 'bg-fact font-medium text-on-fact' : ''}`}
          >
            <span className="font-semibold text-action">{i + 1}</span>
            <span className="min-w-0">{f.source}</span>
          </li>
        ))}
      </ol>
      <div className="mt-3 flex gap-2">
        <button type="button" onClick={() => setApproved(true)} className={`${buttonPrimary} min-h-10 flex-1 px-3 text-sm whitespace-nowrap`}>
          <CheckIcon aria-hidden />
          {t.approve}
        </button>
        <button type="button" onClick={() => setEdited((v) => !v)} className={`${buttonSecondary} min-h-10 px-3 text-sm`}>
          {edited ? t.saveEdit : t.edit}
        </button>
      </div>
      <p className="mt-2 text-center text-[0.6875rem] text-secondary">{t.hint}</p>
    </div>
  )
}

function UnknownFact({ t }: { t: Copy['demo']['unknown'] }) {
  return (
    <div className="mt-auto flex flex-col gap-3">
      <div className="rounded-panel border border-border bg-surface p-3.5">
        <Badge tone="attention" size="sm" icon={<HandIcon />}>
          {t.badge}
        </Badge>
        <p className="mt-2 font-heading text-[0.9375rem] font-bold">{t.title}</p>
        <p className="mt-1 text-sm leading-relaxed text-secondary">{t.body}</p>
      </div>
      <div className="rounded-panel bg-assistant p-3.5">
        <p className="flex items-center gap-1.5 text-xs font-semibold text-action">
          <QuestionIcon aria-hidden /> {t.questionLabel}
        </p>
        <p className="mt-1.5 text-sm leading-relaxed">{t.question}</p>
        <div aria-hidden className="mt-3 flex min-h-10 items-center rounded-control border border-border bg-surface px-3 text-sm text-secondary">
          {t.answer}…
        </div>
        <p className="mt-2 text-[0.6875rem] leading-snug text-secondary">{t.afterAnswer}</p>
      </div>
    </div>
  )
}
