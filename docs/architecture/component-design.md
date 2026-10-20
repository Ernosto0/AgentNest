# Component Design

**Purpose:** Backend modules, their responsibilities, their public interfaces and the dependency rules between them, plus the frontend structure. A coding agent uses this to decide **where code goes** and **what it may import**.

## 1. Backend package layout

```
backend/app/
├── main.py                 # create_app(): FastAPI app, routers, middleware, exception handlers
├── worker.py               # python -m app.worker: worker loop + scheduler
├── cli.py                  # python -m app.cli: seed, reset, simulate, run-due-jobs, generate-key, create-user
├── core/                   # cross-cutting, no domain knowledge
│   ├── config.py           # Settings (pydantic-settings) + startup safety checks
│   ├── db.py               # engine, SessionLocal, Base, naming conventions
│   ├── context.py          # WorkspaceContext, ActorRef (user|system|agent|provider)
│   ├── clock.py            # Clock protocol, SystemClock, FrozenClock
│   ├── ids.py              # uuid generation helpers
│   ├── errors.py           # AppError + error code catalog
│   ├── logging.py          # structlog config, redaction, contextvars binding
│   ├── security.py         # password hashing, session tokens, CSRF, AES-GCM token crypto
│   ├── i18n/               # t(key, locale, **params), tr.json, en.json, Babel formatting helpers
│   └── canonical.py        # canonical JSON + sha256 (payload hashes)
├── identity/               # users, sessions, workspaces, memberships, permissions, invites
├── audit/                  # audit_logs writer + activity feed queries
├── jobs/                   # jobs table, enqueue(), worker runtime, scheduler, handler registry
├── knowledge/              # facts, versions, candidates, templates, readiness, renderer, claims validator, approved answers, impact analysis
├── ai/                     # LLM task definitions (prompts, schemas, context builders, post-validators), task runner, agent_runs
├── commands/               # owner_commands, command registry, reference resolver, executors
├── approvals/              # approvals service, expiry sweep
├── policy/                 # policy engine, rules, automation_policies
├── inbox/                  # webhook ingestion, inbound processing, conversations, messages, reply drafts
├── content/                # content items, media assets + validation, scheduling
├── operations/             # operations ledger, executors (send_reply, publish_content), reconciliation, account health
├── notifications/          # notifications + delivery (web; telegram later)
├── reporting/              # metric definitions, daily reports, activity queries
├── integrations/
│   ├── instagram/          # base.py (protocol, types, errors), mock.py, meta.py, webhook_format.py
│   ├── llm/                # base.py, fake.py, openai_provider.py
│   ├── storage/            # base.py, local.py, s3.py
│   └── channels/           # base.py, web.py, telegram.py (Phase 9)
├── demo/                   # seed data (YAML), simulator scripts, reset, dev routes (mounted only if DEMO_TOOLS_ENABLED)
└── api/                    # router assembly, shared dependencies (auth, membership, pagination), problem+json handlers
```

Each domain module uses the same internal shape where applicable:
- `models.py`: SQLAlchemy models.
- `schemas.py`: Pydantic API schemas.
- `service.py`: public functions; transaction boundaries.
- `repository.py`: queries; always takes `WorkspaceContext`.
- `router.py`: FastAPI routes; thin.
- `jobs.py`: job handlers registered with `jobs`.

## 2. Module responsibilities and public interfaces

Only the functions listed (and their obvious siblings) are called from other modules. Everything else is module-private (by convention, prefixed `_` or not exported from `__init__`).

