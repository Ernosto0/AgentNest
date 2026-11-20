# Feature Phase 3 merge report

**Date:** 2026-11-17. **Baseline:** `main` at `06c5d64`. **Nothing is committed.**
**Scope:** applying Track A (Sessions 01 and 02, worktree `pivoris-p3/s01`) and Track B (Sessions 03 and 04, worktree `pivoris-p3/s03`) to the main tree, merge review, and full verification. Per-session details are in `s01-report.md` to `s04-report.md`; the phase summary is [features-phase-3-summary.md](../phase-summaries/features-phase-3-summary.md).

## 1. What conflicted and how it was resolved

Track A applied cleanly; Track B was then applied on top. The orchestrator resolved three textual conflicts by hand:

| File | Resolution |
|---|---|
| `docs/architecture/observability.md` | Both tracks' rows kept: a "Template images" audit row, `media.template_rendered` and `brand.updated` in the Content row, `account.comment_automation_changed` in Operations & accounts, `COMMENT_AUTOMATION_OFF` in the inbound ignore reasons, and the two metadata paragraphs at the end. |
| `docs/product/mvp-scope.md` | Track A subsection kept; a "Feature Phase 3, Track B" subsection added before section 4; the Deferred row "Real-account comment automation..." removed and "Story/post image generation" renamed to "Story/post AI image generation". |
| `frontend/src/features/settings/hooks.ts` | Both tracks' hooks kept (`useBrand`, `useSaveBrand` appended to Track A's comment-automation hook). |

Migrations were re-chained by the orchestrator: `0057 -> 0058 (template_images, S03) -> 0059 (comment_automation, S02, parent changed from 0057) -> 0060 (price_card_command, S04, parent changed from 0058)`. Parent revisions inside the files were rewritten; content is unchanged.

## 2. Semantic merge review (this session)

Files edited by both tracks were checked for duplicated keys, lost entries and inconsistent text. Results:

| Area | Check | Result |
|---|---|---|
| `backend/app/core/errors.py` | Track B adds three `TEMPLATE_*` codes; Track A adds none (uses `CONFLICT_STATE` with reasons `real_account_required`, `comments_permission_missing`) | no problem |
| `backend/app/core/i18n/{en,tr}.json` | Parsed with duplicate-key detection: no duplicates; 504 keys in each language, identical key sets | no problem |
| Frontend locales `common`, `content`, `agent`, `inbox`, `ai` (en and tr) | No duplicate keys; en and tr key sets identical (792, 339, 258, 308, 212); `npm run i18n:check` passes | no problem |
| `backend/app/activity/{classify,groups}.py` | `account.comment_automation_changed` (Track A) and `content.template_image_*`, `media.template_rendered`, `brand.updated` (Track B) both present, each once; Activity strings in both languages | no problem |
| `backend/app/core/db.py`, `tests/unit/core/test_rls_policies.py` | One new tenant table (`workspace_brand_settings`, Track B); Track A adds a column only. `CATEGORY_C_TABLES` has 63 entries and the test asserts 63 | no problem |
| `ck_approvals_action` in `0060` | The `OLD` tuple (14 actions) equals the set at 0057/0059 (0058 and 0059 do not touch it), `NEW` adds `command.make_price_card` (15), and equals `APPROVAL_ACTIONS` in `approvals/models.py` as a set | no problem |
| `0059` `ck_inbound_events_ignore_reason` | `OLD` (4 reasons) plus `COMMENT_AUTOMATION_OFF` equals `IGNORE_REASONS` in `inbox/models.py` | no problem |
| `frontend/openapi.json` and `src/api/schema.d.ts` | A fresh `export-openapi` differed in one place: the comment `schema` field (`synthetic-comment-v1` only, versus `["synthetic-comment-v1", "provider-comment-v1"]` after Track A). CI regenerates both files and fails on a diff, so the checked-in copy would have failed CI. **Fixed:** `frontend/openapi.json` replaced by the fresh export and `schema.d.ts` regenerated (`npm run gen:api`); the only change in `schema.d.ts` is `schema: "synthetic-comment-v1" | "provider-comment-v1"` | fixed |
| `frontend/src/test/contentFixtures.ts` | Both additions present once (`template_image: null`, `comment_automation_enabled: false`) | no problem |
| `docs/product/mvp-scope.md` | Track A subsection said "Session 01 is done; Session 02 builds the real path", and a stray "Session 02 implementation" paragraph sat after the section 5 guardrails. **Fixed:** the intro now says both sessions are implemented and verified offline with live results pending, and the paragraph moved under the Track A gate. The Track B row correctly describes what was delivered | fixed |
| `docs/architecture/data-model.md` | Session 04 note said migration 0060 has parent `0058` | **fixed** to `0059` |
| `docs/operations/account-agent-rollout.md` | Step 1 said "migration 0059 (parent 0057; merge orchestrator re-chains concurrent 0058)" | **fixed** to "parent 0058" |
| `docs/architecture/api-design.md`, `docs/operations/environment-variables.md`, `docs/architecture/security-and-privacy.md` | Rows and sections of the two tracks are disjoint, none duplicated | no problem |
| Other files edited by both (`api/router.py`, `core/db.py`, `pyproject.toml`) | Router registers both tracks' routers once each; no duplicates | no problem |

