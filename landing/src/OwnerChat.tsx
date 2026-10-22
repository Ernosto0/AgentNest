import type { CSSProperties, ReactNode } from 'react'
import { PRODUCT_NAME } from './brand'
import type { ChatMessage, Copy } from './copy'

type Props = { t: Copy['whatsapp'] }

// The owner's side: the assistant's chat as it looks in WhatsApp, in WhatsApp's light or dark theme.
// A static illustration, labelled as an example.
export function OwnerChat({ t }: Props) {
  return (
    <figure className="w-full max-w-[23rem] justify-self-center">
      <figcaption className="mb-3 flex items-center gap-2 font-mono text-xs text-muted">
        <span aria-hidden className="size-1.5 rounded-full bg-kase" />
        {t.example}
      </figcaption>

      <div className="rounded-[2.9rem] bg-[#0c0c0f] p-[0.55rem] shadow-[0_1px_0_1px_rgb(255_255_255/0.06)_inset,0_24px_60px_-28px_rgb(0_0_0/0.45)]">
        <div className="flex flex-col overflow-hidden rounded-[2.4rem] bg-wa-wall font-system text-wa-text">
          <StatusBar clock={t.clock} />
          <Header online={t.online} />

          <div className="relative flex flex-col gap-1 px-3 pt-3 pb-2">
            <span aria-hidden className="absolute inset-0 bg-wa-doodle" style={doodle} />
            <span className="relative mb-1.5 self-center rounded-lg bg-wa-in px-2.5 py-1 text-[0.6875rem] text-wa-meta uppercase shadow-sm">
              {t.today}
            </span>
            <ol className="relative flex flex-col gap-1">
              {t.chat.map((message, i) => (
                <Message key={i} message={message} groupStart={i === 0 || t.chat[i - 1].from !== message.from} />
              ))}
            </ol>
          </div>

          <InputBar placeholder={t.placeholder} />
        </div>
      </div>
    </figure>
  )
}

function StatusBar({ clock }: { clock: string }) {
  return (
    <div className="flex items-center justify-between bg-wa-header px-7 pt-3 pb-1 text-[0.8125rem] font-semibold">
      <span className="tabular-nums">{clock}</span>
      <span aria-hidden className="flex items-center gap-1.5">
        <Icon size={15} path="M2 20h2v-4H2zM7 20h2v-8H7zM12 20h2V8h-2zM17 20h2V4h-2z" filled />
        <Icon size={15} path="M12 18.5a1.5 1.5 0 1 0 0 .01M8.5 15a5 5 0 0 1 7 0M5.5 12a9 9 0 0 1 13 0M2.5 9a13 13 0 0 1 19 0" />
        <span className="flex h-[11px] w-[22px] items-center rounded-[3px] border border-current p-[1.5px] opacity-90">
          <span className="h-full w-3/4 rounded-[1px] bg-current" />
        </span>
      </span>
    </div>
  )
}

function Header({ online }: { online: string }) {
  return (
    <div className="flex items-center gap-2 bg-wa-header px-2 pt-1 pb-2.5">
      <Icon size={24} path="M15 5l-7 7 7 7" />
      <span aria-hidden className="grid size-9 shrink-0 place-items-center rounded-full bg-kase font-display text-sm font-extrabold text-on-kase">
        {PRODUCT_NAME.slice(0, 1)}
      </span>
      <div className="flex min-w-0 flex-1 flex-col leading-tight">
        <span className="flex items-center gap-1 text-[0.9375rem] font-semibold">
          <span className="truncate">{PRODUCT_NAME}</span>
          <Verified />
        </span>
        <span className="text-xs text-wa-meta">{online}</span>
      </div>
      <span aria-hidden className="flex items-center gap-4 pr-2">
        <Icon size={21} path="M3 7.5A1.5 1.5 0 0 1 4.5 6h9A1.5 1.5 0 0 1 15 7.5v9a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 3 16.5zM15 10.5l5-3v9l-5-3" />
        <Icon size={19} path="M5 4h3.5l1.5 4-2 1.5a11 11 0 0 0 6.5 6.5L16 14l4 1.5V19a1 1 0 0 1-1 1A16 16 0 0 1 4 5a1 1 0 0 1 1-1z" />
      </span>
    </div>
  )
}

