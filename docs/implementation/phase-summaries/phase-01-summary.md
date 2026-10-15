# Phase 1 summary: Foundation

**Status:** implemented and verified locally; **waiting for review** (per [roadmap.md §5](../roadmap.md)). Phase 2 has not been started.
**Scope reference:** [phase-01-foundation.md](../phases/phase-01-foundation.md). All tasks P1-01 … P1-14 are done.

## 1. What changed

| Area | Contents |
|---|---|
| Repository (P1-01) | `.gitignore`, `.gitattributes` (LF), `.editorconfig`, `docker-compose.yml` (Postgres 16 on host port 5433, named volume, healthcheck), `docker/postgres/init/` (creates `agentnest_test`), `.env.example`, `README.md` |
| Backend project (P1-02) | `backend/pyproject.toml` + `uv.lock` (Python 3.12), ruff (lint + format), mypy strict on `app/`, pytest markers (`commits`, `invariant`, `meta_live`), import-linter contracts, `create_app()` |
| `core` (P1-03/04) | `config` (Settings + production safety checks), `logging` (structlog, redaction, stderr), `errors` (catalog + `AppError`/`RetryableError`), `clock`, `ids`, `context`, `security` (argon2id, tokens), `i18n` (tr/en JSON, `t()`), `canonical` (`payload_hash`), `db` (naming convention, mixins, sessions, readiness) |
| API layer | `api/errors` (problem+json, 422 field errors), `api/middleware` (request IDs, one log line per request), `api/deps` (auth, **default-on CSRF**, `require_membership`), `/healthz`, `/readyz`, `/api/v1/meta` |
| `identity` (P1-05…07) | models, schemas (incl. `WorkspaceSettings`), repository, service, permission matrix, routes: `auth/login`, `auth/logout`, `auth/me` (GET/PATCH), `workspaces` (list/create), `workspaces/{id}` (GET/PATCH), `workspaces/{id}/members` |
| `audit` (P1-08) | model, `record()`, query helper; insert-only rule documented in the module |
| `jobs` (P1-09) | model, `enqueue` (dedup), handler registry, claim (`SKIP LOCKED` + lease recovery), execution with retry/backoff/dead/`on_dead`, fencing, heartbeat, threaded `Worker` with graceful shutdown, scheduler tick with advisory lock, `run_due_jobs`; `python -m app.worker` |
| CLI + seed (P1-10) | `seed [--reset]`, `create-user`, `generate-key`, `export-openapi [-o]`; `demo/data/identity.yaml` |
| Migration | `0001`: `users`, `sessions`, `workspaces`, `workspace_members`, `audit_logs`, `jobs` (no other tables) |
| Frontend (P1-11/12) | Vite + React 19 + TS strict, Tailwind 4, React Router, TanStack Query, i18next (tr/en), generated `openapi-fetch` client; screens: Login, Workspace picker, App shell (bottom tabs / sidebar), Home, Inbox/Content/Approvals empty states, More, Settings → Language; `SimulationBanner`, `StatusBadge`, `SimulatedBadge`, workspace switcher; Vitest, Playwright, `check-i18n.mjs` |
| CI (P1-13) | `.github/workflows/ci.yml`: `backend`, `frontend` (incl. OpenAPI drift check), `e2e`, `security` (gitleaks) |
| Docs (P1-14) | Updated: `local-development`, `troubleshooting`, `environment-variables`, `api-design`, `component-design`, `data-model`, `background-jobs`, `observability`, `security-and-privacy`, `docs/README.md` |

## 2. Test results (all run locally, from a freshly rebuilt database and a clean `npm ci`)

| Suite | Result |
|---|---|
| Backend `uv run pytest` | **240 passed** (unit, integration, isolation, security, jobs) |
| Backend `ruff check`, `ruff format --check`, `mypy app` (strict), `lint-imports` | clean; 4 import contracts kept |
| Frontend `npm test` (Vitest) | **47 passed** |
| Frontend `eslint`, `tsc -b`, `npm run i18n:check`, `npm run build` | clean (89 catalog keys, 48 literal `t()` calls verified) |
| OpenAPI drift (re-export + regenerate vs committed files) | identical |
| Playwright, `CI=true` (production build via `vite preview`) | **18 passed** = 6 specs × `mobile-webkit`, `mobile-chromium`, `desktop-chromium` |

