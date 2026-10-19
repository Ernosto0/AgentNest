# Phase 3 summary: AI runtime, commands and approvals core

**Status:** implemented and verified locally; **waiting for review** (per [roadmap.md §5](../roadmap.md)). Phase 4 has not been started.
**Scope reference:** [phase-03-command-system.md](../phases/phase-03-command-system.md). All tasks P3-01 … P3-11 are done.
**Branch:** `phase-03-command-system`, created from `main` (Phase 2 was already committed there). **Nothing is committed yet.**
**Provider change requested for this phase:** the first real LLM adapter is **OpenAI**, not Anthropic (see D1 and Q1).

## 1. What changed

| Area | Contents |
|---|---|
| LLM integration (P3-01) | `integrations/llm`: `LLMProvider` protocol, typed errors, `FakeLLMProvider` (per-task rule-based implementations + `queue(task, output \| Exception)` scripting + call recording), `OpenAIProvider` (Responses API, strict structured outputs from the Pydantic model, `store=false`, no tools, error mapping, usage capture), `build_provider(settings)`. Config: `LLM_PROVIDER=fake\|openai`, `OPENAI_API_KEY`, `LLM_MODEL_DEFAULT=gpt-6-luna` and per-task overrides, `LLM_REASONING_EFFORT`, `LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY`, optional `LLM_PRICE_TABLE`. Production refuses `fake` and requires a key and a model. Import contracts: only `app.ai` imports the integration, only `openai_provider.py` imports the SDK |
| Task runner (P3-02) | `ai/runner.py`: budget (rolling 24 h per workspace), versioned prompt (`prompts/<task>/v1.md`), `agent_runs` row **committed before** the call, no transaction during the call, schema + post-validation, **one repair call**, error classification (`RetryableError` for transient errors, final outcomes for refusal/config/invalid), redacted input snapshots. `execute_task` is the DB-free core that evals reuse. `ai/injection.py` (tr/en heuristics, delimiter and `{{fact:` neutralisation), `ai/prompt.py`, `sweep_agent_runs` periodic job |
| Renderer and claim validator (P3-03) | `knowledge/render.py` (all-or-nothing placeholders with exact spans, `FACT_NOT_USABLE`), `knowledge/claims.py` (money, percent and discount words, times, dates, phones, e-mails, URLs, numbers above the small-number allow-list; length-preserving Turkish folding; byte-length helpers) |
| Approvals and notifications (P3-04) | `approvals/`: model, pure guards, state machine, service (`request`, `decide`, `cancel_for_subject`, `assert_executable`, lazy and swept expiry), callback registry, API (list, detail with `can_decide`, decision). `notifications/`: model, service with unread-dedup, list/read/read-all API |
| Command system (P3-05/06) | `commands/`: model, closed registry, pure resolver (catalog check, value re-parse, clarification), service, `interpret_command` job (context → model call outside any transaction → resolve), approval callback, executors (`query.fact` rendered, `query.pending_approvals`, basic `query.activity_summary`, `knowledge.update_fact`, `knowledge.update_brand_voice`, `unsupported`), API (submit, get, list, clarification, cancel), `expire_commands` job. Fake interpreter grammar for the demo phrases in tr and en |
| Impact framework (P3-07) | `fact_references` table, `ReferrerHandler` registry, `analyze_impact`, `apply_change`, `fact_changed` notification. Runs inside **every** fact update and archive (see D8). No real handler yet |
| Extraction (P3-08) | `extract_fact_candidates` task + prompt + fake; `knowledge/extraction.py` (start, status, deterministic plan/store, job); endpoints `POST/GET /knowledge/extractions` |
| Eval harness (P3-09) | `backend/evals`: loader, runner (real pipeline minus the DB), hard assertions on every case, JSON + Markdown reports, `python -m evals run`, fixture `demo_gym`, 45 `interpret_command` cases (18 tagged `forbidden`), 12 `extract_fact_candidates` cases (5 injection). CI step with the fake provider |
| Frontend (P3-10) | `features/commands` (command bar sticky above the tab bar, result/clarification/confirmation cards), `features/approvals` (list + generic detail sheet), `features/notifications` (bell), `knowledge/PasteExtractSheet`, "Çevrimdışı demo yapay zekâsı" strip from `/meta`, new `ai.json` catalogs (tr/en) and error texts |
| Schema | Migration `0003`: `agent_runs`, `approvals`, `notifications`, `owner_commands`, `fact_references`, and the FK `fact_candidates.agent_run_id → agent_runs` |
| Docs | Updated in the same change: ADR-009 (dated amendment) and every document that named Anthropic; `data-model`, `api-design`, `agent-runtime`, `workflows` §B, `observability`, `component-design`, `environment-variables`, `local-development`, `.env.example`, CI workflow |

