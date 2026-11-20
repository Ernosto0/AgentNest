# Session 05 report: Approval ladder suggestions (D-02)

**Status:** Implemented, uncommitted in the `s05` worktree. Not yet verified against a real Instagram account or a pilot workspace (no real approvals have been counted).
**Baseline commit:** `20a0551`. **Migration head before:** `0048`. **Migration added:** `0053` (`20261116_0053_delegation_suggestions.py`, `down_revision = "0048"`; the orchestrator re-chains it).

## What it does

- A weekly job (`delegation_suggestion`, per active workspace, from Monday 09:00 workspace-local time) counts, per reply topic and per connected real legacy-controlled account, drafts in the last `DELEGATION_SUGGESTION_WINDOW_DAYS` (28) days. A draft is positive evidence only if the assistant wrote it (`source = ai`, `origin = legacy`, not simulated), it was **sent**, never edited (version 1, no `OWNER_EDIT`), and a signed-in owner approved it through web or Telegram with an approval bound to that exact version and the recomputed payload hash. Edits, rejections and failures are counted separately.
- A topic qualifies with at least `DELEGATION_SUGGESTION_MIN_UNCHANGED` (20) unchanged approvals and zero edits, rejections or failures.
- Only `hours`, `location_contact` and `services` can be suggested (`SUGGESTIBLE`), only when the class is currently on `approval`, and only when readiness allows `auto` (`policy.service.auto_allowed`). Price, booking, promotion and FAQ/greeting classes are never suggested; complaint, refund, discount and sensitive intents have no automation class at all. Mock accounts, agent-controlled accounts and simulated drafts are excluded.
- At most one suggestion and one `delegation_suggestion` notification per workspace per local week (`unique (workspace_id, week)` plus the notification dedup key). The notification goes to the first active owner, with params `{account_id, intent}` only, routed under quiet hours, never pushed.
- Confirming uses the existing `POST /accounts/{id}/agent/delegation/preview` then `/apply` with the suggestion's own `DelegationChange` (new optional `suggestion_id`). Preview binds a hash to the owner; apply refuses without it and re-checks everything (still pending, not expired, still on approval, readiness, no new edit/rejection/failure, account still legacy, body equals the proposal). On success it writes the usual delegation version (the agent grant is unchanged), sets the class to `auto`, and audits. Free text cannot confirm anything; no endpoint accepts text.
- "Not now" (`POST /delegation-suggestions/{id}/dismiss`) records a cool-down (`DELEGATION_SUGGESTION_COOLDOWN_DAYS`, 30) for that class. Accepting also sets a cool-down, so a topic the owner later reverts is not re-proposed at once. Unanswered suggestions become `expired` at the next run.
- UI: a card (`DelegationSuggestionCard`, own component file) on Today and on the Assistant overview, owner only. Review, then "Turn on automatic replies"; "Not now" dismisses. Turkish and English.

## Files

Added
- `backend/app/agent/suggestions.py` (the Codex draft, reworked), `backend/app/agent/suggestions_router.py`
- `backend/migrations/versions/20261116_0053_delegation_suggestions.py`
- `backend/tests/integration/agent/test_delegation_suggestions.py`, `backend/tests/isolation/test_delegation_suggestions_isolation.py`
- `frontend/src/features/agent/DelegationSuggestionCard.tsx`, `ladderHooks.ts`, `ladder.test.tsx`
- `frontend/src/i18n/locales/{en,tr}/suggestions.json`

Changed
- Backend: `agent/models.py` (`DelegationSuggestion`), `agent/delegation.py` (`DelegationChange.suggestion_id`, preview takes a `clock`, apply hooks), `agent/router.py` (preview commit, `DelegationPreview.automation_class`), `api/router.py`, `handlers.py`, `core/config.py`, `core/db.py` (tenant table list), `notifications/catalog.py`, `notifications/delivery_policy.py`, `activity/groups.py`, `activity/classify.py`, `core/i18n/{en,tr}.json`, `tests/unit/core/test_rls_policies.py` (56 to 57 tables).
- Frontend: `openapi.json` (full export; the baseline matched the exporter, so the diff is only the new paths and schemas), `api/schema.d.ts` (regenerated), `features/agent/AgentPage.tsx` and `features/home/Dashboard.tsx` (one insertion each), `features/notifications/{describe.ts,target.ts,catalog.json}`, `i18n/index.ts`, `i18n/locales/{en,tr}/ai.json`, `test/mockApi.ts` (a background default for the new list route).
- Docs and config: `.env.example`, `docs/operations/environment-variables.md`, `docs/architecture/{api-design,background-jobs,data-model,observability}.md`, `docs/product/mvp-scope.md`. `backend/pyproject.toml` still has the orchestrator's D-01 line, untouched.

## Contracts

