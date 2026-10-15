# Phase 1: Foundation

## Objective
Create a runnable, tested skeleton with the cross-cutting mechanisms that every later phase depends on: configuration with safety checks, database and migrations, authentication with sessions and CSRF, workspace tenancy enforcement, audit logging, the PostgreSQL job queue and worker, structured logging and error handling, and a mobile-first, bilingual frontend shell. It also includes CI.

## Read first
[CLAUDE.md](../../../CLAUDE.md) · [invariants.md](../../invariants.md) · [component-design.md](../../architecture/component-design.md) · [data-model.md §1–3.2](../../architecture/data-model.md) · [background-jobs.md](../../architecture/background-jobs.md) · [api-design.md §1, §2.1–2.2](../../architecture/api-design.md) · ADRs [001](../../architecture/decisions/ADR-001-modular-monolith.md)–[006](../../architecture/decisions/ADR-006-postgres-job-queue.md), [013](../../architecture/decisions/ADR-013-authentication-and-tenancy.md), [016](../../architecture/decisions/ADR-016-localization.md), [017](../../architecture/decisions/ADR-017-configuration-and-secrets.md), [018](../../architecture/decisions/ADR-018-observability-and-evaluation.md), [020](../../architecture/decisions/ADR-020-frontend-stack.md) · [local-development.md](../../operations/local-development.md) · [environment-variables.md](../../operations/environment-variables.md)

## Scope
**In:** repository scaffolding; backend skeleton; `core` (config, db, clock, errors, logging, security, i18n, canonical hashing); `identity` (users, sessions, workspaces, memberships, permissions); `audit`; `jobs` (queue, worker, scheduler skeleton, test hooks); CLI (seed identity data, create user, generate key, export OpenAPI); frontend shell (login, workspace picker, navigation, language switch, simulation banner, empty states); CI.
**Out (explicitly excluded):** facts, commands, LLM, Instagram, content, invites (Phase 6), password reset UI, email, RLS (Phase 8), Docker images for the app (Phase 8).

## Prerequisites
- Docker Desktop running; `uv` and Node.js LTS installed ([local-development.md §1](../../operations/local-development.md)).

## Files and modules expected to change
```
.gitignore  .gitattributes  .editorconfig  .env.example  README.md  docker-compose.yml
docker/postgres/init/01-create-test-db.sql
.github/workflows/ci.yml
backend/pyproject.toml  backend/uv.lock  backend/alembic.ini  backend/migrations/…
backend/app/{main.py, worker.py, cli.py}
backend/app/core/{config.py, db.py, context.py, clock.py, ids.py, errors.py, logging.py, security.py, canonical.py, i18n/{__init__.py, tr.json, en.json}}
backend/app/identity/{models.py, schemas.py, service.py, repository.py, router.py, permissions.py}
backend/app/audit/{models.py, service.py}
backend/app/jobs/{models.py, queue.py, worker.py, scheduler.py, registry.py, testing.py}
backend/app/api/{deps.py, errors.py, router.py}
backend/app/demo/{seed.py, data/identity.yaml}
backend/tests/{conftest.py, factories.py, unit/…, integration/…, isolation/…, security/…}
frontend/ (Vite project) src/{main.tsx, app/…, api/…, features/{auth,workspaces,home}/…, components/…, i18n/locales/{tr,en}/common.json, lib/…}
frontend/e2e/{playwright.config.ts, phase1.spec.ts}
frontend/scripts/check-i18n.mjs
```

## Key interfaces and contracts
- `Settings` fields for this phase: `APP_ENV`, `DATABASE_URL`, `TEST_DATABASE_URL`, `SECRET_KEY`, `FRONTEND_ORIGIN`, `APP_BASE_URL`, `PRODUCT_NAME`, `COOKIE_SECURE`, `SESSION_TTL_HOURS`, `LOG_LEVEL`, `LOG_FORMAT`, `DEMO_TOOLS_ENABLED`, `DEMO_PASSWORD`, `WORKER_CONCURRENCY`, `WORKER_POLL_INTERVAL_SECONDS`, `JOB_LEASE_SECONDS` ([environment-variables.md](../../operations/environment-variables.md)). Production safety checks: [ADR-017](../../architecture/decisions/ADR-017-configuration-and-secrets.md). Checks for variables introduced in later phases are added in those phases.
- `WorkspaceContext{workspace_id, actor: ActorRef, role: str | None, timezone, locale, is_demo}`; `ActorRef{type: user|system|agent|provider, id}`.
- `require_membership(permission: str)`: a FastAPI dependency that reads `workspace_id` from the path and returns `WorkspaceContext`. Foreign workspace → 404; missing permission → 403.
- `Clock` protocol: `now() -> datetime (UTC, tz-aware)`. `SystemClock`, `FrozenClock(start).advance(...)`.
- `AppError(code: str, http_status: int | None = None, **params)`, plus a problem+json handler ([api-design.md §1](../../architecture/api-design.md)).
- `audit.record(session, ctx_or_none, action, resource_type, resource_id, metadata={}, is_simulated=False, correlation_id=None)`.
- `jobs.enqueue(...)`, `@job_handler(...)`, `run_due_jobs(clock, limit)` ([background-jobs.md §2–3, §8](../../architecture/background-jobs.md)).
- `canonical.payload_hash(obj) -> str` (sorted keys, no whitespace, UTF-8, decimals as strings; hex SHA-256).
- Tables: `users`, `sessions`, `workspaces`, `workspace_members`, `audit_logs`, `jobs` ([data-model.md §3.1–3.2](../../architecture/data-model.md)).
- Endpoints: `/healthz`, `/readyz`, `/api/v1/meta`, auth (`login`, `logout`, `me` GET/PATCH), `GET/POST /workspaces`, `GET/PATCH /workspaces/{ws}`, `GET /workspaces/{ws}/members`.
- Permission matrix as a static mapping in `identity/permissions.py` ([security-and-privacy.md §3](../../architecture/security-and-privacy.md)), complete from day one even though most permissions are used later.

