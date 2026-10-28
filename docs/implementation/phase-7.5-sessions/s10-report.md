# Session 10 report: public comment ingestion and context

**Status:** Offline complete, operator reviewed. Source review, the clean complete broad
rerun and the latest affected/Unicode checks passed. Stop at Session 10. No live Meta, paid model,
public reply, moderation, commit, push or deployment was performed.

## Baseline and implemented behavior

`main` at `d7d3c01`; preserved the intentional, operator-reviewed uncommitted Sessions
05–09. Revalidated no `AGENTS.md` in this checkout. Read the common session rules, own
brief, phase sections 7–8/10, CLAUDE, invariants, roadmap, previous reports and source
ingestion/coordinator/privacy contracts. Migration `0026` follows owner requests `0025`.
Existing accounts remain legacy/inactive unless explicitly activated.

- Added `app/comments` with durable scoped post, public thread and comment records,
  source versions/provider UTC timestamps, optional stable author IDs, placeholder parents
  and visible/hidden/unknown/deleted states. Composite parent FKs bind the same workspace,
  account, media and thread; public agent threads bind a scoped public-thread FK. DB page
  indexes and bounded reads prevent broad context loads. Public sources never resolve or
  merge private customer identities; the schema accepts no display-name identity evidence.
- Added explicitly synthetic `synthetic-comment-v1` input only to the mock codec. The real
  Meta codec stays disabled for comments. Raw-body HMAC verification precedes parsing; the
  existing durable receipt/dedup/ID-only job path is reused. Stored comment receipts are
  reconstructed with their comment schema rather than the DM messaging wrapper. Malformed
  signed shapes and naive timestamps fail closed without breaking messaging ingestion.
- The provisional fixture requires an explicit root ID and supports roots/direct replies
  only. A reply arriving first creates a placeholder root. Conflicting media, lineage or
  established author IDs reject atomically using a savepoint. Missing author IDs preserve
  previously proven identity/owner status. Higher provider revisions replace live state;
  equal revisions retain the first body except deletion wins ties. Deleted/erased source
  tombstones are terminal, including a later higher-revision create.
- Signed simulated customer comments reach exactly one persistent public `AgentThread`,
  with deduplicated source events, cursor-specific wakes and the actual fake coordinator.
  Native owner replies are public source changes, not new customer obligations; owner
  generations and source cursors fence stale work. Own-only threads do not create customer
  work. Captured public-media versions invalidate stale claims across sibling post threads
  and discard carried observations. Restart checkpoints contain routing metadata and reread
  the public tool against current scoped sources.
- Actual model context pins the current event's exact scoped comment source/version even
  beyond the first tool page, includes at most five public turns and a bounded post caption,
  and derives language/knowledge relevance from the current eligible customer comment.
  Missing post metadata stays unknown/unverified with no invented caption. A historical
  comment scaffold without a public link receives empty public context; strict broker
  source guards remain. Poisoned private DM links do not expose private turns or memory.
- Registered only read-only `public.thread` (1–8 comments), plus permission-checked typed
  account comment list/detail/thread and post/thread APIs (1–50, UUID cursors). Real foreign
  workspace, same-workspace account, media and thread references return 404. Private DM,
  customer-memory and owner-question tools are unavailable on the comment surface.
- Stateful mock source records are separate from application sources. Developer-only
  `POST /api/v1/dev/workspaces/{workspace_id}/simulate/comment` records the synthetic remote
  state and submits a signed body through actual ingestion. It supports direct replies,
  missing authors/media, native owner IDs, edits/hidden/deleted states and post metadata.
  Every resulting record/context exposes mock simulation provenance.
- Comment/post deletion and late creates redact source-bearing receipt/mock caches, keeping
  content-free tombstones. Account-disconnect erasure clears public bodies immediately.
  Bounded retention locks the account, refreshes/rechecks source cutoff and advances source
  fences; fresh concurrent edits survive. Caption expiry clears its body and bumps its media
  version without claiming remote post deletion or suppressing fresh comments. Generic run,
  audit and job payloads remain content-free. Existing uncertain operations retain their
  reconciliation evidence. Populated-source downgrade requires explicit archival/erasure.
