import { useEffect, useRef, type ReactNode, type SVGProps } from 'react'

// Stroke icons drawn the same way as the app's (frontend/src/components/icons.tsx).
// Decorative: meaning is always carried by adjacent text.
function Svg({ children, ...props }: SVGProps<SVGSVGElement> & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  )
}

type IconProps = SVGProps<SVGSVGElement>

export const CheckIcon = (p: IconProps) => <Svg {...p}><path d="m5 12 5 5 9-10" /></Svg>
export const ClockIcon = (p: IconProps) => <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Svg>
export const CalendarIcon = (p: IconProps) => <Svg {...p}><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></Svg>
export const PauseIcon = (p: IconProps) => <Svg {...p}><path d="M9 5v14M15 5v14" /></Svg>
export const HandIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 11V5a1.5 1.5 0 0 1 3 0v5m0-1V4a1.5 1.5 0 0 1 3 0v6m0-4a1.5 1.5 0 0 1 3 0v6m0-3a1.5 1.5 0 0 1 3 0v6a7 7 0 0 1-7 7h-1a6 6 0 0 1-5-3l-3-5a1.5 1.5 0 0 1 2.5-1.5L7 14" />
  </Svg>
)
export const AlertIcon = (p: IconProps) => <Svg {...p}><path d="M12 3 2 20h20Z" /><path d="M12 10v4M12 17.5v.01" /></Svg>
export const TagIcon = (p: IconProps) => <Svg {...p}><path d="M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9Z" /><path d="M7.5 7.5v.01" /></Svg>
export const ShieldCheckIcon = (p: IconProps) => <Svg {...p}><path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6Z" /><path d="m9 12 2 2 4-4" /></Svg>
export const ChartIcon = (p: IconProps) => <Svg {...p}><path d="M4 3v17h17M8 15v-4M13 15V7M18 15v-7" /></Svg>
export const BookIcon = (p: IconProps) => <Svg {...p}><path d="M12 5C8 3 5 3 3 4v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-2-1-5-1-9 1Zm0 0v15" /></Svg>
export const ChatIcon = (p: IconProps) => <Svg {...p}><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-5A8 8 0 1 1 21 12Z" /></Svg>
export const SendIcon = (p: IconProps) => <Svg {...p}><path d="m4 12 16-8-6 16-3-7Z" /></Svg>
export const InboxIcon = (p: IconProps) => <Svg {...p}><path d="M3 13h5l1 3h6l1-3h5" /><path d="m5 5-2 8v6h18v-6l-2-8Z" /></Svg>
export const UsersIcon = (p: IconProps) => <Svg {...p}><circle cx="9" cy="8" r="3" /><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6M21 21v-3a6 6 0 0 0-4-5" /></Svg>
export const ListIcon = (p: IconProps) => <Svg {...p}><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" /></Svg>
export const SettingsIcon = (p: IconProps) => <Svg {...p}><path d="M4 7h2m6 0h8M4 17h8m6 0h2" /><circle cx="9" cy="7" r="3" /><circle cx="15" cy="17" r="3" /></Svg>
export const LockIcon = (p: IconProps) => <Svg {...p}><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></Svg>
export const KeyIcon = (p: IconProps) => <Svg {...p}><circle cx="8" cy="15" r="4" /><path d="m11 12 9-9M17 6l3 3M14 9l2 2" /></Svg>
export const LayersIcon = (p: IconProps) => <Svg {...p}><path d="m12 3 9 5-9 5-9-5Z" /><path d="m3 13 9 5 9-5" /></Svg>
export const TrashIcon = (p: IconProps) => (
  <Svg {...p}><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13M9 7V4h6v3" /></Svg>
)
export const SmartphoneIcon = (p: IconProps) => <Svg {...p}><rect x="7" y="2.5" width="10" height="19" rx="2" /><path d="M11 18.5h2" /></Svg>
export const ImageIcon = (p: IconProps) => <Svg {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="1.5" /><path d="m21 16-5-5-9 9" /></Svg>
export const MinusCircleIcon = (p: IconProps) => <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M8 12h8" /></Svg>
export const QuestionIcon = (p: IconProps) => (
  <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17v.01" /></Svg>
)
export const ArrowRightIcon = (p: IconProps) => <Svg {...p}><path d="M5 12h14M13 6l6 6-6 6" /></Svg>
export const ArrowDownIcon = (p: IconProps) => <Svg {...p}><path d="M12 5v14M6 13l6 6 6-6" /></Svg>
export const ArrowUpIcon = (p: IconProps) => <Svg {...p}><path d="M12 19V5M6 11l6-6 6 6" /></Svg>
export const PlusIcon = (p: IconProps) => <Svg {...p}><path d="M12 5v14M5 12h14" /></Svg>
export const MoonIcon = (p: IconProps) => <Svg {...p}><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" /></Svg>
export const SunIcon = (p: IconProps) => (
  <Svg {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></Svg>
)
export const PencilIcon = (p: IconProps) => <Svg {...p}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></Svg>
export const RotateIcon = (p: IconProps) => <Svg {...p}><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" /></Svg>

/** The app's brand tile: the initial on the selected-navigation green. */
export function BrandMark({ name, size = 'md' }: { name: string; size?: 'sm' | 'md' }) {
  const box = size === 'sm' ? 'size-8 rounded-lg text-sm' : 'size-9 rounded-[0.7rem] text-base'
  return (
    <span
      aria-hidden
      className={`grid shrink-0 place-items-center bg-band font-heading font-extrabold text-band-accent ${box}`}
    >
      {name.slice(0, 1)}
    </span>
  )
}

export type Tone = 'neutral' | 'attention' | 'info' | 'success' | 'danger' | 'brand'

const TONES: Record<Tone, string> = {
  neutral: 'bg-surface-subtle text-primary ring-border',
  attention: 'bg-attention-subtle text-attention ring-attention/40',
  info: 'bg-info-subtle text-info ring-info/40',
  success: 'bg-success-subtle text-success ring-success/40',
  danger: 'bg-danger-subtle text-danger ring-danger/40',
  brand: 'bg-fact text-on-fact ring-transparent',
}

/** Same shape as the app's StatusBadge: a pill with an icon, the word carrying the meaning. */
export function Badge({
  tone,
  icon,
  children,
  size = 'md',
  className = '',
}: {
  tone: Tone
  icon?: ReactNode
  children: ReactNode
  size?: 'sm' | 'md'
  className?: string
}) {
  const sizing = size === 'sm' ? 'gap-1 px-2 py-px text-xs leading-5' : 'gap-1.5 px-2.5 py-0.5 text-[0.8125rem] leading-6'
  return (
    <span className={`inline-flex shrink-0 items-center rounded-full font-medium ring-1 ring-inset ${sizing} ${TONES[tone]} ${className}`}>
      {icon}
      {children}
    </span>
  )
}

/** Marks an illustration as an example, as the redesign specification requires. */
export function ExampleLabel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-0.5 text-xs font-medium text-secondary ${className}`}
    >
      <span aria-hidden className="size-1.5 rounded-full bg-control" />
      {children}
    </span>
  )
}

export function Eyebrow({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <p className={`type-eyebrow text-action ${className}`}>{children}</p>
}

export function SectionHeader({
  eyebrow,
  title,
  body,
  center = false,
  className = '',
}: {
  eyebrow: string
  title: string
  body?: string
  center?: boolean
  className?: string
}) {
  return (
    <header className={`reveal max-w-[44rem] ${center ? 'mx-auto text-center' : ''} ${className}`}>
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="type-title mt-3">{title}</h2>
      {body && <p className={`mt-5 text-lg leading-relaxed text-secondary ${center ? 'mx-auto' : ''} max-w-[38rem]`}>{body}</p>}
    </header>
  )
}

// Button looks shared with the app's Button: 44 px minimum, control radius, semibold primary.
export const buttonBase =
  'inline-flex min-h-11 items-center justify-center gap-2 rounded-control px-4 py-2 text-[0.9375rem] font-semibold transition-colors duration-150 [&>svg]:shrink-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-60'
export const buttonPrimary = `${buttonBase} bg-action text-on-action hover:bg-action-hover`
export const buttonSecondary = `${buttonBase} border border-border bg-surface text-primary hover:bg-surface-subtle`
export const buttonLarge = 'min-h-13 px-6 text-base'

/** Adds `is-visible` to every `.reveal` element below `root` as it scrolls into view, once. */
export function useReveal(deps: unknown[] = []) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const root = ref.current
    if (!root) return
    const items = Array.from(root.querySelectorAll<HTMLElement>('.reveal:not(.is-visible)'))
    if (!('IntersectionObserver' in window)) {
      items.forEach((el) => el.classList.add('is-visible'))
      return
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible')
            observer.unobserve(entry.target)
          }
        }
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.08 },
    )
    items.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return ref
}