function Message({ message, groupStart }: { message: ChatMessage; groupStart: boolean }) {
  const own = message.from === 'owner'
  const bubbleColor = own ? 'bg-wa-out' : 'bg-wa-in'
  const tailColor = own ? 'text-wa-out' : 'text-wa-in'

  return (
    <li
      className={`flex flex-col gap-[3px] ${message.attachment ? 'w-[14rem]' : 'max-w-[84%]'} ${own ? 'self-end' : 'self-start'} ${
        groupStart ? 'mt-1.5' : ''
      }`}
    >
      <div
        className={`relative rounded-lg px-[0.4375rem] pt-[0.3125rem] pb-[0.375rem] text-[0.875rem] leading-[1.3] shadow-[0_1px_0.5px_rgb(11_20_26/0.13)] ${bubbleColor} ${
          groupStart ? (own ? 'rounded-tr-none' : 'rounded-tl-none') : ''
        }`}
      >
        {groupStart && (
          <svg
            aria-hidden
            viewBox="0 0 8 13"
            className={`absolute top-0 h-[13px] w-2 ${tailColor} ${own ? '-right-2' : '-left-2'}`}
          >
            <path
              fill="currentColor"
              d={own ? 'M5.188 1H0v11.193l6.467-8.625C7.526 2.156 6.958 1 5.188 1z' : 'M1.533 3.568 8 12.193V1H2.812C1.042 1 .474 2.156 1.533 3.568z'}
              transform="translate(0 -1)"
            />
          </svg>
        )}

        {message.quote && (
          <div className="mb-1 rounded-md border-l-4 border-[#06cf9c] bg-wa-quote px-2 py-1">
            <p className="text-[0.75rem] font-semibold text-[#06cf9c]">{PRODUCT_NAME}</p>
            <p className="line-clamp-2 text-[0.8125rem] text-wa-meta">{message.quote}</p>
          </div>
        )}
        {message.attachment && <Story {...message.attachment} />}

        <p className="relative px-0.5">
          {message.text}
          <span aria-hidden className={`inline-block ${own ? 'w-[4.1rem]' : 'w-[2.6rem]'}`} />
          <span className="absolute right-0 -bottom-[0.1875rem] flex items-center gap-[3px] text-[0.6875rem] text-wa-meta tabular-nums">
            {message.time}
            {own && <Ticks />}
          </span>
        </p>
      </div>

      {message.actions?.map((action) => (
        <span
          key={action}
          className={`flex items-center justify-center gap-1.5 rounded-lg py-2 text-[0.875rem] font-medium text-wa-link shadow-[0_1px_0.5px_rgb(11_20_26/0.13)] ${bubbleColor}`}
        >
          <Icon size={15} path="M10 8V4l-7 7 7 7v-4.1c5 0 8.5 1.6 11 5.1-1-5-4-10-11-11z" filled />
          {action}
        </span>
      ))}
    </li>
  )
}

// The photo the owner sends: a story graphic like one made in a phone design app.
function Story({ kicker, title, note }: { kicker: string; title: string; note: string }) {
  return (
    <div className="relative mb-1 flex aspect-[3/4] flex-col justify-end overflow-hidden rounded-md bg-[#d7dccd] p-3 font-display text-[#1f2a22]">
      <span aria-hidden className="absolute -top-8 -right-10 size-36 rounded-full bg-[#3a3fb0]/85" />
      <span aria-hidden className="absolute top-16 -left-6 size-14 rounded-full border-[6px] border-[#1f2a22]/15" />
      <span className="relative text-[0.625rem] font-bold tracking-[0.14em] uppercase">{kicker}</span>
      <span className="relative mt-1 text-[1.375rem] leading-[1.05] font-extrabold tracking-[-0.02em]">{title}</span>
      <span className="relative mt-1.5 self-start rounded-full bg-[#1f2a22] px-2.5 py-0.5 text-xs font-bold text-[#d7dccd]">
        {note}
      </span>
    </div>
  )
}