## Tasks (in order)

| ID | Task | Details | Size |
|---|---|---|---|
| P1-01 | Repository scaffolding | `.gitignore` (Python, Node, `.env`, `backend/var/`, Playwright artefacts), `.gitattributes` (`* text=auto eol=lf`), `.editorconfig`, `docker-compose.yml` with `postgres:16` on host port 5433 (user/password/db `agentnest`, healthcheck, named volume) and an init SQL creating `agentnest_test`. `.env.example` with the Phase 1 variables and comments. Minimal root `README.md` (what it is, a link to the docs, quickstart). | S |
| P1-02 | Backend project | `uv init` layout under `backend/`, Python 3.12 pin, dependencies: fastapi, uvicorn[standard], sqlalchemy ≥ 2.0, psycopg[binary] ≥ 3.2, alembic, pydantic ≥ 2, pydantic-settings, structlog, argon2-cffi, httpx, babel. Dev: pytest, ruff, mypy, import-linter (or an equivalent custom import test). Configure ruff (format + lint), mypy strict for `app/`, and pytest markers (`commits`, `invariant`, `meta_live`). `create_app()` factory with `/healthz`. | S |
| P1-03 | Core: config, logging, errors, clock, i18n, canonical | Settings with defaults per `APP_ENV` and production safety checks; structlog setup (console/JSON, contextvars binding, redaction processor); request-ID middleware; error catalog skeleton (codes from [observability.md §4](../../architecture/observability.md) used in Phase 1) with problem+json handlers (including a 422 mapping of FastAPI validation errors); `Clock`; `t(key, locale, **params)` with JSON catalogs; `payload_hash`. | M |
| P1-04 | Database and migrations | Engine and session factory, naming conventions, declarative base, mixins (`TimestampMixin`, `WorkspaceScopedMixin` adding `workspace_id` + `unique(workspace_id, id)`), Alembic env using the app metadata, `/readyz` (DB ping + current revision == head). | S |
| P1-05 | Identity schema | Models and migration for `users`, `sessions`, `workspaces`, `workspace_members`, with the constraints from the data model. `WorkspaceSettings` Pydantic model for `workspaces.settings`. | S |
| P1-06 | Authentication | argon2id hashing; login (generic error; session rotation; cookie flags from config); logout (revoke); `GET /auth/me` returning the CSRF token and memberships; `PATCH /auth/me` (display name, ui_locale); CSRF dependency on all state-changing routes except login and webhooks; sliding session expiry. Audit `auth.login`, `auth.logout`; `auth.login_failed` at system level. | M |
| P1-07 | Tenancy and workspaces | `WorkspaceContext`, `require_membership(permission)`, permission matrix, workspace create (creator becomes owner; timezone validated with `zoneinfo`; currency ISO-4217 check) / get / patch / list members. Audit `workspace.created`/`updated`. Isolation harness: a pytest fixture that creates workspaces A and B and enumerates all `/api/v1/workspaces/{workspace_id}/…` routes, calling them as an A member with B's IDs and expecting 404. Routes registered later are covered automatically. | M |
| P1-08 | Audit log | Model + migration, `audit.record`, a query helper for tests. A rule documented in a code comment: insert-only. | S |
| P1-09 | Job queue and worker | `jobs` model + migration (partial unique dedup index, due index), `enqueue`, handler registry with payload models, claim (SKIP LOCKED + lease recovery), run with retry/backoff/dead, `on_dead` hook, heartbeat, graceful shutdown, multi-thread loop, scheduler tick with advisory lock (no periodic jobs registered yet), `run_due_jobs`. `python -m app.worker` entry point. | L |
| P1-10 | CLI and seed | `python -m app.cli` with `seed [--reset]` (creates demo users `owner@demo.local`, `manager@demo.local`, `staff@demo.local`, `other@demo.local` with `DEMO_PASSWORD`; workspaces `golkent-fitness` (tr, gym, TRY, Europe/Istanbul, is_demo) and `harbor-pilates` (en, pilates_studio, EUR, Europe/Lisbon, is_demo) with owner/manager/staff memberships; `other-workspace` owned by `other@demo.local`, used to demonstrate isolation), `create-user`, `generate-key`, `export-openapi`. Seed refuses to run in production. | M |
| P1-11 | Frontend scaffold | Vite + React + TS strict; Tailwind; React Router; TanStack Query; i18next with `tr` and `en` catalogs; `api/client.ts` (openapi-fetch, `credentials: include`, CSRF header from `/auth/me`, problem+json → `AppError` with localised message by code); `npm run gen:api` from `frontend/openapi.json`. Screens: Login; Workspace picker; App shell (bottom tabs on mobile: Ana sayfa, Gelen kutusu, İçerik, Onaylar, Daha fazla; sidebar on desktop) with localised empty states ("Bu bölüm bir sonraki aşamada gelecek"); More → Settings → Language; workspace switcher; `SimulationBanner` shown when the current workspace `is_demo`; `StatusBadge` and `SimulatedBadge` components (used later). The Vite dev proxy forwards `/api`, `/webhooks`, `/oauth` to `:8000`. | L |
| P1-12 | Frontend test setup | Vitest + Testing Library (a component test for `StatusBadge` and the language switch); `check-i18n.mjs` (key parity, non-empty values); Playwright config with `mobile-webkit`, `mobile-chromium`, `desktop-chromium`; `phase1.spec.ts`. | M |
| P1-13 | CI | GitHub Actions: `backend` (Postgres 16 service, uv, ruff, mypy, pytest), `frontend` (npm ci, eslint, tsc, vitest, i18n check, OpenAPI diff: export → gen → `git diff --exit-code`), `e2e` (start stack, seed, Playwright), `security` (gitleaks). | M |
| P1-14 | Docs sync | Verify every command in [local-development.md](../../operations/local-development.md) on Windows; fix the docs where reality differs; update [environment-variables.md](../../operations/environment-variables.md) if variables changed. | S |

