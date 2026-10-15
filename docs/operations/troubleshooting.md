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
| `npm run gen:api` diff fails in CI | Backend schema changed without regenerating | `uv run python -m app.cli export-openapi > ../frontend/openapi.json && npm run gen:api`; commit both |
| i18n check fails | Key missing in `tr` or `en` | Add the key to both catalogs |
| Playwright WebKit fails to launch on Windows | Browsers not installed | `npx playwright install --with-deps` |
| Line-ending noise in diffs on Windows | Git autocrlf | The repo's `.gitattributes` enforces LF; run `git add --renormalize .` once |
| Real LLM mode returns `LLM_BUDGET_EXCEEDED` | Daily cap reached | Increase `LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY` or wait for the next UTC day |
| Real LLM mode fails with authentication errors | Missing or invalid `ANTHROPIC_API_KEY` | Set the key in `.env` and restart API and worker; or switch back to `LLM_PROVIDER=fake` |
| (Phase 7) Meta webhook verification fails | Verify token mismatch or the tunnel URL changed | Match `META_WEBHOOK_VERIFY_TOKEN` with the app dashboard; update the callback URL after a tunnel restart |
| (Phase 7) Container `ERROR` on publish | Media URL unreachable by Meta, not JPEG, or out-of-range aspect ratio | Check the presigned URL from outside your network; check the media validation report |