Mutation checks were run to confirm the key tests can fail: breaking the membership lookup (7 tests fail, including the AC-X1 harness), disabling CSRF (3 fail), removing `SKIP LOCKED` (3 concurrency tests fail), removing lease fencing (1 fails), making `core` import `identity` (import-linter breaks), removing an i18n key (checker fails), adding hard-coded JSX text (lint fails). Each was reverted.

## 3. Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Documented commands start everything on Windows and in CI | **Windows (manual, done):** `docker compose down -v` → `up -d postgres` → `uv sync --locked` → `alembic upgrade head` → `seed --reset` → API (`uvicorn … --reload`), worker and `npm run dev` started with the documented commands; `/healthz`, `/readyz`, `/api/v1/meta`, the Vite proxy and a real login were probed; the live worker dead-lettered a probe job. **CI:** workflow written but **not yet run on GitHub** (see §6) |
| 2 | All Phase 1 tests pass; lint and types clean | §2 |
| 3 | AC-X1 (Phase 1 routes) | `tests/isolation/test_workspace_isolation.py`: `test_every_workspace_route_returns_404_for_a_foreign_workspace`, `…_is_guarded_by_require_membership`, `test_listings_never_contain_the_other_workspaces_rows` (routes are enumerated from the app, so later routes are covered automatically) |
| 3 | AC-X5 | `tests/integration/jobs/test_restart.py` (new worker instance runs queued and scheduled jobs; interrupted job recovered; threaded stop/start) and `test_concurrency_and_leases.py` |
| 3 | AC-X6 | `tests/unit/core/test_settings_safety.py`; `tests/integration/test_cli.py::test_cli_refuses_to_start_on_an_unsafe_production_configuration` and `…_api_and_worker_refuse_…`. **Fake-LLM part deferred, see question Q1** |
| 3 | AC-X7 (redaction part) | `tests/unit/core/test_redaction.py`; schema part: `tests/security/test_api_security.py::test_no_response_schema_exposes_secret_fields` |
| 4 | `other@demo.local` gets 404 for `golkent-fitness` | `tests/integration/test_seed.py::test_other_user_is_isolated_from_the_gym_workspaces`; e2e `tenant isolation: …` |
| 5 | 360×740 without horizontal scroll; strings from catalogs; `i18n:check` | e2e `every main screen fits a 360x740 phone …` (both languages, all screens); ESLint rules reject literal JSX text / `aria-label` / `placeholder`; `npm run i18n:check` |
| 6 | No secrets in the repo; `.env` git-ignored | `.env` is ignored (`git check-ignore`); gitleaks result: see §7 |

AC-X3 (partial): `i18n:check` + e2e language switch. CSRF coverage: `tests/security/test_api_security.py::test_every_unsafe_api_route_rejects_requests_without_the_csrf_token` (enumerates all unsafe routes).

## 4. Demo steps (verified)

1. `docker compose up -d postgres`; `cd backend`; `uv run alembic upgrade head`; `uv run python -m app.cli seed --reset`.
2. Start `uv run uvicorn app.main:create_app --factory --reload --port 8000`, `uv run python -m app.worker`, and `cd frontend && npm run dev`.
3. Open `http://localhost:5173` in a phone-sized window, log in as `owner@demo.local` (password = `DEMO_PASSWORD`, default `demo-password`).
4. See the Turkish shell with "Demo çalışma alanı — simülasyon". More → Ayarlar → English. Switch workspace to Harbor Pilates Studio.
5. Log out, log in as `other@demo.local`: only *Other Workspace* is listed; opening a `golkent-fitness` URL shows "Bulunamadı".
6. `uv run pytest -m commits -k jobs` runs the 37 queue tests.

## 5. Deviations from the docs (and why)

