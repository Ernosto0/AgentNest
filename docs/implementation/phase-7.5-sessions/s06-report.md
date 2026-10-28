# Session 06 report: knowledge, grounding and personality

**Status:** Offline complete, operator reviewed. The clean broader rerun passed.
No real-model quality, live Instagram effect, or end-to-end DM send acceptance is claimed.

## Baseline and scope

Started on `main` at `d7d3c01`, with Session 05's operator-reviewed changes uncommitted in
the actual Windows checkout `C:\Users\ernos\AgentNest`. Read the common rules, inherited
Sessions 01-04 reports, Session 05 report, phase/contract/invariant/roadmap documents and
knowledge/render/claims/approved-answer/context/runner sources. Preserved those changes and
Session 08's preliminary audit. No commit, push, deployment, live Meta action or paid model call.

## Implementation

- `app/agent/knowledge.py` replaces all-facts-then-slice in `knowledge.read` with bounded
  keyset SQL retrieval. Usability (verified, inclusive validity in workspace timezone,
  uncontested), tenant and public-business visibility apply before materialization. Internal
  escalation/brand/schedule facts and disclosure controls are withheld; missing or unusable
  price disclosure defaults to no prices. Money facts are excluded when prices are withheld.
  Facts include IDs, versions, validity, placeholders and visibility. Pages use `limit+1`.
- `knowledge.answers` is separately paginated by UUID, language and limit. SQL excludes
  inactive or stale/unusable/hidden dependencies; each page then boundedly renders and
  claim-validates its templates. It returns answer/fact source IDs and versions, never raw
  customer example questions. Existing malformed rows may underfill a scanned page; the
  continuation cursor advances over the scanned page. No unbounded legacy read is called.
- The real coordinator calls `context.assemble` for current non-deleted turns (8), relevant
  facts (4), active business answers (2), current voice and deterministic reply language.
  Public context never queries DM turns. All variable customer/owner/retrieved data is
  neutralized in an untrusted section; exact server source aliases are separate metadata.
  Summaries remain absent until Session 08 owns versioned summaries and deletion generation.
- Personality persists tone, formality, length, emoji, channel style and bounded TR/EN
  examples. Member-readable GET and owner/manager PATCH use `expected_version`; edits audit
  version metadata, increment persona/configuration versions and cannot change delegation.
  Migration `0022` follows `0021`, captures persona version per step and persists validation
  failures. Freshness rejects results generated before a voice edit without stranding the
  thread's controller epoch.
- `reply.validate` and `grounding.validate_reply` are the common Session 07 send-validation
  path. Every business placeholder requires exact current visible fact ID/version evidence;
  the existing renderer and claim validator remain intact. Customer date/time clarification
  is a closed alternative: empty business template, no fact sources, scoped current inbound
  span, closed date/time pattern, entirely server-written attributed question. Model text
  cannot surround an exempt span; prices, URLs and policies cannot use customer attribution.
  Public contexts cannot use private customer sources. Language must match current context.
- A first failed `reply.validate` result returns bounded feedback; a second failed result
  in the activation persists `AGENT_GROUNDING_REJECTED`. Model/tool/token limits remain
  cumulative and no invalid validation result sends or authorizes anything.
- Added six two-turn scripted fake journeys across beauty, retail and fitness in TR/EN.
  Integration tests drive their tool/wait/follow-up sequences through actual job execution.
  These fixtures are not yet wired into the Session 17 quality evaluator and prove mechanics.

HTTP/OpenAPI/client changes: GET/PATCH
`/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/personality`; closed typed
voice request/response. Turkish/English Activity strings accompany `agent.personality_changed`.
Canonical contract, data model and observability catalog updated.

## Verification

Environment: Python 3.12 local venv, PostgreSQL 16 disposable `agentnest_test` on 5433,
frozen clock and fake/mock providers. Tests explicitly set process-only
`COOKIE_SECURE=false`, `INSTAGRAM_ENABLED_PROVIDERS=mock`, `LLM_PROVIDER=fake`,
`MEDIA_STORAGE_BACKEND=local`; local `.env` was preserved.