- Added source/media audit actions and TR/EN activity strings; updated data-model,
  account-agent contracts and observability documentation. OpenAPI and client types were
  regenerated. No public-send or moderation executor/tool is introduced here.

## Verification evidence

Local Python 3.12 venv; disposable PostgreSQL 16 `agentnest_test` at localhost:5433;
frozen clocks, fake model, mock Instagram and local media only. Every pytest shell sets
`COOKIE_SECURE=false`, `DEMO_TOOLS_ENABLED=true`, `INSTAGRAM_ENABLED_PROVIDERS=mock`,
`LLM_PROVIDER=fake`, `MEDIA_STORAGE_BACKEND=local`. `.env` was not edited; test scratch
directories were not deleted. DB pytest processes ran sequentially under the exclusive slot; the slot was released after
the final 72-pass run.

Commands below run in `backend/` unless stated otherwise. All pytest commands use
`-q --tb=short -p no:cacheprovider --basetemp tmp-session10-<name>`.

| Check / exact selection | Actual result |
|---|---|
| Initial `tests/integration/agent/test_comments.py`, `first` | 1 passed / 14 setup errors: migration check-constraint naming convention doubled a name. Fixed with `op.f`; reran the entire selection. An initial helper command also used the wrong cwd-prefixed Python path and did not run; corrected. |
| Same 15-case selection, `second` | 15 passed in 18.11s. |
| Comments + comments API + operator review selection, `third` | 19 passed / 1 failed in 25.91s: new API fixture reused an existing workspace slug. Fixed fixture, reran the same selection. |
| Same selection, `fourth` | 20 passed in 25.30s. |
| Expanded same selection, `fifth` | 22 passed / 1 failed in 29.54s: JSON null remained distinct from SQL null in redacted caches. Fixed to use SQL `null()`, reran the whole selection. |
| Same expanded selection, `sixth` | 23 passed in 30.05s. |
| Comments/API/operator + `tests/unit/test_activity_templates.py`, `finalfocused` | 29 passed in 31.49s, including current source pinning, native identity, deletion caches, sibling media fencing, retention race and caption expiry. |
| Broad agent/inbox/integrations/retention/approvals/jobs/knowledge + unit knowledge/activity, `broad` | 1,012 passed / 5 failed in 568.20s. Three retained adversarial fixtures had unlinked public scaffolds; assembler now gives empty context without weakening the strict tool guard. Updated the intended public tool allowlist expectation and documented extra bounded retention-session count. The required same-selection rerun passed below. |
| Comments/API/operator, context grounding/review, memory privacy, tool broker, retention and activity, `finalaffected` | 70 passed in 50.53s. Includes final base list API, same-workspace composite FK/foreign-media cases, deterministically pinned max-UUID current source, restart public-read checkpoint and duplicate wake. |
| Same complete broad selection, `broad-rerun` | 1,020 passed in 552.75s (9:12), zero exclusions. Includes the final base API, authority/lifecycle, empty unlinked-scaffold compatibility and test contract fixes. |
| Latest complete affected selection including both maximum Unicode/escaping cases, `latestbounds` | 72 passed in 53.58s. Verifies final rendering through the broker and actual second model request, full stored-source preservation, and all affected authority/privacy/API regressions. |
| `.venv\Scripts\mypy.exe app evals` | Passed, 285 source files. |
| `.venv\Scripts\lint-imports.exe` | 19 contracts kept, zero broken. |
| Scoped changed-source Ruff check and format check | Passed, all 30 Session 10 Python files formatted; prior unrelated baseline lint/format issues were preserved. |
| `APP_ENV=development` fake/mock/local `.venv\Scripts\python.exe -m app.cli export-openapi -o ../frontend/openapi.json` | Passed; regenerated after the base account-comment API addition. |
| `frontend/`: `npm.cmd run gen:api`, `typecheck`, `i18n:check`, `lint` | Passed; i18n: 1,194 keys, 746 literal calls. |
| Independent operator final checks | `git diff --check` clean; HEAD remains `d7d3c01`; ten reports/index valid UTF-8 and 31 local links checked with zero problems. Latest public module + three comment test files: Ruff check passed, nine files already formatted. |

