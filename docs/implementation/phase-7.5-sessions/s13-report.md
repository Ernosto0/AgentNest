# Session 13 report: owner tasks and content tools

**Status:** Offline complete, ready for review.
Real-model quality, owner-task browser UI and live platform acceptance remain later-session
gates. No live account action, paid evaluation or deployment occurred. The user subsequently
authorized committing and pushing this completed work.

## Baseline and review

Resumed clean `main` at `bdbf7c1`, the interrupted Session 13 checkpoint, at the user's
request to check the last commit and continue. No unrelated worktree changes existed.
Sessions 11/12 were already reviewed. Work stays within Session 13.

The checkpoint implemented intake but lacked content tools, generated clients and database
verification. Review also found missing list pagination/foreign-account 404s and intake
replays incorrectly blocked after pause. These are fixed. Coordinator test fixtures now
use real authenticated tasks; a public-tool expectation missing Session 12's private-reply
tool is corrected. Small pre-existing Ruff/format drift was corrected without expanding
behavior in matching, draft-content formatting, money annotation and a template assertion.

## Changes and stable contracts

- Requester-only task POST/list/detail and versioned clarification-answer routes. Intake
  deduplication binds requester/account/request ID, text and initial selections. Answers
  and wakes commit together; information/free text never approves an action. Claims,
  broker dispatch, approval execution and scheduled publication reconstruct current
  active-user/workspace membership and role rather than trusting the stored intake role.
- Owner-task-only `v1` tools: `content.read`, `content.prepare`, `content.schedule`,
  `content.publish`, `content.cancel`, `task.clarify`. Scoped reads issue content-version
  and ready-media/hash receipts. Ambiguous/missing assets require requester selection or
  clarification; unseen IDs and arbitrary aliases cannot select media. No media generation.
  Receipt trimming preserves immutable intake selections. Owner context includes the
  injected clock's workspace-local instant and timezone for natural date interpretation.
- Independent automatic/ask/off rules for preparing, scheduling, publishing and cancelling.
  Scheduling proposes publication separately. Staff can prepare but cannot acquire
  publication authority through a task. Typed action previews show the exact caption,
  overlay, media/hash, fact versions, account, content/version, instant and deadline.
- Exact durable content intents bind critical and noncritical placeholder fact versions.
  Human approval remains explicit, single-use and expiring; automatic publication projects
  a policy grant through the existing executor contract. Future grants last until their
  publish deadline instead of the generic 24-hour lifetime. Ask-required publication for
  now must be explicitly decided within the workspace publication delay.
- Existing content validation, fact holds, deleted-media fences, quotas, ledger and
  reconciliation remain authoritative. Scheduled dispatch rechecks requester authority,
  delegation/pause, exact payload and facts. Unknown results reconcile the same operation/
  container even after revocation, without a second post. Tasks distinguish scheduled,
  unknown and verified published. Manual resubmission/reapproval gets fresh legacy authority.
- Migration `0030` follows checkpoint `0029`, adding content intents and bounded task
  receipts/selections, clarification and answers. Downgrade refuses populated evidence.
  Existing tasks survive additive upgrade; migrated accounts remain legacy/inactive with
  no new grants. Existing commands and saved reporting contracts remain compatible.
