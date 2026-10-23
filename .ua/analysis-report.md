# AgentNest knowledge graph

AgentNest is a Turkish-first, mobile-first Instagram operations assistant for small businesses. It maintains verified business knowledge, drafts grounded customer DM replies, prepares and schedules content with explicit approvals, and reports outcomes with credential-free simulated integrations.

Analyzed at 2026-10-23T10:49:00.846Z. Base Git commit: 5c71606429c3aa355afe428b08677bcac892659b.

Coverage: **827/827 included files**, 5,245 nodes, 18,842 edges, 10 architectural layers, 15 guided tour steps.

4 files were excluded by additional ignore rules, beyond built-in exclusions. Secrets, runtime/dependency directories and generated API artifacts were excluded by the confirmed .understandignore.

## File categories

| Type | Count |
|---|---:|
| code | 656 |
| infra | 2 |
| docs | 113 |
| config | 50 |
| data | 1 |
| markup | 4 |
| script | 1 |

## Node types

| Type | Count |
|---|---:|
| file | 662 |
| function | 3959 |
| class | 459 |
| pipeline | 1 |
| document | 113 |
| service | 1 |
| config | 50 |

## Relationship types

| Type | Count |
|---|---:|
| contains | 4709 |
| exports | 4042 |
| imports | 2537 |
| calls | 6271 |
| inherits | 98 |
| tested_by | 633 |
| triggers | 3 |
| documents | 477 |
| depends_on | 1 |
| configures | 50 |
| serves | 2 |
| migrates | 19 |

## Architecture

- **Workspace Web Application** (125 assigned nodes): Authenticated React workspace screens, shared components, API client, hooks and local formatting present knowledge, approvals, inbox, content and operational reporting.
- **Public Landing Page** (13 assigned nodes): The separately built public React site presents the bilingual product demonstration and pilot signup independently of the authenticated workspace application.
- **HTTP API & Contracts** (31 assigned nodes): FastAPI routers, request and response schemas, authentication dependencies and error middleware expose workspace-scoped services through explicit safe response contracts.
- **Domain Workflows & Policy** (134 assigned nodes): The modular monolith coordinates identity, verified business knowledge, commands, approvals, grounded AI proposals, inbox drafts, content planning, reporting and retention through deterministic policy.
- **External Operations & Adapters** (32 assigned nodes): Ledger-backed reply sends and media publications perform provider effects through Instagram, LLM and media-storage adapters with account health, bounded retries and outcome reconciliation.
- **Data & Persistence** (38 assigned nodes): SQLAlchemy models, tenant-scoped repositories and shared queries, database sessions, Alembic revisions and local SQL initialization enforce durable workspace isolation and lifecycle constraints.
- **Runtime & Shared Foundations** (21 assigned nodes): API and worker bootstraps, the PostgreSQL job queue, scheduler, handler registries and shared clocks, context, security, canonical hashing and localization support the monolith.
- **Verification & Evaluations** (262 assigned nodes): Backend contract, unit, integration, security and tenant-isolation tests, AI evaluation runners and browser and component tests verify approvals, grounding and side-effect idempotency.
- **Configuration & Deployment** (58 assigned nodes): Project manifests, compiler and build tools, localization and fixture catalogs, demo and knowledge configuration, PostgreSQL Compose, CI checks and dashboard tooling configure reproducible local operation.
- **Architecture & Product Documentation** (113 assigned nodes): Product requirements, invariants, architecture decisions, workflow and API contracts, bounded-task prompt templates, implementation reports and operational guides explain AgentNest behavior and development decisions.

## Guided tour

