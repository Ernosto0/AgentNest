/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Where waitlist signups are POSTed as JSON. Unset: the form runs in preview mode.
  readonly VITE_WAITLIST_ENDPOINT?: string
  // A phone number (digits) or a full https:// link for the "message us on WhatsApp" fallback. Unset: hidden.
  readonly VITE_WAITLIST_WHATSAPP?: string
  // The package price, shown verbatim in the package section. Unset or empty: no price is shown.
  readonly VITE_PACKAGE_PRICE?: string
  // The web app's https origin; the package section links its legal pages (/privacy, /terms,
  // /data-deletion) there. Unset: the documents are named but not linked.
  readonly VITE_APP_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
