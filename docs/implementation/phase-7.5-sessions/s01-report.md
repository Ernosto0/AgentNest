# Session 01 report: contracts and architecture alignment

**Status:** Complete. The operator accepted G7.5-A as the target contract baseline. No Phase 7.5 runtime, migration, model-quality or live-platform acceptance is claimed.

## Baseline and preserved work

- Inspected `main` at `b5cdee1` on 2026-10-26. It contains the Phase 7.5 planning commit, Phase 7 offline OAuth/storage/adapter work and the prior Gate 1 close-out. Gate 1 is recorded closed; Gate 2, Phase 7 real-account acceptance and all new Phase 7.5 capability gates remain open. No fresh OAuth work existed in the inspected worktree.
- Existing untracked `s08-report.md` is another subsession's blocked audit and was preserved untouched. No migration, runtime code, account setting, external provider call, commit or push was made in Session 01.
- Current Alembic head is `20261024_0018_general_business_categories` (revision `0018`); Session 02 must verify the head again before allocating its revision.

## Contract decisions and changes

- Accepted [ADR-024](../../architecture/decisions/ADR-024-account-agent-and-delegated-autonomy.md) as the target architecture. ADR-007 remains the legacy bounded-task behavior but its no-agent rule is superseded for the new controller. ADR-009's thin provider abstraction remains, but the single no-tool method restriction is superseded for agent steps. ADR-014's exact human approval mechanism remains, but topic-first agent authority and mandatory per-publication approval are superseded by versioned action delegation. The ADR index and statuses record this scoped supersession.
- [The canonical account-agent contract](../../architecture/account-agent-contracts.md) fixes records, enums, uniqueness and composite FKs; account versus thread controller epochs; stable intent keys independent of model wording; session/step/action transitions; job names and ID-only payloads; short transaction stages; action keys, policy grants, approval/operation names; permissions, public/private broker scope, APIs, privacy boundary and five recovery walkthroughs. Session 02 must implement against this target, updating the data model with its actual migration.
- `CLAUDE.md`, INV-03/04/16 and the security model now distinguish no-tool legacy tasks from typed agent tool **proposals**. No customer/tool/document text grants authority; the broker and executor own scope, policy, fact, capability, exact-payload and effect checks. Product vision/scope/requirements and existing architecture documents point to the staged target while retaining historical MVP behavior.
- Delegation action keys: `dm.send`, `comment.reply`, `comment.private_reply`, `comment.hide`, `comment.unhide`, `comment.delete`, `content.prepare`, `content.schedule`, `content.publish`, `content.cancel`. New comment operation types: `comment_reply`, `comment_private_reply`, `comment_hide`, `comment_unhide`, `comment_delete`; agent DMs reuse `send_reply`, image publishing reuses `publish_content`. Exact naming and full role/API matrix are in the contract.
- Session 08's export gap is explicit: only `data.export`/`data.delete` permissions exist today. Session 08 owns memory-specific export/erase service, retention and disconnect erasure; Phase 8 P8-05 owns general subject export/deletion API and cross-domain orchestration. No existing customer export route is claimed.

## Research and provisional assumptions

R75-01 through R75-06 are opened in [platform-capabilities.md §1.8](../../research/platform-capabilities.md). Official Meta webhook, comment-moderation and messaging pages responded to unauthenticated HEAD requests on 2026-10-26; an old private-replies path returned HTTP 404. The OpenAI function-calling guide responded after redirect. This is reachability only; no page content, permissions, event shape, real account or provider outcome was verified. Comment and private-reply mocks remain provisional, real new-capability flags remain off. Session 04 selects and fixture-tests a production model transport; Session 16 refreshes primary Meta text and authentic sanitized evidence; Session 18 proves application workflows on an authorized account.

## Verification and acceptance scope

- Reviewed the normal DM, owner wait/answer, autonomous comment deletion, private reply and uncertain-operation transitions in the contract. Each now names its source event, state, exact authorization path, deadline/eligibility check and restart or reconciliation outcome. This is design inspection, not runtime proof.
- Documentation-only work has no runtime tests. The command `python - <<'PY' ...` (a local Markdown relative-link existence check over every changed Markdown file, plus the new contract/report) checked **223** relative links and found **0** missing. `git diff --check` exited 0. These checks validate paths and whitespace, not external URL contents or implementation behavior.
- Official-page reachability check: `curl -L -I -sS --max-time 12` returned 200 for the Meta webhook, comment-moderation and messaging pages and the redirected OpenAI function-calling page; the old private-replies path returned 404. The exact R75 research questions remain open in the platform register.
- G7.5-A is operator accepted as a contract baseline. No AC75 behavior is proved by documents alone. The open platform/model/live gates are not represented as passes.

## Session 02 handoff

Read this report, [account-agent-contracts.md](../../architecture/account-agent-contracts.md), the common session rules, and the Session 02 brief. Confirm the current head and preserve the legacy controller. Add `account_agents`, immutable `agent_delegations`, `agent_threads`, `agent_events`, `agent_sessions`, `agent_steps` and `agent_actions` with composite workspace/account integrity and documented unique/index rules. Add nullable step link to `agent_runs` and nullable action origins to existing reply/content rows; backfill existing accounts to `legacy`/`inactive` with no grants. Implement event-plus-job enqueue, compare-and-swap transitions and stable intent admission with commit-level isolation/race tests. Keep customer-memory, owner-request and comment tables for their owning later sessions unless a finalized FK forces a small skeleton. No commit/push/live action is implied.
