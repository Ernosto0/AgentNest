import { Brand } from './BrandIdentity'
import type { ChatMessage, Copy } from './copy'
import { PhoneFrame } from './PhoneFrame'
import { ImageIcon, SendIcon } from './ui'

type Command = Copy['owner']['commands'][number]

// The owner's side: a chat with the assistant's bot, drawn in the product's own palette rather than
// any messenger's. A static illustration, labelled as an example; the buttons are not live.
export function OwnerChat({ t, selected }: { t: Copy['owner']; selected: Command | null }) {
  const messages: ChatMessage[] = selected
    ? [
        ...t.chat,
        { from: 'owner', text: selected.ask, time: '09:15' },
        { from: 'assistant', text: selected.answer, time: '09:15', actions: selected.action ? [selected.action] : undefined },
      ]
    : t.chat

  return (
    <PhoneFrame label={t.example} clock="09:15">
      <div className="flex h-[36rem] flex-col">
        <div className="flex items-center gap-3 border-b border-border px-4 py-2.5">
          <Brand variant="monogram" size="sm" />
          <div className="flex min-w-0 flex-col leading-tight">
            <span className="truncate text-sm font-semibold">{t.bot}</span>
            <span className="text-xs text-secondary">{t.botSub}</span>
          </div>
        </div>

        <div className="dot-field relative flex min-h-0 flex-1 flex-col justify-end overflow-hidden bg-canvas px-3 pb-2">
          <span className="mx-auto mb-2 rounded-full bg-surface px-2.5 py-0.5 text-[0.6875rem] text-secondary shadow-sm">{t.today}</span>
          <ol aria-live="polite" className="flex flex-col gap-1.5">
            {messages.map((message, i) => (
              <Message key={`${i}-${message.text}`} message={message} fresh={Boolean(selected) && i >= t.chat.length} />
            ))}
          </ol>
        </div>

        <div aria-hidden className="flex items-center gap-2 border-t border-border bg-surface px-3 py-2.5">
          <ImageIcon className="text-lg text-control" />
          <span className="flex h-9 flex-1 items-center rounded-full bg-surface-subtle px-3.5 text-sm text-secondary">
            {t.placeholder}
          </span>
          <span className="grid size-9 place-items-center rounded-full bg-action text-on-action">
            <SendIcon />
          </span>
        </div>
      </div>
    </PhoneFrame>
  )
}

function Message({ message, fresh }: { message: ChatMessage; fresh: boolean }) {
  const own = message.from === 'owner'
  return (
    <li className={`flex flex-col gap-1 ${own ? 'items-end self-end' : 'items-start self-start'} max-w-[86%] ${fresh ? 'pop-in' : ''}`}>
      <div
        className={`rounded-2xl px-3 py-2 text-[0.875rem] leading-snug ${
          own ? 'rounded-br-md bg-fact text-on-fact' : 'rounded-bl-md border border-border bg-surface text-primary'
        } ${message.attachment ? 'w-[12rem]' : ''}`}
      >
        {message.attachment && <Story {...message.attachment} />}
        <p>
          {message.text}
          <span className="ml-2 inline-block translate-y-0.5 text-[0.625rem] opacity-60 tabular-nums">{message.time}</span>
        </p>
      </div>
      {message.actions && (
        <div className="grid w-full min-w-[13rem] grid-flow-col gap-1">
          {message.actions.map((action) => (
            <span
              key={action}
              className="rounded-lg bg-band/90 px-3 py-1.5 text-center text-[0.8125rem] font-semibold text-band-text"
            >
              {action}
            </span>
          ))}
        </div>
      )}
    </li>
  )
}

// The photo the owner sends: a story graphic like one made in a phone design app.
function Story({ kicker, title, note }: { kicker: string; title: string; note: string }) {
  return (
    <div className="relative mb-1.5 flex h-28 flex-col justify-end overflow-hidden rounded-xl bg-[#e9dfcf] p-3 font-heading text-[#2a2118]">
      <span aria-hidden className="absolute -top-10 -right-8 size-24 rounded-full bg-[#253b31]" />
      <span aria-hidden className="absolute top-3 -left-5 size-12 rounded-full border-[5px] border-[#2a2118]/15" />
      <span className="relative text-[0.625rem] font-bold tracking-[0.14em] uppercase">{kicker}</span>
      <span className="relative mt-0.5 text-lg leading-[1.05] font-extrabold tracking-[-0.02em]">{title}</span>
      <span className="relative mt-1.5 self-start rounded-full bg-[#2a2118] px-2.5 py-0.5 text-xs font-bold text-[#e9dfcf]">{note}</span>
    </div>
  )
}
