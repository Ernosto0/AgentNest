import type { Lang } from './copy'

export type WaitlistEntry = {
  email: string
  business: string
  category: string
  instagram: string
  city: string
  lang: Lang
}

// 'preview' means no endpoint is configured and nothing left the browser.
// The form must say so instead of showing a success message.
export type SubmitResult = 'sent' | 'preview'

const endpoint = import.meta.env.VITE_WAITLIST_ENDPOINT?.trim()
const whatsappRaw = import.meta.env.VITE_WAITLIST_WHATSAPP?.trim()

// Same shape the backend accepts (POST /api/v1/waitlist); the server validates again.
const EMAIL = /^[^@\s]{1,64}@[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}$/

export function isValidEmail(value: string): boolean {
  const email = value.trim()
  return email.length <= 254 && !email.includes('..') && EMAIL.test(email)
}

export function getWhatsAppContactUrl(text: string): string | undefined {
  if (!whatsappRaw) return undefined
  if (whatsappRaw.startsWith('http://') || whatsappRaw.startsWith('https://')) {
    return whatsappRaw
  }
  const digits = whatsappRaw.replace(/\D/g, '')
  if (!digits) return undefined
  return `https://wa.me/${digits}?text=${encodeURIComponent(text)}`
}

export async function submitWaitlist(entry: WaitlistEntry): Promise<SubmitResult> {
  if (!endpoint) return 'preview'
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({
      email: entry.email,
      business_name: entry.business,
      category: entry.category,
      instagram_handle: entry.instagram,
      city: entry.city,
      locale: entry.lang,
    }),
  })
  if (!response.ok) throw new Error(`Waitlist endpoint answered ${response.status}`)
  return 'sent'
}