- **Table** `delegation_suggestions` (tenant, RLS forced, migration 0053).
- **API** (owner only, `agent.delegation.manage`): `GET /workspaces/{ws}/delegation-suggestions` (`SuggestionList{items: SuggestionOut}`), `POST /workspaces/{ws}/delegation-suggestions/{id}/dismiss` (`SuggestionDismissed`). `DelegationChange.suggestion_id` (optional); `DelegationPreview.automation_class` (optional).
- **Reason codes** (409 `CONFLICT_STATE`, `params.reason`): `suggestion_preview_required`, `suggestion_not_pending`, `suggestion_ineligible`, `suggestion_missing`; `VERSION_CONFLICT` when the body differs from the proposal.
- **Settings**: `DELEGATION_SUGGESTION_WINDOW_DAYS=28`, `DELEGATION_SUGGESTION_MIN_UNCHANGED=20`, `DELEGATION_SUGGESTION_COOLDOWN_DAYS=30`.
- **Job**: `delegation_suggestion` (`{workspace_id, week}`, 3 attempts), periodic dedup key `delegation_suggestion:{ws}:{week_monday}`.
- **Notification type**: `delegation_suggestion` (info).
- **Audit actions**: `agent.delegation_suggested`, `agent.delegation_suggestion_previewed`, `agent.delegation_suggestion_accepted`, `agent.delegation_suggestion_dismissed`; accept also writes `policy.updated` and `agent.delegation_applied` (with `changed_actions: []`).

## Tests and checks

Test database env: `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN= OPENAI_API_KEY= PYTHONUTF8=1`, `TEST_DATABASE_URL` set to the `pivoris_p2s05*_test` databases.

- `pytest tests/integration/agent/test_delegation_suggestions.py`: 44 passed (threshold 19/20, edit/rejection/failure blockers, forbidden intents, off/auto skip, readiness, mock and agent-controlled accounts, one per week, expiry, preview/apply flow, tamper, stale evidence, role checks, idempotent repeat, dismissal and cool-down, job gating and run).
- `pytest tests/isolation/test_delegation_suggestions_isolation.py`: 6 passed (forced RLS, fail-closed, cross-workspace write and FK, one per week, foreign owner gets 404).
- `pytest tests/unit tests/isolation tests/security tests/contract`: 2003 passed, 13 skipped, 3 failed: `test_phase6_isolation::test_the_dev_job_listing_of_a_never_shows_the_jobs_of_b` and `test_publishing_isolation::test_the_simulator_listing_of_a_never_shows_what_b_published` fail with 404 because dev routes are off in this environment; both pass with `DEMO_TOOLS_ENABLED=true`. `test_invite_secrets` failed once in the full run and passed on rerun alone. None touch this work.
- `pytest tests/integration/agent tests/integration/notifications tests/integration/policy tests/integration/activity tests/integration/jobs tests/integration/approvals`: 590 passed.
- `pytest tests/integration/retention tests/integration/identity tests/integration/operations tests/integration/test_seed.py tests/integration/test_hardening_integration_regressions.py`: 197 passed, 1 failed. The failure is `identity/test_members_and_invites.py::test_owner_creates_an_invite_with_a_one_time_link`: the worktree `.env` sets a public base URL (a trycloudflare host) where the test expects `http://localhost:8000`. It is an environment mismatch unrelated to this work.
- Backend static: `ruff check`, `ruff format --check`, `mypy app` (362 files), `lint-imports` (23 kept): all clean.
- Frontend: `npm.cmd run lint`, `typecheck`, `i18n:check` (2454 keys) clean; `ladder.test.tsx` 9 passed; full `npm.cmd test`: 53 files, 794 tests passed; `npm.cmd run build` succeeded.

## Invariants

INV-01 RLS plus composite FK and 404 on foreign IDs; INV-04/16 the suggestion is only a proposal, authority is the owner's own preview-then-apply, bound by hash and re-validated, free text never confirms; INV-09 simulated drafts and mock accounts never count; INV-12 every step audited in the same transaction; INV-19 weeks and the Monday 09:00 start use the workspace timezone, times from `Clock`; no external calls anywhere in the job.

## Deviations and decisions

- The brief says confirm "opens the delegation preview and applies it". The delegation endpoints govern the agent's grant, while per-topic reply automation lives in `automation_policies`. So a suggestion's apply creates an unchanged delegation version (legacy accounts have no running agent work, so the epoch bump is harmless) and flips the topic's policy. The audit shows `changed_actions: []`. This coupling is the main thing to review.
- Only three topics are suggestible; `general_faq` (FAQ and greeting share a class) is excluded on purpose.
- Confirming re-checks only for new negative signals, not the count, so old approvals ageing out of the window do not void a card the owner was shown.
- The weekly job waits until Monday 09:00 local so the notification is not delivered at night.
- Notification type is `delegation_suggestion` (no dot), as the brief suggested; other types are dotted.

## Open questions and limits

- Only the first active owner is notified and can confirm (`agent.delegation.manage` is owner-only).
- A workspace has one active account today; per-account counting is implemented but only exercised with a disconnected second account in tests.
- Evidence for approvals older than the retention scrub of draft text will not match the hash and will not count (conservative).
- The 20/28-day thresholds are defaults, not tuned on pilot data.
- No Web Push for this type (not in `PUSH_TYPES`). Say if you want it.
- Playwright E2E was not run or added.
- Orchestrator merge note: two shared-file hotspots are `frontend/src/i18n/index.ts` (one import pair and the spread) and `frontend/openapi.json` / `schema.d.ts` (regenerate after merging).