- Updated account-agent, API, data-model and audit contracts plus OpenAPI/TypeScript types.
  Detailed schemas/defaults: [account-agent contracts](../../architecture/account-agent-contracts.md#session-13-authenticated-owner-tasks-and-image-content).

## Verification

Windows PowerShell/Python 3.12.3 for the 757-test affected regression, an earlier clean
152-test focused/reporting run, statics, frontend and fake evals. Locked dependencies,
PostgreSQL 16.15, fake model, mock Instagram, local media and frozen clock were used.
Those database runs used disposable `agentnest_test` on `127.0.0.1:55433`; filesystem sync
was disabled only in that temporary test container, which has been removed. This does
not claim power-loss durability. The final focused/reporting rerun uses Python 3.12.16
in a disposable `python:3.12-slim` container, `uv sync --frozen`, and the compose test
database at `postgres:5432/agentnest_test` with normal sync settings. Windows commands
use `python -m uv` because uv is installed as a Python module. Application settings and
machine-wide network settings were not changed.

| Check | Actual result |
|---|---|
| `python -m uv run ruff check .` | Passed |
| `python -m uv run ruff format --check .` | Passed, 550 files; explicit migration lint/format also passed |
| `python -m uv run mypy app evals` | Passed, 292 source files |
| `python -m uv run lint-imports` | Passed, 19 contracts |
| Affected backend regression command below | **757 passed** |
| Final focused Session 13 + reporting command below | **153 passed** in Linux; earlier Windows run **152 passed** before the added receipt regression |
| `python -m uv run python -m evals run --all --provider fake --strict` | **166/166 passed**, no hard failures; existing bounded tasks, not real-model agent quality |
| OpenAPI export/client regeneration with SHA-256 comparison | Stable, no generated drift |
| Frontend `npm.cmd run lint`, `typecheck`, `test`, `i18n:check`, `build` | Passed; **497 tests**, 31 files; TR/EN 1,194 keys; existing bundle-size warning only |
| `git diff --check` | Passed |

Affected command from `backend/` on Windows, with
`TEST_DATABASE_URL=postgresql+psycopg://agentnest:agentnest@127.0.0.1:55433/agentnest_test`:

```powershell
python -m uv run pytest tests/integration/agent tests/integration/content tests/isolation/test_content_isolation.py tests/isolation/test_publishing_isolation.py tests/integration/commands/test_content_commands.py tests/unit/ai/test_fake_interpreter_content.py tests/unit/ai/test_draft_content_task.py tests/unit/content tests/unit/knowledge/test_templates.py -q --tb=short
```

Final focused/reporting command from the container's `/workspace/backend`, with
`TEST_DATABASE_URL=postgresql+psycopg://agentnest:agentnest@postgres:5432/agentnest_test`
and `UV_PROJECT_ENVIRONMENT=/tmp/agentnest-venv` (host `.venv` is preserved):

```sh
uv run pytest tests/integration/agent/test_owner_content.py tests/integration/agent/test_owner_content_migration.py tests/integration/content/test_agent_content_tools.py tests/integration/reporting -q --tb=short --maxfail=1 -p no:cacheprovider --basetemp=/tmp/pytest
```

An earlier affected run had 535 passes and the stale tool expectation; the clean 757-test
rerun supersedes it. Initial focused failures caught projection flush ordering and fixture
mistakes, subsequently fixed. Added isolation/journey fixtures initially reused a globally
unique mock identifier and a running goal on a queued thread; their corrected setup is in
the final focused/reporting rerun. A redundant Windows rerun stalled in Python's
`socketpair`/test-client event-loop setup; further retries hit Winsock address contention
while opening migration connections (over 15,000 local sockets were in `TIME_WAIT`).
IPv4/IPv6 retries produced setup errors, including one run with 3 passes/150 setup errors,
and were not treated as application assertion failures or passes. Final verification
moved to Linux/container networking without weakening tests or changing OS settings.
No failed/interrupted run is represented as acceptance.
The full backend suite/browser E2E were not run; their combined gate remains Session 17.

Evidence: `tests/integration/agent/test_owner_content.py`, `test_owner_content_migration.py`,
`tests/integration/content/test_agent_content_tools.py` and existing agent/content/isolation/
reporting regressions. Strict fake reports: ignored generated files
`backend/evals/reports/20261029T094351Z-fake.{md,json}`.
The final container log is saved at `%TEMP%\agentnest-s13-final-linux.log`.
Both temporary verification containers were removed after their runs.

## Acceptance and demo

- **AC75-13, offline backend scope:** image preparation; separate schedule/publication
  modes; explicit version-2 approvals; story-only capability; deadlines/quota rechecks;
  manual resubmission; stale media/content/fact fences and verified mock publication.
  The scripted coordinator journey waits for publication before completing its goal.
- **AC75-16, content scope:** timeout after successful publication remains unknown until
  same-container reconciliation; revocation cannot cause another post. Existing retry,
  crash and reconciliation regressions remain included.
- **AC75-24, offline backend scope:** authenticated task intake and true requester roles,
  staff restrictions, member revocation, existing foreign-account/task isolation, composite
  FK rejection, versioned/idempotent clarification and actual coordinator continuation.
  Browser and real-model acceptance remain pending later sessions.

Credential-free demo: deliberately activate/delegate the mock account through the existing
controls, upload/select an existing JPEG, and POST a task with its request UUID and optional
exact asset/content selections. Run the worker and inspect GET task/action. Answer a
clarification using its question version and an independent request UUID. Use the approvals
decision endpoint and displayed hash for ask-required actions. Inspect scheduled status;
the automated test harness advances the frozen clock and executes publication. Only a
verified operation reports published. Repeat with ask/off publishing, revocation before
due time or injected timeout-after-success and reconciliation.

The fake provider requires scripted steps; an unscripted natural-language task visibly
hands off. This session does not claim real-model planning or tool-selection quality.

## Handoff

Migration head: `0030`. Stable task/answer/action-preview APIs and generated types are ready
for Session 14's settings/overview UI, then Session 15's task/question experience. Those
sessions are not started. Existing research, model, platform and founder gates remain open;
no new live capability or grant was enabled. Full phase acceptance is not claimed.