1. **Understand the Product** — Start with the project overview: AgentNest helps small businesses manage Instagram knowledge, customer replies and scheduled content in a Turkish-first experience. The architecture document connects the workspace interface, FastAPI API and background worker, giving you a map for the workflows that follow. The current local demonstration uses simulated integrations.
2. **Trace the Runtime Entrypoints** — With the process map in mind, follow the API factory as it installs middleware, routes, startup checks and handler registration. The worker entrypoint initializes the same application foundations for background execution, while typed settings select configuration and reject unsafe production combinations. These two processes share domain services rather than duplicating business policy.
3. **Establish Workspace Boundaries** — Before following a business workflow, understand how explicit workspace and actor context travels through requests and jobs. Authentication services establish identity, and SQLAlchemy sessions and tenant-safe model conventions support isolated persistence. The injected UTC clock is a widely shared dependency that makes time-sensitive workflows reproducible, while the data-model document explains durable relationships and constraints.
4. **Explore the User Interfaces** — The React entrypoint mounts the providers and routes that expose the backend workflows to authenticated workspace members. The application shell makes navigation, notifications and commands available across desktop and phone layouts, while the simulation banner keeps the integration mode visible. The public landing application is built separately and presents a bilingual demonstration and pilot signup rather than participating in workspace operations.
5. **Ground Work in Verified Facts** — The workspace first needs durable business knowledge before replies or content can make trustworthy claims. Knowledge services manage versioned facts and candidate acceptance with permissions and audit history; the renderer substitutes only usable facts and records their inserted spans. Impact propagation links a changed fact to dependent drafts, posts and reusable answers, making later approval invalidation understandable.
6. **Bound the AI Proposals** — Building on verified facts, the AI runtime requests structured proposals under tracing, budgets and typed retry rules. Trusted templates are separated from labelled untrusted message data, and closed schemas constrain the shapes returned for commands, replies and content. Task-specific prompts and semantic checks produce drafts for deterministic services to validate; they do not give the model publishing or sending authority.
7. **Authorize Exact Proposed Changes** — Commands turn the bounded proposals into interpretations, clarification requests and explicit decisions. Approval services bind authorization to an exact payload and version, reject stale or consumed grants, and execute subject callbacks atomically as the human decider. This boundary explains why changing a draft or its dependencies requires renewed authorization before an external effect.
8. **Follow the Reply Workflow** — The inbox combines the knowledge, AI and approval boundaries into grounded reply drafts. Its workflow rejects stale drafting plans, applies deterministic safety rules and attaches an exact-payload grant or a pending authorization. Manual edits, takeover and release recheck messaging eligibility and text versions, while model signals can add restrictions without weakening those guards.
9. **Prepare and Schedule Content** — Content applies the same approval discipline to a longer lifecycle of generated drafts, edits and scheduling. Generation separates preparation and provider work from draft storage, while grounding checks captions and overlays against usable facts and records governing dependencies. Validation checks media, account capabilities, scheduling and quota requirements, and the service invalidates approvals and queued work when relevant versions change.
10. **Run Durable Background Jobs** — Scheduled content and other deferred workflows move through a PostgreSQL transactional job outbox. The queue uses deduplicated enqueueing, skip-locked claims and leases, while the worker supplies heartbeat, retry and graceful shutdown behavior. The scheduler coordinates periodic enqueueing with an advisory lock, connecting the API transactions introduced earlier to reliable work outside a request.
11. **Track External Operation Outcomes** — When a job is ready to send or publish, operation services revalidate authorization and account conditions before crossing the provider boundary. They commit ledger checkpoints before transaction-free provider calls, then distinguish confirmed effects, safe retries, failures and ambiguous results that require reconciliation. The provider protocol and stateful simulator make this behavior locally demonstrable, including failures and quotas, without establishing completed real Meta integration.
12. **Explain Reports with Evidence** — Reports turn persisted workflow state into canonical workspace-filtered SQL metrics and navigable evidence. Today can use live rows, while historical reports use immutable generations with saved membership and measurements so links keep explaining the same numbers after source state changes. Regeneration appends a revision rather than replacing that historical explanation, connecting reporting back to the durable records created by earlier workflows.
13. **Preserve Audit and Retention** — The historical evidence introduced in the previous step must remain honest as sensitive source content ages out. Retention runs idempotent batches that redact or delete eligible data while preserving audit rows and report evidence; failed-event deletion records source gaps atomically so regeneration cannot silently undercount. Append-only audit writing stays in the caller transaction, and lifecycle tests exercise snapshot stability, retention and tenant boundaries together.
14. **Reproduce the Local Environment** — With the workflows understood, use the development guide to assemble the same API, worker, workspace and simulated demonstration locally. Compose supplies a health-checked PostgreSQL instance with persistent storage, while Alembic connects application model metadata to ordered schema changes. This setup makes the transaction and evidence boundaries from earlier steps inspectable in a real local database.
15. **Assess Verification and Readiness** — Finish by checking how CI, deterministic AI evaluations and browser scenarios exercise the boundaries you have followed. Scenario E verifies report agreement and generation-bound evidence, and the later QA record supersedes the original local AC-E3 reporting gap. The same QA record keeps wider Gate 1 acceptance open, so passing local regressions must be read alongside the remaining review and acceptance work.

