import type { ReactNode } from 'react'
import { ExampleLabel } from './ui'

// The phone outline shared by the illustrations. `label` marks the screen as an example.
export function PhoneFrame({ label, clock, children }: { label: string; clock: string; children: ReactNode }) {
  return (
    <figure className="mx-auto w-full max-w-[23.5rem]">
      <figcaption className="mb-3 flex justify-center">
        <ExampleLabel>{label}</ExampleLabel>
      </figcaption>
      <div className="dot-field rounded-[2.25rem] p-3 sm:p-5">
        <div className="rounded-[2.6rem] bg-[#0e1612] p-2 shadow-frame ring-1 ring-black/5 dark:ring-white/10">
          <div className="flex min-h-[34rem] flex-col overflow-hidden rounded-[2.1rem] bg-surface">
            <div aria-hidden className="flex items-center justify-between px-6 pt-2.5 pb-1 text-[0.75rem] font-semibold tabular-nums">
              <span>{clock}</span>
              <span className="h-5 w-20 rounded-full bg-[#0e1612]" />
              <span className="flex items-center gap-1">
                <span className="h-2 w-3 rounded-[2px] bg-current opacity-80" />
                <span className="flex h-2.5 w-5 items-center rounded-[3px] border border-current p-px opacity-80">
                  <span className="h-full w-3/4 rounded-[1px] bg-current" />
                </span>
              </span>
            </div>
            {children}
          </div>
        </div>
      </div>
    </figure>
  )
}
