# Local Development and Demo

**Purpose:** Set up, run, seed, simulate, inspect and reset the application locally, without any external credentials. It also contains the scripted demo walkthrough.

> **Status:** this describes the **target** developer experience. Commands become valid as the phases deliver them (noted per section). Phase 1 task P1-14 verifies the setup commands on Windows and corrects this document where reality differs.

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
uv run python -m app.cli seed --reset     # demo users, workspaces, facts (later phases add more)
cd ../frontend
npm ci
```

## 3. Running (four terminals)

| Terminal | Command (from repo root) |
|---|---|
| Database | `docker compose up -d postgres` (once) |
| API | `cd backend && uv run uvicorn app.main:create_app --factory --reload --port 8000` |
| Worker | `cd backend && uv run python -m app.worker` |
| Frontend | `cd frontend && npm run dev` → http://localhost:5173 |

The worker is required for anything asynchronous: commands, drafts, sends, publishing and reports. If a status stays at *Anlıyorum…* or *Hazırlanıyor…*, check that the worker is running.

## 4. Tests

```bash
cd backend
uv run pytest                              # all backend tests (needs Postgres running)
uv run pytest tests/unit                   # fast, no DB
uv run pytest -m commits                   # queue/concurrency tests
uv run python -m evals run --all --provider fake
cd ../frontend
npm test                                   # Vitest
npm run i18n:check
npx playwright install --with-deps         # first time
npm run e2e                                # needs API + worker + seeded DB (see testing-strategy §7)
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
| `golkent-fitness` "Gölkent Fitness & Pilates" (fictional) | tr / TRY / Europe/Istanbul | P2: facts ([business-knowledge.md §10](../architecture/business-knowledge.md)); P4: simulated Instagram account `@golkent.fitness.demo`; P6: one day of history |
| `harbor-pilates` "Harbor Pilates Studio" (fictional) | en / EUR / Europe/Lisbon | Same structure in English |

All demo workspaces have `is_demo = true` and show the **SİMÜLASYON / SIMULATED** banner.

## 6. Demo walkthrough (complete from Phase 6; about 15 minutes)

Open http://localhost:5173 in a phone-sized window (DevTools device mode, 390×844) or on a real phone (§10). Log in as `owner@demo.local`, workspace `golkent-fitness`.

**A. Business setup:** More → İşletme bilgileri. Show verified facts with sources, the unverified student price, and the pending suggestion "bio says 5.500 ₺". Reject it. Home shows readiness *Hazır*.

**B. Customer price question:** More → Dev panel → scripted message "Ayşe: Merhaba, aylık üyelik ne kadar?" → Inbox → *Onay bekliyor*. Open the conversation and show the draft with "6.000 ₺" chip (source and version) and the reason "Onay gerekli (ayar)" → **Onayla ve gönder** → *Gönderildi · SİMÜLASYON*. Dev panel → scripted complaint → *Size devredildi* with reasons; no sendable draft. Dev panel → injection script → flagged and requiring approval; no discount in the text.

**C. Change a fact:** Home command bar: "Aylık üyelik artık 7.000 TL" → confirmation (6.000 ₺ → 7.000 ₺, impact: 1 scheduled post on hold if step D was done first) → Onayla. Dev panel → a new price question → the draft shows 7.000 ₺.

**D. Story:** Command "Deneme dersi için bir story hazırla" → Content → draft with overlay suggestions → upload `backend/app/demo/media/story-sample.png` → **Onayla ve zamanla** for 2 minutes from now → wait (or Dev panel → *Run due jobs* after the time) → *Yayınlandı · SİMÜLASYON* with a simulated permalink.

**E. Daily review:** Command "Bugün kaç DM geldi?" → answer. More → Raporlar → today's report. Tap a number to see the matching list. More → Etkinlik (activity) shows the same events.

**F. Failure handling:** Dev panel → failure rule *publish: transient ×2* → schedule a post for now → see *Tekrar denenecek* → eventually *Yayınlandı* once. Set *publish: timeout_after_success* → see *Kontrol ediliyor…* → *Yayınlandı*, with exactly one post in Dev panel → Simulator state.

**G. Integration failure:** Dev panel → *auth_revoked* → approve a reply → Home banner "Instagram bağlantınız yenilenmeli" → Settings → Bağlantılar → *Yeniden bağlan (simülasyon)* → the queued reply is sent.

Finish with Dev panel → **Reset demo**.

## 7. Inspecting execution results

| What | Where |
|---|---|
| Jobs (queued, running, dead) | Dev panel → Jobs; or `GET /api/v1/dev/jobs` |
| Trace of a draft, content item or command | Dev panel → Trace (joins audit, jobs, operations and agent runs by `correlation_id`) |
| Simulator state (sent messages, containers, published media, failure rules) | Dev panel → Simulator |
| Activity log | More → Etkinlik |
| System health | More → Ayarlar → Sistem durumu |
| Logs | API and worker terminals (console format). Set `LOG_LEVEL=DEBUG` for more. |
| Database | `docker compose exec postgres psql -U agentnest agentnest`, e.g., `select action, occurred_at from audit_logs order by occurred_at desc limit 20;` |

## 8. Resetting

- One demo workspace: Dev panel → Reset demo (or `POST /api/v1/dev/workspaces/{id}/reset`).
- Everything: `uv run python -m app.cli seed --reset` (drops and re-creates demo data; refuses in production).
- Nuclear option: `docker compose down -v && docker compose up -d postgres`, then migrate and seed.

## 9. Optional: real LLM (Phase 3+)

Set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=…` in `.env`. Restart the API and worker. The status strip changes from "Çevrimdışı demo yapay zekâsı" to the real mode. Costs are recorded per run (System health). Use `LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY` to cap spending.

## 10. Testing on a real phone

`npm run dev -- --host` and open `http://<your-LAN-IP>:5173` on the phone (same Wi-Fi). Keep `COOKIE_SECURE=false` in development. On Windows, allow Node.js through the firewall for private networks.

## 11. Features that need external credentials, and their mock alternatives

| Feature | Real requirement | Default local alternative |
|---|---|---|
| AI drafting, commands, extraction | LLM API key (`anthropic`) | `fake` deterministic provider |
| Instagram messaging and publishing | Meta app, Instagram Login, professional account, public HTTPS webhook (Phase 7) | `mock` stateful simulator + Dev panel |
| Media hosting for publishing | S3-compatible bucket (Phase 7) | local filesystem |
| Owner messenger | Telegram bot token + public HTTPS or polling (Phase 9) | web notifications |
| Email invites / reset | SMTP (Phase 8) | invite link shown on screen; CLI password reset |

## 12. Real Instagram development (Phase 7, optional)

Requires a Meta app (Instagram Login), a professional test account and a tunnel for webhooks (e.g., `cloudflared tunnel --url http://localhost:8000`). Set the `META_*` variables, `MEDIA_STORAGE_BACKEND=s3` and the `S3_*` variables. Detailed steps are added in task P7-10.
