import { useState } from 'react'
import type { Copy } from './copy'
import { PhoneFrame } from './PhoneFrame'
import { Badge, CheckIcon, HandIcon, QuestionIcon } from './ui'

export function DraftDemo({ t }: { t: Copy['demo'] }) {
  const [scenario, setScenario] = useState(0)
  const [sourceOpen, setSourceOpen] = useState(false)
  const conversation = scenario === 0 ? t.known : t.unknown
  return (
    <div className="flex flex-col items-center gap-5">
      <div
        role="group"
        aria-label={t.title}
        className="flex flex-wrap justify-center gap-1 rounded-panel border border-border bg-surface p-1"
      >
        {t.tabs.map((label, i) => (
          <button
            key={label}
            type="button"
            aria-pressed={scenario === i}
            onClick={() => {
              setScenario(i)
              setSourceOpen(false)
            }}
            className="min-h-11 rounded-control px-4 text-sm font-semibold text-secondary hover:text-primary aria-pressed:bg-band aria-pressed:text-band-text"
          >
            {label}
          </button>
        ))}
      </div>
      <PhoneFrame label={t.example} clock={conversation.time}>
        <div className="flex items-center gap-3 border-b border-border px-4 py-3">
          <span
            aria-hidden
            className="grid size-9 shrink-0 place-items-center rounded-full bg-surface-subtle text-sm font-bold text-secondary"
          >
            {conversation.customer.slice(0, 2).toUpperCase()}
          </span>
          <div className="min-w-0">
            <p className="truncate text-base font-semibold">{conversation.customer}</p>
            <p className="text-sm text-secondary">{t.channel}</p>
          </div>
        </div>
        <div key={scenario} className="pop-in flex min-h-[26rem] flex-col gap-4 bg-canvas p-4">
          <p className="max-w-[90%] self-start rounded-2xl rounded-bl-sm border border-border bg-surface p-3 text-base leading-relaxed">
            {conversation.message}
          </p>
          {scenario === 0 ? (
            <>
              <p className="mt-6 self-end text-sm font-semibold text-action">{t.known.draftLabel}</p>
              <p className="max-w-[90%] self-end rounded-2xl rounded-br-sm bg-action p-3 text-base leading-relaxed text-on-action">
                {t.known.draft[0]}
                <button
                  type="button"
                  aria-expanded={sourceOpen}
                  aria-controls="demo-reply-source"
                  onClick={() => setSourceOpen(!sourceOpen)}
                  className="rounded bg-on-action/15 px-1 font-bold underline decoration-dotted underline-offset-4"
                >
                  {t.known.facts[0].value}
                </button>
                {t.known.draft[1]}
              </p>
              <p className="flex items-center justify-end gap-1 text-sm text-success">
                <CheckIcon />
                {t.known.sent}
              </p>
              <p className="text-right text-sm text-secondary">{t.known.hint}</p>
              {sourceOpen && (
                <p id="demo-reply-source" className="pop-in rounded-panel bg-fact p-3 text-sm text-on-fact">
                  {t.known.facts[0].source}
                </p>
              )}
            </>
          ) : (
            <>
              <div className="mt-3 rounded-panel border border-border bg-surface p-4">
                <Badge tone="attention" icon={<HandIcon />}>
                  {t.unknown.badge}
                </Badge>
                <p className="mt-3 text-base leading-relaxed">{t.unknown.body}</p>
              </div>
              <div className="rounded-panel bg-assistant p-4">
                <p className="flex items-center gap-2 text-sm font-semibold text-action">
                  <QuestionIcon />
                  {t.unknown.questionLabel}
                </p>
                <p className="mt-2 text-base leading-relaxed">{t.unknown.question}</p>
                <p className="mt-3 border-t border-border pt-3 text-sm text-secondary">
                  {t.unknown.afterAnswer}
                </p>
              </div>
            </>
          )}
        </div>
      </PhoneFrame>
    </div>
  )
}