| Command | Actual result |
|---|---|
| `.venv\Scripts\python.exe -m pytest tests/integration/agent/test_context_grounding.py tests/integration/agent/test_tools.py -q --tb=short -p no:cacheprovider --basetemp tmp-session06-initial` | 11 passed in 3.13s. |
| `.venv\Scripts\python.exe -m pytest tests/integration/agent -q --tb=short -p no:cacheprovider --basetemp tmp-session06-agent` | 54 passed in 36.71s before final added journey/operator tests. |
| `.venv\Scripts\python.exe -m pytest tests/integration/agent/test_initial_journeys.py tests/integration/agent/test_context_grounding.py -q --tb=short -p no:cacheprovider --basetemp tmp-session06-journeys` | 15 passed in 11.58s. |
| `.venv\Scripts\python.exe -m mypy app evals` | 269 source files passed after final source changes; independently repeated by the operator. |
| `.venv\Scripts\lint-imports.exe` | 19 contracts kept, zero broken. |
| Focused Ruff | `ruff check app/agent app/activity/groups.py tests/integration/agent` and corresponding `format --check` passed, 27 files formatted. |
| OpenAPI/client | `.venv\Scripts\python.exe -m app.cli export-openapi -o ../frontend/openapi.json`, `npm.cmd run gen:api`, `npm.cmd run typecheck`, `npm.cmd run i18n:check` passed with explicit development/demo/fake/mock/local export configuration; en/tr 1,181 keys and 743 literal calls. |
| Final combined regression | `.venv\Scripts\python.exe -m pytest tests/integration/agent tests/integration/knowledge tests/integration/inbox/test_drafting_pipeline.py tests/integration/inbox/test_send.py tests/unit/knowledge tests/unit/ai/test_draft_reply_task.py tests/unit/test_activity_templates.py tests/unit/integrations/test_openai_steps.py -q --tb=short -p no:cacheprovider --basetemp tmp-session06-clean`: **538 passed in 172.74s**. Includes operator foreign-account API and public-context tests, six journeys, and successful/failed single-repair paths. |
| Final diff/encoding | `git diff --check` passed; report/contracts checked as UTF-8. |

Initial generated-client typecheck failed because `.env` had demo tools disabled, so export
omitted existing dev routes/types. Re-export used process-only `APP_ENV=development` and
`DEMO_TOOLS_ENABLED=true`; no API implementation was removed to silence the error. The
initial Ruff output caught line lengths before formatting; final formatting is recorded below.

The first broader run (`tmp-session06-final`) completed **536 passed, 1 failed in 221.75s**:
the new `agent.personality_changed` audit catalog entry lacked an Activity grouping. The
group is now registered; the complete same test selection passed in the clean 538-test rerun,
without dropping the failing check. Whole-tree `ruff check .` still reports the three unchanged baseline
issues in `matching.py` and `test_templates.py` already recorded by Session 02. Whole-tree
`ruff format --check .` panicked in Ruff while traversing restricted old temporary
directories; `ruff format --check app tests evals migrations` completed and reported the three
unchanged baseline formatting issues in `draft_content.py`, `knowledge/values.py` and
`test_templates.py` (503 files formatted). Focused changed paths pass. These checks are not
reported as whole-tree passes.

## Acceptance, demo and limits

AC75-01/03/05/12 have scoped offline context, provenance, voice and adversarial evidence;
public-context/private-source tests and owner/manager permissions are covered. This does not
prove model-selected useful responses, tone quality, mobile UI or actual send delivery.

To inspect locally after migrations: GET the account's personality, PATCH with
`{"expected_version":1,"personality":{"tone":"warm","formality":"professional"}}` as an
owner/manager, then GET version 2. Run the six-journey test file above to see complete
credential-free read/validate/wait/next-turn mechanics through recreated workers.

Lexical key/label/title matching can miss synonyms or return an empty relevant result;
`knowledge.read` pagination remains available. No semantic/vector quality is claimed. Context
remains subject to Session 05's 16,000-byte request cap, and large legitimate context can
handoff. Knowledge material is verified structured facts and active approved business answers;
raw documents are not silently treated as verified facts. One-off owner-answer evidence stays
closed until Session 09 supplies persisted scope/authority/visibility. UI editing is Session 14.

## Session 07 handoff

Head `0022`. Use `context.assemble` and `grounding.validate_reply` directly for DM proposals,
not the old topic-gated drafting context. Persist the exact `ReplyValidationArgs` in domain
storage and revalidate at projection and immediately before dispatch; preserve current fact
references, language, source deletion and cursor/epoch fences. Customer clarification cannot
be accepted through a global numeric exemption: the agent-origin executor must re-run the
same closed source/question path. This session provides validation, not another send ledger.
Keep all actual effects in existing operations and preserve uncertain-send reconciliation.
