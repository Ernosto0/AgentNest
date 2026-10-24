# Local Development and Demo

**Purpose:** Set up, run, seed, simulate, inspect and reset the application locally, without any external credentials. It also contains the scripted demo walkthrough.

> **Status:** Phases 1–6 are implemented locally. The Phase 6 verification results and outstanding human/phone/CI checks are in the [phase summary](../implementation/phase-summaries/phase-06-summary.md). Real Meta integration remains Phase 7.
>
> **Shell syntax:** required commands below use **Windows PowerShell 5.1**, one command per line. Run the next command only if the previous one succeeded (`$LASTEXITCODE` is 0). Do not redirect program output with `>` in Windows PowerShell 5.1 (it writes UTF-16): use the tools' own `-o/--output` options where they exist. Commands assume the repository root unless a working directory is specified.

## 1. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Git | any recent | On Windows, Git Bash or PowerShell both work |
| Docker Desktop | current | Runs PostgreSQL only. WSL2 backend on Windows. |
| uv | current | Installs and pins Python 3.12 for the backend (`uv python install 3.12`) |
| Node.js | current LTS (≥ 20) | Frontend |

No paid accounts or API keys are needed. Defaults: `LLM_PROVIDER=fake`, `INSTAGRAM_ENABLED_PROVIDERS=mock`, `MEDIA_STORAGE_BACKEND=local` ([INV-14](../invariants.md)).

## 2. First-time setup

For a new checkout, replace `<repo>` with this repository's clone URL, then run `git clone <repo> agentnest` and `Set-Location agentnest` on separate lines. For an existing checkout, open PowerShell at its root. Copy the defaults only when `.env` does not exist; keep your existing local configuration otherwise.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d postgres             # Postgres 16 on localhost:5433

