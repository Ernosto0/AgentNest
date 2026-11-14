/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Where waitlist signups are POSTed as JSON. Unset: the form runs in preview mode.
  readonly VITE_WAITLIST_ENDPOINT?: string
  // A phone number (digits) or a full https:// link for the "message us on WhatsApp" fallback. Unset: hidden.
  readonly VITE_WAITLIST_WHATSAPP?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
