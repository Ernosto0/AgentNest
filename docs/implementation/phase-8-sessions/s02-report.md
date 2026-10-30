# Phase 8 — Session 02 Report: Production Images, Compose and Caddy

- **Session:** `S02` (`docs/implementation/phase-8-sessions/phase-08-sessions.md` §Session 02)
- **Date:** 2026-10-30
- **Status:** `offline complete` (Multi-stage non-root `Dockerfile`, `.dockerignore`, `compose.prod.yml`, `Caddyfile`, Phase 8 configuration extensions, documentation, unit/contract tests, and disposable container stack routing/header rehearsal complete; live public ACME TLS certificate issuance and VPS rollout remain externally pending Session 03 / Session 16)
- **Branch / Commit Baseline:** `main` at `6cf4a30` (`Complete Phase 8 Session 01 baseline inventory and ADR-025 contracts`; preceded by `e74a2b5` and `3e25fd9`)
- **Alembic Migration Head:** `20261029_0030_agent_content_intents.py` (revision `0030`, unchanged in Session 02)
- **Unrelated Work Preserved:** Untracked `design-preview/` directory left untouched.

---

## 1. Summary of Implemented Artifacts & Contracts

| Artifact / File | Status | Implementation Summary |
|---|---|---|
| `.dockerignore` | **Created** | Excludes `.git`, `.github`, `.env`, `.env.*`, key/certificate files (`*.pem`, `*.key`, `*.crt`, `*.p12`, `*.pfx`), `.venv/`, `node_modules/`, `frontend/dist/`, `var/`, `backend/var/`, `backend/tests/`, Playwright artifacts, and non-runtime directories (`docs/`, `landing/`, `design-preview/`). Kept total Docker build context to `3.92 MB`. |
| `Dockerfile` | **Created** | Multi-stage production build with 4 named stages: `frontend-builder` (`node:22-alpine`, frozen `npm ci`, `npm run build` with only `ARG VITE_API_BASE_URL=""`), `caddy` (`caddy:2.8-alpine` serving `/srv/app` + `/etc/caddy/Caddyfile`), `backend-builder` (`python:3.12-slim-bookworm` + `ghcr.io/astral-sh/uv:0.6.6`, frozen `uv sync --frozen --no-dev --no-install-project`), and default `backend` runtime stage running as non-root `agentnest:agentnest` (`uid=10001`, `gid=10001`). Supports API (`uvicorn app.main:create_app --factory`), worker (`python -m app.worker`), migrations (`alembic upgrade head`), and CLI (`python -m app.cli`). |
| `compose.prod.yml` | **Created** | Defines `postgres` (`postgres:16-bookworm`, internal-only port `5432`, `pg_isready` health check), `migrate` (`profiles: ["migrate", "ops"]`, runs `alembic upgrade head`), `api` (`10001:10001`, `/readyz` health check, `stop_grace_period: 15s`), `worker` (`10001:10001`, `check_readiness()` health check, `stop_grace_period: 35s` exceeding `SHUTDOWN_GRACE_SECONDS = 30.0` for `INV-07` lease drain), and `caddy` (publishes `80`, `443`, `443/udp`, depends on healthy `api`). Configured with `restart: unless-stopped`, `no-new-privileges:true`, isolated `edge` and `backend` bridge networks, persistent volumes (`postgres_data`, `media_data`, `caddy_data`, `caddy_config`), and bounded `json-file` log rotation (`10m` × `5`). Parameterized via `COMPOSE_PROJECT_NAME`, `ENV_FILE`, `APP_DOMAIN`, `CADDY_TLS_CONFIG`, `IMAGE_TAG`, and `HTTP_PORT`/`HTTPS_PORT` for optional staging (`P8-12`). |
| `Caddyfile` | **Created** | Disables admin API (`admin off`), exposes loopback-only container health probe (`http://127.0.0.1:8080/healthz`), configures `{$APP_DOMAIN::80}` and `{$CADDY_TLS_CONFIG:}`, enforces `10MB` request body cap, sets production security headers (`Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, and strict `Content-Security-Policy` without `unsafe-eval` or `unsafe-inline`), proxies `/api`, `/api/*`, `/webhooks`, `/webhooks/*`, `/oauth`, `/oauth/*`, `/healthz`, and `/readyz` to `{$API_UPSTREAM:api:8000}` preserving full paths/queries/raw bodies/cookies, and serves the static React SPA from `/srv/app` with `try_files {path} /index.html` and immutable asset caching. |
| `backend/app/core/config.py`, `backend/migrations/env.py` | **Updated** | Added Phase 8 configuration fields (`migration_database_url`, `trusted_proxy_cidrs`, `smtp_url`, `mail_from`, `operator_alert_email`, `sentry_dsn`), `effective_migration_database_url`, `trusted_proxy_networks`, CIDR validation, `MAIL_FROM` validation when `SMTP_URL` is set, `_SECRET_FIELDS` redaction in `public_dict()`, and `validate_production_settings()`. Wired `migrations/env.py` to `effective_migration_database_url`. |
| `.env.example`, `docs/operations/environment-variables.md`, `docs/architecture/deployment.md` | **Updated** | Documented all new Phase 8 settings, Compose/Caddy parameterization (`P8-12`), server `.env` ownership and file permissions (`chown deploy:deploy .env && chmod 600 .env`), `.dockerignore` build-context secret exclusion, and startup safety checks. |
| `backend/tests/unit/core/test_settings_safety.py`, `backend/tests/unit/core/test_production_packaging.py` | **Updated / Created** | Added 10 new unit and contract tests covering Phase 8 settings validation, secret redaction, `validate_production_settings()`, `.dockerignore` exclusions, multi-stage `Dockerfile` invariants, `compose.prod.yml` structure/grace periods/networks/volumes, and `Caddyfile` routes/headers/CSP. |

---

## 2. Verification Results

### 2.1 Static Analysis, Typecheck, Import Boundaries & Test Suites

| Check | Command | Exit Code | Result Summary |
|---|---|---|---|
| Backend Lint | `backend/.venv/Scripts/ruff.exe check .` | `0` | `All checks passed!` |
| Backend Format | `backend/.venv/Scripts/ruff.exe format --check .` | `0` | `564 files already formatted` |
| Backend Typecheck | `backend/.venv/Scripts/mypy.exe app evals` | `0` | `Success: no issues found in 298 source files` |
| Backend Import Contracts | `backend/.venv/Scripts/lint-imports.exe` | `0` | `Analyzed 350 files, 2850 dependencies. Contracts: 19 kept, 0 broken.` |
| Backend Unit Tests | `backend/.venv/Scripts/pytest.exe tests/unit -q` | `0` | `1500 passed in 20.07s` (including 91 passed in `test_settings_safety.py` + `test_production_packaging.py`) |
| Frontend Lint | `npm.cmd run lint` | `0` | `eslint .` passed cleanly |
| Frontend Typecheck | `npm.cmd run typecheck` | `0` | `tsc -b --noEmit` passed cleanly |
| Frontend i18n Parity | `npm.cmd run i18n:check` | `0` | `i18n check passed: en, tr \| 1415 keys \| 888 literal t() calls verified` |
| Frontend Unit Tests | `npm.cmd test` | `0` | `33 passed (33), 516 passed (516)` |
| Frontend Production Build | `npm.cmd run build` | `0` | Built `dist/index.html` + hashed JS/CSS bundles in `dist/assets/` with zero inline scripts or styles |

### 2.2 Container Build, Non-Root Execution & Live Disposable Stack Rehearsal

All container checks were executed against Docker Engine `29.4.3` and Docker Compose `v5.1.3` using a disposable rehearsal project (`COMPOSE_PROJECT_NAME=agentnest-s02-rehearsal`, `HTTP_PORT=18080`, `HTTPS_PORT=18443`) and torn down with `down -v` afterwards:

| Verification Step | Command | Exit Code | Observed Output / Evidence |
|---|---|---|---|
| Compose Config Validation | `docker compose -f compose.prod.yml --profile migrate config --services` | `0` | Validated services: `api`, `caddy`, `migrate`, `postgres`, `worker` |
| Production Image Build | `docker compose -f compose.prod.yml build` | `0` | Built `ghcr.io/agentnest/agentnest-backend:latest` and `ghcr.io/agentnest/agentnest-caddy:latest` (build context `3.92 MB`) |
| Non-Root API User Check | `docker compose -f compose.prod.yml --env-file ... run --rm --no-deps api id` | `0` | `uid=10001(agentnest) gid=10001(agentnest) groups=10001(agentnest)` |
| Non-Root Worker User Check | `docker compose -f compose.prod.yml --env-file ... exec -T worker id` | `0` | `uid=10001(agentnest) gid=10001(agentnest) groups=10001(agentnest)` |
| Caddyfile Validation | `docker compose -f compose.prod.yml --env-file ... run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile` | `0` | `Valid configuration` |
| One-Off Database Migration | `docker compose -f compose.prod.yml --env-file ... --profile migrate run --rm migrate` | `0` | Applied all 30 Alembic migrations (`0001` -> `0030`) against rehearsal Postgres container |
| Stack Startup & Health Gates | `docker compose -f compose.prod.yml --env-file ... up -d --wait` | `0` | `postgres-1` (`Healthy`), `api-1` (`Healthy`), `worker-1` (`Healthy`), `caddy-1` (`Healthy`) |
| End-to-End Proxy, Route, Deep-Link & Header Verification | `backend/.venv/Scripts/python.exe .../scratch/verify_stack.py` | `0` | `GET /healthz` -> `200 {"status": "ok"}`; `GET /readyz` -> `200 {"status": "ok", "checks": {"database": true, "migrations": true}}`; `GET /api/v1/meta` -> `200` (`demo_tools_enabled: false`, `mock_requires_demo_workspace: true`); `GET /api/v1/dev/jobs` -> `404` (`INV-20`); `GET /webhooks/instagram?hub.mode=subscribe&...` -> `200 s02-challenge-ok`; `GET /oauth/instagram/callback?...` -> `401`; `GET /` and `GET /w/demo-workspace/inbox` -> `200` with `<div id="root"></div>`, HSTS, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, and strict CSP |
| Rehearsal Stack Teardown | `docker compose -f compose.prod.yml --env-file ... down -v` | `0` | Removed all disposable rehearsal containers, volumes, and networks |

---

## 3. Reproducible Build & Run Commands

### 3.1 Build Production Images & Validate Configuration
```powershell
docker compose -f compose.prod.yml --profile migrate config --quiet
docker compose -f compose.prod.yml build
```

### 3.2 Start Production Stack (Single-VPS with Bundled PostgreSQL)
```powershell
# 1. Ensure .env has mode 0600 on Linux host (chown deploy:deploy .env && chmod 600 .env)
# 2. Start PostgreSQL and wait for health check
docker compose -f compose.prod.yml --env-file .env up -d --wait postgres
# 3. Run one-off Alembic migrations before starting/restarting application containers
docker compose -f compose.prod.yml --env-file .env --profile migrate run --rm migrate
# 4. Start API, worker, and Caddy reverse proxy and wait for all health checks
docker compose -f compose.prod.yml --env-file .env up -d --wait
```

### 3.3 Start Optional Staging Stack (`P8-12`) Using the Same Files
```powershell
$env:COMPOSE_PROJECT_NAME = "agentnest-staging"
$env:ENV_FILE = ".env.staging"
docker compose -f compose.prod.yml --env-file .env.staging up -d --wait postgres
docker compose -f compose.prod.yml --env-file .env.staging --profile migrate run --rm migrate
docker compose -f compose.prod.yml --env-file .env.staging up -d --wait
```

---

## 4. Canonical Task Coverage, External Dependencies & Handoff to Session 03

- **Canonical Phase 8 Task Coverage:**
  - `P8-01` (packaging portion): Multi-stage non-root `Dockerfile`, `.dockerignore`, `compose.prod.yml`, `Caddyfile`, `.env` permission documentation, and startup safety validation are **offline complete**.
  - `P8-12` (optional staging parameterization): `compose.prod.yml` and `Caddyfile` are fully parameterized via environment variables (`COMPOSE_PROJECT_NAME`, `ENV_FILE`, `APP_DOMAIN`, `CADDY_TLS_CONFIG`, `IMAGE_TAG`, `HTTP_PORT`/`HTTPS_PORT`) so staging requires zero file forks.
- **Externally Pending Evidence:**
  - Live public DNS resolution and Let's Encrypt / ZeroSSL ACME certificate issuance on a hosted VPS remain pending external infrastructure provisioning (`Session 16` / `AC-1`).
- **Handoff to Session 03 (`Deployment, migrations and rollback`):**
  - Session 03 will consume `Dockerfile` (targets `backend` and `caddy`), `compose.prod.yml` (including the `--profile migrate` one-off service and `/readyz` health checks), and `MIGRATION_DATABASE_URL` to implement `.github/workflows/deploy.yml` (tag-triggered GHCR image publish, SSH deploy preflight, one-off migration gate before rolling restart, `/readyz` verification, and image rollback runbook).
