# Session 9: AI content generation and `draft_content` evals

**Plan:** `plan.md` §2 **G5, G6, G7**, §3 **P5-03 (generation half)** and **P5-09**. **Depends on:** session 8. **Commits:** `P5-03a: …` (generation) and `P5-09: …` (evals).

## Read first
`agent-runtime.md` §5, `workflows.md` §E step 1, `api-design.md` §2.7 (generate), `docs/invariants.md` (LLM proposal rules, `{{fact:key}}`), the Phase 4 `draft_reply` task, prompt, fake, job and evals as templates; `backend/app/ai/` registry, `llm-provider-openai` memory note (OpenAI is the real provider; default `LLM_PROVIDER=fake`), `testing-strategy.md` evals section.

## Build: generation
- `ai/schemas.py`: `DraftContentInput`, `ContentProposal` (closed schemas).
- `ai/prompts/draft_content/v1.md`: facts and brand voice as data sections, owner objective as owner data, no tools.
- `ai/tasks/draft_content.py` `TaskDefinition`: post-validator checks structure, ≤ 10 hashtags, every `commercial_claims` item maps to a used fact key; model flags can only escalate.
- tr/en fake keyed on objective keywords: deneme/trial → `{{fact:promotion.trial_session}}` overlay; fiyat/üyelik → caption with `{{fact:pricing.membership_monthly}}`.
- `generate_content` job (`content/generation.py`, `content/jobs.py`), three phases with **no transaction open during the model call**: render (`caption_template` → `render` → `caption`, `fact_references` from the render result, hashtags appended by code) → claim validation (issues stored inline, not a hard stop) → re-check the item is still `draft` at the generated version before saving; `content.generated` audit.
- `POST /content-items/generate` with `client_request_id` idempotency (G7): creates the draft plus `agent_runs(status=queued)` linked by `agent_run_id`; response `generation` mirrors the run status. LLM failure leaves a manual draft with `generation: failed` and an error code.
- Docs: agent-runtime §5, api-design §2.7, data-model (G7 link).

## Build: evals (P5-09)
- `evals/draft_content/*.yaml`, ≥ 15 tr/en cases: backed and unbacked promotions, price mentions, story overlay length, `do_not_share`, invented discount.
- `loader.TASKS` + `EVALUATORS["draft_content"]`, DB-free: task → render → claims.
- Hard assertions: 0 ungrounded critical values in passing captions; unbacked claims flagged; a story has no caption.

## Done when
- Tests: AC-D1 `test_generate.py` (draft with placeholders resolved, references stored, claim issues stored); idempotent retry with the same `client_request_id`; LLM failure → manual draft; stale generation discarded after an edit; isolation.
- `uv run python -m evals run --all --provider fake --strict` shows 0 hard failures; all backend checks green.
