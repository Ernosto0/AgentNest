# Session 09 report: owner questions and continuation

**Status:** Offline complete, operator reviewed. Source review, three independent operator
tests, the broad run and latest focused checks passed. No live Meta, paid model,
external owner messenger, commit, push or deployment was used. Session 10 has not started.

## Baseline and scope

`main` at `d7d3c01`, with the operator-reviewed uncommitted Sessions 05–08 preserved.
Migration `0025` follows `0024`. Existing accounts retain legacy/inactive defaults; nothing
activates an account automatically. All tests use the disposable PostgreSQL database
`agentnest_test` on localhost:5433, fake models, mock Instagram and local storage. Process-only
overrides are `COOKIE_SECURE=false`, `DEMO_TOOLS_ENABLED=true`,
`INSTAGRAM_ENABLED_PROVIDERS=mock`, `LLM_PROVIDER=fake`, `MEDIA_STORAGE_BACKEND=local`.
`.env` and ignored prior scratch directories were left alone.

## Implemented behavior

- `app/owner_requests` persists scoped questions, required-information slots, visibility,
  source message/hash/cursor, continuation key and ownership/deletion/knowledge fences.
  Information answers/proposals/cancellations carry immutable version/request/user/role
  provenance. Named composite FKs prevent binding another question's answer or foreign
  account/customer/source/action/candidate records.
- Member-readable paginated list/detail/history APIs and explicit answer/cancel controls.
  Owner/manager authoritative answers are distinct from staff proposals and action approval.
  Identical UUID requests replay; conflicting retries/expected versions reject. Staff cannot
  propose after an authoritative answer and accidentally advance its continuation version.
- `owner.ask` and `approval.request` have distinct closed inputs/results. The first ends the
  activation in a persisted question wait. The second uses the existing exact human action
  approval route and cannot override an off delegation. Free customer prose or owner “okay”
  grants no authority. Notifications remain existing in-app, deduplicated and content-free.
- Answer + durable event + cursor + wake commit together. Account -> thread -> question
  locks never acquire approval locks. Bounded periodic recovery finds committed answers and
  expires questions; human waits hold no transaction/worker lease and consume no failure
  attempts. Existing cumulative model/tool/token budgets remain intact.
- The exact one-conversation evidence is `owner_answer:{id,version}` with an empty template,
  no fact sources/customer clarification. The server renders the whole attributed quote;
  unrestricted model prose cannot borrow its authority. Current author membership, customer,
  question, visibility, expiry, source hash, ownership/deletion and knowledge evidence are
  revalidated at dispatch. Business-fact validators remain unchanged. An exact matching owner
  event extends the existing response-obligation guard; generic wakes cannot create a DM.
- Optional holding replies use fixed truthful text, one question-linked stable intent and
  the existing delegation/send ledger. In-flight/unknown sends keep reserving their slot.
  Cancellation/replacement/expiry immediately cancel linked unsubmitted actions/drafts and
  stale approval cards; deferred cleanup retains the approval-first lock order.
- Closed windows retain valid answers and notify the owner; no background send or false
  delivery result occurs. A subsequent exact repeat of the original request can consume the
  still-valid answer. Changed requests require replan/clarification. Between-claim observations
  clear on thread cursor changes as well as memory generation changes.
- Explicit reusable information creates an unverified typed text `FactCandidate` with
  `source_type=owner_answer` and an inspectable persisted `owner_answer_id`. Verification
  remains the existing knowledge workflow. Private-business answers cannot be promoted.
- Source removal, retention and disconnect erasure redact new private question/answer and
  linked proposal caches; minimal ledger/version IDs survive. Memory-only forgetting does
  not rewrite historical sent business messages. General conversation/data-subject deletion
  remains the separate owner `data.delete`/Phase 8 workflow.

## Verification evidence

Commands below run from `backend/` unless stated otherwise, with the process overrides above.
Every pytest command uses `-q --tb=short -p no:cacheprovider` and a workspace basetemp.

| Command / selection | Actual outcome |
|---|---|
| `.venv\Scripts\python.exe -m pytest tests/integration/agent/test_owner_requests.py`, `--basetemp tmp-session09-first` | Migration setup failed: check-constraint drop name was prefixed twice. Fixed using `op.f`; later clean runs upgraded successfully. |
| Same selection, `tmp-session09-second` through `tmp-session09-fifth` | Test iterations exposed an incorrect JobContext constructor, wrong-version context expectation and owner-only fixture assumptions. Corrected tests, without changing authority semantics. |
| Same selection, `--basetemp backend/tmp-session09-sixth` when invoked from repository root | 12 passed in 20.31s. |
| Owner requests + API, `tmp-session09-seventh` | 12 passed / 1 failed: second connected account fixture violated the one-active-account workspace constraint. Fixture now disconnects the first account before creating a real second account. |
| Same selection, `tmp-session09-eighth` | 13 passed in 21.55s. |
| Owner requests + API + races + independent `test_owner_review.py`, `tmp-session09-focused-final` | 25 passed in 61.41s. This precedes the third operator test, clearer first-reopened-window fixture and final additional observation/FK/tool tests. |
| Broad selection, `tmp-session09-broad` | **988 passed in 554.10s (9m 14s)**. No failures or selection exclusions. This includes migration `0025`/composite FKs and final runtime fixes; subsequent change only gives the same owner-reference shape its distinct `OwnerAnswerEvidence` type/schema. |
| Final owner requests + API + races + independent review + observations + FK selection, `tmp-session09-latest-focused` | **30 passed in 54.71s** on the final distinct evidence schema. Includes all three independent operator tests, first eligible reopened interaction, between-claim cursor/body invalidation, cross-customer isolation, distinct approval tool and actual foreign composite-reference rejection. |
| `.venv\Scripts\python.exe -m mypy app evals` | Passed, 279 source files. |
| `.venv\Scripts\lint-imports.exe` | 19 contracts kept, zero broken. |
| Scoped Ruff check and formatting | Passed after import/format corrections; 39 files formatted at final scoped check. |
| Whole-tree Ruff check / format check | Same three known baseline lint errors (`matching.py`, `test_templates.py`) and three known baseline format files (`draft_content.py`, `knowledge/values.py`, `test_templates.py`); 526 other files formatted at final check. These unrelated files were not edited. |
| Development/demo/fake/mock/local OpenAPI export, frontend `npm.cmd run gen:api`, `typecheck`, `i18n:check`, `lint` | All passed. TR/EN parity: 1,192 keys, 746 literal calls. |
| `git diff --check` and Session 09 documentation UTF-8 verification | Passed on final documentation; no replacement characters. |

