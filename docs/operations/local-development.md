# Local Development and Demo

**Purpose:** Set up, run, seed, simulate, inspect and reset the application locally, without any external credentials. It also contains the scripted demo walkthrough.

> **Status:** this describes the **target** developer experience. Commands become valid as the phases deliver them (noted per section). The setup, run, test, seed and reset commands up to and including **Phase 1** were verified on Windows 11 (Windows PowerShell 5.1 and Git Bash) in task P1-14; later sections are verified by the phase that delivers them.
>
> **Shell syntax:** commands are written for Git Bash / PowerShell 7. In **Windows PowerShell 5.1** `&&` is not a valid separator: use `;` (or separate lines), e.g. `cd backend; uv run alembic upgrade head`. Do not redirect program output with `>` in Windows PowerShell 5.1 (it writes UTF-16): use the tools' own `-o/--output` options where they exist.

## 1. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Git | any recent | On Windows, Git Bash or PowerShell both work |
| Docker Desktop | current | Runs PostgreSQL only. WSL2 backend on Windows. |
| uv | current | Installs and pins Python 3.12 for the backend (`uv python install 3.12`) |
| Node.js | current LTS (≥ 20) | Frontend |

No paid accounts or API keys are needed. Defaults: `LLM_PROVIDER=fake`, `INSTAGRAM_ENABLED_PROVIDERS=mock`, `MEDIA_STORAGE_BACKEND=local` ([INV-14](../invariants.md)).

## 2. First-time setup (Phase 1+)

```bash
git clone <repo> agentnest && cd agentnest
cp .env.example .env                      # PowerShell: Copy-Item .env.example .env
docker compose up -d postgres             # Postgres 16 on localhost:5433

cd backend
uv python install 3.12
uv sync                                   # creates .venv from uv.lock
uv run alembic upgrade head
uv run python -m app.cli seed --reset     # demo users, workspaces, facts, simulated accounts, yesterday's history
cd ../frontend
npm ci
```

`docker compose up -d postgres` also creates the `agentnest_test` database used by the tests (`docker/postgres/init/`). That script only runs when the data volume is first created; if you started Postgres before it existed, create the database once: `docker compose exec postgres psql -U agentnest -c "CREATE DATABASE agentnest_test OWNER agentnest;"`.

Other CLI commands (from `backend/`): `uv run python -m app.cli create-user --email … --display-name …` (prompts for the password), `uv run python -m app.cli generate-key` (a `SECRET_KEY` value; `--kind token-encryption` prints a `TOKEN_ENCRYPTION_KEYS` entry).

## 3. Running (four terminals)

| Terminal | Command (from repo root) |
|---|---|
| Database | `docker compose up -d postgres` (once) |
| API | `cd backend && uv run uvicorn app.main:create_app --factory --reload --port 8000` |
| Worker | `cd backend && uv run python -m app.worker` |
| Frontend | `cd frontend && npm run dev` → http://localhost:5173 |

The worker is required for anything asynchronous: commands, drafts, sends, publishing and reports. If a status stays at *Anlıyorum…* or *Hazırlanıyor…*, check that the worker is running. (Phase 1 has no asynchronous features yet, so the worker only polls the queue and runs the scheduler tick; stop it with Ctrl+C, it finishes the running job first.)

From Windows PowerShell 5.1 the same commands read, for example: `cd backend; uv run uvicorn app.main:create_app --factory --reload --port 8000`.

Logs go to **stderr** (console format in development, JSON in production), so stdout stays clean for machine-readable CLI output.

## 4. Tests

```bash
cd backend
uv run pytest                              # all backend tests (needs Postgres running)
uv run pytest tests/unit                   # fast, no DB
uv run pytest -m commits -k jobs           # queue/concurrency/restart tests (real commits)
uv run ruff check . ; uv run ruff format --check . ; uv run mypy app ; uv run lint-imports
uv run python -m evals run --all --provider fake --strict   # Phase 3+: CI runs this; exit 1 on any failure
uv run python -m evals run --all --provider openai --max-cost-usd 2   # by hand, with OPENAI_API_KEY; reports go to backend/evals/reports/
cd ../frontend
npm test                                   # Vitest
npm run lint ; npm run typecheck ; npm run i18n:check
npx playwright install chromium webkit     # first time (add --with-deps on Linux)
npm run e2e                                # Playwright, 3 projects (see below)
```

