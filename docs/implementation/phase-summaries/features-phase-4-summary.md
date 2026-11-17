# Feature Phase 4 Close-Out Summary: Before Self-Service Launch

- **Phase:** Feature Phase 4 (F-09 import facts from the Instagram profile and from a website, D-06 local package on the landing page)
- **Specification:** [features-phase-4-before-self-service/sessions.md](../features-phase-4-before-self-service/sessions.md), source [pre-launch-feature-recommendations.md](../../review/pre-launch-feature-recommendations.md) §4 step 4 plus D-06
- **Sessions executed:** 01 to 03. Reports in [features-phase-4-before-self-service/](../features-phase-4-before-self-service/): [s01](../features-phase-4-before-self-service/s01-report.md), [s02](../features-phase-4-before-self-service/s02-report.md), [s03](../features-phase-4-before-self-service/s03-report.md), [s03 landing detail](../features-phase-4-before-self-service/s03-landing-report.md)
- **Baseline Git commit:** `e2fcc23` (`main`). **Nothing is committed**: Sessions 01 to 03 are uncommitted on `main`, on top of nothing else (the Feature Phase 2 and 3 work is in the baseline).
- **Alembic migration head:** `0061` (`20261117_0061_candidate_source_detail.py`, parent `0060`). Next free: `0062`.
- **Status:** **Implemented and verified offline. Stopped for review.** Nothing was run against Instagram, a real customer website, a real model, or a device.
- **Date:** 2026-11-17

---

## 1. Executive summary

A new workspace no longer starts from a blank Knowledge page. Connecting the Instagram account produces a first set of fact candidates from the bio and recent captions, and the owner can paste a website address to get candidates from the business's own pages. Both go through the existing extraction task and the existing Suggestions review; **nothing is ever verified automatically** (INV-02), every candidate carries the snippet it came from, and imported text is treated as untrusted (injection segments are dropped before a model sees them). The website fetcher is a new SSRF-safe module with its own import-linter contract. The landing page has a new "Local package" section (Turkish first) that states the local offer with only claims that were checked against the code and the legal documents; the price is hidden behind an empty build-time value because pricing is not settled.

---

## 2. What changed, by feature

### 2.1 F-09 import from the Instagram profile (Session 01)
- **Provider contract** (`integrations/instagram/base.py`, `meta.py`, `mock.py`): `get_profile_details` (bio, website, name, username) and `list_recent_captions(limit)`; plain reads, not ledger operations. Meta uses `GET /{ig-id}?fields=username,name,biography,website` and `GET /{ig-id}/media?fields=id,caption,timestamp,permalink,media_type&limit=N`. The mock returns a deterministic Turkish gym profile with captions 5, 40 and 200 days old.
- **Migration `0061`**: nullable `fact_candidates.source_detail JSONB` (object-only check) for origin, post date, URL and the simulated flag.
- **Source-agnostic pipeline** `knowledge/imports.py` plus `knowledge/profile_import.py`; it reuses `extract_fact_candidates` unchanged. Job `import_instagram_profile` (payload `{run_id}` only, two attempts, dead-run handler). Provider reads and the model call happen with no transaction open.
- **Triggers**: once after the first connection of an account (mock connect and OAuth callback; a reconnect does not re-import; a failing trigger never fails the connection) and the endpoint `POST /workspaces/{id}/knowledge/imports/instagram` (202, `knowledge.edit`). Polling uses the existing extractions endpoint.
- **Rules**: one candidate per fact key per import (bio first, then the newest caption); dedup against the verified fact, pending candidates of any source and values the owner already decided; captions older than 90 days are flagged `stale` at read time from the `Clock` (old prices warn); injection segments dropped; idempotent per account, per `client_request_id`, and per in-progress run.
- **Audit**: `knowledge.import_requested` and `knowledge.import_completed` (counts only).
- **Frontend**: `InstagramImportButton` (Suggestions header and Knowledge teach panel), candidate cards show origin (bio or post date), a "View post" link, a stale-price warning and a "Simulated" chip. TR and EN.
- **Docs**: `mvp-scope.md` (profile and website import moved out of Deferred), `platform-capabilities.md` §1.9 and backlog item V-12, and the architecture documents.

