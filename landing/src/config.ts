// Build-time settings that are decided at deploy time, not in the copy.
// Every value is optional; an empty one hides the part of the page that needs it.

const read = (value: string | undefined): string => (value ?? '').trim()

/**
 * The package price, shown verbatim in the package section (for example "1.490 ₺ / ay + KDV").
 * Pricing is not settled yet, so it is empty by default and the page renders no price at all.
 * Set `VITE_PACKAGE_PRICE` at build time once the price is decided.
 */
export const PACKAGE_PRICE = read(import.meta.env.VITE_PACKAGE_PRICE)

/**
 * The origin of the web app (for example https://app.example.com), without a trailing slash.
 * The legal pages live in the app (/privacy, /terms, /data-deletion), not on this static site,
 * so the links to them are drawn only when this is set. Unset: the documents are named, not linked.
 */
export const APP_URL = read(import.meta.env.VITE_APP_URL).replace(/\/+$/, '')

/** An absolute link into the app, or null when the app origin is unknown or not https. */
export function appLink(path: string): string | null {
  if (!/^https:\/\//i.test(APP_URL)) return null
  return `${APP_URL}${path}`
}
