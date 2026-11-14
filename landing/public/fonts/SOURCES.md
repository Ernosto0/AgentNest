# Bundled fonts

The same unmodified Manrope and Inter variable WOFF2 files the app uses
(`frontend/src/assets/fonts/`, see `frontend/public/fonts/SOURCES.md` for provenance and
checksums). They live in `src/assets/fonts/`; Vite emits content-hashed URLs, so visitors'
browsers make no request to a font CDN. Both fonts use the SIL Open Font License 1.1; the
licences are in this directory.