Status lines updated for close-out: `docs/implementation/roadmap.md` (Feature Phase 3 row) and the status line of `sessions.md`.

## 3. Migration round trip

Single head: `uv run alembic heads` shows `0060 (head)`. On shard DB `pivoris_p3m_d_test` (with `DATABASE_URL` pointed at it): `upgrade head` (current `0060`), `downgrade 0057` (current `0057`), `upgrade head` (current `0060`). All succeeded. The test fixtures also run `alembic upgrade head` on a fresh schema in every shard.

## 4. Verification

Environment: `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN= OPENAI_API_KEY= PYTHONUTF8=1 DEMO_TOOLS_ENABLED=true`. The whole backend suite ran as four parallel shards on four empty databases (`pivoris_p3m_{a,b,c,d}_test`, dropped afterwards). The shards shared one Postgres container and were slow (about 80 to 90 minutes for the integration shards, dominated by per-test `TRUNCATE` fsyncs), not hung.

| Check | Result |
|---|---|
| `uv run alembic heads` | single head `0060` |
| Migration `upgrade head`, `downgrade 0057`, `upgrade head` (shard DB) | pass (`0060`, `0057`, `0060`) |
| `ruff check .`, `ruff format --check .` | pass (799 files formatted) |
| `mypy app` | pass (422 source files) |
| `lint-imports` | 23 contracts kept, 0 broken |
| (a) `tests/unit tests/isolation tests/security tests/contract` | 2274 passed, 18 skipped, 2 failed (both known, see below) |
| (b) `tests/integration/{agent,commands,ai,approvals,integrations}` and `tests/integration/test_*.py` | 722 passed, 1 failed (`test_cors_allows_only_the_frontend_origin`, known) |
| (c) `tests/integration/{inbox,activity,demo,identity}` | 615 passed, 1 failed (`test_owner_creates_an_invite_with_a_one_time_link`, known) |
| (d) `tests/integration/{content,knowledge,jobs,notifications,operations,plans,policy,reporting,retention,waitlist}` | 924 passed |
| Total backend | 4535 passed, 18 skipped, 4 failed (all classified below; no `tests/e2e` run) |
| Evals, fake provider (`python -m evals run --all`) | interpret_command 84/84 (77 before plus 7 new price-card cases), extract_fact_candidates 12/12, draft_reply 86/86, draft_content 26/26; 0 hard failures |
| Frontend `npm.cmd run lint`, `typecheck`, `i18n:check`, `build` | pass (2717 keys, 1989 literal `t()` calls verified) |
| Frontend `npm.cmd test` | 61 files, 885 tests passed (baseline 833 at Feature Phase 2 close, 859 after S03, 864 after S01) |
| `frontend/openapi.json` against a fresh `export-openapi`; `schema.d.ts` against `npm run gen:api` | identical after the merge fix (the file had drifted by one enum, see the merge report) |

**Failures, all environmental or known, none caused by this phase:**
- `tests/unit/core/test_deployment_workflow_and_rollback.py::test_cli_migration_status_head_only_and_check_config`: fails only while `DEMO_TOOLS_ENABLED=true` is exported (it conflicts with the test's `--production` config check). Re-run with the variable unset: 7 passed in that file.
- `tests/security/test_invite_secrets.py::test_the_invite_token_is_never_logged_audited_notified_or_queued`: fails in the long shard (log capture is order-dependent) and passes alone with `DEMO_TOOLS_ENABLED=true`: 2 passed in that file. Same as the Feature Phase 2 Session 08 report.
- `test_cors_allows_only_the_frontend_origin`: the local `.env` allows another frontend origin (no `access-control-allow-origin` for `http://localhost:5173`). Baseline failure listed in the Feature Phase 2 close-out.
- `test_owner_creates_an_invite_with_a_one_time_link`: the local `.env` public URL is a `trycloudflare.com` address, so the invite link starts with `https://...trycloudflare.com` instead of `http://localhost:8000`. Baseline failure listed in the Feature Phase 2 close-out.

Not run: Playwright (`npm run e2e`), `tests/e2e`, anything against Meta, a real model, or a device. The comment live probes are collected and reported as skipped (all 18 skipped tests are in `tests/contract`: 5 new comment probes, 10 Meta probes, 3 Telegram probes).
