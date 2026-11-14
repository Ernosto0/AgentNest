# Landing page

The public pilot-waitlist page. It is a separate static site and shares no code with `frontend/`.
React + TypeScript + Vite + Tailwind, Turkish and English, light and dark.

```
npm install
npm run dev        # http://localhost:5174
npm run build      # static files in dist/, deployable to any static host
npm run typecheck
```

- **Look**: the light colour tokens, fonts (Manrope headings, Inter text), radii, buttons and status
  pills are the app's own (`frontend/src/index.css`, `StatusBadge`, `Button`), so the page and the
  product read as one thing. The page adds larger display type, a dark theme and the dark-green brand
  band. Tokens live in `src/index.css`; shared pieces (icons, badges, buttons) in `src/ui.tsx`.
- **Copy** for both languages lives in `src/copy.ts`. It describes what is built: the web app and the
  Telegram owner channel (Phase 9). WhatsApp owner control and comment replies are deferred
  (`docs/product/mvp-scope.md`) and the page says so. Re-check the copy, including the pilot price
  wording in the FAQ, against the product before publishing.
- **Product name** is a single constant in `src/brand.ts` (the final name is still open, OQ-10).
- **Waitlist**: set `VITE_WAITLIST_ENDPOINT` at build time to a URL that accepts a JSON `POST` of
  `{ business, category, instagram, contact, city, lang }`. Without it, the form runs in preview mode
  and tells the visitor that nothing was sent. `VITE_WAITLIST_WHATSAPP` (digits or an `https://` link)
  shows a "message us on WhatsApp" fallback under the form; unset, it is hidden.
- **Fonts** are the app's self-hosted WOFF2 files (`src/assets/fonts/`, notices in `public/fonts/`),
  so visitors' browsers make no request to a font CDN.
- **Theme**: an inline script in `index.html` applies the saved choice, or the OS preference, before
  first paint. Language and theme choices are remembered in `localStorage`.
- Every screen, chat and summary on the page is an illustration with example data and is labelled
  as an example. The interactive parts (approve, verify, scenario tabs, commands) only change local
  state; nothing is sent anywhere.

## Deploying (Railway)

The page ships as its own container: `Dockerfile` builds the static site and serves it with Caddy
(`Caddyfile`: strict CSP, long-lived caching for hashed assets, `/healthz`). It listens on `$PORT`.

1. In the Railway project, add a service from the GitHub repo (branch `main`) and set its
   **Root Directory** to `/landing`. Railway then reads `landing/railway.json` (Dockerfile build,
   `/healthz` health check, rebuilds only when `landing/**` changes).
2. Optional variables: `VITE_WAITLIST_ENDPOINT` and `VITE_WAITLIST_WHATSAPP` (build-time), and
   `LANDING_CONNECT_SRC` (runtime) set to the endpoint's origin so the CSP allows the POST.
3. Under **Settings → Networking**, generate a domain or attach your own.

Local check: `docker build -t agentnest-landing . && docker run -e PORT=8080 -p 8080:8080 agentnest-landing`.
