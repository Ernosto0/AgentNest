# Bundled application fonts

Manrope and Inter normal variable WOFF2 files are copied **without modification**
from `@fontsource-variable/manrope@5.3.0` and
`@fontsource-variable/inter@5.3.0`, retrieved on 2026-10-30. No runtime CDN or npm
font dependency is required. Both fonts use the SIL Open Font License 1.1; the
complete copyright notices and licenses accompany this file. Package tarball
integrity was checked against npm's SHA-512 metadata before extraction.

`font-manifest.json` records the exact package source, subset, byte count and
SHA-256 for each binary. Source binaries live in `src/assets/fonts/` and Vite
emits content-hashed asset URLs. This directory and the licenses are copied into
the production build, alongside those assets.

- Manrope upstream: https://github.com/googlefonts/manrope
- Manrope Google Fonts metadata: https://github.com/google/fonts/tree/main/ofl/manrope
- Inter upstream and license: https://github.com/rsms/inter
- Distribution: https://github.com/fontsource/fontsource

The application declares normal weights 400–700. The unmodified distribution
files retain their full variable weight axes. Latin and Latin Extended subsets
cover Turkish; `unicode-range` restricts browser requests to necessary subsets.
No new graphic product mark is approved: keep the AgentNest wordmark and local
24px stroke icon family. These icons are repository-authored SVG paths and have
no external runtime source. Photographs and fictional concept imagery are not
application assets.