- Backend tests always run against `TEST_DATABASE_URL` (the `agentnest_test` database): the test session refuses any database whose name does not end in `_test`. The schema is dropped and rebuilt with `alembic upgrade head` at the start of every test session, so never point `TEST_DATABASE_URL` at data you care about.
- `npm run e2e` needs Postgres running with migrations applied (`uv run alembic upgrade head`). It **re-seeds** the demo data (`seed --reset`), starts the API (`:8000`) and the Vite dev server (`:5173`) itself, and reuses them if they are already running. In CI (`CI=true`) it serves the production build with `vite preview` instead. Projects: `mobile-webkit` (iPhone 13), `mobile-chromium` (Pixel 7), `desktop-chromium`. Run one with `npm run e2e -- --project=desktop-chromium`. The Phase 3 and 4 scenarios (commands, extraction, inbox) need the worker: Playwright starts `python -m app.worker` itself (`WORKER_POLL_INTERVAL_SECONDS=0.2`, `REPLY_DEBOUNCE_SECONDS=1`) and waits for its startup log line. To run a second stack next to another checkout, move the ports: `E2E_API_PORT=8001 E2E_WEB_PORT=5174 npm run e2e` (the Vite proxy follows `E2E_API_PORT`) and point `DATABASE_URL` / `TEST_DATABASE_URL` at databases of your own.

### Regenerating the API client

The OpenAPI document and the generated TypeScript types are committed; CI fails if they drift. After changing any endpoint or response model:

```bash
cd backend && uv run python -m app.cli export-openapi -o ../frontend/openapi.json
cd ../frontend && npm run gen:api          # writes src/api/schema.d.ts
```

## 5. Demo data (seeded)

| Login | Password | Memberships |
|---|---|---|
| `owner@demo.local` | value of `DEMO_PASSWORD` (default in `.env.example`) | owner of `golkent-fitness` and `harbor-pilates` |
| `manager@demo.local` | same | manager of both |
| `staff@demo.local` | same | staff of both |
| `other@demo.local` | same | owner of `other-workspace` (isolation demo) |

| Workspace | Locale / currency / timezone | Contents (by phase) |
|---|---|---|
| `golkent-fitness` "Gölkent Fitness & Pilates" (fictional) | tr / TRY / Europe/Istanbul | P2: 16 facts and one pending suggestion ([business-knowledge.md §10](../architecture/business-knowledge.md), `backend/app/demo/data/facts_golkent_fitness.yaml`); P4: simulated Instagram account `@golkent.fitness.demo`; P6: one day of history (below) |
| `harbor-pilates` "Harbor Pilates Studio" (fictional) | en / EUR / Europe/Lisbon | Same structure in English (`facts_harbor_pilates.yaml`), including the P6 history |
| `other-workspace` | en / EUR / Europe/Berlin | No facts (isolation demo) |

All demo workspaces have `is_demo = true` and show the **SİMÜLASYON / SIMULATED** banner.