## 2. Test results

| Suite | Result |
|---|---|
| Backend `uv run pytest` | **926 passed** (was 444 after Phase 2): LLM adapter and fake (stubbed transport), runner (budget, repair, retry classification, queued runs), injection and prompt helpers, renderer and claim validator (117 cases), approvals (guards, state machine, service, API, sweep, isolation), notifications, impact framework, commands (resolver, registry, state machine, update/clarify/expire/cancel flows, queries, unsupported, LLM failure paths, permissions), extraction (incl. race and injection cases), eval harness, strict-schema guard |
| Backend `ruff check`, `ruff format --check`, `mypy app` (strict), `lint-imports` | clean; 10 import contracts kept (5 new) |
| AI evals, fake provider (`python -m evals run --all --provider fake --strict`) | `interpret_command` 45/45, `extract_fact_candidates` 12/12, 0 hard failures |
| Frontend `npm test` | **206 passed** (was 170) |
| Frontend `eslint`, `tsc -b`, `npm run i18n:check` | clean (452 catalog keys, 240 literal `t()` calls verified; run-time keys pinned by `catalog.test.ts`) |
| OpenAPI drift | `frontend/openapi.json` and `src/api/schema.d.ts` regenerated from the code |
| Playwright (`npm run e2e`: Phase 1, Scenario A, new Scenario C) | **54 passed** = (5 + 5 + 7 tests) x `mobile-webkit`, `mobile-chromium`, `desktop-chromium` |

What the end-to-end and review loops caught (each fixed, with a regression test): the extraction run was reported finished before its candidates were stored (D11); a short excerpt inside an injected line slipped past the injection check (D12); an approval that had already expired answered "already decided" (D10); the strict-schema `oneOf`/`discriminator` problem (D4); two grammar bugs in the fake interpreter ("membership" matched "member"; "automatic replies").

Not run: any call to the real OpenAI API (no key here), so the manual check and the real-provider eval run are still open (see §6).

## 3. Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| AC-C1 | "Aylık üyelik artık 7.000 TL" → `awaiting_confirmation` with a `confirmation` approval, 6.000 ₺ → 7.000 ₺, impact counts | `tests/integration/commands/test_update_fact.py::test_ac_c1_…`; e2e `C1/C2` |
| AC-C2 | Confirmed: value 7000 TRY, version +1, previous version preserved, audit `fact.updated` references the command | `…::test_ac_c2_…` (version rows, `source_ref`, notification to the other verifier); e2e `C1/C2` (source "Sohbet komutu", history) |
| AC-C6 | Ambiguous price → `needs_clarification` with choices; nothing changes until a choice and a confirmation | `test_clarification_and_expiry.py::test_ac_c6_…` and the follow-ups; unit resolver tests; e2e `C6` |
| AC-C7 | Unconfirmed command expires after 30 minutes (frozen clock), nothing changes | `…::test_ac_c7_…` (lazy), `test_the_sweep_expires_…`, clarification expiry (job and lazy) |
| AC-A6 | Pasted "Aylık üyelik 6.000 TL" → candidate with amount and excerpt; no fact changed | `tests/integration/knowledge/test_extraction.py::test_ac_a6_…`; e2e `A6` |
| INV-04 | No command type can approve, publish or send; the decision API accepts only explicit approval ids and payload hashes | `tests/unit/commands/test_registry_and_transitions.py` (registry and output schema), `test_task_schemas.py` (unknown type → `unsupported`), `test_queries_failures_permissions.py::test_a_model_that_invents_an_approve_command…` and `::test_free_text_never_approves…`, `approvals/test_api.py::test_only_approve_and_reject_exist_as_decisions`, evals (18 forbidden cases, hard) |
| AC-A6/AC-C real provider | `LLM_PROVIDER=openai` with a key works for the demo commands | **Not run** (no key here; manual check, see §6) |
| `agent_runs` per execution | rows with tokens (real) and `is_fake` (fake) | `test_runner.py` (fake and a stubbed real provider), `test_every_execution_has_an_agent_run` |
| Approval decide cases | wrong hash, double decision, expired, foreign workspace, missing permission | `tests/integration/approvals/test_approvals.py`, `test_api.py`, `tests/isolation/test_approvals_isolation.py`, guard unit tests |
| Deferred | AC-C3–C5 (need referrers from Phases 4–5) | — |