The base account-comment list and final same-workspace foreign-media tests were added
while the initial broad process was already running; the subsequent complete broad rerun
includes these changes and the fail-closed compatibility guard for old unlinked public
scaffold fixtures.

The broad command is `.venv\Scripts\python.exe -m pytest tests/integration/agent
tests/integration/inbox tests/integration/integrations tests/integration/retention
tests/integration/approvals tests/integration/jobs tests/integration/knowledge
tests/unit/knowledge tests/unit/test_activity_templates.py -q --tb=short
-p no:cacheprovider --basetemp tmp-session10-broad` (subsequent rerun uses a fresh basename).
The five failures were the public-surface date clarification, poisoned-DM surface switch,
same-handle private-memory public context, exact broker allowlist and retention batch-session
count tests. No failure was excluded or represented as passed by a focused retry. The clean complete
same-selection rerun resolved those five failures.

During that rerun, the final rendering-only byte caps were added after module loading.
The broad result covers final authority/lifecycle/API fixes before those preview caps; the
subsequent full affected selection verifies the latest rendering with Unicode and escaping
expansion through the actual second model request. No authority or source persistence
changed with that rendering adjustment.

## Concrete offline demo

1. On a local development/demo mock account, explicitly activate its account agent using the
   existing controller API. Authenticate as a workspace owner and use the CSRF header.
2. POST the developer simulator route with `schema: synthetic-comment-v1`, `id: demo-root`,
   `root_id: demo-root`, `media_id: demo-post`, `author_id: demo-public-customer`,
   `text: Hello, what services do you offer?`, `version: 1`, and an aware UTC `timestamp`.
   Optional `media_verified: true`, `media_caption: Public post`, `media_version: 1` labels
   synthetic post ownership; omit them to demonstrate unknown post details.
3. Run due jobs using the existing developer job runner. Inspect
   `/api/v1/workspaces/{workspace_id}/accounts/{account_id}/comments` and its comment/thread
   routes, agent thread/event/run rows and simulated provenance. Repeat the same request:
   one receipt/source/thread/wake obligation remains.
4. Send a direct reply using a distinct `id`, `parent_id: demo-root`, `root_id: demo-root`.
   Try a higher-revision edit, hidden state, deletion, missing author, or account external ID
   as author for native owner activity. No send/moderation action can execute.
5. Deterministic executable demo: run `test_comments.py`, `test_comments_api.py` and
   `test_comments_review.py`; the operator test drives actual queued wake jobs through a
   fake public read and verifies completion with a poisoned private link excluded.

## Acceptance boundaries and handoff

AC75-09 has public post/thread context and fake loop evidence only; public reply/no-response
quality and effects remain Session 11/17. AC75-12 has public/private source separation,
no identity merge and actual-model-request evidence. AC75-15 has durable receipt/source/wake
dedup and stale result fences; public-effect exactly-once/reconciliation is not claimed.
AC75-19 has bounded scoped APIs/tools, foreign-ID 404s and composite FK evidence.

R75-01/02 remain unverified. These fixtures are synthetic, not authentic Meta recordings;
the two-level lineage, revision/tie/delete rules and ownership marker are provisional mock
assumptions, not platform claims. No real comment permission, subscription, fetch/readback,
native-event delivery, model tool-selection quality, public reply, moderation or private-reply
success is evidenced. Public model/tool previews are capped after neutralisation and
double-JSON escaping: comment text 280 bytes, post caption 320 bytes. An opaque author ID
is emitted exactly only when its display fits 100 bytes and needs no neutralisation;
otherwise it is omitted with `author_id_omitted: true`. Stored provider IDs, source UUIDs,
versions and full scoped API/source bodies remain exact. Long-comment suffixes can therefore
be absent from model previews; full-topic coverage/model quality remain Session 17 evidence.
Session 11 must add exact action subjects, delegation/approval/ledger
execution and conclusive result verification; Session 16 must validate authentic provider
shapes/capabilities. It must recheck source cursor, ownership/deletion and shared media version
before effects. The generic DSAR/export/callback rollout remains Phase 8.
