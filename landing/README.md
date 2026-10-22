# Landing page

The public pilot-waitlist page. It is a separate static site and shares no code with `frontend/`.
React + TypeScript + Vite + Tailwind, Turkish and English.

```
npm install
npm run dev        # http://localhost:5174
npm run build      # static files in dist/, deployable to any static host
npm run typecheck
```

- **Copy** for both languages lives in `src/copy.ts`.
- **Product name** is a single constant in `src/brand.ts` (the final name is still open, OQ-10).
- **Waitlist**: set `VITE_WAITLIST_ENDPOINT` at build time to a URL that accepts a JSON `POST` of
  `{ business, instagram, contact, city, lang }`. Without it, the form runs in preview mode and
  tells the visitor that nothing was sent.
- **Fonts** are self-hosted from npm (`@fontsource/*`), so visitors' browsers make no request to Google.
- The phone screen and the daily summary are illustrations and are labelled as examples.
- The copy describes the finished product (WhatsApp control, self-service setup and so on). Check it against
  what is actually built before publishing the page.