cd backend
uv python install 3.12
uv sync                                   # creates .venv from uv.lock
uv run alembic upgrade head
uv run python -m app.cli seed --reset     # demo users, workspaces, facts, simulated accounts, yesterday's history
cd ../frontend
npm ci
npx playwright install chromium webkit    # needed for the E2E checks, not for the walkthrough
```

`docker compose up -d postgres` also creates the `agentnest_test` database used by the tests (`docker/postgres/init/`). That script only runs when the data volume is first created; if you started Postgres before it existed, create the database once: `docker compose exec postgres psql -U agentnest -c "CREATE DATABASE agentnest_test OWNER agentnest;"`.

Other CLI commands (from `backend/`): `uv run python -m app.cli create-user --email … --display-name …` (prompts for the password), `uv run python -m app.cli generate-key` (a `SECRET_KEY` value; `--kind token-encryption` prints a `TOKEN_ENCRYPTION_KEYS` entry).

## 3. Running (four terminals)

| Terminal | Command (from repo root) |
|---|---|
| Database | `docker compose up -d postgres` (once) |
| API | `cd backend; uv run uvicorn app.main:create_app --factory --reload --port 8000` |
| Worker | `cd backend; uv run python -m app.worker` |
| Frontend | `cd frontend; npm run dev` → http://localhost:5173 |

The worker is required for anything asynchronous: commands, drafts, sends, publishing and reports. If a status stays at *Anlıyorum…* or *Hazırlanıyor…*, check that the worker is running. Stop it with Ctrl+C; it finishes the running job first. Use a separate terminal for each command and leave all three running. If a port is occupied, use the existing server only if it belongs to this checkout; otherwise stop that server in its own terminal before starting this one.

From Windows PowerShell 5.1 the same commands read, for example: `cd backend; uv run uvicorn app.main:create_app --factory --reload --port 8000`.

Logs go to **stderr** (console format in development, JSON in production), so stdout stays clean for machine-readable CLI output.

## 4. Tests

```powershell
cd backend
uv run pytest                              # all backend tests (needs Postgres running)
uv run pytest tests/unit                   # fast, no DB
uv run pytest -m commits -k jobs           # queue/concurrency/restart tests (real commits)
uv run ruff check .
uv run ruff format --check .
uv run mypy app evals
uv run lint-imports
uv run python -m evals run --all --provider fake --strict   # Phase 3+: CI runs this; exit 1 on any failure
uv run python -m evals run --all --provider openai --max-cost-usd 2   # by hand, with OPENAI_API_KEY; reports go to backend/evals/reports/
cd ../frontend
npm test                                   # Vitest
npm run lint
npm run typecheck
npm run i18n:check
npx playwright install chromium webkit     # first time (add --with-deps on Linux)
npm run e2e                                # Playwright, 3 projects (see below)
```

- Backend tests always run against `TEST_DATABASE_URL` (the `agentnest_test` database): the test session refuses any database whose name does not end in `_test`. The schema is dropped and rebuilt with `alembic upgrade head` at the start of every test session, so never point `TEST_DATABASE_URL` at data you care about.
- `npm run e2e` needs Postgres running with migrations applied (`uv run alembic upgrade head`). It **re-seeds** the demo data (`seed --reset`), starts the API (`:8000`) and the Vite dev server (`:5173`) itself, and reuses them if they are already running. In CI (`CI=true`) it serves the production build with `vite preview` instead. Projects: `mobile-webkit` (iPhone 13 settings, 390x844 viewport), `mobile-chromium` (Pixel 7 settings, 390x844 viewport), `desktop-chromium`. Run one with `npm run e2e -- --project=desktop-chromium`. Specs: `phase1` (shell, language, isolation), `scenario-a` to `scenario-g` (the walkthrough of section 6, one spec per scenario; `scenario-g` advances its future post deadline through the existing frozen-clock job hook, without waiting minutes), `i18n` (tr, en, tr on the main screens) and `a11y` (axe via `@axe-core/playwright`: no serious or critical violation; every screen must also fit the phone width). Run times per project are recorded in the [session 10 report](../implementation/phase-6-sessions/s10-report.md). A stale server on the E2E ports is reused, so check that they are free first. The Phase 3 and 4 scenarios (commands, extraction, inbox) need the worker: Playwright starts `python -m app.worker` itself (`WORKER_POLL_INTERVAL_SECONDS=0.2`, `REPLY_DEBOUNCE_SECONDS=1`) and waits for its startup log line. To run a second stack next to another checkout, move the ports: `$env:E2E_API_PORT="8001"; $env:E2E_WEB_PORT="5174"; npm run e2e` (PowerShell; clear the overrides afterwards with `Remove-Item Env:E2E_API_PORT, Env:E2E_WEB_PORT`) (the Vite proxy follows `E2E_API_PORT`) and point `DATABASE_URL` / `TEST_DATABASE_URL` at databases of your own.

### Regenerating the API client

The OpenAPI document and the generated TypeScript types are committed; CI fails if they drift. After changing any endpoint or response model:

```powershell
cd backend
uv run python -m app.cli export-openapi -o ../frontend/openapi.json
cd ../frontend
npm run gen:api                           # writes src/api/schema.d.ts
git diff --exit-code -- openapi.json src/api/schema.d.ts
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

All demo workspaces have `is_demo = true` and show a **Demo çalışma alanı / Demo workspace** notice. The seeded mock accounts and their records show **SİMÜLASYON / SIMULATED** badges. Provider-derived flags determine simulation: a real Meta connection can act on a real account even on a demo workspace.

