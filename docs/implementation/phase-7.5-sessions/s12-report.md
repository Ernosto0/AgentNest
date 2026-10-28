# Session 12 report: comment-to-DM

**Status:** Offline complete, operator reviewed. R75-04/05, authentic Meta
private-reply capability/eligibility, real-model tool choice and live founder acceptance
remain open. No live Meta action, paid model evaluation, deployment, commit or push was
made by the implementation agent.

## Baseline and implementation

Started from clean `main` at `25c80ec` (Session 11 operator reviewed). No unrelated
changes were present. Read the common rules, Session 12 brief, phase plan, invariants,
CLAUDE, architecture contracts and Session 11 report. Migration `0028` follows `0027`.

- `comment.private_reply` is a separate comment/customer broker action. It requires the
  current source event, same-account owned synthetic media, exact comment/media versions,
  visible customer comment, grounded text, explicit delegation and
  `comment_private_reply` capability. The mock has an explicit provisional seven-day
  source-timestamp window and one private reply per comment. This is **not** a claimed
  Meta limit. The real adapter refuses private mutation and lookup.
- `private_reply_opportunities` has a unique account/comment reservation bound to the
  action, text hash, source/policy versions, deadline, and operation. Pending, unknown,
  succeeded, failed and cancelled opportunities all prevent another attempt on the same
  source. Approval `ask` waits for an exact human decision; `off` cannot send. The
  executor rechecks approval, delegation, capability, source state, deadline and
  grounding, then commits an in-progress ledger row before calling the provider.
  Public and private replies remain separate grants/operations; the verified combined
  path orders a public reply before a private reply.
- Independent `sim_private_replies` evidence is keyed by account/comment and operation.
  A timeout after success becomes `outcome_unknown` without resend. Positive keyed
  readback settles it; missing or failed lookup leaves it unresolved and reserved.
  Mock recipient evidence comes from the provider result, never a public display name.
- A new signed inbound DM binds source context only if its account-scoped participant ID
  matches a successful provider-returned recipient. An old conversation or duplicate
  webhook cannot bind without a new message. Zero or multiple unbound matches fail
  closed. An unknown result, missing recipient or different sender remains unlinked.
  Bounded public source context appears only in the private DM model request after
  binding; public model context and public tools cannot read private messages/memory.
  The private reply does not create a conversation or messaging window. Normal `dm.send`
  still requires an independently received customer message and its existing send gate.
- Public source/media/account erasure scrubs private-reply text, proposal, recipient
  evidence and conversation link. Generic action/operation/audit rows carry IDs, hashes,
  statuses and provider result IDs, not the raw comment or private-reply body.
  The `0028` downgrade refuses populated opportunity/provider evidence.

## Verification evidence

Windows PowerShell, Python 3.12 `.venv`, disposable PostgreSQL 16 `agentnest_test`
at localhost:5433, fake model, mock Instagram, local media, frozen clock. Pytest shells
set `COOKIE_SECURE=false`, `DEMO_TOOLS_ENABLED=true`,
`INSTAGRAM_ENABLED_PROVIDERS=mock`, `LLM_PROVIDER=fake`, and
`MEDIA_STORAGE_BACKEND=local`; every run used `-q --tb=short -p no:cacheprovider` and a
fresh `--basetemp`.

