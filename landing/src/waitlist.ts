import type { Lang } from './copy'

export type WaitlistEntry = {
  business: string
  instagram: string
  contact: string
  city: string
  lang: Lang
}

// 'preview' means no endpoint is configured and nothing left the browser.
// The form must say so instead of showing a success message.
export type SubmitResult = 'sent' | 'preview'

const endpoint = import.meta.env.VITE_WAITLIST_ENDPOINT?.trim()

export async function submitWaitlist(entry: WaitlistEntry): Promise<SubmitResult> {
  if (!endpoint) return 'preview'
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(entry),
  })
  if (!response.ok) throw new Error(`Waitlist endpoint answered ${response.status}`)
  return 'sent'
}
