# Feature Phase 4, Session 03: local package on the landing page and phase close-out (D-06)

- **Status:** done offline (2026-11-17). Landing section built; phase closed; stopped for review. Nothing committed, pushed or deployed.
- **Baseline commit:** `e2fcc23` (`main`). **Migration head:** `0061`. Session 03 itself adds no backend code and no migration; the close-out made one small backend fix (below).
- **Who wrote what:** the landing section was written directly by Sonnet 5.5 (see [s03-landing-report.md](s03-landing-report.md), which holds the full claim-by-claim evidence table). The close-out (all checks, one small fix, reports, roadmap) was done by a close-out agent (Sonnet 5.5). Codex was not used in this session.

## 1. Landing section (D-06), summary

Full detail and the 14-row claim evidence table: [s03-landing-report.md](s03-landing-report.md).

- New section `#paket` ("Yerel paket" / "Local package") in `landing/src/App.tsx` (`LocalPackage`), between Trust and the FAQ, with a nav link. Copy in `landing/src/copy.ts` (Turkish first, English second; the `Copy` type forces parity).
- Five cards: Turkish interface and replies; KVKK documents (prepared, "draft, awaiting legal review", not "ready"); invoice and pilot terms (marked "Planned": no invoicing process exists in code, entity per OQ-05 open); in-person (around Burdur and Antalya) or video setup of about 30 minutes; the verified-price guarantee (provenance, not truth; "is not sent", not "can never happen"). A sixth cell holds the optional price and the "apply for the pilot" button.
- `landing/src/config.ts` (new): `VITE_PACKAGE_PRICE` (shown verbatim; empty means no price and no price label) and `VITE_APP_URL` (an `https://` origin; the privacy, terms and data-deletion links are drawn only when it is set, because those pages are routes of the web app, not of the landing site).
- **Pricing gate.** The brief says to ask the user for the settled TRY price. Pricing is not settled (user decision), so no amount appears anywhere in either language and the price block is hidden behind the empty config value.
- Every claim was checked against the code, `docs/legal/` and the pilot checklist; claims the code cannot support today were softened (invoice) or omitted (lawyer-approved documents, any price, WhatsApp owner control, comment replies, live model behaviour).

## 2. Close-out checks

All commands run on 2026-11-17 against the merged, uncommitted tree (Sessions 01 to 03).

### Backend (from `backend/`)

| Check | Result |
|---|---|
| `uv run ruff check .` | pass |
| `uv run ruff format --check .` | pass (817 files) |
| `uv run mypy app` | pass (432 files) |
| `uv run lint-imports` | pass (24 contracts kept, 0 broken) |
| `uv run alembic upgrade head`, `downgrade -1`, `upgrade head` (shard DB `agentnest_p4close_d_test`, `DATABASE_URL` only for those commands) | pass: `0061` -> `0060` -> `0061`; single head `0061`; `fact_candidates.source_detail` present |
| `python -m evals run --all` (fake provider) | interpret_command 84/84, extract_fact_candidates 12/12, draft_reply 86/86, draft_content 26/26; 0 hard failures |
| `frontend/openapi.json` against a fresh `export-openapi` (`INSTAGRAM_ENABLED_PROVIDERS=mock`) | identical after one fix (an out-of-date endpoint description, see section 3); `schema.d.ts` patched to match |

Full pytest suite, four parallel shards on four empty databases (`agentnest_p4close_{a,b,c,d}_test`, dropped afterwards), always with `PYTHONUTF8=1 LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN=` and `WEBSITE_IMPORT_FETCHER=fake`, `-p no:cacheprovider -q`:

| Shard | Paths | `DEMO_TOOLS_ENABLED` | First run | After attribution |
|---|---|---|---|---|
| a | `tests/unit tests/contract tests/isolation tests/security` | unset | 2405 passed, 18 skipped, 20 failed | all 20 pass when re-run alone (see below) |
| b | `tests/integration/{inbox,reporting,activity,ai,demo}` | true | 703 passed | 703 passed |
| c | `tests/integration/{content,agent,commands}` | true | 853 passed, 1 failed | 854 passed (the failure passes alone) |
| d | `tests/integration/{identity,knowledge,approvals,notifications,operations,plans,policy,retention,waitlist,integrations,jobs}`, `tests/integration/test_*.py`, `tests/e2e` | true | 745 passed, 3 failed | 2 known environment failures remain, 1 explained and passing |
| **Total** | | | 4706 passed, 18 skipped, 24 failed | **2 failures remain: both known environment failures at baseline; 18 skipped are the explicit live probes** |