function InputBar({ placeholder }: { placeholder: string }) {
  return (
    <div aria-hidden className="relative flex items-center gap-1.5 px-2 pt-1 pb-4">
      <span className="flex h-10 flex-1 items-center gap-2.5 rounded-full bg-wa-in px-3 text-wa-meta shadow-[0_1px_0.5px_rgb(11_20_26/0.13)]">
        <Icon size={20} path="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8.5 14a4.5 4.5 0 0 0 7 0M9 9.5h.01M15 9.5h.01" />
        <span className="flex-1 text-[0.9375rem]">{placeholder}</span>
        <Icon size={19} path="M15.5 7.5l-6.4 6.4a1.6 1.6 0 0 0 2.3 2.3l6.7-6.8a3.2 3.2 0 0 0-4.5-4.5l-6.9 6.9a4.8 4.8 0 0 0 6.8 6.8l5-5" />
        <Icon size={20} path="M4 8.5A1.5 1.5 0 0 1 5.5 7h2l1.5-2h6l1.5 2h2A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5zM12 16a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" />
      </span>
      <span className="grid size-10 place-items-center rounded-full bg-wa-green text-white">
        <Icon size={20} path="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM6 11a6 6 0 0 0 12 0M12 17v3" />
      </span>
    </div>
  )
}

function Ticks() {
  return (
    <svg aria-hidden viewBox="0 0 18 11" className="h-[11px] w-[16px] text-wa-tick">
      <path d="M1 5.8l2.9 2.9L10.6 1.6M6.6 8.4l.6.6 7.2-7.4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function Verified() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className="size-4 shrink-0 text-wa-green">
      <path
        fill="currentColor"
        d="M12 1.5l2.6 1.9 3.2-.2.9 3.1 2.6 1.9-1 3 1 3-2.6 1.9-.9 3.1-3.2-.2L12 22.5l-2.6-1.9-3.2.2-.9-3.1-2.6-1.9 1-3-1-3 2.6-1.9.9-3.1 3.2.2z"
      />
      <path d="M8 12.2l2.7 2.6L16.2 9.3" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function Icon({ path, size, filled = false }: { path: string; size: number; filled?: boolean }): ReactNode {
  return (
    <svg aria-hidden viewBox="0 0 24 24" width={size} height={size} className="shrink-0">
      <path
        d={path}
        fill={filled ? 'currentColor' : 'none'}
        stroke={filled ? 'none' : 'currentColor'}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

// WhatsApp's wallpaper is a faint doodle pattern; this tile is drawn here and tinted by --wa-doodle.
const tile = `<svg xmlns='http://www.w3.org/2000/svg' width='150' height='150' fill='none' stroke='black' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'>
<circle cx='22' cy='22' r='8'/>
<path d='M68 12l3 6.2 6.8 1-4.9 4.7 1.2 6.7L68 27.4l-6.1 3.2 1.2-6.7-4.9-4.7 6.8-1z'/>
<path d='M118 20c-3.2-4.4-10-2.2-10 3 0 5.6 10 11 10 11s10-5.4 10-11c0-5.2-6.8-7.4-10-3z'/>
<path d='M14 72h18v10a9 9 0 0 1-18 0zM32 74h3a3.5 3.5 0 0 1 0 7h-3'/>
<path d='M72 84V66l14-3.5v17M72 84a4 4 0 1 1-4-4h4M86 79.5a4 4 0 1 1-4-4h4'/>
<path d='M112 70h18M121 61v18'/>
<rect x='12' y='112' width='22' height='16' rx='3'/><circle cx='23' cy='120' r='4.5'/>
<path d='M60 130c4-11 16-11 20 0'/>
<path d='M110 112l10 17 10-17z'/>
</svg>`

const doodle: CSSProperties = {
  maskImage: `url("data:image/svg+xml,${encodeURIComponent(tile)}")`,
  WebkitMaskImage: `url("data:image/svg+xml,${encodeURIComponent(tile)}")`,
  maskSize: '150px',
  WebkitMaskSize: '150px',
}