**Yesterday's history (Phase 6, `backend/app/demo/history_seed.py`).** `seed` gives each studio (`golkent-fitness`, `harbor-pilates`) one day of history, so Home, Activity and Reports are not empty on the first run: **6 inbound customer messages, 4 replies sent (each approved by the owner and sent through the operations ledger), 1 conversation handed to a person (a complaint), 1 draft still waiting for approval, 1 published feed post and 1 failed feed post** (`invalid_media`). It runs through the real paths (simulator webhook, jobs, approvals, mock send, publish executor) with a frozen clock at 17:00-21:00 local time **yesterday** in the workspace timezone, and then stores yesterday's daily report. Every row is simulated, and no job is left queued (periodic jobs are the worker's). `seed` adds the history only to a studio that has no conversations yet, so running `seed` again changes nothing; `other-workspace` has none. The draft left waiting is valid for 24 hours from yesterday evening, so it may show as expired when you open the demo late the next day. A conversation's `created_at` is set by the database, so the seed back-dates it to the first message (otherwise "new conversations" would read 0 for yesterday). The draft-stage audit entries `content.created` and `media.uploaded` are not marked simulated (Phase 5 behaviour: a draft has no account yet).

**Sample images (Phase 5).** `backend/app/demo/media/story-sample.png` (1080×1920) and `feed-sample.jpg` (1080×1350) are committed for the content demo and the E2E specs. They are plain gradients with a caption, generated once with Pillow, and are valid uploads: every upload is validated and re-encoded as a baseline JPEG, and the stored files live under `MEDIA_LOCAL_ROOT` (default `backend/var/media`, git-ignored; delete the folder to start clean). From Phase 5 on, upload one from the Content screen (the file input in the draft), or call `POST /api/v1/workspaces/{id}/media` with a multipart `file` field.

**Phase 4:** both studios also get a simulated Instagram account (`@golkent.fitness.demo`, `@harbor.pilates.demo`), `reply_languages` (Gölkent answers in Turkish and English, Harbor in English) and a recorded automation review, so their readiness is *Hazır* / *Ready*. Everything produced through the simulated account is labelled **SİMÜLASYON**.

**Business knowledge walkthrough:** both studios now seed to readiness *Hazır* / *Ready*, with a simulated account and a recorded automation review. Each has one **unverified** fact (the student price) and one pending **discrepancy** suggestion ("bio says 5.500 ₺"). Log in as `owner@demo.local` → More → İşletme bilgileri → Fiyatlar → verify the student price → Geçmiş (history) → İşletme bilgileri → Öneriler → *Mevcut değeri koru* (reject). Then log in as `staff@demo.local`, change the monthly price (*Değişiklik öner*): it appears as a suggestion for the owner and the fact shows *İtiraz var* (contested) until the owner accepts or rejects. More → Çalışma alanı oluştur starts the new-workspace wizard. `seed` is idempotent and also adds the facts to workspaces created before Phase 2; `seed --reset` re-creates everything.

## 6. Demo walkthrough (A–G and reset)

Allow about **15 minutes for the core demo**, or **25–35 minutes for every branch below**, including the real 1- and 5-minute retry waits and the five-send circuit exercise. The automated suite uses frozen-clock job hooks for future deadlines; the UI's **Zamanı gelen işleri şimdi çalıştır** runs only jobs due **now** and does not advance time.

Start from §2's `seed --reset`, with the API, worker and `npm run dev` running (§3). Do not run E2E at the same time: it resets the same demo database. Open http://localhost:5173 in a phone-sized window (DevTools device mode, 390×844), or use the LAN URL in §10. Log in as `owner@demo.local` with `DEMO_PASSWORD` from `.env` (default `demo-password` in `.env.example`), then select **Gölkent Fitness & Pilates**. The navigation labels below are Turkish: **Daha fazla** means More, **Gelen kutusu** means Inbox.

**A. Business setup:** Daha fazla → **İşletme bilgileri**. Open **Fiyatlar** to show verified values and their sources and the unverified student price. Return to İşletme bilgileri → **Öneriler**, open the pending discrepancy about the monthly price (5.500 ₺), then **Mevcut değeri koru** to reject it. Home already reads **Hazır**: the seed includes the simulated account and the recorded automation review. Show the connection, **SİMÜLASYON** and offline AI status strip, and the attention cards from yesterday's history.

**B. Customer price question:** Daha fazla → **Geliştirici araçları** → scripted price question from **Ayşe** → Gelen kutusu → Ayşe. Wait about 8 seconds for the debounce and draft. Show **Onay bekliyor**, the **6.000 ₺ / ay** fact chip (tap it for source/version), and **Otomatik gönderim kapalı** → **Onayla ve gönder** → **Gönderildi · SİMÜLASYON**. Repeat with the complaint script (**Burak**): **Size gerek var**, a complaint reason and no approve/send button. Repeat with the injection script (**Kerem**): the reply needs a person, shows **İndirim istiyor**, offers no approve/send button and contains no 100% discount.

**C. Change a fact:** Home command bar: **Aylık üyelik artık 7.000 TL** → confirmation (6.000 ₺ → 7.000 ₺) → **Onayla**. Simulate another price question from Ayşe; the new draft shows **7.000 ₺**. Optional fact-impact branch: before this change, create and schedule a **feed post about the monthly price**, whose caption uses that fact. The confirmation then includes one content item, and İçerik → Sorunlar shows it **Beklemede**. The trial Story in D uses a promotion fact and does not by itself demonstrate a monthly-price hold.

**D. Story:** Home command **Deneme dersi için bir story hazırla** → **İçeriği aç**. Wait for the overlay suggestions and the note that they belong on the picture (a Story has no caption). **Görsel seç** → `backend/app/demo/media/story-sample.png` → **Zamanla** → set the **date and time in Europe/Istanbul** to 2 minutes ahead → **Onayla ve zamanla** → **Zamanlandı**. Keep the worker running and wait until that minute: **Yayınlanıyor**, then about ten seconds later **Yayınlandı · SİMÜLASYON** and a simulated permalink. For the shorter core demo choose **Hemen yayınla** instead. Staff cannot use that option and need at least 15 minutes' lead for approval. Editing a scheduled post returns it to **Taslak** and invalidates the old approval.

**E. Daily review:** Home command **Bugün kaç DM geldi?** → answer. Daha fazla → **Günlük rapor**, today's report: compare **Gelen mesaj** with the answer while no new messages arrive. Open a nonzero number and count the rows, using **Daha fazla göster** if present; the response-time median opens answered bursts with their durations rather than that many rows. Return to the report and select yesterday to show the seeded six inbound messages and four sent replies. Daha fazla → **Etkinlik** shows the corresponding events; try its group and date filters. Reports and records show **SİMÜLASYON**. Historical drill-downs stay pinned to the selected saved generation, preserving its membership and counts after state changes or regeneration. The response-time median links to its original durations. Legacy generations without saved evidence explain that limitation instead of inventing a list.

**F. Failure handling:** In Geliştirici araçları, choose **İşlem: publish**, **Hata: transient**, and press **Sonraki çağrı için ekle** **twice** (one call per rule). Create a feed post from İçerik → **Taslak iste**, using **Aylık üyelik fiyatı hakkında bir gönderi**; open it, wait for generation, attach `backend/app/demo/media/feed-sample.jpg`, then Zamanla → **Hemen yayınla** → **Onayla ve hemen yayınla**. Watch **Tekrar denenecek HH:mm**; retries occur 1 and then 5 minutes later. After roughly 6 minutes it is **Yayınlandı**. Geliştirici araçları → **Simülatörde yayınlananlar** → refresh: exactly one new row for this post (the seeded publication and D's Story are separate rows). For the short demo, show the first retry and continue with E while it waits.

For the permanent-error branch, add one **publish / invalid_media** rule and create another feed post the same way: it becomes **Başarısız**, with “Instagram görseli işleyemedi.” and **Düzenle ve yeniden gönder**. For the ambiguous-outcome branch, add one **publish / timeout_after_success** rule and publish another: **Kontrol ediliyor…**, then **Yayınlandı** at reconciliation about one minute later, with one new simulator row. Wait for each branch's rule to be consumed before adding another. Consumed rules remain in the list with `(0)`; they no longer affect calls.

**G. Integration failure:** Add one **send / auth_revoked** rule, simulate a price question and approve its new draft. It stays **Birazdan gönderilecek**; Home shows the red **Instagram bağlantınız yenilenmeli.** banner. Open the bell to see the critical **Instagram hesabınızı yeniden bağlayın** notification (severity **Acil** and simulation badge). Home → **Bağlantıyı yenile**, or Daha fazla → **Instagram bağlantısı** → **Yeniden bağlan (simülasyon)**. The account becomes connected, the banner clears and the queued reply becomes **Gönderildi · SİMÜLASYON** without approving again. Reconnect clears that account's `auth_revoked` rules only. For the due-post branch, schedule a post **before** revoking the connection, let it fall due while reauth is needed, and verify **Beklemede**; reconnect leaves it held until the owner re-approves it.

For the circuit branch, add **five send / transient** rules (five clicks) and five **profile / transient** rules (five clicks) to keep the periodic health probe from recovering before you inspect the banner. Simulate **Fiyat sorusu** (Ayşe), **Çalışma saatleri** (Mehmet), **Adres ve telefon** (Zeynep), **Deneme seansı** (Can) and **İngilizce turist** (Sarah), using each row's **Gönder** button. Wait until all five new drafts exist, then approve those five replies promptly (within ten minutes), so an earlier retry does not consume another rule before the remaining drafts are ready. All five sends fail and Home shows the amber **Instagram'a şu an ulaşılamıyor…** banner. Instagram bağlantısı shows **kararsız** and the cooldown time in the workspace timezone. In Geliştirici araçları remove **all remaining failure rules**, then press **Sağlık kontrolünü şimdi çalıştır**. It reports one checked and one recovered; Home returns to connected and the amber banner clears. Daha fazla → **Sistem durumu** shows the account and the last 24 hours' counts. Keep a failed profile rule only while demonstrating the degraded state; retries or a successful probe otherwise change it.

Finish with Geliştirici araçları → **Demo'yu sıfırla** → confirm. The URL gets a **new workspace id**, yesterday's history returns, the monthly price is **6.000 ₺** again, the account is connected, and the app opens the new workspace. Other workspaces are unchanged.

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

- One demo workspace: Dev panel → **Demo'yu sıfırla** (or `POST /api/v1/dev/workspaces/{id}/reset`, owner only, `is_demo` workspaces only). The workspace is **deleted and re-created with a new id** (same slug, members and settings from the seed data), because audit rows are insert-only and keyed by the workspace id; the old audit rows stay, orphaned. Its simulator rows (`sim_*`), content, invites and local media files go with it; facts, the simulated account, the automation review and yesterday's history are seeded again, and `demo.reset` is audited on the new workspace. Other workspaces are not touched. The history is built in one database transaction, committed when the day is complete, so a running worker never sees its jobs (they would otherwise be claimed with the real clock).
- Everything: `uv run python -m app.cli seed --reset` (drops and re-creates the demo users and workspaces, removes their local media files, seeds the history again; refuses in production).
- Nuclear option: `docker compose down -v && docker compose up -d postgres`, then migrate and seed.

## 9. Optional: real LLM (Phase 3+)

Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY=…` in `.env` (optionally `LLM_MODEL_DEFAULT`). Restart the API and worker. The status strip changes from "Çevrimdışı demo yapay zekâsı" to the real mode. Costs are recorded per run (System health). Use `LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY` to cap spending.

## 10. Testing on a real phone

From `frontend/`, run `npm run dev -- --host 0.0.0.0`. In another PowerShell run `ipconfig` and take the Wi-Fi adapter's IPv4 address; open `http://<your-LAN-IP>:5173` on the phone on the same Wi-Fi. Keep the API and worker running (§3), and `COOKIE_SECURE=false` in development; Vite proxies `/api` to the local API, so the phone needs port 5173 only. Allow Node.js through Windows Firewall for **private networks** if prompted. Follow §6 A–G and reset, checking that forms, sheets, banners and badges fit without horizontal scrolling. Browser emulation does not complete this real-phone check; record the phone, OS/browser, date and any failures in the phase summary.

## 11. Features that need external credentials, and their mock alternatives

| Feature | Real requirement | Default local alternative |
|---|---|---|
| AI drafting, commands, extraction | LLM API key (`openai`) | `fake` deterministic provider |
| Instagram messaging and publishing | Meta app, Instagram Login, professional account, public HTTPS webhook (Phase 7) | `mock` stateful simulator + Dev panel |
| Media hosting for publishing | S3-compatible bucket (Phase 7) | local filesystem |
| Owner messenger | Telegram bot token + public HTTPS or polling (Phase 9) | web notifications |
| Email invites / reset | SMTP (Phase 8) | invite link shown on screen; CLI password reset |

## 12. Real Instagram development (Phase 7, optional)

**Status (2026-10-23):** the offline implementation is available; Gate 1, Gate 2, P7-00 research and real-account acceptance remain pending. The following is a future owner-operated setup, not evidence that a tunnel, dashboard, bucket or live account has been tested. Keep the credential-free fake/mock/local defaults for ordinary development. Do not run `seed --reset` or the default E2E setup against data you need to preserve.

### Same-origin HTTPS for sign-in, OAuth and webhooks

The OAuth callback requires the same authenticated user session that started the connection. Tunnel the **frontend on 5173**: Vite already proxies `/api`, `/oauth` and `/webhooks` to the backend on 8000. Opening the UI at localhost while receiving the callback on a backend-only public tunnel loses the host-bound session cookie. A tunnel to 8000 alone is suitable for webhook-only investigation, not this OAuth sign-in flow.

1. Install `cloudflared` separately, start the API on 8000 and later keep its worker running. Start the tunnel in a separate terminal:

   ```powershell
   cloudflared tunnel --url http://localhost:5173
   ```

2. Copy only the assigned hostname into an explicit Vite allow-list before starting/restarting Vite. For example, replace this placeholder with the exact hostname assigned to your tunnel:

   ```powershell
   cd frontend
   $env:__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS = 'your-assigned-host.trycloudflare.com'
   npm run dev -- --host 127.0.0.1 --strictPort
   ```

   Do not use `allowedHosts: true` or allow all `.trycloudflare.com` hosts. The installed Vite version supports this environment variable. No host-header rewrite is needed with the exact allow-list; the proxy preserves the request origin. Stop the tunnel after testing. Quick-tunnel hostnames can change on restart; update every origin/redirect setting together.

3. In the backend's private environment set `FRONTEND_ORIGIN=https://your-assigned-host.trycloudflare.com`, `META_OAUTH_REDIRECT_URI=https://your-assigned-host.trycloudflare.com/oauth/instagram/callback`, and `COOKIE_SECURE=true`. Keep `VITE_API_BASE_URL` unset so browser API calls stay same-origin. Restart API/worker after configuration changes. Sign in **at that HTTPS origin**, then open More → Instagram connection. A localhost session does not transfer to it. A stable named tunnel/reverse proxy can use the same route arrangement.

The [Vite allowed-host documentation](https://vite.dev/config/server-options#server-allowedhosts) and [Cloudflare Quick Tunnel documentation](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) were accessible on 2026-10-23. This verifies configuration instructions only; no public tunnel was launched during offline implementation.

### Private configuration and Meta dashboard checklist

- Generate the **token-encryption** ring from `backend/`: `uv run python -m app.cli generate-key --kind token-encryption`. Store the returned ring privately in `TOKEN_ENCRYPTION_KEYS` and select its ID with `TOKEN_ENCRYPTION_ACTIVE_KEY_ID`. The command's default kind generates `SECRET_KEY`, which is not a token key ring. Retain old IDs while old ciphertext exists.
- Set `INSTAGRAM_ENABLED_PROVIDERS=meta` (or `mock,meta` only if you need both), `META_APP_ID`, `META_APP_SECRET`, a distinct explicit `META_WEBHOOK_VERIFY_TOKEN`, the pinned `META_GRAPH_API_VERSION` and the exact redirect URI above. Meta requires the ring and S3 in every environment. Never paste tokens/secrets into screenshots, tickets, shell history, logs or frontend variables. Keep stories gated by research V-03; the configuration flag alone does not verify support.
- In the developer app's **Instagram API with Instagram Login** configuration, register the exact HTTPS OAuth redirect including `/oauth/instagram/callback`. Verify the professional account/tester role and granted scopes (`instagram_business_basic`, `instagram_business_manage_messages`, `instagram_business_content_publish`). UI labels, access-level limitations and tester onboarding remain V-01 research; do not substitute Facebook Login instructions.
- Configure webhook callback `https://your-assigned-host.trycloudflare.com/webhooks/instagram` with the private verification token. The handshake must echo `hub.challenge`; POST bodies require `X-Hub-Signature-256` signed with `META_APP_SECRET`. Select the planned `messages` and `message_echoes` subscriptions where offered, and verify any account-level subscription/Live-mode requirements before acceptance. The application does not currently auto-subscribe an account. Capture real text, attachments, native-app echoes, story replies, reactions and deletion shapes only during authorized research, sanitizing all identifiers/content before adding fixtures.
- Official Meta business-login and webhook pages returned HTTP 429 during this session. These dashboard steps are the repository's provisional checklist, not freshly verified Meta behavior. V-01/V-02/V-03/V-05/V-08/V-09 and P7-00 remain open; see [platform-capabilities.md](../research/platform-capabilities.md).

### S3, R2 or MinIO media fetches

Use `MEDIA_STORAGE_BACKEND=s3` with a private bucket, scoped explicit `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY`, and `S3_BUCKET`. For AWS leave `S3_ENDPOINT_URL` empty and set the actual bucket `S3_REGION`. For R2 use its S3 API endpoint and `S3_REGION=auto`. MinIO requires its S3 API endpoint (not the console), a valid publicly trusted HTTPS endpoint reachable by Meta, and an appropriate region. A localhost/private-network MinIO URL or self-signed certificate cannot demonstrate a Meta fetch.

`S3MediaStorage` signs GET requests for `MEDIA_PUBLIC_URL_TTL_SECONDS` (default 3600). Presigned URLs grant temporary access to a private object: do not publish/log them, rewrite their host/query after signing, or replace them with a public bucket website URL. The adapter receives the URL only for container creation; owners view media through the authenticated API. `MEDIA_PUBLIC_BASE_URL` is reserved and does not expose local files or bypass the Meta/S3 startup requirement. Mock/local remains the default; mixed mock/S3 publishing is unsupported. V-09 must verify Meta's actual fetch, TTL and processing behavior.

### Manual adapter probes (future explicit opt-in)

`backend/tests/contract/test_meta_live.py` is marked `meta_live`. Both `META_LIVE_ACCESS_TOKEN` and `META_LIVE_IG_USER_ID` must be present or all probes skip. Supply them only through your private process environment when live research is authorized; do not put credentials in commands or captured output. Then run `uv run pytest -m meta_live tests/contract/test_meta_live.py -q --tb=no` from `backend/`.

With only the two required inputs, probes read profile and publishing quota. Adding `META_LIVE_RECIPIENT_ID` opts into **one real DM**, then read-only lookup polling matching its returned ID and recipient; the recipient must be eligible and inside the messaging window. Adding `META_LIVE_IMAGE_URL` opts into **one real feed post** from a public HTTPS JPEG, including bounded processing polls and permalink lookup. Omit these optional inputs for read-only probes. These are deliberate direct adapter contract probes, outside the application ledger; production/customer sends and publishes must still use approvals and the operations ledger. The harness never automatically retries a send/publish. On ambiguity, inspect the real account safely before another manual run. It neither records fixtures nor prints live objects/URLs/exceptions; do not use `--showlocals`, debugger capture or HTTP debug logging with credentials. Passing a probe does not prove OAuth/webhook/scheduled-ledger acceptance. No live probe was run in offline Sessions 1-4.

For ordinary full-suite runs, explicitly blank both required live inputs, even if your parent shell has credentials:

```powershell
$env:META_LIVE_ACCESS_TOKEN = ''
$env:META_LIVE_IG_USER_ID = ''
uv run pytest -q
```

### Troubleshooting

| Symptom | Next check |
|---|---|
| Vite blocks the public hostname | Set the exact assigned hostname in `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS`, then restart Vite. Keep port 5173 fixed with `--strictPort`. |
| OAuth callback requires sign-in or state is invalid | Sign in on the public HTTPS frontend origin, verify the exact registered redirect and current tunnel hostname, then start a fresh connection. State is single use and lasts ten minutes. |
| Account mismatch after reconnect | Choose the same Instagram account originally linked to this workspace. A different account cannot overwrite it. |
| Connection blocked after deleting history | An ongoing send may still need verification; failed cleanup may require operator recovery. Do not bypass cleanup or force a second authorization. |
| Webhook handshake/signature rejected | Check the explicit verify token, app secret, exact path and unmodified raw body. Never disable signature verification. |
| No webhook despite successful handshake | Verify dashboard/account subscriptions, app mode, tester access and real payload shapes in V-01/V-08. OAuth success alone does not prove delivery. |
| Image fetch/container fails | Verify trusted public HTTPS reachability, private-object signing endpoint/region, JPEG constraints, clock/expiry and V-09. Do not reveal the signed URL. |
| Mock connect is absent | Check public `instagram_providers` and `mock_requires_demo_workspace` plus `workspace.is_demo`; `demo_tools_enabled` is a separate setting. Production also requires permitted simulated workspaces. |

## 13. Landing page (outside the phase roadmap)

`landing/` is the pilot-waitlist page: a separate static React + Vite + Tailwind site that shares no code with `frontend/` and needs no backend. It describes the finished product, so its copy must be checked against what is actually built before it is published.

```bash
cd landing
npm install
npm run dev          # http://localhost:5174
npm run build        # static files in landing/dist/
```

Without `VITE_WAITLIST_ENDPOINT` the form runs in preview mode (see [environment-variables.md](environment-variables.md)). Details: [landing/README.md](../../landing/README.md).
