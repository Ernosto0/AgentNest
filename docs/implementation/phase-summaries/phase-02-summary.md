# Phase 2 summary: Business knowledge

**Status:** implemented and verified locally; **waiting for review** (per [roadmap.md §5](../roadmap.md)). Phase 3 has not been started.
**Scope reference:** [phase-02-business-knowledge.md](../phases/phase-02-business-knowledge.md). All tasks P2-01 … P2-11 are done.
**Branch:** `phase-02-business-knowledge`, created from `phase-01-foundation` (see deviation D1 and question Q1). Nothing is committed yet.

## 1. What changed

| Area | Contents |
|---|---|
| Value types (P2-01) | `knowledge/values.py`: Pydantic model per `value_type` (money, weekly hours, text, localized text, phone, email, address, URL, boolean, enum, string list), canonical form (`"6000.00"`, sorted hours), `validate_value`, `values_equal`. `parsing.py`: `parse_money` (tr/en, ambiguity → `ParseAmbiguity` with alternatives), TR phone → E.164, weekly-hours editor model, `tr_casefold`/`normalize_for_match`. `formatting.py`: `6.000 ₺ / ay`, `€1,200`, `TRY 6,000`, grouped weekly hours (`Pzt–Cum 07:00–23:00, Cmt …, Paz kapalı · 29 Eki: kapalı`) |
| Templates (P2-02) | `knowledge/templates/{common,gym,pilates_studio}.yaml` + `templates.py`, validated when the app starts |
| Schema (P2-03) | Migration `0002`: `business_facts`, `fact_versions` (with `valid_from/valid_until`), `fact_candidates`; composite FKs, partial unique live-key index, CHECKs |
| FactService (P2-04) | `service.py`: `create_fact`, `update_fact`, `verify_fact`, `archive_fact`, `restore_fact`, `usable_facts`, read models, `insert_trusted_fact` (seed). `transitions.py`: the only place fact/candidate states change. `usability.py`: usable/state rules on the workspace-local date |
| Candidates (P2-05) | `candidates.py`: relation (`new`/`same`/`discrepancy`/`contest`), propose, recompute after every fact change; `service.accept_candidate` / `reject_candidate` |
| Readiness (P2-06) | `readiness.py`: pure `compute_readiness` + `readiness()`; `settings.automation_reviewed_at` via workspace PATCH |
| API (P2-07) | `knowledge/router.py` + `schemas.py`: 11 routes under `/workspaces/{ws}` (facts, template, versions, candidates, readiness) |
| Seed (P2-08) | `demo/facts_seed.py` + `data/facts_{golkent_fitness,harbor_pilates}.yaml`: 16 facts + 1 discrepancy candidate per studio; idempotent per key; also runs for workspaces that already exist |
| Knowledge UI (P2-09) | `features/knowledge/*`: overview, category screen, fact card + status chip, editors for all 11 types, verify, archive/restore, history sheet, suggestions, readiness checklist; Home `ReadinessCard`; `BottomSheet` component |
| Wizard (P2-10) | `features/workspaces/CreateWorkspaceWizard.tsx` (`/workspaces/new`, linked from the picker and More) |
| Shared | `shared/money-cases.json` (40 money vectors run by pytest **and** vitest); `core/pagination.py` (`Page` moved out of identity); error codes `VERSION_CONFLICT`, `FACT_VERSION_CONFLICT` (tr/en, backend + frontend); import-linter contracts for `knowledge` |
| Docs | Updated in the same change: `data-model`, `api-design`, `business-knowledge`, `workflows` (§A readiness), `component-design`, `observability`, `local-development` |

## 2. Test results

| Suite | Result |
|---|---|
| Backend `uv run pytest` | **444 passed** (was 240): 144 knowledge unit tests, 58 knowledge integration tests (API, candidates, readiness, seed, DB constraints), isolation (8, now with real fact/candidate IDs) |
| Backend `ruff check`, `ruff format --check`, `mypy app` (strict), `lint-imports` | clean; 5 import contracts kept |
| Frontend `npm test` | **170 passed** (was 47) |
| Frontend `eslint`, `tsc -b`, `npm run i18n:check`, `npm run build` | clean (308 catalog keys, 174 literal `t()` calls verified; dynamic keys pinned by `catalog.test.ts`) |
| OpenAPI drift (re-export + regenerate vs committed) | identical |
| Playwright (`CI`-like run of both specs, 3 projects) | **33 passed** = (6 Phase 1 + 5 scenario A) × `mobile-webkit`, `mobile-chromium`, `desktop-chromium` |