## 4. Demo steps (verified in the e2e scenario)

1. `docker compose up -d postgres`; `cd backend`; `uv run alembic upgrade head`; `uv run python -m app.cli seed --reset`; start the API, **the worker** (`uv run python -m app.worker`, required for commands) and `npm run dev`.
2. Sign in as `owner@demo.local`, open *Gölkent Fitness & Pilates*. Home shows the command bar and the "Çevrimdışı demo yapay zekâsı" strip.
3. Type **"Aylık üyelik artık 7.000 TL"** → *Anlıyorum…* → confirmation card **6.000 ₺ / ay → 7.000 ₺ / ay** → **Onayla** → result card; Business information → Fiyatlar shows 7.000 ₺ with source *Sohbet komutu*; **Geçmiş** shows versions 1 and 2.
4. Type **"fiyat artık 7000"** → chips (Aylık üyelik / 3 aylık üyelik / Reformer 8 seans); pick one → confirmation; **Vazgeç** changes nothing.
5. Type **"gönderiyi şimdi yayınla"** → "Bunu henüz yapamıyorum" with *İçeriğe git*; there is nothing to approve.
6. Business information → **Metinden öneri al** → paste a bio with prices → suggestions with excerpts; no fact changes.
7. Approvals tab: a pending confirmation can be opened and decided there as well. Notification bell: the other owner/manager is told when a fact changes.
8. Evals: `uv run python -m evals run --all --provider fake --strict`.

## 5. Deviations from the docs (and why)