| # | Deviation | Reason / where recorded |
|---|---|---|
| D1 | `audit.record` has extra keyword arguments `clock`, `actor`, `workspace_id` | The phase signature had no way to give a time (INV-19) or a user actor for workspace-less events such as `auth.login`. Documented in `component-design.md` |
| D2 | `require_membership(permission)` lives in `api/deps.py`, not `identity`; `permission=None` means "any member" | Keeps `identity.service` free of FastAPI/API imports (import-linter contract); the two docs disagreed on the signature. `component-design.md` updated |
| D3 | CSRF is a **router-level default** (`enforce_csrf` on `/api/v1`), with `/api/v1/auth/login` as the only exemption, instead of a per-route dependency | A route added later cannot forget it; a test enumerates all unsafe routes |
| D4 | Permission `reports.view` split into `reports.view` (owner, manager) and `reports.view_inbox_metrics` (all) | The matrix cell "inbox metrics only" needs its own name. `security-and-privacy.md` updated |
| D5 | Log redaction: key `code` matches only exactly; booleans/None are never masked | `error_code` and `cookie_secure=true` were useful and not secrets. `observability.md` updated (ADR-017 text is unchanged) |
| D6 | Logs go to **stderr** | Keeps stdout machine-readable for CLI output. Documented |
| D7 | `export-openapi` takes `-o/--output` | Windows PowerShell 5.1 `>` writes UTF-16. Docs and CI use `-o` |
| D8 | TypeScript pinned to 5.9 (latest is 7.x) | `typescript-eslint` supports `<6.1` and `openapi-typescript` needs `^5`; ADR-020 says "current and stable" for the *toolchain as a whole* |
| D9 | `audit_logs.workspace_id` is not a foreign key | Audit rows must survive workspace deletion without being updated. `data-model.md` updated |
| D10 | Workspace `reply_languages` is initialised to `[default_locale]` (DB default `{tr}` kept for raw inserts) | An English workspace should not default to Turkish replies |
| D11 | Currency check accepts only currencies in current use (Babel/CLDR), not every ISO 4217 historic code | Rejects `DEM`, `XXX`. `data-model.md` updated |
| D12 | Job `timeout` is the initial lease for that type (not a hard limit); unknown job type → `dead` + `JOB_PAYLOAD_INVALID` | Threads cannot be killed; the catalog has no better code. `background-jobs.md` updated |
| D13 | `httpx2` added as a dev dependency | Starlette's `TestClient` deprecates `httpx` |
| D14 | Summary location `docs/implementation/phase-summaries/` | The docs do not say where summaries go |

## 6. Known limitations

- **CI has not run on GitHub.** The workflow was validated as YAML and every step was reproduced locally, but action versions (`checkout@v4`, `setup-node@v4`, `setup-uv@v6`, `upload-artifact@v4`, `gitleaks-action@v2`) were chosen from memory and may need adjustment on the first run. `gitleaks-action` needs a licence key for organisation-owned repositories (not for a personal account).
- Playwright's WebKit is not real iOS Safari; the manual phone test over the LAN ([local-development.md §10](../../operations/local-development.md)) has **not** been done.
- No login throttling or password reset (Phase 8 / out of scope); failed logins write one audit row each, so the table grows under attack until throttling exists.
- List endpoints (`/workspaces`, `/members`) return the `{items, next_cursor}` envelope with `next_cursor` always `null` (bounded lists); real cursor pagination arrives with the first unbounded list.
- No accessibility (axe) tests yet; they are listed in the testing strategy for "main screens" and fit best once Phase 2 adds real content.
- E2E does not run the worker (nothing asynchronous in Phase 1); the "no real network egress" test guard (`pytest-socket`) is not installed yet, since no test code makes outbound calls so far.
- The PowerShell 5.1 console mis-displays UTF-8 JSON from `Invoke-RestMethod` (shows `GÃ¶lkent`); the API and browsers are correct.

## 7. Secret scan (criterion 6)

gitleaks (`ghcr.io/gitleaks/gitleaks:latest`, `gitleaks git --staged`) was run over all 165 files of the Phase 1 commit before it was created (≈735 KB): **no leaks found**. `.env` is git-ignored and was never staged; `.env.example` holds only documented placeholders (`SECRET_KEY` is a development value that production refuses). The CI `security` job repeats the scan over the full history on every push.

## 8. Questions for review

- **Q1 (AC-X6):** AC-X6 requires refusing the *fake LLM* in production, but `LLM_PROVIDER` is not a Phase 1 setting ("checks for later variables are added in those phases"). I implemented the Phase 1 checks and will add the fake-LLM check in Phase 3 together with the variable. Confirm.
- **Q2:** `GET /workspaces` and `/members` use the pagination envelope without real cursors (see §6). Acceptable until an unbounded list exists?
- **Q3:** Is `docs/implementation/phase-summaries/` the right home for phase summaries?
- **Q4:** Work was committed on a branch `phase-01-foundation` rather than `main`, so the phase can be reviewed as a pull request. Confirm this is the desired flow for later phases.