### 2.2 F-09 import from a website (Session 02)
- **SSRF-safe fetcher**, new package `app/integrations/web/` (imports only `app.core`; a new import-linter contract): `urls.py` (http and https only, default ports only, no userinfo, every IP literal refused, single-label and internal-looking hostnames refused, IDNA), `address_policy.py` (explicit blocked IPv4 and IPv6 ranges, unwrapping of mapped, compatible, 6to4 and NAT64 forms), `safe_fetch.py` (one DNS resolution per hop, all answers must be public, the connection is pinned to the chosen IP while TLS verification and SNI use the hostname, at most 3 redirects each fully re-checked, 2 MB streaming cap, 5/10/20 s timeouts, HTML content types only, `Accept-Encoding: identity`, fixed headers with no cookies or credentials), `html_text.py` (stdlib parser, `tel:` and `mailto:` retained, charset handling including windows-1254, depth cap 256), `fake.py` (offline fake gym site), `registry.py`.
- **Website import** `knowledge/website_import.py`: job `import_website`. Home page plus up to three same-site pages chosen by Turkish and English price, contact and about keywords; text chunked; first chunk per page and every chunk with a digit, `@`, `tel:` or `mailto:` kept (at most 40 segments) with origin `website_page`; the shared pipeline does the rest. **No migration** (`website` was already an allowed candidate source).
- **Rate limit and audit**: `WEBSITE_IMPORT_MAX_PER_WORKSPACE_PER_DAY` (default 10) counted from `agent_runs`, one import in progress per workspace, 429 `RATE_LIMITED`. Every fetch is audited as `knowledge.website_fetched` with host, outcome, reason and sizes, **never the URL, path or query** (tested, including logs and job payload).
- **API**: `POST .../knowledge/imports/website` (`{client_request_id, url}`) and `GET .../knowledge/imports/website/prefill`. New error codes `WEBSITE_UNREACHABLE`, `WEBSITE_BLOCKED`, `WEBSITE_NOT_HTML`, `WEBSITE_TOO_LARGE`. Settings `WEBSITE_IMPORT_FETCHER` (`auto`, `live`, `fake`; fake refused in production) and `WEBSITE_IMPORT_MAX_PER_WORKSPACE_PER_DAY`.
- **Frontend**: `WebsiteImportForm`, `ProfileImport` (combined section in the Knowledge teach panel), a fifth skippable "Import" step in `CreateWorkspaceWizard`, `website_page` origin labels and "View page" links in Suggestions.
- **Docs**: `security-and-privacy.md` (T14 and the §7 fetch rules and residual risks), `security-review-and-threat-model.md`, `environment-variables.md`, and the architecture documents.

### 2.3 D-06 local package on the landing page (Session 03)
- New `#paket` section in `landing/src/App.tsx` with copy in `landing/src/copy.ts` (Turkish first, English second): Turkish interface and replies, KVKK documents, invoice and pilot terms, in-person or video setup, the verified-price guarantee, and a price and "apply for the pilot" cell.
- `landing/src/config.ts`: `VITE_PACKAGE_PRICE` (empty hides the price block and label; no amount appears in the copy) and `VITE_APP_URL` (the legal-page links render only when set).
- Claims were verified one by one (14 rows in the [landing report](../features-phase-4-before-self-service/s03-landing-report.md)); the KVKK card says "awaiting legal review", the invoice card is marked "Planned", and the setup card names the cities (Burdur, Antalya) and video.
- Close-out: all checks, one parser performance fix, OpenAPI description sync, this summary and the roadmap.

---

## 3. Tests proving each acceptance criterion

