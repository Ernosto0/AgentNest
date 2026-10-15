# ADR-002: Monorepo layout: `backend/`, `frontend/`, `docs/`

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
The repository is empty apart from `docs/idea.md`. Backend (Python) and frontend (TypeScript) must evolve together: API contracts change with the UI that consumes them. Coding agents work best when the layout is predictable and documented.

## Alternatives
1. Separate repositories for backend and frontend.
2. Monorepo with a JS workspace tool (Nx/Turborepo) managing both.
3. Plain monorepo with two independent toolchains in top-level folders.

## Decision
Option 3:

```
/
├── CLAUDE.md                 # instructions for coding agents (points to docs)
├── README.md                 # project intro + quickstart (created in Phase 1)
├── docker-compose.yml        # local Postgres (+ optional MinIO later)
├── .env.example              # documented env vars, no secrets
├── .github/workflows/ci.yml  # lint, type-check, tests (backend + frontend)
├── docs/                     # this documentation system
├── backend/
│   ├── pyproject.toml / uv.lock
│   ├── alembic.ini
│   ├── migrations/           # Alembic versions
│   ├── app/                  # application package (modules per component-design.md)
│   ├── evals/                # AI evaluation datasets + runner
│   └── tests/                # unit/ integration/ contract/ isolation/
└── frontend/
    ├── package.json / package-lock.json
    ├── vite.config.ts
    ├── src/                  # app/, features/<area>/, components/, i18n/, api/
    └── e2e/                  # Playwright scenarios
```

The API contract is shared through **OpenAPI**: the backend publishes `openapi.json`, and the frontend generates TypeScript types from it (`npm run gen:api`). The generated file is committed so that frontend builds do not need a running backend.

## Rationale
- One repository keeps contract changes atomic and reviewable.
- No JS monorepo tool is needed for a single frontend package.
- OpenAPI generation removes hand-maintained duplicate types.

## Trade-offs
- Two toolchains (uv + npm) must both be installed by contributors. Documented in [local-development.md](../../operations/local-development.md).
- The committed generated client can drift. CI regenerates it and fails on diff.

## Consequences
- Every phase doc lists changes under `backend/…` and `frontend/…` paths.
- Cross-platform commands: the founder develops on Windows, so no Makefile dependency. Commands are `uv run …` and `npm run …`, documented per OS where they differ.

## Revisit when
- A second frontend appears (e.g., a separate marketing site or admin console) and shared UI packages are needed.
- Hosted-only code needs a private repository (see [ADR-019](ADR-019-open-source-and-hosted-boundary.md)).
