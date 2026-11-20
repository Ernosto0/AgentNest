# Pivoris brand identity

The official symbol is the supplied root `logo.svg`. Its path, nine-unit stroke,
round joins and round caps stay unchanged. The component crops and centers the
viewport optically; icon exports translate and scale the entire symbol uniformly.

The lowercase wordmark starts with the bundled **Manrope variable font at 680**.
Its open bowls and restrained geometry complement the existing Manrope headings
and Inter interface. Hand-set letter spacing and circular `i` dots echo the
monogram's rounded terminals. The wordmark ships as SVG outlines, so no additional
font request, fallback lettering or font-loading layout shift is introduced.
Manrope is licensed under SIL OFL 1.1; provenance and license remain in both apps'
`public/fonts/` directories. The customized wordmark is artwork, not a modified
font distribution. Global typography and palette are unchanged.

## Brand component

Import `Brand` from `@/components/Brand` in the dashboard, or `./BrandIdentity` in
the landing page. Both are generated from `scripts/brand/Brand.tsx` and `Brand.css`,
which are the canonical sources. Checked-in local outputs preserve independent
builds and existing Docker build contexts.

```tsx
<Brand />
<Brand variant="wordmark" size="sm" label={productName} />
<Brand variant="monogram" size="lg" tone="dark" />
<Link to={home} aria-label={productName}><Brand /></Link>
```

Variants are `horizontal` (default), `wordmark` and `monogram`. Sizes are `xs`
(20px), `sm` (28px), `md` (36px) and `lg` (40px). All dimensions scale with root
text size. The wordmark is 80% of the selected height; symbol-to-wordmark spacing
is 18%. The landing navigation and public phone header use a 24px compact size
below 360px.

Tone `inherit` (default) follows the surrounding semantic text color and supports
the landing theme toggle. `light` uses forest green `#253b31` on light surfaces;
`dark` uses the supplied cream `#edf5ec` on dark surfaces. Forced-color mode uses
the system text color. Do not stretch either SVG or apply decorative effects.

Supply `label` for a standalone image. Omit it within a link that already has an
accessible name; its artwork stays decorative. Brand labels retain the product's
accessible spelling, **Pivoris**, while the visual lettering stays lowercase.

## Integration and assets

- Landing: desktop and mobile header, footer, mobile call to action, and the
  existing illustrated product/chat headers.
- Dashboard: expanded sidebar with workspace subtitle, collapsed sidebar symbol,
  and mobile header. Sidebar widths and navigation interactions are preserved.
- Public shell: desktop brand region and phone header, covering sign-in, signup,
  workspace selection, and legal pages that already use this shell.
- Both public directories: SVG and multi-size ICO favicons, 32px PNG favicon,
  180px Apple touch icon, 192/512/1024px app icons, a separate 512px maskable icon,
  and a 1200×630 PNG social card. The existing dashboard manifest and push-worker
  icon references point to these updated assets. The landing page remains a
  static site, without adding install or service-worker behavior.
- `public/brand/`: forest and cream monogram/wordmark SVG exports and vector
  sources for the raster artwork.

The maskable symbol fits entirely inside the central 80% safe circle. App PNGs
are full bleed so operating systems can apply their own masks.

Both HTML entry points link the social card. Set **`VITE_PUBLIC_URL`** to each
site's final public base URL when building to produce absolute crawler image
URLs (including a subdirectory if applicable). Unset, the URLs remain local and
the landing build retains its relative-base portability. Docker builds accept
the same public build argument. No domain is assumed or published by this change.
All visual assets are supplied; the production public URL is configuration.

## Regeneration

Normal app builds need no additional dependencies. To change the canonical
artwork or component, install these development tools and regenerate from the
repository root:

```sh
python -m pip install fonttools brotli pillow
npm --prefix frontend exec playwright install chromium
python scripts/generate_brand.py
```

The generator reads `logo.svg` and the existing Manrope WOFF2, updates both local
components and vector files, then uses the existing Playwright Chromium to
rasterize icons without network requests. Pillow writes a 16/32/48px ICO.
Edit canonical sources instead of generated app copies.

## Verification

Frontend lint, both app type checks and production builds pass. The landing has
no lint script; Vite continues to report its existing non-module `theme.js`
notice. The script intentionally runs before first paint and remains external.
The existing navigation, login, workspace picker, legal-page and PWA suites pass
(47 tests).

Production previews were checked in Chromium and WebKit at 320, 390, 768 and
1440px: landing light/dark, mobile menu, footer, public shell, dashboard mobile
header, and expanded/collapsed sidebar. Workspace API responses were fictional
local fixtures. Browser checks found no JavaScript errors or horizontal overflow.
At 320px, compact navigation artwork and shrinkable hero grid children prevent
clipping. No business logic or API behavior changed.