| Criterion | Proof |
|---|---|
| S01: first connection creates a first set of candidates, once; reconnect does not re-import; a failing trigger does not fail the connection | `tests/integration/knowledge/test_profile_import.py`, OAuth connect and reconnect assertions in `tests/integration/integrations/test_oauth.py` |
| S01: candidates keep their snippet and source; nothing is verified; staff stay pending | `test_profile_import.py` (evidence and source detail, no facts, staff pending) |
| S01: dedup against verified facts, pending and decided candidates | `test_profile_import.py` (five dedup forms), `tests/unit/knowledge/test_imports.py` |
| S01: caption prices older than 90 days warn | `test_profile_import.py` (stale warning at read time) |
| S01: idempotency (per account, per request, in progress, redelivery) | `test_profile_import.py` |
| S01: injected bio or caption never reaches the model | `test_profile_import.py` (injection), `test_imports.py` |
| S01: provider contract, strict Meta shapes | `tests/unit/integrations/test_meta_provider.py`, `tests/contract/test_instagram_provider_contract.py` |
| S01/S02: isolation (foreign workspace 404, foreign account refused) | `tests/isolation/test_knowledge_isolation.py` |
| S01: no external call inside a transaction | `test_profile_import.py`, `test_website_import.py` (no open transaction around provider, fetch and model calls) |
| S02: blocked address classes, IP literals, odd ports, hostnames | `tests/unit/integrations/web/test_urls.py`, `test_address_policy.py` |
| S02: DNS rebinding (both ways), mixed answers, redirects to private addresses and `file://`, redirect limit and re-resolution, pinned IP and SNI, size caps (with and without a length header, lying length), wrong content type or encoding, slow trickle, exact request headers, no URL in exceptions | `tests/unit/integrations/web/test_safe_fetch.py` |
| S02: HTML to text, charsets, hidden and head content, links, depth bound | `tests/unit/integrations/web/test_html_text.py` (the depth test now takes 0.8 s) |
| S02: end-to-end website import with the fake fetcher, same-site page choice, injection, empty import without a model call, permanent and retryable failures | `tests/integration/knowledge/test_website_import.py` |
| S02: rate limit, replay by `client_request_id`, in-progress reuse, invalid URLs, prefill priority | `test_website_import.py` |
| S02: no URL, path or query in audit, job payload or logs | `test_website_import.py` |
| S01/S02: UI states (working, done, none, failed, injection), field error for a bad address, wizard step | `frontend/src/features/knowledge/instagramImport.test.tsx`, `websiteImport.test.tsx`, `frontend/src/features/workspaces/wizardImport.test.tsx`, `wizard.test.tsx` |
| S03: landing builds, both languages type-check against one `Copy` type | `npm.cmd run typecheck` and `build` in `landing/` |
| S03: no horizontal overflow at 390, 820, 1024 and 1280 px, light and dark, TR and EN, with and without the build variables | Playwright screenshots recorded in the landing report (session scratchpad; not re-run at close-out) |

Full check results: section 4.

---

## 4. Checks run

Environment for the backend suite: `PYTHONUTF8=1 LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN= WEBSITE_IMPORT_FETCHER=fake`, with `DEMO_TOOLS_ENABLED=true` for the integration shards. Four parallel shards on four empty databases (`agentnest_p4close_{a,b,c,d}_test`, dropped afterwards).

| Check | Result |
|---|---|
| `uv run alembic heads`; `upgrade head`, `downgrade -1`, `upgrade head` (shard DB) | single head `0061`; `0061 -> 0060 -> 0061` pass |
| `ruff check .`, `ruff format --check .` | pass (817 files) |
| `mypy app` | pass (432 files) |
| `lint-imports` | 24 contracts kept, 0 broken |
| (a) `tests/unit tests/contract tests/isolation tests/security` | first run 2405 passed, 18 skipped, 20 failed; every failure explained (below), all 20 pass re-run with the right environment |
| (b) `tests/integration/{inbox,reporting,activity,ai,demo}` | 703 passed |
| (c) `tests/integration/{content,agent,commands}` | 853 passed, 1 failed (load flake, passes alone) |
| (d) `tests/integration/{identity,knowledge,approvals,notifications,operations,plans,policy,retention,waitlist,integrations,jobs}`, `tests/integration/test_*.py`, `tests/e2e` | 745 passed, 3 failed (2 known baseline environment failures, 1 environment artifact) |
| Total backend, first run | 4706 passed, 18 skipped, 24 failed; **2 failures remain after attribution, both known baseline environment failures** |
| Evals, fake provider (`python -m evals run --all`) | interpret_command 84/84, extract_fact_candidates 12/12, draft_reply 86/86, draft_content 26/26; 0 hard failures |
| `frontend/openapi.json` against a fresh `export-openapi` | identical (one stale endpoint description patched, `schema.d.ts` too) |
| Frontend `lint`, `typecheck`, `i18n:check` (2762 keys), `build` | pass |
| Frontend `npm.cmd test` | 64 files, 913 tests passed (885 at Feature Phase 3 close) |
| Landing `typecheck`, `build` | pass (no lint or test scripts exist) |