## Validation

- Inline deterministic validation: 0 issues; 60 orphan-node warnings.
- Dashboard schema: passed; 0 missing files, 0 paths outside the inventory, 0 invalid source ranges.
- Layer and tour references checked against the assembled node inventory; each file-level node belongs to exactly one layer.
- Structural fingerprints cover all included code and non-code files, enabling future incremental updates. Automatic updates remain disabled as configured.
- This task validated the analysis artifacts. It did not execute or change the application, its databases, or its test suites.

## Limitations and diagnostics

- The graph describes the current working tree, including pre-existing uncommitted reporting/snapshot changes. The commit hash identifies its base revision, not a clean-tree snapshot.
- Some frontend @/ aliases are unresolved by the bundled import resolver in this nested frontend layout. The graph is not an exhaustive frontend dependency map. A scanner-produced self-import on backend/app/core/logging.py was intentionally omitted to obey the graph no-self-edge rule; other resolved imports were checked during assembly.
- Large import communities were split during batching. Neighbor context was capped for six high-degree files; the complete resolved import map remained available for merging.
- The bundled extractor supplies Python class method names without method bounds. Some method nodes omit optional line ranges; other method ranges were verified directly from source.
- Unsupported markup/config/template/CSS/PowerShell files were read and supplemented after structural extraction; no unreadable or omitted inventory files remain.
- Transient generation issues (UTF-8 BOM input, Windows command length, and a missing helper description caught by a completeness assertion) were corrected before final validation.
- A refresh dispatch was interrupted by a usage limit. Resumed analysis completed and validated all remaining file batches.
- Freshness checks detected reporting, retention, E2E, documentation and landing-page edits during analysis. Twenty-four affected/new files were reanalyzed against a refreshed inventory; a per-file SHA256 snapshot was used to check final source stability.
- The restored catalog tested_by edge is semantically valid but would be removed by the current merger file-only tested_by classifier on a future merge; retain this review correction if reassembling.
- Upstream unresolved frontend @/ aliases remain a known deterministic import-extractor limitation; no speculative edges were added or importMap entries changed.
- Freshness reconciliation reanalyzed 24 changed/new files. Final coverage 827/827; all 2537 canonical non-self imports present, with no extra imports, duplicate roots, dangling endpoints or self edges. The previously source-verified catalog test link was preserved after re-merge.

Empty Python package markers and standalone specification files may be valid orphan nodes. Their lack of edges is informational and does not mean they were omitted.

The generated graph is .ua/knowledge-graph.json. The deterministic inventory is retained at .ua/intermediate/scan-result.json; other scratch output is archived under .ua/.trash-*/ after completion.

## Dashboard launch

The version-pinned prebuilt viewer download returned HTTP 404. The first installed-dashboard launch hit Vite dependency-cache loading errors. Dependencies were restored in the external plugin checkout, then starting Vite from its physical directory with forced dependency optimization succeeded. Viewer HTML, the entry module, and the token-protected graph endpoint all returned HTTP 200, serving 5,245 nodes, 18,842 edges, 10 layers and 15 tour steps.