Mutation checks (each reverted afterwards; each made a named test fail): removing the optimistic-concurrency check (`test_stale_expected_version_is_a_conflict_and_changes_nothing`); letting staff verify (`test_staff_cannot_verify`); ignoring a pending `contest` in `is_usable` (`test_only_verified_uncontested_facts_in_their_window_are_usable`); removing the `workspace_id` filter from `get_fact` (`test_b_resources_are_not_found_through_a_workspace_url`; the composite FK additionally refused the cross-workspace write).

## 3. Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| AC-A1 | Home shows workspace, readiness status and the SİMÜLASYON banner (390×844) | e2e `A1`; vitest `Home readiness card …` |
| AC-A2 | Facts grouped by category with status; verified facts show source and last-verified date | `test_facts_api.py::test_owner_creates_a_verified_fact_…`, `::test_listing_filters_and_template_checklist`; e2e `A2`; vitest `lists facts with status, source and date …` |
| AC-A3 | Verify → `verified`, new `fact_versions` row, audit `fact.verified` | `test_facts_api.py::test_verifying_an_unverified_fact`; e2e `A3` |
| AC-A4 | Staff verify → 403, nothing changes; staff edit → candidate | `test_facts_api.py::test_staff_cannot_verify`, `::test_staff_cannot_archive_or_restore_either`; `test_candidates_api.py::test_a_staff_edit_becomes_a_contest_candidate_…`, `::test_staff_cannot_resolve_candidates`; e2e `A5` |
| AC-A5 | Readiness `ready` / `ready_for_drafts` / `not_ready`, missing items listed | `tests/unit/knowledge/test_readiness.py` (all levels, with `account_connected=True` for `ready`); `test_usable_readiness_settings.py::test_readiness_api_…` |
| AC-X1 (new routes) | Foreign IDs → 404, listings never leak | `tests/isolation/test_workspace_isolation.py` (enumerates the new routes automatically, with B's real `fact_id`/`candidate_id`), `test_knowledge_isolation.py` (B's sub-resources through A's own URL) |
| One version row + one audit entry per change; history untouched (INV-12, INV-17) | `test_update_creates_exactly_one_version_and_one_audit_entry`, `test_saving_the_same_value_changes_nothing`, `tests/unit/knowledge/test_history_is_append_only.py` |
| Seeded demo gym is `ready_for_drafts` | `test_seed_facts.py::test_seeded_workspaces_are_ready_for_drafts` (both studios) |
| All new UI strings in tr and en; money in locale format | `npm run i18n:check`, `catalog.test.ts`; `test_values_and_formatting.py` (formatting), `money.test.ts` |
| Time is workspace-local (INV-19) | `test_a_promotion_ends_at_the_end_of_the_workspace_local_day`, `test_today_is_the_workspace_local_date_not_the_utc_date` |

## 4. Demo steps (verified in the e2e scenario)

1. `docker compose up -d postgres`; `cd backend`; `uv run alembic upgrade head`; `uv run python -m app.cli seed --reset`; start API and `npm run dev`.
2. Log in as `owner@demo.local` (tr), open *Gölkent Fitness & Pilates*: Home shows the SİMÜLASYON banner and the readiness card *Taslaklar için hazır* with the open steps.
3. More → İşletme bilgileri → Fiyatlar: the monthly price `6.000 ₺ / ay` is *Doğrulandı* with source and date; the student price is *Doğrulanmamış* → **Doğrula** → **Geçmiş** shows versions 1 and 2.
4. İşletme bilgileri → Öneriler: "Yapıştırdığınız metin 5.500 ₺ / ay diyor, ama doğrulanmış değeriniz 6.000 ₺ / ay." → **Mevcut değeri koru**. Home lists what is left.
5. Log in as `staff@demo.local`, Fiyatlar → **Değişiklik öner** → 7500 → the fact shows *İtiraz var*; as the owner the suggestion names "Demo Personel" → **7.500 ₺ / ay değerini kullan** → version 2, usable again.
6. More → Çalışma alanı oluştur: the wizard (name → category → market/language/time zone/currency), landing on the checklist.

## 5. Deviations from the docs (and why)

| # | Deviation | Reason / where recorded |
|---|---|---|
| D1 | **Branch base.** The agreed plan was "merge Phase 1 to `main` first, then branch". It was not merged when implementation was requested, so `phase-02-business-knowledge` was created from `phase-01-foundation` (stacked). Nothing was merged | See Q1. The branch rebases onto `main` without conflicts once Phase 1 is merged |
| D2 | `fact_versions` gets `valid_from/valid_until`, so a window edit is a versioned change | Decided with the owner of the project; `data-model.md` |
| D3 | Staff may propose only fixed template keys (no `custom.*`, no pattern keys, no validity window) | Decided with the owner of the project; a candidate carries no label or window. `business-knowledge.md`, `api-design.md` |
| D4 | `automation_reviewed_at` is set through `settings: {automation_reviewed: true}`; the server stamps the time and writes `policy.reviewed` | A client-supplied timestamp would break "time comes from the Clock". Temporary until Phase 4. `api-design.md`, `data-model.md` |
| D5 | Extra modules: `transitions.py`, `usability.py`, `constants.py`; `candidates.py` holds proposal/recompute logic and `service.py` holds accept/reject (avoids an import cycle). `Page` moved to `core` | `state-machines.md` requires one transition function per entity; `component-design.md` |
| D6 | List endpoints return `{items, next_cursor: null}` (the docs show arrays); `POST/PATCH /facts` answer 201/200 with a fact or **202 with a candidate** (`kind` discriminates); verify/archive/restore require `expected_version` | Consistency with Phase 1 envelope and with the docs' 202 rule. `api-design.md` |
| D7 | `FactOut` adds `state`, `source_type`, `last_verified_by_name`; `display` follows the **user's** UI locale | AC-A2 needs the source; the workspace locale is the wrong one for display. `api-design.md` |
| D8 | Readiness uses **usable** facts for the draft requirements too (docs said "verified"); `link` is structured (`target/category/key`), plus a `status` per requirement | A contested/expired fact must lower readiness. `workflows.md`, `api-design.md` |
| D9 | Template metadata: `required_group`, `required_when`, `key_pattern`; `pricing.student_monthly` added to both templates; ready-price per template (gym: monthly membership, Pilates: reformer 8 sessions) | The docs list conditions in prose only. `business-knowledge.md` |
| D10 | Relation against an **unverified** fact is `new`; relations are recomputed from the source tier after every fact change | Unspecified in the docs. `business-knowledge.md` §5 |
| D11 | Overnight hours ranges are rejected (`open < close`); `24:00` is allowed as a closing time | Limitation noted; multiple ranges per day are supported |
| D12 | Money shown with a plain space (`6.000 ₺`), assembled from Babel's number/symbol data rather than a CLDR currency pattern | Matches the docs exactly regardless of CLDR currency-spacing rules |
| D13 | Fact audit entries do not set `is_simulated` | INV-09 derives it from a mock provider; facts are not produced by one |
| D14 | `shared/money-cases.json` at the repository root is read by both test suites | One source for both parsers |
| D15 | E2E re-seeds the demo data before every test (`reseedDemo()` in `e2e/helpers.ts`) | Tests change facts and run in three projects |
| D16 | Knowledge strings live in `knowledge.json` and are merged into the single `common` namespace | Keeps `t("knowledge.…")` keys and the existing checker |
| D17 | `seed` now also adds facts to workspaces that already exist; the CLI prints the number added | A Phase 1 database must receive the facts without `--reset` |

## 6. Known limitations

- **No accessibility (axe) tests yet** (listed in the Phase 1 summary): not part of the phase document; offered for review.
- CI has still not run on GitHub; the new scenario reuses the Phase 1 e2e job. Real iOS Safari and the LAN phone test are still pending.
- `fact_views` issues one version query per fact (N+1, ~20 facts); fine at this size, replace with one join when workspaces grow.
- No cursor pagination (bounded lists, `next_cursor` is always null). Overlapping opening hours are rejected by the server and shown as a generic message (the editor does not mark the offending row).
- Changing a workspace's business category or currency later does not migrate its facts or template.
- `FACT_NOT_USABLE` and `FACT_CHANGED_MEANWHILE` are not added yet (Phase 3 uses them). Unverified facts can only arise from the seed and from *restore* (owners create verified facts).
- Optimistic concurrency is tested through stale versions, not with two truly concurrent transactions.

## 7. Questions for review

- **Q1:** Phase 1 was not merged to `main` (D1). Merge it, or keep stacking and merge both branches together? Q1–Q4 from the Phase 1 summary are also still open.
- **Q2:** Please confirm the defaults chosen for gaps in the docs: D8 (usable, not just verified, for readiness), D10 (relation vs unverified facts; staff contest stays `contest` after the owner edits), and D9 (which price is required for `ready` per template).
- **Q3:** Should an owner be able to save a value as *unverified* (a draft) from the UI? Today only the seed and *restore* create unverified facts, so *Doğrula* is rarely needed for new data.
- **Q4:** Add axe accessibility tests for the knowledge screens now, or in a hardening step?
- **Q5:** Archive/restore require `knowledge.verify`; staff cannot propose archiving. Is that the intended rule?
