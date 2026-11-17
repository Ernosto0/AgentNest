# Session 04 report: template images in the content flow (F-07, part 2)

**Status:** Implemented offline; backend pytest finished with 2 failures that match known Session 08 failures (section 4). Evals not re-run by the reviewer. Nothing is committed. Nothing live is involved.
**Baseline:** `06c5d64` (`main`) plus Session 03's uncommitted work. **Migration head:** `0060` (`20261117_0060_price_card_command.py`, parent `0058`; extends the `ck_approvals_action` CHECK with `command.make_price_card`). The orchestrator re-chains at merge.

## 1. Who built what
- **Codex (gpt-6.1-sol, medium)** built the whole backend (links, re-render, hours rows, command, job, migration, evals, docs, OpenAPI), then hit its usage limit (reset 7:41 PM) while running checks. No resume was attempted.
- **Reviewer (Claude) took over:** reviewed the backend diff (kept as is), ran ruff, format, mypy, lint-imports (all pass), and wrote the whole frontend (picker sheet, hooks, stale notice, entry points, command card, i18n, tests).

## 2. What was built
- Backend: `content/templates/{link,rerender,staging,jobs}.py`; fact references of a rendered image are merged into the item's `fact_references` on create, edit, submit, re-approve, generation and agent paths (the render's recorded version wins, so a stale image stays visible); `TEMPLATE_IMAGE_STALE` blocks submit and re-approve; `ContentItemOut.template_image`; `POST /content-items/{id}/template-image/rerender` (new version, draft again, approval cancelled, never auto-approved or published; audit `content.template_image_rerendered`); structured hours rows (comma in an exception note); command `content.make_price_card` (model names a fact key, never a price; confirmation card; executor stages a draft plus a `render_template_image` job in the decision transaction, rendering and storage run later outside any transaction); interpret_command prompt `v3`, fake grammar, `evals/interpret_command/price_card.yaml`.
- Frontend: `TemplateImageSheet` (template and format pickers, verified-fact selects, announcement fields, debounced live preview, phone Fields/Preview toggle), entry points in the editor, the content composer, the Today story prompt and the Today header; `TemplateImageNotice` (badge, out-of-date warning, "re-render with the new value", needs-approval-again text); re-approve hidden while the image is stale; command confirmation summary and result messages; TR and EN strings.

## 3. Files
Backend and docs: see `git status` (new: `app/content/templates/{link,rerender,staging,jobs}.py`, `app/commands/price_card.py`, `app/commands/executors/content_make_price_card.py`, `app/ai/prompts/interpret_command/v3.md`, migration 0060, evals yaml, new tests under `tests/integration/{content,commands}`, `tests/isolation`, `tests/unit/ai`). Frontend new: `features/content/{TemplateImageSheet,TemplateImageNotice,templateHooks,templateImage.test}.ts(x)`, `features/approvals/{PriceCardSummary,priceCard.test}.tsx`; changed: editor, composer, content page, detail page, on-hold actions, Today (HomePage, UpcomingPanel, WeekCalendar), commands card and messages, approvals sheet, i18n (ai, common, content), test fixtures.

## 4. Checks (test DB `agentnest_p3s03_test`)
| Check | Result |
|---|---|
| ruff check, ruff format --check, mypy app (420 files), lint-imports | pass, 791 files formatted, 23 contracts kept |
| backend pytest `tests/unit tests/isolation tests/security tests/contract tests/integration/{content,commands,knowledge,approvals}` | 2,813 passed, 13 skipped, 2 failed: `test_cli_migration_status_head_only_and_check_config` (fails only with `DEMO_TOOLS_ENABLED=true`) and `test_invite_secrets` (order-dependent). Both are the known failures from the Feature Phase 2 Session 08 report; not re-confirmed at HEAD here |
| evals `--all`, migration up/down/up | Codex reported the migration round trip passed; evals not re-run by the reviewer |
| frontend lint, typecheck, i18n:check (2,706 keys), build | pass |
| frontend `npm.cmd test` | 871 passed (61 files); baseline 859 plus 12 new |

## 5. Open points
- Confirm the two known failures at HEAD; run the evals.
- The command draft shows no image until the render job runs (no polling on the draft page).
- Price disclosure policy (`policy.price_disclosure`) is not applied to price cards (same as Session 03).
- Merge watch: `app/core/errors.py`, i18n catalogs, `app/activity/groups.py`, `ai.json`, `schema.d.ts`, `openapi.json`, `approvals/{models,schemas}.py`, migration number.