**Failures and their causes:**
- **Environment artifact of the check setup, 17 tests:** `WEBSITE_IMPORT_FETCHER=fake` exported for the whole suite makes every test that builds a production `Settings` fail, because production refuses a fake fetcher by design. These are `test_settings_safety.py` (14), `test_deployment_workflow_and_rollback.py` (1), `tests/security/test_security_audit.py` (1) and `tests/integration/test_seed.py::test_seed_refuses_to_run_in_production` (1). They pass without the variable, which is not needed (`auto` picks the fake fetcher when `LLM_PROVIDER=fake`). Do not export it for the full suite.
- **Needs `DEMO_TOOLS_ENABLED=true`, 2 tests** (two isolation tests of dev routes in shard a, which ran without it): pass with it.
- **Real defect, fixed:** `tests/unit/integrations/web/test_html_text.py::test_deeply_nested_page_is_bounded` exceeded its 5 s allowance under load (4.8 s even alone). The HTML parser rescanned the element stack on every event. Fixed in `app/integrations/web/html_text.py` with inherited head and title flags: 0.8 s, same output.
- **Order-dependent, 1:** `tests/security/test_invite_secrets.py` (known since Feature Phase 2); passes alone.
- **Load flake, 1:** `tests/integration/agent/test_dm_transcript.py::..._voice_note_is_in_the_conversation[True]` (one extra simulated message under load); passes alone; the file is not touched by this phase.
- **Known baseline, 2 (not fixed):** `test_health_and_errors.py::test_cors_allows_only_the_frontend_origin` (`.env` `FRONTEND_ORIGIN`) and `test_members_and_invites.py::test_owner_creates_an_invite_with_a_one_time_link` (`.env` public URL is a `trycloudflare.com` address).

Not run: Playwright specs (`npm run e2e`), anything against Meta, real websites, a real model, a real device.

---

## 5. Demo steps

Credential-free defaults (`LLM_PROVIDER=fake`, `INSTAGRAM_ENABLED_PROVIDERS=mock`, `DEMO_TOOLS_ENABLED=true`, `WEBSITE_IMPORT_FETCHER` unset so `auto` picks the fake fetcher). API, worker (`uv run python -m app.worker`, required for the import jobs) and `npm run dev` running; see [local-development.md](../../operations/local-development.md).

1. **Profile import, first connection (S01).** Create a new workspace (More, then the new-workspace wizard) or use a workspace with no connected account. Connect the demo account (Connections, "Connect a demo account (simulation)"). Within a few seconds the worker runs one import. Open Suggestions: candidates from the bio (opening hours, price, phone) and from the captions appear with a "Simulated" chip and the source ("bio" or "post on <date>"). The 200-day-old caption price shows the stale-price warning. Accept one: only then does the fact exist, and it is still unverified until the owner verifies it. Reconnecting does not import again.
2. **Re-import (S01).** On Suggestions or the Knowledge teach panel press "Re-import from Instagram": the already-known values are skipped as duplicates and the result line says so.
3. **Website import (S02).** In the wizard's fifth step, or on the Knowledge page in the combined "Import from Instagram or your website" section, enter any `https://` address (for example `https://golkent-fitness.example`; the fake fetcher serves its offline Gölkent Fitness pages for any valid hostname, and a host ending in `.invalid` shows the "could not be reached" failure). Progress shows, then "Review suggestions" opens the candidates with origin "website page" and a "View page" link. An address such as `http://localhost`, an IP address or `https://example.com:8443` is refused with a field error. Importing the same address twice returns the same run; the eleventh import within 24 hours returns 429.
4. **Real fetcher smoke (optional, needs outbound network).** Start the API with `WEBSITE_IMPORT_FETCHER=live` and import a public site. With the live fetcher the audit trail (Activity) shows `knowledge.website_fetched` with the host only.
5. **Landing (S03).** From `landing/`: `npm.cmd run dev` (or `build` then `preview`). Without environment variables: the "Local package" section (nav link "Paket") shows five cards, no price, the three legal documents as plain chips, and a pilot button. With `VITE_PACKAGE_PRICE="..."` set at build or dev start the price cell appears; with `VITE_APP_URL=https://app.example` the privacy, terms and data-deletion chips become links. Check at phone width (390 px) in both languages.

---

## 6. Deviations from the briefs

1. **Pricing hidden by user decision.** The Session 03 gate said to ask for the settled TRY price; pricing is not settled, so the price block sits behind the empty `VITE_PACKAGE_PRICE` and no amount appears anywhere. The FAQ line "12 ay sabit kurucu fiyati" was left untouched.
2. **Contact fields not available from the API.** The brief asked for bio, website, contact fields and captions. The IG User reference lists no email, phone or address contact-button fields, so none are read; phone and e-mail come only from bio and caption text. Recorded as Unavailable in `platform-capabilities.md` §1.9.
3. **Caption read with Instagram Login unverified.** `caption` is documented as Facebook-Login-only on one page and not on others; the job degrades to a profile-only import (`captions_unavailable`) if the media read is rejected. Order, limit and permission of `GET /{id}/media` under Instagram Login are Unverified (V-12).
4. **Website is not a model segment** for Instagram imports; it is stored as prefill metadata only (`profile_website`), then used by the website step's prefill endpoint.
5. **No decompression and no headless browser** in the website fetcher (documented): a site that sends gzip anyway fails with `WEBSITE_NOT_HTML`; script-rendered sites yield little text.
6. **Odd ports and IP literals refused outright** rather than checked (documented in the security docs), and cross-host redirects are allowed at fetcher level (every hop re-checked) but the importer follows only same-site links.
7. **Session 02 fixes after Codex review**: a staff-role denial was removed (staff can request; candidates are pending anyway), a parser depth cap was added, and `http://` page URLs are kept on candidates.
8. **Staff and viewer roles**: the repo has no viewer role; an unsupported read-only role is denied at the service layer in tests.
9. **Close-out fix**: the parser performance fix and an OpenAPI description sync (section 4 and the [S03 report](../features-phase-4-before-self-service/s03-report.md)).
10. **Codex use**: Codex (gpt-6.1-sol) wrote the backend, tests and frontend of Sessions 01 and 02 in two runs each; the landing section and the close-out were done by Claude directly. No usage limit was hit.

