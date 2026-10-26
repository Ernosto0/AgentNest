# Architecture Decision Records

Each ADR records one significant decision: its context, the alternatives, the choice, the trade-offs, the consequences for implementation, and the conditions that would justify revisiting it.

**Rules**
- ADRs are immutable once accepted. To change a decision, write a new ADR that supersedes the old one, and set the old one's status to `Superseded by ADR-XXX`.
- Implementation must follow accepted ADRs. If a phase task conflicts with an ADR, stop and raise it. Do not silently deviate.
- `Provisional` means the decision is the default until a named open question ([open-questions.md](../../research/open-questions.md)) is resolved. Implementation may proceed, but must keep the decision easy to reverse.

| ADR | Title | Status |
|---|---|---|
| [ADR-001](ADR-001-modular-monolith.md) | Modular monolith with a separate worker process | Accepted |
| [ADR-002](ADR-002-repository-structure.md) | Monorepo layout: `backend/`, `frontend/`, `docs/` | Accepted |
| [ADR-003](ADR-003-backend-stack.md) | Python 3.12, FastAPI, synchronous SQLAlchemy 2.0, Pydantic v2, uv | Accepted |
| [ADR-004](ADR-004-postgresql-only-datastore.md) | PostgreSQL as the only datastore (no Redis in MVP) | Accepted |
| [ADR-005](ADR-005-sync-api-vs-background-jobs.md) | What runs in the request vs in background jobs | Accepted |
| [ADR-006](ADR-006-postgres-job-queue.md) | PostgreSQL-backed job queue and scheduler | Accepted |
| [ADR-007](ADR-007-deterministic-workflows-bounded-llm-tasks.md) | Deterministic workflows with bounded LLM tasks (legacy controller) | Superseded by ADR-024 for account-agent coordination |
| [ADR-008](ADR-008-structured-business-knowledge.md) | Structured, versioned business facts with placeholder rendering | Accepted |
| [ADR-009](ADR-009-llm-provider-abstraction.md) | Thin LLM provider abstraction with structured outputs and a deterministic fake | Superseded by ADR-024 only for no-tool/single-method restriction |
| [ADR-010](ADR-010-instagram-provider-adapter.md) | Instagram provider interface; mock and Meta (Instagram Login) adapters | Accepted |
| [ADR-011](ADR-011-external-operations-ledger.md) | Write-ahead external operations ledger and reconciliation | Accepted |
| [ADR-012](ADR-012-owner-channel-abstraction.md) | Owner channel abstraction; web first | Accepted (channel #2 provisional, OQ-01) |
| [ADR-013](ADR-013-authentication-and-tenancy.md) | Built-in session auth; shared-schema multi-tenancy with composite keys | Accepted |
| [ADR-014](ADR-014-approval-and-policy-model.md) | Deterministic policy engine and version-bound approvals | Superseded by ADR-024 only for agent authority defaults; exact approvals retained |
| [ADR-015](ADR-015-media-storage.md) | Media storage abstraction: local filesystem and S3-compatible | Accepted |
| [ADR-016](ADR-016-localization.md) | Localisation: three locale concepts, catalogs on both tiers | Accepted |
| [ADR-017](ADR-017-configuration-and-secrets.md) | Environment-based configuration, startup safety checks, encrypted tokens | Accepted |
| [ADR-018](ADR-018-observability-and-evaluation.md) | Structured logs, correlation IDs, error catalog, versioned AI evals | Accepted |
| [ADR-019](ADR-019-open-source-and-hosted-boundary.md) | One codebase; hosted-only features as optional modules; license undecided | Provisional (OQ-02) |
| [ADR-020](ADR-020-frontend-stack.md) | React + TypeScript + Vite SPA, TanStack Query, generated API client | Accepted |
| [ADR-021](ADR-021-simulation-provenance-boundary.md) | Provider-result provenance; neutral uploads and internal simulator state | Accepted |
| [ADR-022](ADR-022-privacy-redaction-and-audit-retention.md) | Bounded privacy erasure; append-only audit retention | Accepted |
| [ADR-024](ADR-024-account-agent-and-delegated-autonomy.md) | Account agent with memory and delegated autonomy | Accepted target; implementation pending |
