# ADR-020: React + TypeScript + Vite SPA, TanStack Query, generated API client

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
The original spec chooses React and TypeScript, mobile-first, with PWA later and localisation support. Open choices: build tool, routing, server-state management, styling, API typing, real-time updates, testing.

## Decision
- **Vite + React (current stable major, ≥ 18) + TypeScript (strict)** single-page app. Exact versions are whatever is current and stable when Phase 1 starts, recorded in `package-lock.json`. No SSR: the app is behind login, and SEO is irrelevant.
- **React Router** for routing.
- **TanStack Query** for server state, caching and polling (`refetchInterval` on screens awaiting async results). No global state library. Local UI state uses React state.
- **API types generated from OpenAPI** (`openapi-typescript`) with a thin typed fetch wrapper (`openapi-fetch`) that sets `credentials: "include"` and the CSRF header, and maps error `code`s to i18n messages.
- **Styling:** Tailwind CSS with a small set of in-house components (Button, Card, Badge, Sheet/BottomSheet, Tabs, Field). Accessible primitives (e.g., Radix UI) only where needed (dialogs, menus).
- **i18n:** `i18next` + `react-i18next` ([ADR-016](ADR-016-localization.md)).
- **Mobile-first layout:** bottom tab bar (Home, Inbox, Content, Approvals, More) under 768 px, side navigation above. Touch targets ≥ 44 px. Primary actions within thumb reach.
- **Real-time:** polling (OQ-17). Default 15 s on lists, 1 s while a submitted command or generation is pending, paused when the tab is hidden.
- **PWA (installable, Web Push):** deferred to after Phase 6. The decision depends on OQ-01.
- **Tests:** Vitest + Testing Library for components and hooks; **Playwright** for end-to-end demo scenarios at a mobile viewport (390×844) and a desktop viewport.

## Alternatives considered
- Next.js: SSR and server components add complexity without benefit for an authenticated dashboard backed by a separate Python API.
- Redux/Zustand: unnecessary with TanStack Query for server state.
- A full component library (MUI, Ant): heavy, desktop-oriented look, harder to make feel native on mobile.

## Consequences
- `frontend/src/` structure: `app/` (router, providers, layout), `features/<area>/` (pages, components, hooks per domain area), `components/` (shared UI), `api/` (generated types + client), `i18n/`.
- A visible, global **simulation banner/badge** component is mandatory wherever simulated data is shown ([invariants.md](../../invariants.md) INV-09).

## Revisit when
- Offline support is needed (PWA with background sync).
- A native mobile app is considered. A React Native app would reuse the generated API types.