| # | Deviation | Reason / where recorded |
|---|---|---|
| D1 | **OpenAI instead of Anthropic**; adapter file `openai_provider.py` (not `openai.py`, which would shadow the SDK); default model `gpt-6-luna`; `httpx2` is now a runtime dependency (the SDK 3.x HTTP client); `LLM_REASONING_EFFORT` and `LLM_PRICE_TABLE` added | Requested. ADR-009 amended; all docs updated |
| D2 | `LLMProvider.generate_structured` has one optional extra argument, `context` (typed task input), ignored by real providers | The fake reads typed input instead of parsing prompts. ADR-009 amendment |
| D3 | `agent_runs.status` adds `queued` | The extraction endpoint stores the redacted pasted text on the run before the job starts (workflow A forbids the text in the job payload). `data-model.md` |
| D4 | `interpret_command` provider schema is `{interpretation: <union>}` with plain `anyOf` unions; `unsupported.reason` is a closed code and `suggestions` are chosen by code; `clarify` carries `intent`, `candidate_fact_keys`, `raw_value_text` (not `question`, `candidate_types`); `normalized_value` supports money, text and boolean; a `type` outside the registry becomes `unsupported` in the schema itself | Strict structured outputs need an object at the root and reject `oneOf`; model prose must never reach the owner. `agent-runtime.md` §3 |
| D5 | A stale fact at execution does **not** raise: the callback marks the command `failed (FACT_CHANGED_MEANWHILE)` and the approval stays `approved` | A raising callback rolls the decision back, which contradicts "fail the command". `workflows.md` §B; the code is not an HTTP error (`observability.md` §4) |
| D6 | Execution runs as the human who **decided** (not necessarily the requester); confirmations store `required_permission = knowledge.verify` and the requester may also decide | INV-04 and ADR-014; staff → `contest` candidate |
| D7 | No `approval.requested` notification for `confirmation` approvals; `knowledge.fact_changed` is not sent to the person who made the change | The requester is looking at the card |
| D8 | Impact propagation (`apply_change` + notification) runs inside every fact update and archive, not only inside commands | One behaviour for UI edits, accepted candidates and commands. `workflows.md` §B step 3.4 |
| D9 | `knowledge.service.apply_update` (non-committing) is the core of `update_fact`; `fact.updated` audit metadata includes `source_ref` | The approval callback owns the transaction; AC-C2 needs the command reference |
| D10 | The decision requires the payload hash for **reject** as well as approve; an approval that already expired answers `APPROVAL_EXPIRED` (not `…ALREADY_DECIDED`) | ADR-014 §2 lists the guards for every decision; consistent message to the user |
| D11 | The extraction run is reported `running` until its candidates are stored (`stored_at` in the run snapshot) | The runner marks the run succeeded one step earlier; found by the e2e run (UI saw "nothing found") |
| D12 | Extraction accepts fixed template keys only (no `custom.*` or pattern keys), drops ambiguous money notation, and rejects an item when the **whole line** around its excerpt looks like an instruction | A candidate needs a known value type; found by the eval harness (a short excerpt inside an injected line) |
| D13 | New shared loader `app/handlers.py` (job modules + approval subjects) called by the API and the worker | `enqueue` refuses job types the process does not know; the API enqueues |
| D14 | `payload_hash` is allowed in the response-schema secret scan | It is the public integrity binding the client must echo, not a credential |
| D15 | `query.activity_summary` needs `reports.view`; staff get a `FORBIDDEN` result | Counts of fact changes and approvals are owner/manager data |
| D16 | The Playwright stack starts the worker (waits for its startup log line) | Commands are asynchronous |

## 6. Known limitations

- **The OpenAI adapter has not talked to OpenAI.** It is tested against a stubbed transport (request body, strict schema, `store=false`, no tools, error mapping, usage). The manual check in the phase document, the real-provider eval run and the exact model ID are pending an API key. `gpt-6-luna` came from a web search that disagreed with itself.
- `LLM_TIMEOUT_SECONDS` exists but each task uses its own timeout (30 s / 60 s, as in the table); the setting is not wired.
- The claim validator is deliberately conservative (e.g. a number above 20, the words "ücretsiz", "bedava", "free" without a promotion fact are issues). It is exercised by tests and by `query.fact` rendering; the customer-facing flows that use it arrive in Phase 4.
- INV-03 "no path from `inbound_events`/`messages` to the command system" is enforced by an import contract on the modules that exist; **Phase 4 must add `inbox` to the contract**.
- Commands cannot edit opening hours, addresses or lists (answer `unsupported`); a missing brand voice fact is an error, not a creation.
- The fake interpreter's grammar is narrow (documented demo phrases); exploratory typing is best done with the real provider.
- Real iOS Safari, a LAN phone test and CI on GitHub have still not run. No accessibility (axe) tests yet (carried over).
- Notifications poll every 30 s; command polling is 1 s while working; lists are not paginated.
- The extraction status for runs older than the snapshot retention (30 days) reads as finished by definition.

## 7. Questions for review

- **Q1:** Confirm the default model `gpt-6-luna`, or give the ID to use; and the key for the manual check and the real-provider eval run.
- **Q2:** D6: should a manager who confirms a staff member's command write the fact directly (as built), or should the requester's role limit it?
- **Q3:** D8: is it right that UI edits also notify the other verifiers and run the impact handlers, or should that stay command-only?
- **Q4:** D4: are the closed `unsupported.reason` codes and the typed `clarify` acceptable replacements for the free-text fields in `agent-runtime.md`?
- **Q5:** The claim validator flags any number above 20 outside a placeholder. Keep that strictness (more reviews, fewer fabricated claims) or relax it for specific classes?
- **Q6:** Phase 1 and 2 questions (merge strategy, accessibility tests) are still open.
