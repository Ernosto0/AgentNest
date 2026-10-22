/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Where waitlist signups are POSTed as JSON. Unset: the form runs in preview mode.
  readonly VITE_WAITLIST_ENDPOINT?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
