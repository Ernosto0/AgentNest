import { useState } from 'react'
import { PRODUCT_NAME } from './brand'
import { Brand } from './BrandIdentity'
import type { Copy } from './copy'
import {
  Badge,
  CheckIcon,
  ChatIcon,
  ClockIcon,
  ExampleLabel,
  HandIcon,
  PauseIcon,
  RotateIcon,
  buttonPrimary,
  buttonSecondary,
} from './ui'

// A simplified "Today" screen in the app's own visual language, plus one pending reply that can be
// approved here. An illustration with example data, labelled as such; nothing is sent anywhere.
export function HeroPreview({ t }: { t: Copy['preview'] }) {
  const [approved, setApproved] = useState(false)
  const counts = t.queueCounts.map((n, i) => (i === 0 && approved ? n - 1 : n))
  const metrics = t.metricValues.map((n, i) => (i === 1 && approved ? n + 1 : n))
  const queueIcons = [<ClockIcon key="c" />, <HandIcon key="h" />, <PauseIcon key="p" />]

  return (
    <figure className="relative mx-auto w-full min-w-0 max-w-[36rem] lg:mr-0">
      <figcaption className="mb-3 flex justify-end">
        <ExampleLabel>{t.example}</ExampleLabel>
      </figcaption>

      <div className="overflow-hidden rounded-frame border border-border bg-surface shadow-frame">
        <div className="flex items-center gap-3 border-b border-border px-4 py-3">
          <Brand variant="monogram" size="sm" />
          <div className="flex min-w-0 flex-col leading-tight">
            <Brand variant="wordmark" size="xs" label={PRODUCT_NAME} />
            <span className="text-xs text-secondary">{t.screen}</span>
          </div>
          <span aria-hidden className="ml-auto flex gap-1.5">
            <span className="size-2 rounded-full bg-border" />
            <span className="size-2 rounded-full bg-border" />
            <span className="size-2 rounded-full bg-border" />
          </span>
        </div>

        <div className="flex flex-col gap-4 bg-canvas p-4 sm:p-5 sm:pb-16">
          <div>
            <p className="text-xs text-secondary">{t.date}</p>
            <p className="mt-0.5 font-heading text-xl font-bold tracking-tight">{t.greeting}</p>
          </div>

          <div className="rounded-panel border border-border bg-surface p-4">
            <p className="font-heading text-sm font-semibold">{t.waitingTitle}</p>
            <ul className="mt-2 divide-y divide-border">
              {t.queue.map((label, i) => (
                <li key={label} className="flex items-center gap-3 py-2.5 text-sm">
                  <span aria-hidden className="text-base text-attention">
                    {queueIcons[i]}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{label}</span>
                  <span
                    key={counts[i]}
                    className="pop-in grid min-w-7 place-items-center rounded-md bg-attention-subtle px-1.5 py-0.5 text-sm font-bold tabular-nums text-attention"
                  >
                    {counts[i]}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <dl className="grid grid-cols-3 gap-2.5">
            {t.metrics.map((label, i) => (
              <div key={label} className="rounded-panel bg-surface-subtle px-3 py-2.5">
                <dt className="min-h-8 text-[0.6875rem] leading-4 text-secondary sm:min-h-0 sm:text-xs">{label}</dt>
                <dd key={metrics[i]} className="pop-in mt-1 font-heading text-2xl font-bold tabular-nums text-action">
                  {metrics[i]}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </div>

      {/* The pending reply. From tablet width it overlaps the frame's empty bottom edge. */}
      <div className="relative z-10 mt-4 rounded-panel border border-border bg-surface p-4 shadow-frame sm:mx-6 sm:-mt-10 lg:mr-0 lg:-ml-6 lg:w-[24rem]">
        <div className="flex items-center gap-2.5">
          <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-surface-subtle text-xs font-bold text-secondary">
            {t.customer.slice(0, 2).toUpperCase()}
          </span>
          <div className="flex min-w-0 flex-1 flex-col leading-tight">
            <span className="truncate text-sm font-semibold">{t.customer}</span>
            <span className="flex items-center gap-1 text-xs text-secondary">
              <ChatIcon aria-hidden /> Instagram · {t.time}
            </span>
          </div>
          <span aria-live="polite">
            {approved ? (
              <Badge tone="success" size="sm" icon={<CheckIcon />}>
                {t.sent}
              </Badge>
            ) : (
              <Badge tone="attention" size="sm" icon={<ClockIcon />}>
                {t.pending}
              </Badge>
            )}
          </span>
        </div>

        <p className="mt-3 rounded-xl rounded-tl-sm bg-surface-subtle px-3 py-2 text-sm leading-snug">{t.message}</p>
        <p className="mt-2.5 text-sm leading-relaxed">
          {t.reply[0]}
          <FactMark>{t.facts[0]}</FactMark>
          {t.reply[1]}
          <FactMark>{t.facts[1]}</FactMark>
          {t.reply[2]}
        </p>

        <div className="mt-3.5 flex items-center gap-2">
          {approved ? (
            <button type="button" onClick={() => setApproved(false)} className={`${buttonSecondary} min-h-10 text-sm`}>
              <RotateIcon />
              {t.undo}
            </button>
          ) : (
            <button type="button" onClick={() => setApproved(true)} className={`${buttonPrimary} min-h-10 flex-1 text-sm`}>
              <CheckIcon />
              {t.approve}
            </button>
          )}
        </div>
      </div>
    </figure>
  )
}

function FactMark({ children }: { children: string }) {
  return (
    <mark className="inline-flex items-baseline gap-0.5 rounded bg-fact px-1 font-semibold text-on-fact">
      {children}
      <CheckIcon className="self-center text-[0.75em]" />
    </mark>
  )
}