| Module | Owns (tables) | Responsibility | Key public interface |
|---|---|---|---|
| `core` | — | Config, DB session, clock, errors, logging, security, i18n, canonical hashing | `get_settings()`, `Clock`, `AppError(code, **params)`, `t()`, `payload_hash(obj)` |
| `identity` | `users`, `sessions` (model `AuthSession`), `workspaces`, `workspace_members`, `invites` | Auth, membership, roles, permissions | `login()`, `resolve_session()`, `create_workspace()`, `update_workspace()`, `has_permission(role, perm)`. The FastAPI dependency `require_membership(permission)` lives in `api/deps.py` (it reads `workspace_id` from the path and returns `WorkspaceContext`; `permission=None` allows any member) |
| `audit` | `audit_logs` | Append-only audit records, activity feed | `audit.record(session, ctx_or_none, action, resource_type, resource_id, metadata={}, is_simulated=False, correlation_id=None, *, clock=None, actor=None, workspace_id=None)`. Must be called inside the caller's transaction (it flushes, never commits). Without a `ctx` the entry is system-level unless `actor`/`workspace_id` are given (e.g. `auth.login`: actor = the user, no workspace). `occurred_at` comes from `clock` |
| `jobs` | `jobs` | Queue, worker runtime, scheduler | `enqueue(session, job_type, payload, *, workspace_id, correlation_id, run_at=None, dedup_key=None, priority=100, max_attempts=None, clock=None)`, `@job_handler("type", payload_model, max_attempts=3, timeout=None, on_dead=None, backoff=None)`, `run_due_jobs(clock, limit=100, *, session_factory=None)` (tests/dev) |
| `knowledge` | `business_facts`, `fact_versions`, `fact_candidates`, `approved_answers`, `fact_references` | Fact lifecycle, conflicts, readiness, rendering, claim validation, impact analysis | Phase 2 (all take `session, clock, ctx` first and commit): `create_fact`, `update_fact(fact_id, expected_version, value=UNSET, valid_from=UNSET, valid_until=UNSET, …)`, `verify_fact`, `archive_fact`, `restore_fact`, `accept_candidate`, `reject_candidate`, `usable_facts(categories?, on_date?, locale?)`, `fact_views`/`candidate_views`/`version_views`/`template_checklist` (read models for the API), `insert_trusted_fact` (seed only), `candidates.propose_candidate`, `candidates.recompute_relations`, `readiness.readiness`/`compute_readiness` (pure). `update_fact` and `create_fact` route staff to a candidate. Internal modules: `transitions` (the only place fact/candidate states change), `usability` (pure usable/state/local-date rules), `values`, `parsing`, `formatting`, `templates`. Phase 3: `render.render(template, usable_facts, locale) → RenderResult{text, used, spans, errors}` (all-or-nothing, `FACT_NOT_USABLE`), `claims.validate_claims(text, render_result, locale, *, allow_suffix_span=None) → ClaimReport` (+ `byte_length`, `length_issue`), `impact.analyze_impact(session, ctx, fact_id) → ImpactReport` and `impact.apply_change` over a `ReferrerHandler` registry (`register_handler`; no handler of its own yet; every fact update and archive propagates through it), `impact.replace_references` / `references_to_fact`, `apply_update(…)` (the non-committing `update_fact`, for callers that own a transaction), `extraction.start` / `status_of` / `plan_candidates` / `store_candidates` and the `extract_fact_candidates` job. `knowledge` modules other than `extraction` never import `ai`, `approvals` or `commands` (import-linter) |
| `ai` | `agent_runs` | LLM tasks and runner | `run_task(deps, ctx, task_definition, input, correlation_id, *, job_id=None, agent_run_id=None) → TaskOutcome` (raises `RetryableError` for transient provider errors; budget, run row committed before the call, one repair call), `execute_task(provider, task, input, model)` (the DB-free call/validate/repair loop that evals reuse), `create_queued_run`, `runtime.runner_deps(session_factory, clock)` / `override_runtime(...)` (tests), `injection.detect_injection` / `neutralise_untrusted`, `prompt` helpers, `tasks/interpret_command.py` and `tasks/extract_fact_candidates.py` (definition + fake), `jobs.sweep_agent_runs`. Only `ai` imports `integrations.llm` |
| `policy` | `automation_policies` | Deterministic decisions | `evaluate_reply(ctx, ReplyPolicyInput) → Decision`, `evaluate_content(ctx, ContentPolicyInput) → Decision`, `get_policies(ctx)`, `set_policy(...)` |
| `approvals` | `approvals` | Create, decide, expire, invalidate | `request(session, clock, ctx, *, kind, action, subject_type, subject_id, subject_version, payload, summary, required_permission, expires_at, execute_before=None)` (no commit), `decide(session, clock, ctx, approval_id, *, decision, payload_hash, note=None, channel="web")` (commits; callback in the same transaction), `cancel_for_subject(session, clock, ctx, subject_type, subject_id, reason)`, `assert_executable(session, clock, ctx, approval_id, subject_version, *, operation_id=None)`, `expire_due_in_workspace` (lazy expiry on reads), `callbacks.register(subject_type, on_decided, *, current_version, status_of)`, `guards.decision_blocker` (pure), `transitions`, job `expire_approvals`. Knows no subject module |
| `commands` | `owner_commands` | Submit, interpret (via `ai`), clarify, confirm (via `approvals`), execute | `submit(session, clock, ctx, *, text, client_request_id, channel="web")`, `prepare_interpretation` / `finish_interpretation` (the job's two short transactions around the model call), `answer_clarification`, `cancel`, `get_command` / `list_commands` (lazy expiry), `on_approval_decided` (registered as the `owner_command` approval subject). `registry.REGISTRY` is the closed list of command types (no approve, publish or send); `resolver` is pure (catalog check, value re-parse, clarification); `transitions`; executors under `executors/` (Phase 5 adds `content.create_draft`, `content.cancel_scheduled` with the `command.cancel_content` confirmation, `query.content_status` and `query.explain_failure`; the `ContentRef` resolver turns "tomorrow's story" into an item). Reached only from the API, the handler loader and the worker (import-linter, INV-03) |
| `inbox` | `inbound_events`, `conversations`, `messages`, `reply_drafts` | Webhook ingestion, conversation state, draft workflow | `ingest_webhook(session, clock, settings, provider_kind, raw_body, headers) → IngestResult` (commits; shared by the HTTP routes and the simulator; only verifies and parses, so it needs no provider instance), `process_inbound_event(event_id)`, `draft_reply(conversation_id)`, `submit_manual_reply(...)`, `takeover()/release()` |
| `content` | `content_items`, `media_assets` | Drafting, media, validation, scheduling | Phase 5 (all take `session, clock, ctx` first and commit): `media.ingest`, `service.create_draft(…, client_request_id) → (item, created)`, `service.update(content_id, expected_version, fields)` (a payload change is a new version and voids the approval, state-machines §5), `service.get_item` / `list_items(tab, status)` / `validate`, `grounding.check` (claim validation + `fact_references`), `views.item_out`. `transitions.next_status` (pure) and `transitions.apply` are the only way a status changes. `hooks` is how cancel and hold reach the operations ledger without importing `operations`: `operations` registers `LedgerHooks(operation_summary, cancel_operation)` at startup. Submission (P5-04): `service.submit(session, clock, settings, ctx, content_id, schedule=, self_approve=, expected_version=)` (validation per G17 in the pure `validation.py` / `scheduling.py`, canonical payload in `payload.py`, self-approval or a pending `content.publish` approval, queues `publish_content`), `service.reapprove(...)`, `service.cancel(...)`, `service.validate(...)` (dry run); `subject.py` registers `content_item` as an approval subject (approve schedules, reject rejects, expire returns to draft); `notifications.notify(...)` defines `content.on_hold` / `content.published` / `content.failed`. Generation (P5-03a): `generation.*` (the `generate_content` job: render, claim validation, save as an `edit`), reached from `POST /content-items/generate` and the `content.create_draft` command executor. Fact changes (P5-07): `impact_handlers.ContentItemReferrers` registered with the knowledge impact registry (`scheduled` / `retry_scheduled` → `on_hold`, `pending_approval` → `draft`, `draft` → `validation.stale`; never `publishing` or `published`). `content` never imports `operations`, `commands` or the API layer (import-linter) |
| `operations` | `operations`, `sim_*` (via mock), account health fields | Execute external side effects, reconcile, account health and circuit | `execute_send_reply(draft_id)`, `publish.execute_publish(session_factory, clock, settings, workspace_id, content_id, version, *, provider, sleep, heartbeat)`, `publish.reconcile_publish(...)`, `reconcile(operation_id)`, `record_provider_failure(account, error)`. `content_ledger` registers the `content.hooks` (operation summary, cancel of a waiting operation) at startup |
| `notifications` | `notifications`, `notification_deliveries` (Phase 9) | Create, list, mark read, deliver | `notify(session, clock, ctx, *, recipient_user_id, type, severity, params, subject_type, subject_id, dedup_key, is_simulated)` (an unread duplicate returns `None`), `notify_permission_holders(..., permission, exclude_user_id=None)`, `list_notifications`, `mark_read`, `mark_all_read` |
| `reporting` | `daily_reports` | Metric definitions and aggregation | `compute_metrics(ctx, period) → Metrics`, `generate_daily_report(ctx, local_date)`, `activity_summary(ctx, period)` |
| `integrations.*` | `social_accounts` (instagram), `channel_links` (channels) | Provider adapters | Protocols in [integrations.md](integrations.md) |
| `demo` | — | Seed, simulator, reset, dev routes | `seed()`, `reset(workspace_id)`, `simulate_customer_message(...)`, `set_failure_rule(...)` |

## 3. Dependency rules (enforced by an import-linter test)

```mermaid
flowchart TB
  api[api / routers] --> services
  subgraph services[domain modules]
    commands --> ai
    commands --> knowledge
    commands --> approvals
    commands --> content
    inbox --> ai
    inbox --> knowledge
    inbox --> policy
    inbox --> approvals
    content --> ai
    content --> knowledge
    content --> policy
    content --> approvals
    operations --> inbox
    operations --> content
    reporting
    knowledge
  end
  services --> audit
  services --> jobs
  services --> notifications
  services --> core
  ai --> llm[integrations.llm]
  operations --> ig[integrations.instagram]
  inbox --> igw[integrations.instagram webhook parsing only]
  content --> storage[integrations.storage]
  audit --> core
  jobs --> core
```

Rules:
1. `core` imports nothing from the app.
2. `integrations.*` import only `core`. They know nothing of domain tables except their own (`social_accounts`, `channel_links`, `sim_*`).
3. **Only `operations` may call side-effecting `InstagramProvider` methods** (`send_text_message`, `create_media_container`, `publish_container`, `refresh_token`). `inbox` may use `verify_signature` and `parse_webhook`. Reads used for reconciliation are also only in `operations`. ([INV-15](../invariants.md))
4. **Only `ai` may import `integrations.llm`.**
5. Routers call services only. No queries and no provider calls in routers.
6. Domain modules call each other only through the public interfaces above. Circular imports are resolved by callbacks registered at startup (e.g., `approvals` emits "decided" to a registry, and `commands`, `inbox` and `content` subscribe), not by importing back.
7. `demo` may import anything but must not be imported by anything except `main.py` (conditional mount) and `cli.py`.

## 4. Transaction boundaries

- **One request = one transaction** for synchronous state changes, committed by the service function at the end. Audit entries, approvals, notifications and job enqueues are written in the **same** transaction.
- **Job handlers** open their own transactions. A handler that performs an external call uses **at least two transactions**: (1) mark the operation `in_progress` and commit; (2) after the external call, record the outcome and the domain update and commit. It never holds a DB transaction open across an external call ([background-jobs.md §5](background-jobs.md)).
- Row locks (`SELECT … FOR UPDATE`) on the subject (content item, reply draft) when changing its state, to serialise concurrent workers and user actions.
- State transitions use **conditional updates** (`UPDATE … WHERE id = :id AND status = :expected`) and check the affected row count, as a second guard against races.

## 5. Cross-module workflows (who orchestrates)

| Workflow | Orchestrating module | Collaborators |
|---|---|---|
| A. Onboarding | `identity` (workspace) + `knowledge` (facts, readiness) | `ai` (extraction), `integrations.instagram` (connect) |
| B. Fact update | `commands` | `ai`, `knowledge`, `approvals`, `content` (hold), `inbox` (supersede drafts), `notifications` |
| C. Incoming message | `inbox` | `ai`, `knowledge`, `policy`, `approvals`, `operations`, `notifications` |
| D. Approval | `approvals` | subject owner modules via decided-callbacks |
| E. Content scheduling | `content` | `ai`, `knowledge`, `policy`, `approvals`, `jobs`; `operations` only through `content/hooks.py` (`operations` imports `content`, never the reverse) |
| F. Daily report | `reporting` | `notifications`, `jobs` (schedule) |
| G. Integration failure | `operations` | `integrations.instagram`, `notifications`, `content` (hold), `inbox` |

Full contracts: [workflows.md](workflows.md).

## 6. Frontend structure

```
frontend/src/
├── main.tsx, app/
│   ├── router.tsx            # routes; auth guard; workspace guard
│   ├── providers.tsx         # QueryClient, i18n, auth context
│   └── layout/               # MobileShell (bottom tabs), DesktopShell (sidebar), SimulationBanner
├── api/
│   ├── schema.d.ts           # generated from openapi.json (committed)
│   └── client.ts             # openapi-fetch wrapper: credentials, CSRF header, error → AppError(code)
├── features/
│   ├── auth/  workspaces/  home/  inbox/  approvals/  content/  knowledge/
│   ├── commands/             # CommandBar, CommandResultCard, ConfirmationCard, ClarificationChips
│   ├── reports/  activity/  notifications/  settings/
│   └── dev/                  # Dev panel (route mounted only when /api/v1/meta reports demo tools enabled)
├── components/               # Button, Card, StatusBadge, SimulatedBadge, BottomSheet, EmptyState, TimeLeft, FactValueChip
├── i18n/locales/{tr,en}/*.json
└── lib/                      # formatting (Intl), dates in workspace TZ, polling helpers
```

Frontend rules:
- No business rules: the frontend never decides whether something needs approval or is valid. It renders server decisions and validation results.
- Status badges are a single component mapping server states to labels ([user-journeys.md §1](../product/user-journeys.md)).
- Every list or detail of workspace data shows `SimulatedBadge` when `is_simulated` is true.
- Money and time are displayed from server-provided values plus the workspace locale and timezone. Schedule inputs are sent as `{local_date, local_time}` and the server converts them.
