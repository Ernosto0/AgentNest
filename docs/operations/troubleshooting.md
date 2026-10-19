# Troubleshooting

**Purpose:** Known problems and fixes for local development and the demo. Add an entry whenever a problem costs more than 15 minutes to diagnose.

| Symptom | Likely cause | Fix |
|---|---|---|
| `connection refused` on port 5433 | Postgres container not running | `docker compose up -d postgres`; `docker compose ps`; check that Docker Desktop is started |
| Port 5433 already in use | Another Postgres or container | Change the host port in `docker-compose.yml` **and** `DATABASE_URL`/`TEST_DATABASE_URL` in `.env` |
| `alembic upgrade head` fails with "relation already exists" | DB created by an older schema | `docker compose down -v && docker compose up -d postgres`, then migrate and seed (demo data only) |
| Status stuck at *Anlıyorum…* / *Hazırlanıyor…* / *Zamanlandı* past its time | Worker not running, or crashed | Start `uv run python -m app.worker`; check its terminal; Dev panel → Jobs for `dead` jobs and their `last_error_code` |
| Scheduled post did not publish at the time | Approval missing/expired, account not connected, or a failure rule active | Content card shows the state and reason; Dev panel → Simulator → Failure rules; Trace view |
| Login works, but every POST returns 403 `CSRF_FAILED` | Missing `X-CSRF-Token` header, or a stale session | Reload the page (the frontend refetches `/auth/me`); for curl, read `csrf_token` from `/auth/me` |
| Login loop on a phone over the LAN | `COOKIE_SECURE=true` on HTTP | Set `COOKIE_SECURE=false` in development |
| Simulated message produces no draft | Conversation in *human* mode, or the debounce delay (8 s) not elapsed | Release the conversation; wait or run due jobs |
| Draft says *Size devredildi* for a simple price question | Price fact unverified/contested, or `price_disclosure=do_not_share` | Business knowledge: verify the fact or resolve the suggestion |
| Webhook returns 401 in the simulator | `MOCK_INSTAGRAM_APP_SECRET` differs between the simulator and the API process | Use one `.env`; restart both processes |
| `npm run gen:api` diff fails in CI | Backend schema changed without regenerating | `cd backend && uv run python -m app.cli export-openapi -o ../frontend/openapi.json`, then `cd ../frontend && npm run gen:api`; commit both |
| `openapi.json` is unreadable / "invalid JSON" after export | Output redirected with `>` in Windows PowerShell 5.1 (writes UTF-16) | Use the `-o` option instead of `>` |
| `&&` or `cp` fails in PowerShell | Windows PowerShell 5.1 has no `&&`; `cp` is `Copy-Item` | Use `;` between commands and `Copy-Item .env.example .env` |
| i18n check fails | Key missing in `tr` or `en`, different `{{placeholders}}`, or `t("x")` with an unknown key | Add/fix the key in both catalogs; the message names the file and key |
| Playwright WebKit fails to launch on Windows | Browsers not installed | `npx playwright install chromium webkit` |
| `npm run e2e` fails at global setup | Postgres not running or migrations not applied | `docker compose up -d postgres`, then `uv run alembic upgrade head` in `backend/` |
| `npm run e2e`: "port 8000/5173 already in use" by something that is not the app | Another process owns the port (the runner reuses a *healthy* API/Vite, but not a foreign process) | Stop it, or free the port |
| `database "agentnest_test" does not exist` | Postgres volume created before the init script existed | `docker compose exec postgres psql -U agentnest -c "CREATE DATABASE agentnest_test OWNER agentnest;"` |
| pytest: `refusing to run tests against database …` | `TEST_DATABASE_URL` does not point at a database ending in `_test` | Fix `TEST_DATABASE_URL` in `.env`; the test session drops and recreates that schema |
| Startup error `Refusing to start, unsafe configuration` | `APP_ENV=production` with demo tools on, an example/short `SECRET_KEY`, insecure cookies or no explicit `DATABASE_URL` | Fix the variables listed in the message; generate a key with `uv run python -m app.cli generate-key` |
| `seed` fails with `DEMO_PASSWORD must be at least 10 characters` | `DEMO_PASSWORD` too short or a common password | Set a longer `DEMO_PASSWORD` in `.env` |
| `seed` says it refuses to run | `APP_ENV=production` | The seed is for development and test only |
| Line-ending noise in diffs on Windows | Git autocrlf | The repo's `.gitattributes` enforces LF; run `git add --renormalize .` once |
| Real LLM mode returns `LLM_BUDGET_EXCEEDED` | Daily cap reached | Increase `LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY` or wait for the next UTC day |
| Real LLM mode fails with authentication errors | Missing or invalid `OPENAI_API_KEY` | Set the key in `.env` and restart API and worker; or switch back to `LLM_PROVIDER=fake` |
| (Phase 7) Meta webhook verification fails | Verify token mismatch or the tunnel URL changed | Match `META_WEBHOOK_VERIFY_TOKEN` with the app dashboard; update the callback URL after a tunnel restart |
| (Phase 7) Container `ERROR` on publish | Media URL unreachable by Meta, not JPEG, or out-of-range aspect ratio | Check the presigned URL from outside your network; check the media validation report |
