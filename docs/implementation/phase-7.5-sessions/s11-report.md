# Session 11 report: public replies and moderation

**Status:** Offline complete, operator reviewed. R75-03/06, authentic Meta
capability, real-model moderation quality, and live founder acceptance remain open. No
live Meta call, paid model evaluation, or deployment was made by this session.

## Baseline and implementation

Started from clean `main` at `601024d` (Sessions 01-10). No unrelated work was present.
Read the common rules, own brief, phase sections 6/10, invariants, CLAUDE, and Session 10
report. Migration `0027` follows `0026` and refuses downgrade with effect history.

- Added `comment.reply` and `comment.moderate` broker tools for the comment/customer surface.
  The latter accepts exact `hide`, `unhide`, or `delete` effects. A current customer-comment
  event, same-account/thread target, exact comment version, verified synthetic post,
  appropriate target state, and non-owner source are required. Replies use the existing
  grounded reply validator; critical facts remain version-bound. A model may complete
  without proposing any effect. No keyword-only moderation rule was added.
- `public_comment_actions` is the exact action subject. It binds target, comment/media
  versions, effect and hash. Per-target pending/unknown actions serialize conflicting
  intents; a succeeded reply prevents a later reworded reply to the same target. `automatic`
  uses current delegation evidence; `ask` creates a single-use `agent_action` approval;
  `off` cancels the proposal. The approval callback revalidates the source before queuing.
- Added distinct `comment_reply`, `comment_hide`, `comment_unhide`, `comment_delete`
  operation types and ID-only jobs. The executor under `app/operations` rechecks delegation,
  approval, account capability/state, media ownership, source versions, reply grounding and
  deadline. It commits the operation in `in_progress` before the provider call, then records
  the result in a separate transaction. The mock maintains independent stateful
  `sim_comment_effects` with failure injection and positive readback by operation key.
- Successful moderation updates local state only when its target version still matches.
  A remote missing target is a failed action, never proof that a delete succeeded.
  `outcome_unknown` is never sent again. Positive readback resolves it; missing or failed
  readback leaves it visibly unresolved and blocks duplicate proposals. Conclusive typed
  provider errors fail with their code; no automatic public-effect retry is attempted.
- The coordinator observes public action outcomes and waits on their approvals/operations.
  Scoped `GET /accounts/{account_id}/agent/actions/{action_id}` exposes status, IDs and
  outcome code; the existing operation detail shows ledger status. Neither returns reply
  bodies. Public source erasure, media deletion and account erasure scrub action/mock text;
  audit transitions carry IDs/status/effect only. OpenAPI and client types were regenerated.
  Meta's new mutation and lookup methods explicitly reject unverified use. Existing accounts
  stay on their previous controller and grant defaults.

## Verification evidence

Windows PowerShell, Python 3.12 local `.venv`, disposable PostgreSQL 16 `agentnest_test`
at localhost:5433, frozen clocks, fake model, mock Instagram, local media. Every pytest
shell set `COOKIE_SECURE=false`, `DEMO_TOOLS_ENABLED=true`,
`INSTAGRAM_ENABLED_PROVIDERS=mock`, `LLM_PROVIDER=fake`, and
`MEDIA_STORAGE_BACKEND=local`. Pytest used `-q --tb=short -p no:cacheprovider` and a fresh
`--basetemp` per run. DB pytest selections ran sequentially.

| Check (from `backend/` unless noted) | Actual result |
|---|---|
| `test_comments.py::test_signed_duplicate_and_coordinator_public_context`, `tmp-session11-smoke` | 1 passed (28.66s); migration-backed old public path. |
| `test_public_actions.py`, `tmp-session11-actions` | 3 passed (44.27s); initial reply, hide/reconciliation, stale target. |
| `test_public_actions.py`, `tmp-session11-actions2` | 5 passed (63.35s); added exact human approval and inconclusive lookup. |
| `test_public_actions.py test_comments.py test_comments_api.py test_comments_review.py test_tools.py test_delegation.py test_dm.py tests/integration/retention/test_retention.py`, `tmp-session11-affected` | 76 passed (290.30s). This run preceded the final focused test additions and provider-error refinement. |
| `test_public_actions.py`, `tmp-session11-finalactions` | 9 passed, 1 failed (20.96s): a two-account test fixture selected the first account's `root` comment. Scoped the fixture query to its account. No implementation change was required. |
| Same complete focused selection, `tmp-session11-finalactions-rerun` | 10 passed (18.21s): public reply dedup, fake-model no-op, hide/unhide/delete, ask, two-worker race, revoked grant, stale target, remote missing target, ambiguous positive and inconclusive readback, conflicting intent, foreign target. |
| Scoped `ruff check` / `ruff format`; `.venv\Scripts\mypy.exe app evals`; `.venv\Scripts\lint-imports.exe` | Ruff passed after formatting/import fix; mypy passed 287 source files; import-linter kept all 19 contracts. |
| `python -m app.cli export-openapi -o ../frontend/openapi.json`; `frontend/npm.cmd run gen:api`; `frontend/npm.cmd run typecheck` | Passed; generated client contains action status route. |
| `git diff --check` | Passed before report writing; rerun at operator review. |

The broader run passed on the implementation state before its last provider-error
classification change. The final 10-case focused rerun covers that change; a clean broad
rerun on the final tree remains an operator review choice, not a claimed result.

## Reproducible offline demo

1. On a local mock account, grant `comment.reply`/moderation action modes and activate the
   account agent. Use the Session 10 signed `synthetic-comment-v1` developer route with
   `media_verified: true` to create a customer comment on an owned mock post.
2. Have the fake agent call `comment.reply` with the returned comment UUID/version and a
   grounded template, or `comment.moderate` with `hide`, `unhide`, or `delete`. Run due jobs.
   Inspect the agent action status and operation detail; repeat the call/job and observe one
   `sim_comment_effects` row. Choose model completion without a tool for no action.
3. Inject a `comment_hide` `timeout_after_success` rule, run the effect once, inspect
   `outcome_unknown`, then run reconciliation. Positive mock evidence resolves it. Inject
   a `comment_lookup` transient failure to leave it unknown; a new proposal cannot resend.
   `test_public_actions.py` executes these flows without credentials.

## Acceptance boundaries and Session 12 handoff

AC75-09 has offline mechanics for contextual public reply and no-action completion;
semantic appropriateness remains Session 17 real-model evaluation. AC75-10 has mock
automatic hide/unhide/delete and ask/off authority wiring; live moderation is pending.
AC75-15 has target reservation, repeated job and two-worker duplicate fences in the mock.
AC75-16 has positive/inconclusive readback and no blind resend, not real Meta readback.
Complaints versus spam and arbitrary criticism judgment are model-quality questions, not
proved by fake tool selection. Post capability limits and provider quotas remain provisional.

Session 12 can build a separate private-reply action beside these public effects; it must
share the target conflict fence where needed and retain private/public context separation.
Migration head is `0027`. R75-03/06 and Session 16 must establish authentic Meta response,
lookup, quota and already-absent semantics before enabling real comment capabilities.
