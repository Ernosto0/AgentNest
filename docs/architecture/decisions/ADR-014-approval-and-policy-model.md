# ADR-014: Deterministic policy engine and version-bound approvals

- **Status:** Superseded by ADR-024 only for topic-first agent authority and mandatory approval of every publication; legacy policy and exact human approvals retained
- **Date:** 2026-10-15

## Context
Autonomy must be configurable per action type, defaulting to supervised. The LLM must not be able to bypass approval "by generating a different tool call". Approvals must be tied to a specific operation, user, workspace and expiry. A vague "okay" must never authorise an unrelated action. The original spec does not distinguish between *confirmation* ("did the system understand my command?") and *approval* ("may this proposed action happen?").

## Decision

### 1. Policy engine (deterministic, no LLM)
`PolicyEngine.evaluate(action, context) → Decision{outcome, reasons[]}` where `outcome` ∈ `auto` | `approval_required` | `human_required` | `blocked`, and `reasons` are stable codes (e.g., `INTENT_COMPLAINT`, `GROUNDING_FAILED`, `MESSAGING_WINDOW_CLOSED`).

- **Inputs are facts computed by code**: action type, intent and flags from the validated LLM output, claim-validator result, fact usability, automation policy settings, conversation mode, messaging window, account capability and health, rate guards, injection heuristics.
- **The LLM's output can only make a decision stricter.** A model flag such as `needs_human=true` or low self-reported confidence can escalate. Nothing the model outputs can relax a rule.
- Rule order and the full rule table are in [workflows.md §C](../workflows.md) (replies) and §E (content).
- **Automation policies** (`automation_policies` table): per workspace and **action class** (`reply.hours`, `reply.location_contact`, `reply.pricing`, `reply.services`, `reply.booking`, `reply.promotions`, `reply.general_faq`, `content.publish`; the mapping from intents is in [agent-runtime.md §4](../agent-runtime.md)), mode ∈ `auto` | `approval` | `off`. Defaults: all `approval`. `content.publish` is fixed to `approval` in MVP. `auto` can only be enabled when workspace readiness is `ready`.

### 2. Approvals (one mechanism, two kinds)
Table `approvals`, with `kind` ∈:
- `confirmation`: the requesting user confirms the system's interpretation of *their own* command (e.g., "Update monthly price 6.000 ₺ → 7.000 ₺?"). Approver = requester, or anyone with the needed permission. Short expiry (default 30 minutes).
- `authorization`: an action proposed by the system (reply draft, content publication) or by a user lacking the permission. Approver must hold the action's `required_permission`.

**Binding.** Each approval stores `subject_type`, `subject_id`, `subject_version`, `payload_hash` (SHA-256 of a canonical JSON of exactly what will happen: rendered text, media IDs, target account, schedule) and `summary` (the snapshot shown to the approver).

**Decision API.** `decide(approval_id, decision, payload_hash_seen_by_user, actor)` succeeds only if all of these hold:
1. The approval belongs to the actor's workspace.
2. The actor holds `required_permission`.
3. `status = pending` (atomic conditional update; a second decision gets `409 APPROVAL_ALREADY_DECIDED`).
4. `now < expires_at`.
5. `payload_hash_seen_by_user == approvals.payload_hash` **and** the subject's current version still equals `subject_version` (otherwise `409 APPROVAL_STALE`).

**Invalidation.** Any edit to a subject increments its version and **cancels** pending approvals for it. Scheduled content affected by a fact change moves to `on_hold` and its approval is cancelled ([workflows.md §B](../workflows.md)).

**Execution eligibility.** Executors (send/publish jobs) re-check at execution time: approval `approved`, same subject version, not past the execution deadline (`execute_before`), and the operation idempotency key matches. An approval authorises exactly **one operation** (`approvals.operation_id`). Retries of that operation are covered; a new operation needs a new approval.

**Channels.** Decisions come only from explicit UI actions (web button, Telegram inline button with an opaque single-use token). Free text such as "ok", "evet" or "tamam" is **never** interpreted as a decision. The command interpreter has no "approve" command type.

**Self-approval.** A user with the permission who submits an action (e.g., the owner presses "Approve & schedule" on their own draft) creates an approval that is decided in the same request. It is recorded with the same binding, so audit stays uniform.

### 3. Expiry defaults
| Subject | `expires_at` |
|---|---|
| Command confirmation | created + 30 min |
| Reply draft approval | min(messaging window end − 5 min, created + 24 h) |
| Content publication approval | scheduled_at (if pending past the scheduled time → expired, content back to `draft` with reason `APPROVAL_EXPIRED`) |
| Content execution deadline (`execute_before`) | scheduled_at + `publish_max_delay_minutes` (default 1440 = 24 h) |

**Note (Phase 5, G16).** There is no `PUBLISH_MAX_DELAY` environment variable. The deadline is the existing **workspace setting** `publish_max_delay_minutes` (`WorkspaceSettings`, default 1440, allowed range 1 to 1440, [data-model.md §3.1](../data-model.md)), read when the item is scheduled and stored on the approval as `execute_before`, which `assert_executable` enforces. Changing the setting later does not move the deadline of an approval that already exists. A re-approval (G2) computes it again. The default was 360 (6 h) until Phase 5 follow-up Q3, which raised it to 1440 (24 h, also the maximum): a publishing quota that is exhausted for longer than the deadline ends the item as `failed (PUBLISH_DEADLINE_PASSED)` rather than waiting for the window to open, and the quota window is itself 24 h, so a 6 h default made that the usual outcome. A workspace created earlier keeps the value stored in its settings (the default applies when a workspace is created); change it with `PATCH /workspaces/{id}`.

## Alternatives considered
- Separate tables for confirmations and approvals: duplicated logic for the same safety properties.
- LLM-judged risk: non-deterministic and injectable.
- Approval by reply text ("yes"): ambiguous, replayable, unbound.

## Consequences
- `app/policy/` (engine, rules, automation settings) and `app/approvals/` (service, expiry sweep job).
- Approval cards in every channel render `summary` and carry `payload_hash`.

## Revisit when
- Multi-step approvals (e.g., staff proposes, manager reviews, owner approves) are needed. Extend with an approval chain, keeping the binding rules.