Additional validation setup mistakes were corrected: invoking mypy/import-linter from the
repository root omitted backend configuration, and `python -m lint_imports` is not an installed
module entry point. Only the configured backend-cwd `mypy app evals` and
`.venv\Scripts\lint-imports.exe` passes above are acceptance evidence.

The broad command is `.venv\Scripts\python.exe -m pytest tests/integration/agent
tests/integration/inbox tests/integration/integrations tests/integration/retention
tests/integration/approvals tests/integration/jobs tests/integration/knowledge tests/unit/knowledge
tests/unit/test_activity_templates.py -q --tb=short -p no:cacheprovider
--basetemp tmp-session09-broad`. No tests were removed from the Session 08 broad selection;
knowledge regressions were added. The batching assertion accounts for one new bounded
owner-question expiry selection. A clean same-selection rerun is required for any broad failure.

The latest focused command was `.venv\Scripts\python.exe -m pytest
tests/integration/agent/test_owner_requests.py tests/integration/agent/test_owner_requests_api.py
tests/integration/agent/test_owner_requests_races.py tests/integration/agent/test_owner_review.py
tests/integration/agent/test_owner_observations.py tests/integration/agent/test_owner_fk.py
-q --tb=short -p no:cacheprovider --basetemp tmp-session09-latest-focused`.

## Acceptance evidence and limitations

AC75-06 is exercised through signed inbound ingestion, real persisted jobs/coordinator wait,
authoritative answer and the existing mock send operation ledger. AC75-07 covers staff versus
owner/manager, free “okay”, the original exact approval route, off delegation, cancellation
and takeover. AC75-08 covers changed customer requests/source text, expiry, facts, policy,
ownership/takeover and window-before-dispatch, alongside existing Session 05–08 races.
The passing results above and operator source review establish this session's offline
acceptance; no UI Session 15, real-model tool-selection,
live Meta, owner phone/manual or platform acceptance is claimed by these tests.

Two deliberate conservative limits remain: automatic reuse after the messaging window needs
an **exact repeat** of the original customer request; a semantically similar follow-up needs
clarification/replan. The knowledge invalidation digest aggregates all workspace facts and
candidates; its result is small but its DB work grows with knowledge volume, and an unrelated
candidate edit can require a fresh owner answer. This favors stale-action prevention over
maximum answer reuse. Reusable knowledge currently creates typed **text** candidates only;
structured prices/hours/policies still use the existing knowledge editing/verification path.

## Frontend payload examples and demo

All paths are below `/api/v1/workspaces/{workspace}/accounts/{account}/owner-questions`.
Use returned IDs and versions rather than trusting prose or a notification as authority.

```json
{"expected_version":1,"client_request_id":"8ee0569b-e7c4-42f7-a2c2-6fd36c286cbe","kind":"answer","body":"A one-off exception is available for this request.","reusable_knowledge":null}
```

POST that body to `/{question}/answer` as owner/manager. Staff can send `kind:"proposal"`
while pending, which returns a proposal and leaves the question pending. The response is
`{id,question_id,version,kind,body,author_role,candidate_id,expires_at}`; it is information,
never a delivery/approval receipt. A cancellation uses:

```json
{"expected_version":2,"client_request_id":"d63d00e0-96cf-42d3-ae37-74237ed643d1"}
```

GET `?limit=20&cursor=<last-id>&customer_id=<identity-id>` and `/{question}/answers?limit=20`
return `{items,next_cursor}`. Detail exposes `thread_id`, `customer_id`, `source_cursor`,
`required_info`, `visibility`, `body`, `state`, `version`, `answer_id`, `expires_at`.

Offline demo: explicitly activate a mock account with automatic DM authority; ingest a signed
customer request missing business information; scripted fake selects `owner.ask`; inspect the
pending card/list and settled worker; submit the authoritative answer; drain jobs and inspect
the succeeded mock send/operation. Repeat under ask/off authority and observe the original
human approval/no send. Advance the clock beyond the messaging window and observe retained
information plus owner notification, then repeat the exact request to reopen eligibility.

## Handoff

Migration head `0025`. Stable interfaces are the question API, `owner.ask`,
`approval.request`, `ReplyValidationArgs.owner_answer`, and the existing coordinator/DM
projection/executor. The parent operator accepted Session 09 after source review, 988 broad
passes and 30 latest focused passes (including three independent operator tests). This child
session stops at Session 09; the parent may hand Session 10 to a fresh subsession. External
owner messaging remains Phase 9; customer-facing UI is Session
15; real model/platform/founder gates remain separate.
