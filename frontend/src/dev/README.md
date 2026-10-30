# Local design reference

Run `npm.cmd run dev -- --host 127.0.0.1 --port 5186 --strictPort`, then open
`http://127.0.0.1:5186/?ui-reference=1&lang=tr` (or `lang=en`). The view has no API,
workspace, account, mutation or public product route. `main.tsx` guards its dynamic
import with `import.meta.env.DEV`; production builds discard it. It contains only
fictional type, color and focus specimens. Session 03 can extend this same view
with actual shared interactive controls. Keep fixture labels distinct from product
catalogs; both TR and EN specimens are supplied.

Use semantic utilities from `index.css` when migrating components:

| Purpose | Utilities |
|---|---|
| Working surfaces | `bg-canvas`, `bg-surface`, `bg-surface-subtle`, `bg-assistant` |
| Text | `text-primary`, `text-secondary`, `text-on-action` |
| Navigation | `bg-navigation`, `text-navigation-text`, `bg-navigation-selected`, `text-navigation-selected-text` |
| Actions and focus | `bg-action`, `hover:bg-action-hover`, `border-control`, `outline-focus`, `outline-focus-inverse` |
| State pairs | `text-success` + `bg-success-subtle`; equivalent `attention`, `danger`, `info`, `simulation` pairs |
| Type | `type-page`, `type-section`, `type-metric`, `text-body`, `text-form`, `text-metadata`, `font-heading` |
| Geometry | `rounded-control`, `rounded-panel`, `rounded-dialog`, `shadow-float`; Tailwind's 4px spacing scale |

`border-border` is a quiet panel divider; use `border-control` when a boundary is
needed to identify a control. Use the inverse focus token only against the dark
navigation surface. A state always needs a readable label and, when useful, an
icon; color alone never establishes an outcome. The existing canonical status
mapper remains authoritative.

CSS variables `--an-space-1/2/3/4/5/6/8/10/12` expose 4/8/12/16/20/24/32/40/48px
spacing for nonutility consumers. `--an-duration-fast/normal/slow` expose
120/160/200ms and reduce to 0.01ms under reduced motion. Form text stays 16px on
phones. The app has one light canvas and dark navigation; these tokens do not add
an app dark mode. Existing feature utility colors remain until their assigned
migration sessions.

Asset verification: run `npm.cmd run build`, keep a production preview on5185 and
this dev server on5186, then run `node scripts/ui-assets.mjs` from `frontend/`.
That script blocks all external requests, mocks only anonymous auth/meta GETs,
checks deployed OFL notices and binary hashes, confirms real Turkish glyphs use
downloaded fonts via Chromium's font inspection, measures CLS and computed contrast,
checks keyboard focus/reduced motion, and writes evidence into the session02
directory. The production login also receives `?ui-reference=1` to prove the dev
view cannot be activated in a production build. It never runs E2E global setup.

Font provenance, hashes and licenses ship from `public/fonts/`; actual WOFF2
assets live in `src/assets/fonts/` and receive content-hashed Vite names. The
Docker frontend builder copies `public/` so distribution includes those notices.
