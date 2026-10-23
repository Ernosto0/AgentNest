import type { ReactNode } from 'react'

type Props = {
  label: string
  title: string
  channel: string
  avatar: ReactNode
  children: ReactNode
}

// The phone outline shared by the illustrations. `label` marks the screen as an example.
export function PhoneFrame({ label, title, channel, avatar, children }: Props) {
  return (
    <figure className="w-full max-w-[25rem] justify-self-center">
      <figcaption className="mb-3 flex items-center gap-2 font-mono text-xs text-muted">
        <span aria-hidden className="size-1.5 rounded-full bg-kase" />
        {label}
      </figcaption>

      <div className="ledger-grid rounded-3xl border border-rule/80 p-3 sm:p-5">
        <div className="rounded-[2.25rem] border border-rule bg-surface p-2.5 shadow-sm">
          <div className="overflow-hidden rounded-[1.75rem] bg-paper font-display">
            <div className="flex items-center gap-3 border-b border-rule px-4 py-3">
              {avatar}
              <div className="flex min-w-0 flex-col">
                <span className="truncate text-sm font-bold">{title}</span>
                <span className="font-mono text-[0.625rem] text-muted">{channel}</span>
              </div>
            </div>
            {children}
          </div>
        </div>
      </div>
    </figure>
  )
}
