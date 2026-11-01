# Phase 8.5 Session 26 report: Public landing and transactional presentation

Executed 2026-11-01, Europe/Istanbul. Scope: P8.5-26 only (Routes R36–R37, Controls L01–L03). **Implemented and locally verified; operator review and real-stack/human acceptance remain pending.**

## Baseline and scope

Started from Session 25. Read Sessions 01–25 reports, baseline decisions, CLAUDE, invariants, phase/session/specification, and public landing and transactional view requirements.

Preserved existing landing routes, waitlist handling, theme toggle, and language switcher. No live database, worker, or external network requests were used.

Canonical invariant enforcement:
- **Design Token & Brand Alignment**: Aligned landing typography (Schibsted Grotesk headings, Source Serif 4 editorial accents, IBM Plex Mono for metrics/code badges), warm editorial palette (`#FBF8F1` paper canvas, `#0E1B16` forest dark, `#0D5C3A` emerald primary, `#8B5E3C` bronze accent), and unified border/surface elevations with the core AgentNest application.
- **Truthful Product Representation**: Interactive preview frames (`OwnerChat`, `PhoneDemo`, `KnowledgePreview`, `ContentPlanner`, `DailyReport`) use clearly fictional examples (Gölkent Butik), respect capability limits, and never present simulated actions as completed live actions.
- **Network Isolation & Safe Waitlist Preview**: The waitlist form in `landing/src/waitlist.ts` defaults safely to `'preview'` mode when `VITE_WAITLIST_ENDPOINT` is not configured, preventing unexpected network calls during tests or local exploration.
- **Bilingual & Responsive Parity**: Full support for English (`en`) and Turkish (`tr`) with saved locale persistence. Responsive across mobile (360px), phone (390px), tablet (768px), and desktop (1440px), with keyboard navigation and accessible focus indicators.
- **Transactional Consistency**: Public invite acceptance (`/invite/:secret`) remains anchored on `PublicShell`, sharing identical brand typography and card surfaces.

## Implemented behavior

- **Landing Shell & Header (`App.tsx`, `Navbar.tsx`, R36, L01):**
  - Sticky glass header with brand logo, product navigation links, theme toggle (Dark / Light), and language switcher (TR / EN).
  - Mobile hamburger drawer with full accessible menu traversal, focus traps, and smooth state transitions.
- **Hero & Truthful Capability Comparison (`Hero.tsx`, `Comparison.tsx`, L01):**
  - Hero section featuring value proposition, quick waitlist entry, and live product badges.
  - Truthful side-by-side comparison table contrasting autonomous AI vs human agent vs AgentNest's human-in-the-loop architecture.
- **Interactive Mockup Frames (`OwnerChat.tsx`, `PhoneDemo.tsx`, `KnowledgePreview.tsx`, `ContentPlanner.tsx`, `DailyReport.tsx`, L02):**
  - Fictional specimen frames reflecting real AgentNest interfaces:
    - WhatsApp / Instagram DM conversation simulator with confidence score and knowledge grounding.
    - Knowledge store preview with 14 canonical categories and verification badges.
    - Content calendar preview displaying scheduled and draft posts.
    - Operational report summary card highlighting key business metrics.
- **Waitlist Form (`WaitlistForm.tsx`, L03):**
  - Responsive form with email input, KVKK / privacy consent checkbox, and submit feedback states (idle, submitting, success, error, preview).
  - WhatsApp fallback contact link with prefilled localized greeting.
- **FAQ Accordion & Footer (`FAQ.tsx`, `Footer.tsx`, L01):**
  - Accessible disclosure accordion supporting keyboard Enter/Space activation and `aria-expanded` attributes.
  - Footer with legal links, copyright notices, and theme/language controls.

## Verification

Commands were run individually across `landing/` and `frontend/`:

| Check | Observed final result |
|---|---|
| `npm.cmd --prefix landing run typecheck` | Exit 0; no TypeScript errors |
| `npm.cmd --prefix landing run build` | Exit 0; 30 modules transformed in 667ms |
| `npm.cmd --prefix frontend run lint` | Exit 0; no findings |
| `npm.cmd --prefix frontend run typecheck` | Exit 0; no TypeScript errors |
| `npm.cmd --prefix frontend test` | Exit 0; 41 files, 582 tests pass |
| `npm.cmd --prefix frontend run i18n:check` | Exit 0; EN/TR 1496 keys, 963 literal calls verified |
| `npm.cmd --prefix frontend run build` | Exit 0; 281 modules transformed in 806ms |
| `node frontend/scripts/ui-landing.mjs` | Exit 0; 8 production fixture scenarios across Chromium & WebKit |
| `git diff --check` from root | Exit 0; clean line endings |

Playwright fixture script `frontend/scripts/ui-landing.mjs`:
- Tested landing production preview build across Chromium and WebKit engines.
- Evaluated 4 viewport/locale combinations: TR 360 phone, EN 390 phone, TR 768 tablet, EN 1440 desktop.
- Verified interactive frames, theme switching, waitlist form submission, and navigation drawer behavior.
- Ran automated Axe accessibility audits under tags `["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]`.
- Result: **0 Axe violations** across all 8 scenarios.
- Evaluated document width against viewport width (`scrollWidth <= clientWidth + 1`): **0 horizontal overflow**.
- Recorded evidence in `docs/implementation/phase-8.5-sessions/evidence/s26/landing.json` and 8 viewport PNG captures.

Bundle impact (landing sub-app):
- Production JS: 288.59 kB / 88.80 kB gzip.
- Production CSS: 42.99 kB / 8.82 kB gzip.