Failure attribution (none caused by this phase's behaviour):

1. **`WEBSITE_IMPORT_FETCHER=fake` set in the test environment (artifact of the check setup), 16 tests in shard a plus one in shard d.** Production settings refuse a fake fetcher by design (`WEBSITE_IMPORT_FETCHER must not be fake in production`), so every test that builds a production `Settings` fails while the variable is exported: `test_deployment_workflow_and_rollback.py::test_cli_migration_status_head_only_and_check_config`, 14 tests in `tests/unit/core/test_settings_safety.py`, `tests/integration/test_seed.py::test_seed_refuses_to_run_in_production` and, in shard a, `tests/security/test_security_audit.py::test_automated_security_scanner_runs_and_passes_all_checks` (the scanner builds production settings). Re-run **without** the variable: all pass (105 passed in those five files). The variable is not needed for the suite: `auto` already selects the fake fetcher when `LLM_PROVIDER=fake`. Re-running `test_seed.py` with the variable set reproduces the failure. Note for future checks: do not export `WEBSITE_IMPORT_FETCHER=fake` for the full suite.
2. **`tests/isolation/test_phase6_isolation.py::test_the_dev_job_listing_of_a_never_shows_the_jobs_of_b` and `tests/isolation/test_publishing_isolation.py::test_the_simulator_listing_of_a_never_shows_what_b_published`**: need `DEMO_TOOLS_ENABLED=true` (dev routes return 404 otherwise, by configuration). Shard a ran without it per the brief; both pass with it (10 passed in the two files).
3. **`tests/unit/integrations/web/test_html_text.py::test_deeply_nested_page_is_bounded`** (a real, small defect, fixed): the test allows 5 seconds for 100,000 unclosed `<div>` and took 5.3 s under four-way load (4.8 s even alone, so it passed by luck). Cause: the HTML parser rescanned the whole (capped, 256 deep) element stack for `head` and `title` on every start tag, end tag and text event, about 25 million steps on a hostile page. Fixed in `backend/app/integrations/web/html_text.py`: each stack entry now carries inherited "inside head" and "inside title" flags, so there is no scan. Same output; now **0.8 s**. All 126 tests in `tests/unit/integrations/web` and 318 tests in `tests/unit/knowledge` plus the two import integration files pass after the change; ruff, format and mypy re-run clean.
4. **`tests/security/test_invite_secrets.py::test_the_invite_token_is_never_logged_audited_notified_or_queued`**: order-dependent (log capture) in the long shard, passes alone (documented in Feature Phase 2 and 3). Passed in the re-run above.
5. **`tests/integration/agent/test_dm_transcript.py::test_an_automatic_dm_delegation_still_asks_when_a_voice_note_is_in_the_conversation[True]`** (shard c, one extra simulated message under load): passes when re-run alone (2 passed). The file is untouched by this phase; treated as a load-dependent flake.
6. **`tests/integration/test_health_and_errors.py::test_cors_allows_only_the_frontend_origin`**: known baseline failure (the repo-root `.env` `FRONTEND_ORIGIN`). Not fixed.
7. **`tests/integration/identity/test_members_and_invites.py::test_owner_creates_an_invite_with_a_one_time_link`**: known baseline failure listed in the Feature Phase 2 and 3 close-outs. The invite link starts with the `.env` public URL (a `trycloudflare.com` address) instead of `http://localhost:8000`. No file under `identity/` or the invite code is changed in this phase's diff. Not fixed. It was not re-run on a baseline worktree because the cause is visible in the assertion and the code is untouched.

### Frontend (PowerShell, `frontend/`)

| Command | Result |
|---|---|
| `npm.cmd run lint` | pass |
| `npm.cmd run typecheck` | pass |
| `npm.cmd test` | pass: 64 files, 913 tests |
| `npm.cmd run i18n:check` | pass: 2762 keys, 2021 literal `t()` calls verified |
| `npm.cmd run build` | pass |

### Landing (PowerShell, `landing/`; no lint or test scripts exist)

| Command | Result |
|---|---|
| `npm.cmd run typecheck` | pass |
| `npm.cmd run build` | pass (`tsc -b && vite build`) |

Not run: Playwright (`npm run e2e`), anything against Meta, a real model, a real Instagram account, real websites, or a device.

## 3. Changes made during close-out

- `backend/app/integrations/web/html_text.py`: parser performance fix (failure 3 above).
- `frontend/openapi.json` and `frontend/src/api/schema.d.ts`: the description of `POST .../knowledge/imports/instagram` still carried the Session 01 wording ("Reusable trigger for Session 02's combined onboarding step ...") while the route docstring says "Import profile suggestions without verifying facts."; both patched so the checked-in file equals a fresh export.
- Docs: this report, the [phase summary](../phase-summaries/features-phase-4-summary.md), the roadmap row, and the status line of [sessions.md](sessions.md).

## 4. P-10 and P-11 (self-service launch depends on them)

Neither is part of this phase; their state was read from [pre-launch-problems.md](../../review/pre-launch-problems.md) and checked against the code.

- **P-10 self-service signup: done behind a flag.** `POST /auth/register`, `/auth/resend-verification`, `/auth/verify-email` exist in `backend/app/identity/router.py` and `signup.py`, gated by `SIGNUP_ENABLED` (default off), with email verification, throttling and a stored terms version (`identity/legal.py`). Still open: legal review of the terms and privacy text (placeholders) and a `TERMS_VERSION` bump, `SMTP_URL` and `MAIL_FROM` before the flag goes on in production, no purge of unverified accounts, no CAPTCHA.
- **P-11 plans and quotas: partial.** `backend/app/plans/` (tiers `starter` 500, `growth` 2,500, `pro` 7,500 AI replies per month, a concurrency-safe counter, warnings at 80 and 100 percent, grace then pause) and the operator CLI `plan-usage`, `plan-set`, `plan-reset`, `plan-extend` exist. There is no payment (iyzico or PayTR; nothing in `backend/app`), no self-service upgrade, and no limits other than AI replies (seats, posts, retention, the 100-reply trial cap); plan `status` is stored but changes nothing.
- Self-service launch therefore needs: this phase's live items (section 5 of the summary), P-10's open items, and P-11 payment plus a settled price. Assisted pilots do not.

## 5. Open items for the owner

1. Settle the TRY price and tier names (OQ-06), then set `VITE_PACKAGE_PRICE` in the landing service and rebuild.
2. Set `VITE_APP_URL` at deploy so the legal links render.
3. Decide on the invoice card if a TRY invoice cannot be issued (entity, OQ-05).
4. Update the KVKK card when counsel signs off.
5. V-12 and the real-site import trials (see the summary).
6. Local scratch: the git-ignored `.tmp/` folder is not part of the diff (`backend/.pytest-tmp/` from Session 01 no longer exists).
