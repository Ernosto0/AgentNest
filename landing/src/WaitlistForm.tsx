import { useState, type FormEvent } from 'react'
import type { Copy, Lang } from './copy'
import { submitWaitlist, type SubmitResult } from './waitlist'

type Props = { t: Copy['form']; lang: Lang }

type Field = 'business' | 'instagram' | 'contact' | 'city'
type Values = Record<Field, string>
type Status = { kind: 'idle' } | { kind: 'sending' } | { kind: 'done'; result: SubmitResult } | { kind: 'failed' }

const empty: Values = { business: '', instagram: '', contact: '', city: '' }

export function WaitlistForm({ t, lang }: Props) {
  const [values, setValues] = useState<Values>(empty)
  const [consent, setConsent] = useState(false)
  const [errors, setErrors] = useState<Partial<Record<Field | 'consent', string>>>({})
  const [status, setStatus] = useState<Status>({ kind: 'idle' })

  const fields: { id: Field; label: string; hint?: string; autoComplete: string; inputMode?: 'email' | 'text' }[] = [
    { id: 'business', label: t.business, autoComplete: 'organization' },
    { id: 'instagram', label: t.instagram, hint: t.instagramHint, autoComplete: 'off' },
    { id: 'contact', label: t.contact, hint: t.contactHint, autoComplete: 'email', inputMode: 'email' },
    { id: 'city', label: t.city, autoComplete: 'address-level2' },
  ]

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const next: typeof errors = {}
    for (const { id } of fields) if (!values[id].trim()) next[id] = t.required
    if (!consent) next.consent = t.consentRequired
    setErrors(next)
    if (Object.keys(next).length > 0) return

    setStatus({ kind: 'sending' })
    try {
      const result = await submitWaitlist({
        business: values.business.trim(),
        instagram: values.instagram.trim().replace(/^@/, ''),
        contact: values.contact.trim(),
        city: values.city.trim(),
        lang,
      })
      setStatus({ kind: 'done', result })
      if (result === 'sent') {
        setValues(empty)
        setConsent(false)
      }
    } catch {
      setStatus({ kind: 'failed' })
    }
  }

  return (
    <form noValidate onSubmit={onSubmit} className="flex flex-col gap-7 font-display">
      {fields.map(({ id, label, hint, autoComplete, inputMode }) => (
        <div key={id} className="flex flex-col gap-1.5">
          <label htmlFor={`wl-${id}`} className="text-sm font-bold">
            {label}
          </label>
          <input
            id={`wl-${id}`}
            name={id}
            type="text"
            autoComplete={autoComplete}
            inputMode={inputMode}
            placeholder={hint}
            value={values[id]}
            aria-invalid={errors[id] ? true : undefined}
            aria-describedby={errors[id] ? `wl-${id}-error` : undefined}
            onChange={(e) => setValues((v) => ({ ...v, [id]: e.target.value }))}
            className="border-b-2 border-rule bg-transparent py-2 text-lg placeholder:text-muted/70 focus:border-kase focus:outline-none aria-invalid:border-kase"
          />
          {errors[id] && (
            <p id={`wl-${id}-error`} className="font-mono text-xs text-kase">
              {errors[id]}
            </p>
          )}
        </div>
      ))}

      <div className="flex flex-col gap-1.5">
        <label htmlFor="wl-consent" className="flex items-start gap-3 font-serif text-[0.9375rem] leading-snug text-muted">
          <input
            id="wl-consent"
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
            aria-invalid={errors.consent ? true : undefined}
            className="mt-1 size-4 shrink-0 accent-kase"
          />
          <span>{t.consent}</span>
        </label>
        {errors.consent && <p className="ml-7 font-mono text-xs text-kase">{errors.consent}</p>}
      </div>

      <div className="flex flex-col gap-4">
        <button
          type="submit"
          disabled={status.kind === 'sending'}
          className="h-13 self-start rounded-md bg-kase px-7 text-base font-bold text-on-kase transition-transform active:scale-[0.98] disabled:opacity-60"
        >
          {status.kind === 'sending' ? t.sending : t.submit}
        </button>
        <p aria-live="polite" className="font-mono text-xs leading-relaxed text-muted empty:hidden">
          {status.kind === 'done' && (status.result === 'sent' ? t.sent : t.preview)}
          {status.kind === 'failed' && t.failed}
        </p>
      </div>
    </form>
  )
}
