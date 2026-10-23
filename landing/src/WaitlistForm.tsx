import { useState, type FormEvent } from 'react'
import type { Copy, Lang } from './copy'
import { getWhatsAppContactUrl, submitWaitlist, type SubmitResult } from './waitlist'

type Props = { t: Copy['form']; pilot: Copy['pilot']; lang: Lang }

type Field = 'business' | 'instagram' | 'contact' | 'city'
type Values = Record<Field, string>
type Status = { kind: 'idle' } | { kind: 'sending' } | { kind: 'done'; result: SubmitResult } | { kind: 'failed' }

const empty: Values = { business: '', instagram: '', contact: '', city: '' }

export function WaitlistForm({ t, pilot, lang }: Props) {
  const [categoryIdx, setCategoryIdx] = useState<number>(0)
  const [values, setValues] = useState<Values>(empty)
  const [consent, setConsent] = useState(false)
  const [errors, setErrors] = useState<Partial<Record<Field | 'consent', string>>>({})
  const [status, setStatus] = useState<Status>({ kind: 'idle' })

  const selectedCategory = t.categories[categoryIdx] ?? t.categories[0] ?? ''
  const whatsappUrl = getWhatsAppContactUrl(pilot.whatsappPrefill)

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
        category: selectedCategory,
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
    <form
      noValidate
      onSubmit={onSubmit}
      className="flex flex-col gap-6 rounded-2xl border border-rule bg-surface/60 p-6 font-display shadow-sm md:p-8"
    >
      <div className="flex items-center justify-between gap-2 border-b border-rule pb-4">
        <span className="flex items-center gap-2 font-mono text-xs font-medium tracking-wide text-kase uppercase">
          <span aria-hidden className="size-2 rounded-full bg-kase" />
          {t.dossierHeader}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-bold">{t.categoryLabel}</span>
        <div role="group" aria-label={t.categoryLabel} className="flex flex-wrap gap-2">
          {t.categories.map((cat, idx) => (
            <button
              key={cat}
              type="button"
              aria-pressed={categoryIdx === idx}
              onClick={() => setCategoryIdx(idx)}
              className="rounded-full border border-rule bg-paper px-3.5 py-1.5 font-mono text-xs text-muted transition-colors hover:border-ink hover:text-ink aria-pressed:border-kase aria-pressed:bg-kase-soft aria-pressed:font-medium aria-pressed:text-kase"
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

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
            className="rounded-lg border border-rule bg-paper px-3.5 py-2.5 text-base placeholder:text-muted/70 focus:border-kase focus:outline-none aria-invalid:border-kase"
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

      <div className="border-t border-rule pt-5 font-serif">
        <p className="font-mono text-xs tracking-wide text-muted uppercase">{pilot.nextStepsTitle}</p>
        <ol className="mt-3 flex flex-col gap-2 text-sm leading-relaxed text-muted">
          {pilot.nextSteps.map((step, i) => (
            <li key={step} className="flex gap-2.5">
              <span className="font-mono text-xs text-kase">{i + 1}.</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>

        {whatsappUrl && (
          <a
            href={whatsappUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-4 inline-block font-mono text-xs text-kase underline underline-offset-4 hover:text-ink"
          >
            {pilot.whatsappDirectLabel}
          </a>
        )}
      </div>
    </form>
  )
}
