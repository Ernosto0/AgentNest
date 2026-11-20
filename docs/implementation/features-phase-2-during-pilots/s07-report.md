# Session 07 report: visible learning loop (D-05)

- **Status:** implemented and verified offline. Nothing was run against a real Telegram bot, a real phone or the real model. Stopped for review.
- **Baseline commit:** `20a0551` (worktree `pivoris-p2/s07`, nothing committed).
- **Migration:** `0055` (`20261116_0055_fact_save_tokens.py`, `down_revision = "0048"`). The orchestrator re-chains it.

## What was built

After an owner answers an assistant question, they are offered "Save this as a verified fact?" with one tap, on the web and on Telegram. The tap goes through the existing candidate accept path. The Assistant page shows "Learned N things from you this month" with a list linking to each fact.

- **Candidate for every answer.** `owner_requests.service.decide` now proposes the unverified text candidate (`source_type=owner_answer`, key `custom.owner_answer_<question id hex>` or the key in `reusable_knowledge`) for every authoritative answer to a `customer_reply` question. Before, only the "save for future answers" checkbox did. Staff proposals and `private_business` answers still create none. The checkbox was removed from the web form (the API field stays). Nothing is verified by creating it.
- **Web.** The question page shows the offer (also when reopened later, for example from a Web Push link) for the owner's answer whose candidate is `pending`. One tap calls `POST /fact-candidates/{id}/accept` with no body. A confirmation replaces the offer.
- **Typed editor.** If the answer text carries a price, hours, a phone number, an e-mail or a URL (claim-validator codes MONEY, TIME, PHONE, EMAIL, URL), one tap is refused (422 `VALIDATION_FAILED`, reason `owner_answer_requires_editor`). The question page then links to Suggestions, where the card shows the matching typed editor and accepts with `{value_type, value}`; the fact becomes a typed fact (for example `money`), and a price retyped as `text` is refused too. Words such as "free" or bare numbers keep the one-tap path (the owner sees the exact text).
- **Telegram.** The confirmation of an answer carries a button `fsv:<token>` (22-character token, within the 64-byte limit) when the answer is plain text and the user holds `knowledge.verify`. For a structured answer it carries a note instead. The token is single use, expires after 48 hours, is bound to one candidate and one user, and only its hash is stored. The tap resolves it with a SECURITY DEFINER function, checks the Telegram account is linked to that user and workspace, marks it used and runs `accept_candidate` as that user.
- **Learned this month.** `GET /learning/month`. A fact counts once, in the month (workspace time zone) in which its insert-only history first holds a `candidate_accepted` verified version whose candidate came from an owner answer. Later edits do not recount, archived facts are left out, and hand-typed, pasted or staff-proposed facts never count.
- **Fact label.** For an auto-keyed fact the label is the first 60 characters of the answer itself (nothing from the question or the customer).
- **Fence fix (found while testing).** Accepting or rejecting the answer's own candidate changes the knowledge fence, which made the answer unusable as evidence and stopped the pending reply from being sent (reproduced: 0 messages sent). `accept_candidate` and `reject_candidate` now move that question to the new fence, only if it was current just before; a foreign knowledge change still voids it (both tested). `knowledge_fence` moved from `owner_requests.service` to `knowledge/learning.py` (still importable from the old place) to keep the import contract.

## Files

Backend, changed: `app/core/db.py` (`fact_save_tokens` in the tenant table list), `app/integrations/channels/telegram/{dispatcher,handlers}.py`, `app/knowledge/{router,schemas,service}.py`, `app/owner_requests/{models,router,service}.py`, `tests/unit/core/test_rls_policies.py` (56 to 57 tables). `pyproject.toml` only has the orchestrator's D-01 line.
Backend, new: `app/knowledge/learning.py`, `app/owner_requests/save_tokens.py`, `migrations/versions/20261116_0055_fact_save_tokens.py`, `tests/integration/agent/test_owner_answer_learning.py` (25 tests).
Frontend, changed: `openapi.json` (only the touched paths and schemas) and `src/api/schema.d.ts` (regenerated), `features/agent/AgentPage.tsx` (one import and one insertion line after the overview panel), `features/agent-work/{WorkPages.tsx,work.test.tsx}`, `features/knowledge/{SuggestionsPage.tsx,hooks.ts}`, `test/mockApi.ts` (background route for the new endpoint), i18n `agentWork.json` and `knowledge.json` (tr and en; `agentWork.reuse` removed).
Frontend, new: `features/agent/LearnedThisMonth.tsx` (own component), `features/agent-work/SaveAsFactOffer.tsx`, `features/knowledge/{OwnerAnswerSave.tsx,learning.ts}`, `features/agent-work/learning.test.tsx` (6 tests).
Docs: `architecture/{api-design,account-agent-contracts,data-model,integrations}.md`.