## Tests to add
- **Unit:** settings safety (AC-X6); redaction processor (AC-X7, partial); `payload_hash` stability (key order, decimals, unicode); permission matrix; backoff schedule; i18n `t()` fallback.
- **Integration:** login/logout/me; CSRF required on POST; session expiry and revocation; workspace create/get/patch; membership 403 vs 404; audit entries for auth and workspace actions; `/readyz`.
- **Jobs (`@commits`):** enqueue + run; dedup (second enqueue returns the same job); retry → success; exhausted → dead + `on_dead` called; concurrent claim (two threads, one claims); lease expiry recovery; "restart" (new worker instance picks up queued and scheduled jobs; AC-X5); `run_at` in the future is not claimed until the clock advances.
- **Isolation:** harness in place (AC-X1 for existing routes).
- **Frontend:** component tests; i18n parity (AC-X3 partial).
- **E2E (`phase1.spec.ts`):** log in as owner on mobile → Home shell in Turkish with the simulation banner → switch to English → strings change → switch workspace → log out.

## Acceptance criteria
1. `docker compose up -d postgres`, `uv run alembic upgrade head`, `uv run python -m app.cli seed`, API, worker and frontend all start with the documented commands on Windows (manual) and in CI.
2. All Phase 1 tests pass in CI. Lint and type checks are clean.
3. AC-X1 (for Phase 1 routes), AC-X5, AC-X6 and AC-X7 (redaction part) pass.
4. A member of `golkent-fitness` gets 404 for `harbor-pilates` resources when not a member (logged in as `other@demo.local`).
5. The frontend renders at 360×740 without horizontal scroll. Every visible string comes from the catalogs. `npm run i18n:check` passes.
6. No secrets in the repository (gitleaks passes). `.env` is git-ignored.

## Demo scenario
1. `docker compose up -d postgres` → migrate → seed → start API, worker and frontend.
2. Open `http://localhost:5173` in a phone-sized window, log in as `owner@demo.local`.
3. See the Turkish shell with the "Demo çalışma alanı — simülasyon" banner. Switch to English in Settings. Switch to `harbor-pilates`.
4. Log in as `other@demo.local`: only `other-workspace` is listed. Manually requesting a `golkent-fitness` URL shows "not found".
5. Run `uv run pytest -m commits -k jobs` to see queue behaviour tests pass.

## Known risks
- Job queue correctness (RK-07): mitigated by the concurrency, lease and restart tests in this phase.
- Windows setup issues (RK-12): P1-14 verifies the docs on the founder's machine.

## Explicitly excluded
Any domain feature. Do not create tables beyond those listed. Do not add Redis or Celery. Do not add an auth bypass.