**Yesterday's history (Phase 6, `backend/app/demo/history_seed.py`).** `seed` gives each studio (`golkent-fitness`, `harbor-pilates`) one day of history, so Home, Activity and Reports are not empty on the first run: **6 inbound customer messages, 4 replies sent (each approved by the owner and sent through the operations ledger), 1 conversation handed to a person (a complaint), 1 draft still waiting for approval, 1 published feed post and 1 failed feed post** (`invalid_media`). It runs through the real paths (simulator webhook, jobs, approvals, mock send, publish executor) with a frozen clock at 17:00-21:00 local time **yesterday** in the workspace timezone, and then stores yesterday's daily report. Every row is simulated, and no job is left queued (periodic jobs are the worker's). `seed` adds the history only to a studio that has no conversations yet, so running `seed` again changes nothing; `other-workspace` has none. The draft left waiting is valid for 24 hours from yesterday evening, so it may show as expired when you open the demo late the next day. A conversation's `created_at` is set by the database, so the seed back-dates it to the first message (otherwise "new conversations" would read 0 for yesterday). The draft-stage audit entries `content.created` and `media.uploaded` are not marked simulated (Phase 5 behaviour: a draft has no account yet).

**Sample images (Phase 5).** `backend/app/demo/media/story-sample.png` (1080×1920) and `feed-sample.jpg` (1080×1350) are committed for the content demo and the E2E specs. They are plain gradients with a caption, generated once with Pillow, and are valid uploads: every upload is validated and re-encoded as a baseline JPEG, and the stored files live under `MEDIA_LOCAL_ROOT` (default `backend/var/media`, git-ignored; delete the folder to start clean). From Phase 5 on, upload one from the Content screen (the file input in the draft), or call `POST /api/v1/workspaces/{id}/media` with a multipart `file` field.

**Phase 4:** both studios also get a simulated Instagram account (`@golkent.fitness.demo`, `@harbor.pilates.demo`), `reply_languages` (Gölkent answers in Turkish and English, Harbor in English) and a recorded automation review, so their readiness is *Hazır* / *Ready*. Everything produced through the simulated account is labelled **SİMÜLASYON**.

**Phase 2 (business knowledge)** is demonstrable now: both studios seed to readiness *Taslaklar için hazır* / *Ready for drafts* (the full *Hazır* level also needs the simulated account and the automation review, which arrive in Phase 4). Each has one **unverified** fact (the student price) and one pending **discrepancy** suggestion ("bio says 5.500 ₺"). Walkthrough: log in as `owner@demo.local` → More → İşletme bilgileri → Fiyatlar → verify the student price → Geçmiş (history) → İşletme bilgileri → Öneriler → *Mevcut değeri koru* (reject) → Ana sayfa shows what is left. Then log in as `staff@demo.local`, change the monthly price (*Değişiklik öner*): it appears as a suggestion for the owner and the fact shows *İtiraz var* (contested) until the owner accepts or rejects. More → Çalışma alanı oluştur starts the new-workspace wizard. `seed` is idempotent and also adds the facts to workspaces created before Phase 2; `seed --reset` re-creates everything.

## 6. Demo walkthrough (complete from Phase 6; about 15 minutes)

Open http://localhost:5173 in a phone-sized window (DevTools device mode, 390×844) or on a real phone (§10). Log in as `owner@demo.local`, workspace `golkent-fitness`.

**A. Business setup:** More → İşletme bilgileri. Show verified facts with sources, the unverified student price, and the pending suggestion "bio says 5.500 ₺". Reject it. Home shows readiness *Taslaklar için hazır* (*Hazır* once Phase 4 adds the simulated account and the automation review).

**B. Customer price question:** More → Dev panel → scripted message "Ayşe: Merhaba, aylık üyelik ne kadar?" → Inbox → *Onay bekliyor*. Open the conversation and show the draft with "6.000 ₺" chip (source and version) and the reason "Onay gerekli (ayar)" → **Onayla ve gönder** → *Gönderildi · SİMÜLASYON*. Dev panel → scripted complaint → *Size devredildi* with reasons; no sendable draft. Dev panel → injection script → flagged and requiring approval; no discount in the text.

**C. Change a fact:** Home command bar: "Aylık üyelik artık 7.000 TL" → confirmation (6.000 ₺ → 7.000 ₺, impact: 1 scheduled post on hold if step D was done first) → Onayla. Dev panel → a new price question → the draft shows 7.000 ₺.

**D. Story:** Command "Deneme dersi için bir story hazırla" → the result links "İçeriği aç" → the draft shows overlay suggestions and the note that the text belongs on the picture (a story has no caption) → **Görsel seç** and pick `backend/app/demo/media/story-sample.png` → **Zamanla** → set the time to 2 minutes from now (the sheet says "İstanbul saati") → **Onayla ve zamanla** → *Zamanlandı*. At the scheduled minute the badge reads *Yayınlanıyor* for about ten seconds (the executor checks the container every 10 s; the mock container is ready after `SIM_CONTAINER_DELAY_SECONDS`) and then *Yayınlandı · SİMÜLASYON* with a simulated permalink. Do not want to wait? Choose **Hemen yayınla** instead of a time (owners and managers only; staff can only ask for approval, at least 15 minutes ahead). If the worker is not running, Dev panel → *Zamanı gelen işleri şimdi çalıştır* runs what is due. Editing a scheduled post sends it back to *Taslak* and voids its approval.

**E. Daily review:** Command "Bugün kaç DM geldi?" → answer. More → Raporlar → today's report. Tap a number to see the matching list. More → Etkinlik (activity) shows the same events.

**F. Failure handling:** Dev panel → failure rule: operation *publish*, error *transient*, press **Sonraki çağrı için ekle** **twice** (each rule covers the next call only, so two clicks are "×2") → publish a post with **Hemen yayınla** → *Tekrar denenecek 22:24*, then *Tekrar denenecek 22:29* (the retries come 1 and 5 minutes later) → *Yayınlandı* after about 6 minutes, once. Dev panel → "Simülatörde yayınlananlar" has one row for that post (one row per published post). A permanent error, *publish: invalid_media*, ends at once as *Başarısız* with the cause ("Instagram görseli işleyemedi.") and **Düzenle ve yeniden gönder**. Set *publish: timeout_after_success* → *Kontrol ediliyor…* and, at the first check a minute later, *Yayınlandı*, with exactly one post in the same list.

**G. Integration failure:** Dev panel → failure rule *send → auth_revoked* → send a customer price question and approve the reply → the reply stays *Birazdan gönderilecek*, the account becomes *yeniden bağlanmalı* and the bell shows a critical "Instagram hesabınızı yeniden bağlayın" → the red Home banner (**Bağlantıyı yenile**) or More → Instagram bağlantısı (*Connections*, `more/settings/connections`) → **Yeniden bağlan (simülasyon)** (owner) → the queued reply is sent (*Gönderildi · SİMÜLASYON*) without approving it again. Reconnecting does not resume held posts (re-approve them from Content) and does not remove failure rules. The same screen shows the account status, the last error in plain language, the capabilities and, for a *kararsız* account, the time until which no calls are made (workspace time); **Bağlantıyı kes** asks for confirmation first. For the circuit breaker: add five *transient* failure rules, trigger five sends, then remove the rules and press **Sağlık kontrolünü şimdi çalıştır** in the Dev panel (runs the health check of the workspace's degraded accounts now; it shows how many were checked and recovered).

Finish with Dev panel → **Demo'yu sıfırla** (confirm). The workspace is re-created with a new id, yesterday's history is back, and the app opens the new workspace.

### The developer simulator (Phase 4)

With `DEMO_TOOLS_ENABLED=true` (never in production) More → Geliştirici araçları (Dev panel) sends scripted customer messages through the **real** signed-webhook path, adds failure rules for the simulated Instagram (`send`, `lookup`, `echo`, `create_container`, `container_status`, `publish`, … with `transient`, `rate_limited`, `auth_revoked`, `permission_missing`, `window_closed`, `invalid_media`, `timeout_after_success`) and runs due jobs. The same from a terminal, with the API running:

```bash
cd backend
uv run python -m app.cli simulate-message --workspace golkent-fitness --script price   # also: complaint, refund, discount, injection, english_tourist, russian, photo_only, hours, location, trial
uv run python -m app.cli simulate-message --workspace golkent-fitness --customer "Ayşe" --text "Çalışma saatleriniz nedir?"
uv run python -m app.cli simulate-native-reply --workspace golkent-fitness --conversation <id> --text "Merhaba"   # the owner answers in the Instagram app
uv run python -m app.cli run-due-jobs                                                 # when no worker is running
```

A drafted reply appears about `REPLY_DEBOUNCE_SECONDS` (default 8) after the last message. The worker must be running for drafts and sends.

## 7. Inspecting execution results

| What | Where |
|---|---|
| Jobs (queued, running, dead) | Dev panel → Jobs; or `GET /api/v1/dev/jobs` |
| Trace of a draft, content item or command | Dev panel → Trace (joins audit, jobs, operations and agent runs by `correlation_id`) |
| Simulator state: published media (the "exactly one post" evidence) and failure rules | Dev panel → "Simülatörde yayınlananlar" and "Hata kuralları" (sent messages and containers have no view yet) |
| Activity log | More → Etkinlik |
| System health | More → Sistem durumu (owner and manager; `more/settings/system-health`, also linked from Ayarlar and the connection screen): accounts, operations, jobs, webhooks (with the system-wide invalid-signature count) and AI use of the last 24 hours, with a refresh button |
| Instagram connection | More → Instagram bağlantısı (`more/settings/connections`): status, last error, capabilities, reconnect (simulation), disconnect |
| Logs | API and worker terminals (console format). Set `LOG_LEVEL=DEBUG` for more. |
| Database | `docker compose exec postgres psql -U agentnest agentnest`, e.g., `select action, occurred_at from audit_logs order by occurred_at desc limit 20;` |

## 8. Resetting

- One demo workspace: Dev panel → **Demo'yu sıfırla** (or `POST /api/v1/dev/workspaces/{id}/reset`, owner only, `is_demo` workspaces only). The workspace is **deleted and re-created with a new id** (same slug, members and settings from the seed data), because audit rows are insert-only and keyed by the workspace id; the old audit rows stay, orphaned. Its simulator rows (`sim_*`), content, invites and local media files go with it; facts, the simulated account, the automation review and yesterday's history are seeded again, and `demo.reset` is audited on the new workspace. Other workspaces are not touched. Known limitation: the history is built by running jobs in the API process with a frozen clock, so a worker that is running at that moment can, rarely, claim one of those jobs first and process it with the real clock (the numbers of yesterday's report would then differ); reset again if the Dev panel shows odd history.
- Everything: `uv run python -m app.cli seed --reset` (drops and re-creates the demo users and workspaces, removes their local media files, seeds the history again; refuses in production).
- Nuclear option: `docker compose down -v && docker compose up -d postgres`, then migrate and seed.

## 9. Optional: real LLM (Phase 3+)

Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY=…` in `.env` (optionally `LLM_MODEL_DEFAULT`). Restart the API and worker. The status strip changes from "Çevrimdışı demo yapay zekâsı" to the real mode. Costs are recorded per run (System health). Use `LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY` to cap spending.

## 10. Testing on a real phone

`npm run dev -- --host` and open `http://<your-LAN-IP>:5173` on the phone (same Wi-Fi). Keep `COOKIE_SECURE=false` in development. On Windows, allow Node.js through the firewall for private networks.

## 11. Features that need external credentials, and their mock alternatives

| Feature | Real requirement | Default local alternative |
|---|---|---|
| AI drafting, commands, extraction | LLM API key (`openai`) | `fake` deterministic provider |
| Instagram messaging and publishing | Meta app, Instagram Login, professional account, public HTTPS webhook (Phase 7) | `mock` stateful simulator + Dev panel |
| Media hosting for publishing | S3-compatible bucket (Phase 7) | local filesystem |
| Owner messenger | Telegram bot token + public HTTPS or polling (Phase 9) | web notifications |
| Email invites / reset | SMTP (Phase 8) | invite link shown on screen; CLI password reset |

## 12. Real Instagram development (Phase 7, optional)

Requires a Meta app (Instagram Login), a professional test account and a tunnel for webhooks (e.g., `cloudflared tunnel --url http://localhost:8000`). Set the `META_*` variables, `MEDIA_STORAGE_BACKEND=s3` and the `S3_*` variables. Detailed steps are added in task P7-10.