## Contracts

- `GET /api/v1/workspaces/{id}/learning/month` (any member) returning `{month, count, items:[{fact_id,key,category,label,value_type,learned_at}]}`.
- `POST /fact-candidates/{id}/accept` takes an optional body `{value_type, value}`.
- `CandidateOut.editor_type`; `AnswerOut.candidate_status` and `AnswerOut.candidate_editor_type`.
- Table `fact_save_tokens` (RLS enabled and forced, in `CATEGORY_C_TABLES`), function `resolve_fact_save_token_by_hash(text)`.
- Telegram callback prefix `fsv:`; dispatcher actions `fact_saved`, `fact_save_already_used`, `fact_save_expired`, `fact_save_unauthorized`, `fact_save_conflict`, `fact_save_needs_editor`, `fact_save_failed`.
- No new setting, job type, notification type or reason code beyond `owner_answer_requires_editor`.

## Checks

Backend (from `backend/`, env `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN= OPENAI_API_KEY= PYTHONUTF8=1`, `TEST_DATABASE_URL` set to the session databases):

| Check | Result |
|---|---|
| `ruff check .`, `ruff format --check .` | pass (684 files formatted) |
| `mypy app` | pass (362 files) |
| `lint-imports` | 23 kept, 0 broken |
| `pytest tests/integration/agent/test_owner_answer_learning.py` | 25 passed |
| `pytest tests/unit tests/isolation tests/security tests/contract` (run before the fence change) | 1,997 passed, 13 skipped, 3 failed (see below) |
| `pytest tests/integration/agent tests/integration/knowledge tests/integration/test_hardening_integration_regressions.py tests/e2e/test_owner_channel_acceptance.py tests/integration/notifications` (before the fence change) | 534 passed |
| Re-run after the fence change: owner request tests, `tests/integration/knowledge`, `tests/unit/approvals`, `tests/unit/knowledge`, RLS policy test, owner channel e2e | see the line at the end of this file |

The 3 failures in the unit group are not related to this session: `isolation/test_phase6_isolation.py::test_the_dev_job_listing_of_a_never_shows_the_jobs_of_b` and `isolation/test_publishing_isolation.py::test_the_simulator_listing_of_a_never_shows_what_b_published` get a 404 from dev routes that need `DEMO_TOOLS_ENABLED`, and `security/test_invite_secrets.py::test_the_invite_token_is_never_logged_audited_notified_or_queued` is the known invite-response failure. I did not re-run them at an untouched commit.

Frontend (from `frontend/`, PowerShell): `npm.cmd run lint` clean, `typecheck` clean, `i18n:check` passed (2,452 keys), `build` ok, `npm.cmd test` 53 files, 790 tests passed. One earlier run, made while three backend shards were running, had 10 unrelated timeouts in 7 files; the clean re-run passed everything.

## Deviations and open questions

1. **Candidate for every answer** (brief said "the candidate the service already creates", which only existed with the checkbox). Consequence: each customer-facing answer leaves one pending candidate in Suggestions until saved or rejected. Question for review: should unsaved candidates expire?
2. **Typed editor lives in Suggestions**, not inline on the question page (the question page links there). Percentages, dates and discount words are not treated as structured.
3. **Accepting through the typed editor** mutates the candidate's `value_type` and value before accepting and does not recompute `relation`. A new fact is the normal case; if a fact of another type already holds the key, accept returns `CONFLICT_STATE`.
4. **Fence rebase** touches the knowledge service (`accept_candidate`, `reject_candidate`). Question for review: acceptable, or should the fence ignore owner-answer candidates instead?
5. **Telegram button for staff**: only people with `knowledge.verify` get it; staff can only propose, so they never see it.
6. The Web Push deep link needed no change: it opens the question page, which shows the offer. Not tried on a real phone.
7. Not verified against a real Telegram bot or the real model. The Telegram flow is tested through `process_update` with a mock HTTP transport.
8. Migration upgrade is exercised by the test databases; the downgrade (drops the function and table) was not run.

Re-run after the fence change: `tests/integration/agent/test_owner_requests.py test_owner_requests_api.py test_owner_requests_races.py test_owner_review.py test_owner_fk.py tests/integration/knowledge tests/unit/approvals tests/unit/core/test_rls_policies.py tests/unit/knowledge tests/e2e/test_owner_channel_acceptance.py`: **447 passed**. The wider `tests/unit tests/isolation tests/security tests/contract` and the integration agent/notifications groups were not repeated after the fence change (it only touches `accept_candidate`, `reject_candidate` and the fence helper).