| Check (from `backend/` unless noted) | Actual result |
|---|---|
| Existing `test_comments.py::test_signed_duplicate_and_coordinator_public_context`, `tmp-session12-smoke` | 1 passed; migration `0028` and prior public ingestion path. |
| `test_private_reply.py`, `tmp-session12-private1` | 3 passed / 2 failed: empty synthetic author was rejected by the existing schema; inbound test consumed an earlier queued comment receipt. Fixed only the test fixtures and reran. |
| `test_private_reply.py`, `tmp-session12-private2` | 5 passed. |
| `test_private_reply.py`, `tmp-session12-private3` | 6 passed, including signed comment → private reply → customer DM → normal `dm.send`. |
| `test_private_reply.py`, `tmp-session12-private4` | 6 passed / 1 failed: combined effect fixture lacked `comment_reply` capability. Fixed fixture and reran. |
| `test_private_reply.py`, `tmp-session12-private5` | 7 passed. |
| Affected public/private/DM/memory/privacy/retention selection, `tmp-session12-affected` | 86 passed / 2 failed: the new tool schema exceeded the coordinator's existing 16 KB envelope in two maximum-public-preview cases on an account without private-reply capability. Filtered unavailable private-reply tool exposure; focused max-preview rerun passed 2/2. |
| Same complete affected selection, `tmp-session12-affected-rerun` | **89 passed** in 114.64s; no exclusions. |
| Latest `test_private_reply.py`, `tmp-session12-private-final` and `tmp-session12-private-provider` | **8 passed** in 17.15s and **8 passed** in 14.57s respectively. The latest run covers the mock's independent remote deadline check. |
| Final `test_private_reply.py`, `tmp-session12-private-latest` | **8 passed** in 14.23s after unknown-outcome body scrubbing. |
| Final `test_private_reply.py`, `tmp-session12-private-ambiguity` | **9 passed** in 15.90s, including two same-recipient opportunities that remain unlinked on an ambiguous inbound. |
| Final `test_private_reply.py`, `tmp-session12-private-final2` | **9 passed** in 15.85s after the mock timestamp type guard. |
| Operator rerun of complete `test_private_reply.py`, `tmp-session12-operator` | **9 passed** in 122.96s on the final worktree. |
| Scoped Ruff check/format (17 Python files), `.venv\Scripts\mypy.exe app evals`, `.venv\Scripts\lint-imports.exe` | Ruff passed, 17 files formatted; mypy passed 289 source files; import-linter kept all 19 contracts. |
| `git diff --check`; `load_handlers()` | Passed; both private effect handlers registered. |

The clean 89-case affected run preceded the final test-only ask-approval case and the
mock's independent deadline rejection and unknown-outcome body scrubbing. The final
complete 9-case private selection verified those changes and ambiguous identity
matching. A full repository suite, real model evaluation and Meta
contract probe were not run or claimed for Session 12.

## Reproducible offline demo

1. On a local mock account, activate the agent and grant `comment.private_reply` in
   automatic or ask mode. Submit Session 10's signed `synthetic-comment-v1` event with
   `media_verified: true`, an eligible timestamp and a visible customer comment.
2. Let the agent call `comment.private_reply` with its exact comment UUID/version and
   grounded text. Run the private effect job. Inspect the scoped action status and
   `comment_private_reply` operation; a repeated tool call/job leaves one
   `sim_private_replies` record. Without a customer DM, no normal DM window exists.
3. Send a signed mock customer DM from the provider-returned recipient. Its new inbound
   message binds bounded public source context to that DM thread, after which the
   existing `dm.send` operation can respond. Send from another recipient, replay the
   webhook, or inject timeout/readback failure to observe unlinked/unknown boundaries.
   `test_private_reply.py` executes these paths without credentials.

## Acceptance boundaries and Session 13 handoff

AC75-11 has offline one-shot reservation, exact eligibility, signed response and normal
DM continuation evidence; authentic platform behavior remains Session 16/18 work.
AC75-12 has private-only source context, no public memory leak and provider-result
identity matching. AC75-15 has repeated tool/job, duplicate webhook and two-worker
fences. AC75-16 has positive/inconclusive mock reconciliation without blind resend.
Real model selection quality remains Session 17. The seven-day mock window and returned
recipient shape are provisional, not authentic Meta evidence. An inconclusive outcome
retains its reservation indefinitely until evidence or an explicit future resolution
workflow; it is never silently released. Existing migrated accounts remain on their
previous controller/delegation defaults.

Session 13 can use the unchanged coordinator/broker/delegation API and migration head
`0028`. It must preserve the independent customer DM authority path and current
privacy/operation fences when adding owner tasks. R75-04/05 and Session 16 must validate
the real private-reply eligibility, count, recipient and lookup semantics before
enabling Meta capability.