---

## 7. Limitations and live items pending

- **V-12, real Instagram import:** real `biography` and `website` reads, whether `caption` is returned under Instagram Login, `/media` ordering, `limit` behaviour, `@` handling, with fixtures to record from the founder's test account. Until then Session 01 is verified against the mock and synthetic Meta responses only.
- **Real website imports on 3 to 5 Turkish small-business sites** are untried: gzip served despite `Accept-Encoding: identity`, script-rendered sites, sites that block the `AgentNestImport/1.0` user agent, and whether the daily limit of 10 suits onboarding. One manual fetch of `example.com` over TLS and plain HTTP succeeded; `localhost.localdomain` and a port other than 443 were refused.
- The OS resolver call has no own timeout; only the 180 s job timeout bounds it.
- Website text goes to the LLM provider like pasted text; the pages are public, but a pilot owner should know.
- A re-import does not supersede pending candidates whose key no longer appears in the profile (open question).
- `gpt-6-luna` was never run live, so the extraction quality on real bios and pages is unmeasured (evals ran with the fake model).
- **Landing:** `VITE_APP_URL` must be set at deploy for the privacy, terms and data-deletion links; the settled price must be set in `VITE_PACKAGE_PRICE` (and tier names if wanted); the invoice card should be dropped if a TRY invoice cannot be issued (OQ-05); the KVKK card text changes when counsel signs off. The landing app has no lint or test scripts.
- Playwright and a real-phone look were not part of the close-out.

---

## 8. P-10 and P-11 status (self-service launch depends on them)

Read from [pre-launch-problems.md](../../review/pre-launch-problems.md) and verified in the code on 2026-11-17.

| Item | State | Evidence | Open |
|---|---|---|---|
| **P-10 self-service signup** | **Done behind a flag** (default off) | `POST /auth/register`, `/auth/resend-verification`, `/auth/verify-email` in `backend/app/identity/router.py` and `signup.py`; `SIGNUP_ENABLED`; email verification, throttling, stored terms version (`identity/legal.py`) | Legal review of the terms and privacy text and a `TERMS_VERSION` bump; `SMTP_URL` and `MAIL_FROM` in production before turning the flag on; unverified accounts are never purged; no CAPTCHA |
| **P-11 plans and quotas** | **Partial** | `backend/app/plans/` (tiers `starter` 500, `growth` 2,500, `pro` 7,500 AI replies per month; counter, warnings at 80 and 100 percent, 10 percent grace, then a pause) and the operator CLI `plan-usage`, `plan-set`, `plan-reset`, `plan-extend` in `backend/app/plans/cli.py` | **No payment** (no iyzico or PayTR code), no self-service upgrade, no limits other than AI replies (seats, posts, retention, the 100-reply trial cap); plan `status` is stored but changes nothing |

**Consequence.** A self-service public launch needs: P-10 turned on after its open items; P-11 payment and a settled price (which also unblocks showing the price on the landing page); and this phase's live items (V-12, real-site import trials). Assisted pilots do not depend on P-10 or P-11.

---

## 9. Open questions for the owner and working-tree note

1. What is the package price and are there tier names (OQ-06)? Until then the landing page shows none.
2. Can a TRY invoice be issued (OQ-05)? If not, drop the invoice card.
3. Is the daily website-import limit of 10 per workspace acceptable?
4. Should a re-import supersede pending candidates whose key no longer appears?
5. Is the Instagram `caption` field readable with the current Instagram Login grant? V-12 answers it.
6. **Working tree.** Everything from Sessions 01 to 03 is uncommitted on `main` (about 52 modified tracked files plus the new files listed in the session reports). Suggested next step: review, then commit in logical pieces (profile import, website import and fetcher, landing, docs) before the next phase.
