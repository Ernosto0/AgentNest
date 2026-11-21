import { useState } from 'react'
import { Brand } from './BrandIdentity'
import type { Copy } from './copy'
import { Badge, BookIcon, CalendarIcon, ChatIcon, CheckIcon, ExampleLabel, HandIcon } from './ui'

// Illustrative recorded outcomes, never a live connection or a real customer send.
export function HeroPreview({ t }: { t: Copy['preview'] }) {
  const [sourceOpen, setSourceOpen] = useState(false)
  return (
    <figure className="relative mx-auto w-full min-w-0 max-w-[36rem] lg:mr-0">
      <figcaption className="mb-3 flex justify-end">
        <ExampleLabel>{t.example}</ExampleLabel>
      </figcaption>
      <div className="overflow-hidden rounded-frame border border-border bg-surface shadow-frame">
        <div className="flex items-center gap-3 border-b border-border px-5 py-4">
          <Brand variant="monogram" size="sm" />
          <div className="min-w-0 flex-1">
            <p className="font-heading text-base font-bold">{t.waitingTitle}</p>
            <p className="text-sm text-secondary">{t.date}</p>
          </div>
          <div className="text-right">
            <Badge tone="brand">Full Auto</Badge>
            <p className="mt-1 text-xs text-secondary">{t.screen}</p>
          </div>
        </div>
        <div className="bg-canvas p-4 sm:p-6">
          <dl className="grid grid-cols-3 gap-2">
            {t.metrics.map((label, i) => (
              <div key={label} className="rounded-panel border border-border bg-surface p-3">
                <dd className="font-heading text-3xl font-extrabold tracking-tight text-action tabular-nums">
                  {t.metricValues[i]}
                </dd>
                <dt className="mt-1 text-sm leading-snug text-secondary">{label}</dt>
              </div>
            ))}
          </dl>
          <div className="mt-5 rounded-panel border border-border bg-surface p-4 sm:p-5">
            <div className="flex items-center gap-2 text-sm text-secondary">
              <ChatIcon /> Instagram DM <span className="ml-auto tabular-nums">{t.time}</span>
            </div>
            <p className="mt-4 max-w-[90%] rounded-2xl rounded-bl-sm bg-surface-subtle p-3 text-base">
              {t.message}
            </p>
            <div className="mt-3 ml-5 rounded-2xl rounded-br-sm bg-action p-3 text-base leading-relaxed text-on-action">
              {t.reply[0]}
              <strong>{t.facts[0]}</strong>
              {t.reply[1]}
            </div>
            <p className="mt-3 flex items-center justify-end gap-1.5 text-sm font-medium text-success">
              <CheckIcon />
              {t.sent}
            </p>
            <div className="mt-4 border-t border-border pt-3">
              <button
                type="button"
                aria-expanded={sourceOpen}
                aria-controls="hero-reply-source"
                onClick={() => setSourceOpen(!sourceOpen)}
                className="flex min-h-11 items-center gap-2 rounded-control text-sm font-semibold text-action"
              >
                <BookIcon />
                {sourceOpen ? t.hideSource : t.showSource}
              </button>
              {sourceOpen && (
                <p
                  id="hero-reply-source"
                  className="pop-in rounded-control bg-fact px-3 py-2 text-sm text-on-fact"
                >
                  {t.source} · {t.facts[0]}
                </p>
              )}
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-secondary">
            <span className="flex items-center gap-1.5">
              <HandIcon />
              {t.queueCounts[1]} · {t.queue[1]}
            </span>
            <span className="flex items-center gap-1.5">
              <CalendarIcon />
              {t.queueCounts[2]} · {t.queue[2]}
            </span>
          </div>
        </div>
      </div>
    </figure>
  )
}
