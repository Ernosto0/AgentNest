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
  (`docs/product/mvp-scope.md`), so the page does not promise them; the FAQ answers honestly if asked.
  Re-check the copy, including the pilot price
  wording in the FAQ, against the product before publishing.
- **Product name** is a single constant in `src/brand.ts` (the final name is still open, OQ-10).
- **Waitlist**: the form posts to the AgentNest backend, `POST /api/v1/waitlist`. Set
  `VITE_WAITLIST_ENDPOINT` at build time to that full URL (for example
  `https://<api-host>/api/v1/waitlist`; locally `http://localhost:8000/api/v1/waitlist`). The body is
  JSON `{ email, business_name, category, instagram_handle, city, locale }`; only `email` is
  required, and the form asks for an email address (not a phone number). The backend stores one
  row per email, answers `202` for a new and a repeated email alike, rate-limits per client, and
  emails `OPERATOR_ALERT_EMAIL` about each new entry (`uv run python -m app.cli waitlist-list`
  prints them all, `waitlist-delete --email ...` removes one on request).
  Without the variable the form runs in preview mode and tells the visitor that nothing was sent.
  The API must allow this site's origin: set `LANDING_ORIGINS` on the **API** service to the
  landing origin (for example `https://landing.example`), see `.env.example`. Only the waitlist
  route answers cross-origin requests. `VITE_WAITLIST_WHATSAPP` (digits or an `https://` link)
  shows a "message us on WhatsApp" fallback under the form for visitors who prefer a phone number;
  unset, it is hidden.
- **Fonts** are the app's self-hosted WOFF2 files (`src/assets/fonts/`, notices in `public/fonts/`),
  so visitors' browsers make no request to a font CDN.
- **Theme**: `public/theme.js` applies the saved choice before first paint; light is the default, whatever the OS
  preference. Language and theme choices are remembered in `localStorage`.
- Every screen, chat and summary on the page is an illustration with example data and is labelled
  as an example. The interactive parts (approve, verify, scenario tabs, commands) only change local
  state; nothing is sent anywhere.

## Deploying (Railway)

The page ships as its own container: `Dockerfile` builds the static site and serves it with Caddy
(`Caddyfile`: strict CSP, long-lived caching for hashed assets, `/healthz`). It listens on `$PORT`.

1. In the Railway project, add a service from the GitHub repo (branch `main`) and set its
   **Root Directory** to `/landing`. Railway then reads `landing/railway.json` (Dockerfile build,
   `/healthz` health check, rebuilds only when `landing/**` changes).
2. Variables: `VITE_WAITLIST_ENDPOINT` (build-time; without it the form sends nothing) and optionally
   `VITE_WAITLIST_WHATSAPP` (build-time), and `LANDING_CONNECT_SRC` (runtime) set to the API's
   origin (e.g. `https://api.example`) so the CSP allows the POST. On the API service set
   `LANDING_ORIGINS` to this site's origin and `OPERATOR_ALERT_EMAIL`, `SMTP_URL`, `MAIL_FROM`
   so the operator is emailed.
3. Under **Settings → Networking**, generate a domain or attach your own.

Local check: `docker build -t agentnest-landing . && docker run -e PORT=8080 -p 8080:8080 agentnest-landing`.
